# -*- coding: utf-8 -*-
"""
analysis.py — pure mathematical / statistical analysis (NO technical indicators).

Reads raw data from nse.db, computes per-stock stats + F&O math, writes to `stats`.
All math is vectorized (pandas/numpy) — no per-row Python loops.

Beta note: beta is computed against the REAL Nifty 50 index (from the `indices`
table). If the index series is unavailable (e.g. before the first index backfill),
it falls back to a MARKET PROXY = equal-weighted mean of all stocks' daily returns.
"""
import re

import numpy as np
import pandas as pd

import db

TRADING_DAYS = 252


# --------------------------------------------------------------------------- #
# Loaders
# --------------------------------------------------------------------------- #
def load_prices():
    conn = db.connect()
    try:
        df = pd.read_sql_query(
            "SELECT symbol, date, close, volume, deliv_pct FROM prices ORDER BY symbol, date",
            conn, parse_dates=["date"])
    finally:
        conn.close()
    return df


def load_index(name="Nifty 50"):
    """Daily close Series (indexed by date) for one index, or None if absent."""
    conn = db.connect()
    try:
        df = pd.read_sql_query(
            "SELECT date, close FROM indices WHERE name=? ORDER BY date",
            conn, params=(name,), parse_dates=["date"])
    finally:
        conn.close()
    if df.empty:
        return None
    return df.set_index("date")["close"].sort_index()


def close_matrix(prices):
    """Wide frame: index=date, columns=symbol, values=close."""
    return prices.pivot(index="date", columns="symbol", values="close").sort_index()


# Heuristic split/bonus thresholds — used ONLY as a fallback when no corporate-
# action data is available. A genuine one-day move for a large-cap never exceeds
# these, so a bigger jump is assumed to be a split/bonus.
SPLIT_LO, SPLIT_HI = 0.6, 1.6

# When real corp-action factors ARE supplied, we still guard against data gaps
# (a split the API somehow missed) — but only for EXTREME jumps that no ordinary
# market move produces, so genuine crashes/surges are left untouched.
EXTREME_LO, EXTREME_HI = 0.35, 2.85


def _action_factor(action_type, subject):
    """Theoretical price-adjustment factor for a split/bonus, or None if unparseable.

    Split  "From Rs 10 To Rs 2"  -> price × (2/10)   = 0.20
    Bonus  a:b (a new per b held) -> price × b/(a+b)  (1:1 -> 0.5, 4:1 -> 0.2)
    """
    s = subject or ""
    if action_type == "Bonus":
        m = re.search(r"(\d+)\s*:\s*(\d+)", s)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if a + b > 0:
                return b / (a + b)
    elif action_type == "Split":
        fm = re.search(r"From\s+R[se]\.?\s*(\d+(?:\.\d+)?)", s, re.I)
        tm = re.search(r"To\s+R[se]\.?\s*(\d+(?:\.\d+)?)", s, re.I)
        if fm and tm:
            frm, to = float(fm.group(1)), float(tm.group(1))
            if frm > 0:
                return to / frm
    return None


def load_corp_factors():
    """{symbol: {ex_date(Timestamp): factor}} for splits & bonuses, from corp_actions.

    Multiple actions on the same ex-date are combined (multiplied). Used to
    back-adjust prices with EXACT ratios instead of guessing from price jumps.
    """
    conn = db.connect()
    try:
        df = pd.read_sql_query(
            "SELECT symbol, ex_date, action_type, subject FROM corp_actions "
            "WHERE action_type IN ('Split','Bonus')", conn, parse_dates=["ex_date"])
    except Exception:
        return {}                                # table may not exist yet
    finally:
        conn.close()
    out = {}
    for r in df.itertuples():
        f = _action_factor(r.action_type, r.subject)
        if f and 0 < f < 1e6:
            d = out.setdefault(r.symbol, {})
            d[r.ex_date] = d.get(r.ex_date, 1.0) * f
    return out


# A corp-action factor is trusted only if the actual ex-date price jump confirms
# it within this tolerance. Guards against actions that DON'T move the equity
# price — e.g. "Bonus NCRPS 4:1" (preference shares), demergers mislabelled as
# bonus, or parse errors. |raw_ratio / factor − 1| must be under this.
FACTOR_TOL = 0.35


