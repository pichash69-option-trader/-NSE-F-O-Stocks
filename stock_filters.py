# -*- coding: utf-8 -*-
"""
stock_filters.py — evaluate 24 per-stock filter rules for the "Stocks filter"
tab. Uses ONLY per-stock data (no market-wide participant/FII-DII). Returns, for
every F&O stock, each rule's pass/fail + the value behind it, as of the latest
available day per dataset (F&O lags cash by 1–2 days).

Pure data → DataFrames; the dashboard renders the screener + checklist.
Research/education only — not trading advice.
"""
import numpy as np
import pandas as pd

import db
import analysis

# (num, group, label, rule-text) — order defines display order
FILTERS = [
    (1,  "Price",   "Price thrust",          "|chg%| ≥ 2%"),
    (2,  "Price",   "Gap",                   "|gap%| ≥ 2%"),
    (3,  "Price",   "Range expansion",       "range% ≥ 1.5× 20d-avg"),
    (4,  "Price",   "Volume surge",          "volume ≥ 2× 20d-avg"),
    (5,  "Price",   "Turnover (liquidity)",  "turnover ≥ ₹100 Cr"),
    (6,  "Price",   "Delivery conviction",   "delivery% ≥ 50%"),
    (7,  "Price",   "Avg trade size",        "trade-size ≥ 1.5× 20d-avg"),
    (8,  "Price",   "New-high/low breakout", "close > 20d high or < 20d low"),
    (9,  "Price",   "Strong close",          "close in top 25% of day range"),
    (10, "Futures", "OI buildup",            "futures ΔOI ≥ +5%"),
    (11, "Futures", "Long/short buildup",    "OI↑ with a ≥1% move"),
    (12, "Futures", "Premium/discount",      "|premium%| ≥ 0.3%"),
    (13, "Futures", "Days-to-expiry",        "near-expiry dte ≥ 15"),
    (14, "Options", "PCR extreme",           "PCR > 1.2 or < 0.7"),
    (15, "Options", "Total OI rising",       "opt total OI ≥ +5% d/d"),
    (16, "Options", "Max-pain distance",     "|price − max-pain| ≥ 3%"),
    (17, "Options", "Strike liquidity",      "ATM CE&PE OI≥1000, vol≥200"),
    (18, "Events",  "Institutional deal",    "bulk/block deal today"),
    (19, "Events",  "Not in F&O ban",        "not in secban today"),
    (20, "Events",  "No corp-action ±3d",    "no ex-date within 3 days"),
    (21, "Events",  "Short-selling low",     "short qty < 20d-avg (or none)"),
    (22, "Stats",   "52-week percentile",    "pct_rank_52w ≥ 80"),
    (23, "Stats",   "Relative strength",     "stock chg% > Nifty chg%"),
    (24, "Stats",   "Volatility band",       "ann_vol 20–60%"),
    # 25-26 are BUYER-specific and only filled when IV data is supplied.
    (25, "IV (buyer)", "IV Rank low (cheap)",       "IV Rank ≤ 30 (buy-friendly)"),
    (26, "IV (buyer)", "IV cheaper than realized",  "IV/HV < 1"),
]
FILTER_NUMS = [f[0] for f in FILTERS]


def _price_features(conn):
    """Latest per-stock price row with rolling features (vectorised)."""
    px = pd.read_sql_query(
        "SELECT symbol,date,open,high,low,close,prev_close,volume,turnover,"
        "num_trades,deliv_pct FROM prices ORDER BY symbol,date", conn)
    px["chg"] = (px.close / px.prev_close - 1) * 100
    px["gap"] = (px.open / px.prev_close - 1) * 100
    px["rng"] = (px.high - px.low) / px.prev_close * 100
    g = px.groupby("symbol")
    px["vol_a20"] = g["volume"].transform(lambda s: s.rolling(20).mean().shift(1))
    px["rng_a20"] = g["rng"].transform(lambda s: s.rolling(20).mean().shift(1))
    px["hi20"] = g["high"].transform(lambda s: s.rolling(20).max().shift(1))
    px["lo20"] = g["low"].transform(lambda s: s.rolling(20).min().shift(1))
    px["tsz"] = px.turnover / px.num_trades.replace(0, np.nan)
    px["tsz_a20"] = g["tsz"].transform(lambda s: s.rolling(20).mean().shift(1))
    rng = (px.high - px.low).replace(0, np.nan)
    px["strong"] = (px.close - px.low) / rng
    return px.groupby("symbol").tail(1).set_index("symbol")


