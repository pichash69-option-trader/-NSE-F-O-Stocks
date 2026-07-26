# -*- coding: utf-8 -*-
"""
analysis.py — pure mathematical / statistical analysis (NO technical indicators).

Reads raw data from nse.db, computes per-stock stats + F&O math, writes to `stats`.
All math is vectorized (pandas/numpy) — no per-row Python loops.

Beta note: we don't store a separate NIFTY index series, so beta is computed against a
MARKET PROXY = equal-weighted mean of the 50 stocks' daily returns. Good approximation of
NIFTY; to use the real index later, replace `market_returns()` with the index return series.
"""
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


def close_matrix(prices):
    """Wide frame: index=date, columns=symbol, values=close."""
    return prices.pivot(index="date", columns="symbol", values="close").sort_index()


# Split/bonus threshold: a genuine one-day move for a NIFTY large-cap never exceeds
# these; anything past them is a corporate action (split/bonus) to be back-adjusted.
SPLIT_LO, SPLIT_HI = 0.6, 1.6


def adjust_ohlc(df):
    """Split/bonus-adjust a single symbol's OHLC (date-sorted) for a continuous
    display series. Same detection as adjust_for_splits, applied to O/H/L/C so
    the candle chart and chg% don't show a fake crash on a split day."""
    df = df.sort_values("date").reset_index(drop=True)
    if len(df) < 2:
        return df
    ratio = df["close"] / df["close"].shift()
    factor = pd.Series(1.0, index=df.index)
    is_action = (ratio < SPLIT_LO) | (ratio > SPLIT_HI)
    factor[is_action] = ratio[is_action]
    adj_factor = factor[::-1].cumprod()[::-1] / factor      # product of factors after t
    for col in ("open", "high", "low", "close"):
        if col in df.columns:
            df[col] = df[col] * adj_factor
    return df


def adjust_for_splits(wide):
    """Back-adjust close prices for splits/bonuses (auto-detected from close jumps).

    On a corporate-action day the close jumps by a non-market factor; we multiply all
    EARLIER prices by that factor so the series is continuous. The action day's own
    return then becomes ~0 (its real move is tiny vs the split) — removes the fake
    -90%-type artifacts. Later prices are untouched, so today's price stays real.
    """
    adj = wide.copy()
    for sym in wide.columns:
        s = wide[sym].dropna()
        if len(s) < 2:
            continue
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


def equity_stats(prices):
    """Return a DataFrame of per-symbol statistics."""
    wide = adjust_for_splits(close_matrix(prices))   # split-adjusted date × symbol
    rets = wide.pct_change()                     # daily returns
    market = rets.mean(axis=1)                   # equal-weighted market proxy

    # Vectorized beta for every symbol at once: cov(s, m) / var(m)
    mkt_dm = market - market.mean()
    mkt_var = float((mkt_dm ** 2).mean())
    cov = rets.sub(rets.mean()).mul(mkt_dm, axis=0).mean()   # per-symbol cov with market
    betas = (cov / mkt_var) if mkt_var else cov * np.nan

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
            "sharpe": float(mean_r / vol) if vol else np.nan,
            "max_drawdown": max_drawdown(close),
            "beta": float(beta),
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
    """PCR, total OI, OI change, futures premium per symbol (latest F&O date)."""
    conn = db.connect()
    try:
        opt = pd.read_sql_query(
            "SELECT symbol,date,expiry,strike,opt_type,oi,chg_oi FROM options", conn)
        fut = pd.read_sql_query(
            "SELECT symbol,date,expiry,close,oi,chg_oi FROM futures", conn)
        spot = pd.read_sql_query("SELECT symbol,date,close FROM prices", conn)
    finally:
        conn.close()
    if opt.empty:
        return pd.DataFrame()

    latest = opt["date"].max()                   # use most recent F&O day
    o = opt[opt["date"] == latest]
    f = fut[fut["date"] == latest]
    s = spot[spot["date"] == latest].set_index("symbol")["close"]

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

    eq = equity_stats(prices)
    fo = fno_stats()
    merged = eq.join(fo, how="left") if not fo.empty else eq

    cols = ["date", "daily_return", "cum_return", "mean_return", "volatility",
            "ann_volatility", "sharpe", "max_drawdown", "beta", "zscore",
            "pct_rank_52w", "cagr", "skew", "kurtosis",
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