def _corp_factor_series(s, cf):
    """Per-date split/bonus factor for close series `s`, using exact corp-action
    factors `cf` = {ex_date: factor}. A factor is applied only if the real price
    jump that day confirms it (see FACTOR_TOL); a narrow extreme-jump fallback
    then catches any split the corp-action feed missed."""
    ratio = s / s.shift()
    factor = pd.Series(1.0, index=s.index)
    for exd, f in (cf or {}).items():
        if exd in s.index and f:
            rt = ratio.get(exd)
            if pd.notna(rt) and abs(rt / f - 1) < FACTOR_TOL:
                factor.loc[exd] = f
    fb = ((ratio < EXTREME_LO) | (ratio > EXTREME_HI)) & (factor == 1.0)
    factor[fb] = ratio[fb]
    return factor


def adjust_ohlc(df, factors=None):
    """Split/bonus-adjust a single symbol's OHLC (date-sorted) for a continuous
    display series, so the candle chart and chg% don't show a fake crash on a
    split day.

    `factors` = {ex_date(Timestamp): factor} for THIS symbol (from corp_actions);
    pass {} to use exact-mode with no known actions. When None, it falls back to
    the price-jump heuristic (SPLIT_LO/HI)."""
    df = df.sort_values("date").reset_index(drop=True)
    if len(df) < 2:
        return df
    if factors is not None:
        s = pd.Series(df["close"].values, index=pd.to_datetime(df["date"]))
        factor = pd.Series(_corp_factor_series(s, factors).values, index=df.index)
    else:
        ratio = df["close"] / df["close"].shift()
        factor = pd.Series(1.0, index=df.index)
        is_action = (ratio < SPLIT_LO) | (ratio > SPLIT_HI)
        factor[is_action] = ratio[is_action]
    adj_factor = factor[::-1].cumprod()[::-1] / factor      # product of factors after t
    for col in ("open", "high", "low", "close"):
        if col in df.columns:
            df[col] = df[col] * adj_factor
    return df


def adjust_for_splits(wide, corp_factors=None):
    """Back-adjust close prices for splits/bonuses so the series is continuous.

    On a corporate-action day the price jumps by a non-market factor; we multiply
    all EARLIER prices by that factor. The action day's own return then reflects
    only the real market move — removing fake -90%-type artifacts. Later prices
    are untouched, so today's price stays real.

    `corp_factors` = {symbol: {ex_date: factor}} from load_corp_factors(). When
    provided, EXACT corp-action ratios are used (a genuine crash is no longer
    mistaken for a split), with a narrow safety net for extreme unexplained jumps.
    When None, it falls back to the price-jump heuristic (SPLIT_LO/HI).
    """
    adj = wide.copy()
    use_real = corp_factors is not None
    for sym in wide.columns:
        s = wide[sym].dropna()
        if len(s) < 2:
            continue
        if use_real:
            factor = _corp_factor_series(s, corp_factors.get(sym, {}))
        else:
            ratio = s / s.shift()
            factor = pd.Series(1.0, index=s.index)
            is_action = (ratio < SPLIT_LO) | (ratio > SPLIT_HI)
            factor[is_action] = ratio[is_action]
        # adj_factor[t] = product of factors strictly AFTER t
        rev_cumprod = factor[::-1].cumprod()[::-1]        # product of factor[k], k>=t
        adj_factor = rev_cumprod / factor                 # exclude factor[t] itself
        adj.loc[s.index, sym] = s * adj_factor
    return adj


# --------------------------------------------------------------------------- #
# Equity math
# --------------------------------------------------------------------------- #
def max_drawdown(close):
    """Largest peak-to-trough drop (%) of a close series."""
    running_max = close.cummax()
    dd = close / running_max - 1.0
    return float(dd.min())