def _futures_latest(conn):
    """Per-stock futures aggregates on the latest futures day."""
    d = pd.read_sql_query("SELECT MAX(date) d FROM futures", conn)["d"].iloc[0]
    if not d:
        return pd.DataFrame(), d
    fut = pd.read_sql_query(
        "SELECT symbol,expiry,close,oi,chg_oi FROM futures WHERE date=?", conn, params=(d,))
    if fut.empty:
        return pd.DataFrame(), d
    agg = fut.groupby("symbol").agg(tot_oi=("oi", "sum"), tot_chg=("chg_oi", "sum")).reset_index()
    near = fut.sort_values("expiry").groupby("symbol").first().reset_index()
    near = near.rename(columns={"expiry": "near_exp", "close": "near_close"})[
        ["symbol", "near_exp", "near_close"]]
    out = agg.merge(near, on="symbol", how="left").set_index("symbol")
    out["dte"] = (pd.to_datetime(out["near_exp"]) - pd.Timestamp(d)).dt.days
    prior = out["tot_oi"] - out["tot_chg"]
    out["oi_chg_pct"] = np.where(prior > 0, out["tot_chg"] / prior * 100, np.nan)
    return out, d


def _options_latest(conn):
    """Per-stock options aggregates (PCR, OI d/d, max-pain, ATM liquidity)."""
    dates = pd.read_sql_query(
        "SELECT DISTINCT date FROM options ORDER BY date DESC LIMIT 2", conn)["date"].tolist()
    if not dates:
        return pd.DataFrame(), None
    d = dates[0]
    prev = dates[1] if len(dates) > 1 else None
    oi = pd.read_sql_query(
        "SELECT symbol,opt_type,SUM(oi) oi FROM options WHERE date=? GROUP BY symbol,opt_type",
        conn, params=(d,))
    p = oi.pivot_table(index="symbol", columns="opt_type", values="oi", aggfunc="sum").fillna(0)
    p["tot_oi"] = p.get("CE", 0) + p.get("PE", 0)
    p["pcr"] = np.where(p.get("CE", 0) > 0, p.get("PE", 0) / p.get("CE", 0), np.nan)
    if prev:
        pv = pd.read_sql_query(
            "SELECT symbol,SUM(oi) oi FROM options WHERE date=? GROUP BY symbol",
            conn, params=(prev,)).set_index("symbol")["oi"]
        p["oi_chg_pct"] = np.where(pv.reindex(p.index) > 0,
                                   (p["tot_oi"] - pv.reindex(p.index)) / pv.reindex(p.index) * 100, np.nan)
    else:
        p["oi_chg_pct"] = np.nan
    return p, d


def compute(iv_df=None):
    """Return (passes, values, meta): passes = bool DataFrame [symbol × f1..f24],
    values = str DataFrame for display, meta = dict of latest dates."""
    conn = db.connect()
    try:
        price = _price_features(conn)
        fut, fdate = _futures_latest(conn)
        opt, odate = _options_latest(conn)
        syms = list(price.index)

        # events
        dl_date = pd.read_sql_query("SELECT MAX(date) d FROM deals", conn)["d"].iloc[0]
        deals = set(pd.read_sql_query(
            "SELECT DISTINCT symbol FROM deals WHERE date=?", conn, params=(dl_date,))["symbol"])
        ban_date = pd.read_sql_query(
            "SELECT MAX(date) d FROM ingest_log WHERE dataset='secban' AND status='ok'",
            conn)["d"].iloc[0]
        banned = set(pd.read_sql_query(
            "SELECT symbol FROM secban WHERE date=?", conn, params=(ban_date,))["symbol"])
        today = pd.Timestamp.today().normalize()
        ca = pd.read_sql_query(
            "SELECT DISTINCT symbol FROM corp_actions WHERE ex_date BETWEEN ? AND ?",
            conn, params=((today - pd.Timedelta(days=3)).strftime("%Y-%m-%d"),
                          (today + pd.Timedelta(days=3)).strftime("%Y-%m-%d")))["symbol"]
        ca_near = set(ca)
        # short selling: latest qty vs 60-day avg per symbol
        ss = pd.read_sql_query(
            "SELECT symbol,date,qty FROM short_selling ORDER BY symbol,date", conn)
        ss_last = ss.groupby("symbol").tail(1).set_index("symbol")["qty"]
        ss_avg = ss.groupby("symbol")["qty"].apply(lambda s: s.tail(60).mean())
        # stats + nifty
        stats = pd.read_sql_query(
            "SELECT symbol,pct_rank_52w,ann_volatility FROM stats", conn).set_index("symbol")
        nifty = pd.read_sql_query(
            "SELECT chg_pct FROM indices WHERE name='Nifty 50' ORDER BY date DESC LIMIT 1", conn)
        nifty_chg = float(nifty["chg_pct"].iloc[0]) if not nifty.empty else 0.0

        # max-pain + ATM liquidity per symbol on the latest options day
        maxpain, atm_liq = {}, {}
        if odate:
            near_exp = pd.read_sql_query(
                "SELECT symbol, MIN(expiry) e FROM options WHERE date=? GROUP BY symbol",
                conn, params=(odate,)).set_index("symbol")["e"]
            chain = pd.read_sql_query(
                "SELECT symbol,strike,opt_type,oi,volume FROM options WHERE date=? AND expiry IN "
                "(SELECT DISTINCT MIN(expiry) FROM options WHERE date=? GROUP BY symbol)",
                conn, params=(odate, odate))
            for sym in syms:
                e = near_exp.get(sym)
                if e is None:
                    continue
                try:
                    maxpain[sym] = analysis.max_pain(sym, odate, e)
                except Exception:
                    maxpain[sym] = None
                sub = chain[chain.symbol == sym]
                if sub.empty or sym not in price.index:
                    continue
                spot = float(price.loc[sym, "close"])
                strikes = np.sort(sub["strike"].unique())
                if len(strikes) == 0:
                    continue
                atm = float(strikes[np.abs(strikes - spot).argmin()])
                ce = sub[(sub.strike == atm) & (sub.opt_type == "CE")]
                pe = sub[(sub.strike == atm) & (sub.opt_type == "PE")]
                ok = (not ce.empty and not pe.empty and ce.oi.iloc[0] >= 1000 and
                      pe.oi.iloc[0] >= 1000 and ce.volume.iloc[0] >= 200 and pe.volume.iloc[0] >= 200)
                atm_liq[sym] = ok

        # ---- build passes + values per symbol ----
        passes, values = {}, {}
        for sym in syms:
            pr = price.loc[sym]
            f, v = {}, {}

            def put(n, cond, val):
                f[n] = (bool(cond) if pd.notna(cond) else False) if not isinstance(cond, bool) else cond
                v[n] = val

            put(1, abs(pr.chg) >= 2, f"{pr.chg:+.1f}%")
            put(2, abs(pr.gap) >= 2, f"{pr.gap:+.1f}%")
            put(3, pd.notna(pr.rng_a20) and pr.rng >= 1.5 * pr.rng_a20,
                f"{pr.rng:.1f}% vs {pr.rng_a20:.1f}" if pd.notna(pr.rng_a20) else "—")
            put(4, pd.notna(pr.vol_a20) and pr.volume >= 2 * pr.vol_a20,
                f"{pr.volume/pr.vol_a20:.1f}×" if pd.notna(pr.vol_a20) and pr.vol_a20 else "—")
            put(5, pr.turnover >= 100e7, f"₹{pr.turnover/1e7:,.0f}Cr")
            put(6, pd.notna(pr.deliv_pct) and pr.deliv_pct >= 50,
                f"{pr.deliv_pct:.0f}%" if pd.notna(pr.deliv_pct) else "—")
            put(7, pd.notna(pr.tsz_a20) and pd.notna(pr.tsz) and pr.tsz >= 1.5 * pr.tsz_a20,
                f"{pr.tsz/pr.tsz_a20:.1f}×" if pd.notna(pr.tsz_a20) and pr.tsz_a20 else "—")
            put(8, (pd.notna(pr.hi20) and pr.close > pr.hi20) or
                   (pd.notna(pr.lo20) and pr.close < pr.lo20),
                "↑new-high" if (pd.notna(pr.hi20) and pr.close > pr.hi20)
                else "↓new-low" if (pd.notna(pr.lo20) and pr.close < pr.lo20) else "no")
            put(9, pd.notna(pr.strong) and pr.strong >= 0.75,
                f"{pr.strong*100:.0f}% of range" if pd.notna(pr.strong) else "—")

            fr = fut.loc[sym] if sym in fut.index else None
            put(10, fr is not None and pd.notna(fr.oi_chg_pct) and fr.oi_chg_pct >= 5,
                f"{fr.oi_chg_pct:+.1f}%" if fr is not None and pd.notna(fr.oi_chg_pct) else "—")
            put(11, fr is not None and fr.tot_chg > 0 and abs(pr.chg) >= 1,
                "OI↑+move" if fr is not None and fr.tot_chg > 0 and abs(pr.chg) >= 1 else "no")
            prem = ((fr.near_close - pr.close) / pr.close * 100) if (fr is not None and pd.notna(fr.near_close)) else np.nan
            put(12, pd.notna(prem) and abs(prem) >= 0.3, f"{prem:+.2f}%" if pd.notna(prem) else "—")
            put(13, fr is not None and pd.notna(fr.dte) and fr.dte >= 15,
                f"{int(fr.dte)}d" if fr is not None and pd.notna(fr.dte) else "—")

            orow = opt.loc[sym] if sym in opt.index else None
            pcr = orow["pcr"] if orow is not None else np.nan
            put(14, pd.notna(pcr) and (pcr > 1.2 or pcr < 0.7), f"{pcr:.2f}" if pd.notna(pcr) else "—")
            oichg = orow["oi_chg_pct"] if orow is not None else np.nan
            put(15, pd.notna(oichg) and oichg >= 5, f"{oichg:+.1f}%" if pd.notna(oichg) else "—")
            mp = maxpain.get(sym)
            mpd = (abs(pr.close - mp) / pr.close * 100) if mp else np.nan
            put(16, pd.notna(mpd) and mpd >= 3, f"{mpd:.1f}% away" if pd.notna(mpd) else "—")
            put(17, atm_liq.get(sym, False), "ok" if atm_liq.get(sym) else "thin/—")

            put(18, sym in deals, "deal" if sym in deals else "no")
            put(19, sym not in banned, "banned" if sym in banned else "clear")
            put(20, sym not in ca_near, "ex-date!" if sym in ca_near else "clear")
            slast, savg = ss_last.get(sym), ss_avg.get(sym)
            put(21, (slast is None) or (pd.notna(savg) and pd.notna(slast) and slast < savg),
                "low/none" if (slast is None or (pd.notna(savg) and slast < savg)) else "high")

            strow = stats.loc[sym] if sym in stats.index else None
            pctl = strow["pct_rank_52w"] if strow is not None else np.nan
            put(22, pd.notna(pctl) and pctl >= 80, f"{pctl:.0f}" if pd.notna(pctl) else "—")
            put(23, pr.chg > nifty_chg, f"{pr.chg:+.1f} vs Nifty {nifty_chg:+.1f}")
            av = strow["ann_volatility"] * 100 if strow is not None and pd.notna(strow["ann_volatility"]) else np.nan
            put(24, pd.notna(av) and 20 <= av <= 60, f"{av:.0f}%" if pd.notna(av) else "—")

            # 25-26: buyer IV filters — only when an IV snapshot is supplied
            if iv_df is not None and sym in iv_df.index:
                ivr = iv_df.loc[sym, "iv_rank"]
                ivh = iv_df.loc[sym, "iv_hv"]
                put(25, pd.notna(ivr) and ivr <= 30, f"{ivr:.0f}" if pd.notna(ivr) else "—")
                put(26, pd.notna(ivh) and ivh < 1, f"{ivh:.2f}" if pd.notna(ivh) else "—")

            passes[sym] = f
            values[sym] = v

        cols = FILTER_NUMS if iv_df is not None else [n for n in FILTER_NUMS if n <= 24]
        pdf = pd.DataFrame(passes).T.reindex(columns=cols)
        vdf = pd.DataFrame(values).T.reindex(columns=cols)
        meta = dict(price_date=str(price["date"].iloc[0]) if len(price) else "—",
                    fut_date=fdate, opt_date=odate)
        return pdf, vdf, meta
    finally:
        conn.close()