def equity_stats(prices, index_close=None, corp_factors=None):
    """Return a DataFrame of per-symbol statistics.

    Beta uses `index_close` (real Nifty 50) when given & long enough; otherwise
    falls back to an equal-weighted market proxy so it never breaks.
    `corp_factors` (from load_corp_factors) gives exact split/bonus adjustment.
    """
    wide = adjust_for_splits(close_matrix(prices), corp_factors)   # split-adjusted date × symbol
    rets = wide.pct_change()                     # daily returns
    if index_close is not None and index_close.reindex(wide.index).dropna().shape[0] > 30:
        market = index_close.reindex(wide.index).pct_change()   # real Nifty 50
    else:
        market = rets.mean(axis=1)               # equal-weighted market proxy

    # Vectorized beta for every symbol at once: cov(s, m) / var(m)
    mkt_dm = market - market.mean()
    mkt_var = float((mkt_dm ** 2).mean())
    cov = rets.sub(rets.mean()).mul(mkt_dm, axis=0).mean()   # per-symbol cov with market
    betas = (cov / mkt_var) if mkt_var else cov * np.nan
    corrs = rets.corrwith(market)                # per-symbol correlation with market
    avg_deliv = prices.groupby("symbol")["deliv_pct"].mean()   # avg delivery % (conviction)

    rows = []
    for sym in wide.columns:
        close = wide[sym].dropna()
        r = rets[sym].dropna()
        if len(close) < 2:
            continue

        mean_r = r.mean()
        vol = r.std()
        beta = betas.get(sym, np.nan)

        # 52-week (trailing 252d) percentile rank of the latest close
        win = close.tail(TRADING_DAYS)
        last = close.iloc[-1]
        pct_rank = float((win < last).mean() * 100)

        # CAGR (annualized from actual span)
        span_days = (close.index[-1] - close.index[0]).days or 1
        cagr = (close.iloc[-1] / close.iloc[0]) ** (365.0 / span_days) - 1.0

        rows.append({
            "symbol": sym,
            "date": close.index[-1].strftime("%Y-%m-%d"),
            "daily_return": float(r.iloc[-1]),
            "cum_return": float(close.iloc[-1] / close.iloc[0] - 1.0),
            "mean_return": float(mean_r),
            "volatility": float(vol),
            "ann_volatility": float(vol * np.sqrt(TRADING_DAYS)),
            "sharpe": float(mean_r / vol * np.sqrt(TRADING_DAYS)) if vol else np.nan,
            "max_drawdown": max_drawdown(close),
            "beta": float(beta),
            "correlation": float(corrs.get(sym, np.nan)),
            "avg_deliv_pct": float(avg_deliv.get(sym, np.nan)),
            "zscore": float((last - close.mean()) / close.std()) if close.std() else np.nan,
            "pct_rank_52w": pct_rank,
            "cagr": float(cagr),
            "skew": float(r.skew()),
            "kurtosis": float(r.kurt()),
        })
    return pd.DataFrame(rows).set_index("symbol")


# --------------------------------------------------------------------------- #
# F&O math
# --------------------------------------------------------------------------- #
def fno_stats():
    """PCR, total OI, OI change, futures premium per symbol (latest F&O date).

    Only the latest day is loaded (via SQL) — loading the whole options table
    (millions of rows) blew up memory and got OOM-killed on small servers.
    """
    conn = db.connect()
    try:
        latest = conn.execute("SELECT MAX(date) FROM options").fetchone()[0]
        if not latest:
            return pd.DataFrame()
        o = pd.read_sql_query(
            "SELECT symbol,expiry,strike,opt_type,oi,chg_oi FROM options WHERE date=?",
            conn, params=(latest,))
        f = pd.read_sql_query(
            "SELECT symbol,expiry,close,oi,chg_oi FROM futures WHERE date=?",
            conn, params=(latest,))
        s = pd.read_sql_query(
            "SELECT symbol,close FROM prices WHERE date=?",
            conn, params=(latest,)).set_index("symbol")["close"]
    finally:
        conn.close()
    if o.empty:
        return pd.DataFrame()

    rows = []
    for sym, g in o.groupby("symbol"):
        ce_oi = g.loc[g.opt_type == "CE", "oi"].sum()
        pe_oi = g.loc[g.opt_type == "PE", "oi"].sum()
        pcr = (pe_oi / ce_oi) if ce_oi else np.nan

        fg = f[f.symbol == sym]
        total_oi = int(fg["oi"].sum()) if not fg.empty else None
        oi_change = int(fg["chg_oi"].sum()) if not fg.empty else None

        premium = np.nan
        if not fg.empty and sym in s.index:
            near_expiry = fg["expiry"].min()     # near-month
            near_close = fg.loc[fg.expiry == near_expiry, "close"].iloc[0]
            premium = float(near_close - s[sym])

        rows.append({"symbol": sym, "put_call_ratio": float(pcr) if pcr == pcr else None,
                     "total_oi": total_oi, "oi_change": oi_change,
                     "futures_premium": premium})
    return pd.DataFrame(rows).set_index("symbol")


def max_pain(symbol, date, expiry):
    """Strike at which total option writer payout is minimized (pure calc)."""
    conn = db.connect()
    try:
        df = pd.read_sql_query(
            "SELECT strike,opt_type,oi FROM options WHERE symbol=? AND date=? AND expiry=?",
            conn, params=(symbol, date, expiry))
    finally:
        conn.close()
    if df.empty:
        return None
    strikes = np.sort(df["strike"].unique())
    ce = df[df.opt_type == "CE"].set_index("strike")["oi"]
    pe = df[df.opt_type == "PE"].set_index("strike")["oi"]
    best_k, best_pain = None, None
    for k in strikes:                            # test each strike as expiry price
        pain = 0.0
        for st in strikes:
            if st < k and st in ce.index:        # ITM calls
                pain += ce[st] * (k - st)
            if st > k and st in pe.index:        # ITM puts
                pain += pe[st] * (st - k)
        if best_pain is None or pain < best_pain:
            best_pain, best_k = pain, float(k)
    return best_k


def sum_chain(symbol, date):
    """Strike-wise sum across ALL expiries (the dashboard 'sum chain'). Returns DataFrame."""
    conn = db.connect()
    try:
        df = pd.read_sql_query(
            """SELECT strike,opt_type,oi,chg_oi,volume FROM options
               WHERE symbol=? AND date=?""", conn, params=(symbol, date))
    finally:
        conn.close()
    if df.empty:
        return df
    agg = (df.groupby(["strike", "opt_type"])[["oi", "chg_oi", "volume"]]
             .sum().unstack("opt_type"))
    agg.columns = [f"{a}_{b}" for a, b in agg.columns]   # e.g. oi_CE, oi_PE
    return agg.reset_index().sort_values("strike")


# --------------------------------------------------------------------------- #
# Write results
# --------------------------------------------------------------------------- #
def run():
    db.init_db()
    prices = load_prices()
    if prices.empty:
        print("No price data. Run fetch_data first.")
        return

    eq = equity_stats(prices, index_close=load_index("Nifty 50"),
                      corp_factors=load_corp_factors())
    fo = fno_stats()
    merged = eq.join(fo, how="left") if not fo.empty else eq

    cols = ["date", "daily_return", "cum_return", "mean_return", "volatility",
            "ann_volatility", "sharpe", "max_drawdown", "beta", "correlation",
            "avg_deliv_pct", "zscore", "pct_rank_52w", "cagr", "skew", "kurtosis",
            "put_call_ratio", "total_oi", "oi_change", "futures_premium"]
    for c in cols:
        if c not in merged.columns:
            merged[c] = None

    def _py(v):
        """numpy scalar -> native python (else sqlite stores ints as BLOBs)."""
        if pd.isna(v):
            return None
        if isinstance(v, np.integer):
            return int(v)
        if isinstance(v, np.floating):
            return float(v)
        return v

    conn = db.connect()
    try:
        conn.execute("DELETE FROM stats")        # latest snapshot only
        rows = [(sym, *[_py(v) for v in merged.loc[sym, cols]])
                for sym in merged.index]
        conn.executemany(
            f"INSERT OR REPLACE INTO stats (symbol,{','.join(cols)}) "
            f"VALUES ({','.join('?' * (len(cols) + 1))})", rows)
        conn.commit()
    finally:
        conn.close()
    print(f"stats computed for {len(merged)} symbols (F&O math for "
          f"{0 if fo.empty else len(fo)}).")


if __name__ == "__main__":
    run()
