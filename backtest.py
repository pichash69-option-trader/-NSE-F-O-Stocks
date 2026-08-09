# -*- coding: utf-8 -*-
"""
backtest.py — option-strategy backtests on our NSE EOD data.

Currently ships one named strategy: **"Momentum buying"** — a non-directional
long strangle (BUY OTM+3 CE + OTM+3 PE) entered on a multi-factor momentum
burst, managed with a trailing stop / loss cap / time exit. All logic is pure
(DB in, DataFrames out) so it can be unit-tested and cached by the dashboard.

Everything is EOD/daily: entries and exits use the daily CLOSE, and the
trailing stop is evaluated on daily closes. Research/education only — not advice.
"""
import numpy as np
import pandas as pd

import db

# Default parameters for "Momentum buying" (see strategy.md).
MOMENTUM_PARAMS = dict(
    min_factors=4,            # need >=4 of the 5 factors
    price_move_pct=2.0,       # |chg%| >= 2
    vol_mult=2.0,             # volume >= 2x prior-20d avg
    deliv_min=50.0,           # delivery% >= 50
    breakout_window=20,       # broke prior-N-day high/low (swing S/R proxy)
    otm_steps=3,              # OTM+3 strikes each side
    dte_min=15,               # days-to-expiry >= 15 at entry (calendar)
    turnover_min_cr=100.0,    # underlying turnover >= 100 Cr
    leg_oi_min=1000,          # each leg OI >= 1000 at entry
    leg_vol_min=200,          # each leg volume >= 200 at entry
    hold_days=10,             # max 10 trading days
    exit_before_expiry=5,     # or exit at expiry - 5 calendar days
    trail_activate_pct=100.0, # trailing turns on at +100%
    trail_pullback_pct=30.0,  # then exit on -30% from peak
    loss_exit_pct=50.0,       # hard loss exit at -50%
    lots=2,                   # position size (for the rupee P&L column)
)


def lot_sizes(conn):
    """Per-symbol NSE lot size, derived from futures: lot = value / (contracts ×
    price). (The `value_lakh` column actually holds value in rupees.) Median per
    symbol, used only to turn premium-points into a rupee estimate."""
    fut = pd.read_sql_query(
        "SELECT symbol, contracts, value_lakh, close FROM futures "
        "WHERE contracts > 0 AND close > 0", conn)
    if fut.empty:
        return pd.Series(dtype=float)
    fut["lot"] = fut["value_lakh"] / (fut["contracts"] * fut["close"])
    return fut.groupby("symbol")["lot"].median().round().clip(lower=1)


# --------------------------------------------------------------------------- #
# Signal preparation (vectorised, per stock)
# --------------------------------------------------------------------------- #
def prepare_signals(px, fut_oi, p):
    """Add factor columns + `signal`/`turnover_ok` flags to a price frame.

    `px`: DataFrame with date/open/high/low/close/prev_close/volume/turnover/
    deliv_pct (ascending date). `fut_oi`: Series date->total futures OI.
    """
    px = px.sort_values("date").reset_index(drop=True).copy()
    px["chg_pct"] = (px["close"] / px["prev_close"] - 1) * 100
    px["vol_avg20"] = px["volume"].rolling(20).mean().shift(1)
    w = p["breakout_window"]
    px["roll_hi"] = px["high"].rolling(w).max().shift(1)   # prior-N-day high
    px["roll_lo"] = px["low"].rolling(w).min().shift(1)    # prior-N-day low
    px["fut_oi"] = px["date"].map(fut_oi) if fut_oi is not None else np.nan

    f1 = (px["chg_pct"].abs() >= p["price_move_pct"])
    f2 = (px["volume"] >= p["vol_mult"] * px["vol_avg20"])
    f3 = (px["deliv_pct"] >= p["deliv_min"])
    f4 = (px["close"] > px["roll_hi"]) | (px["close"] < px["roll_lo"])
    f5 = (px["fut_oi"] > px["fut_oi"].shift(1))
    px["nfac"] = sum(f.fillna(False).astype(int) for f in (f1, f2, f3, f4, f5))
    px["signal"] = px["nfac"] >= p["min_factors"]
    px["turnover_ok"] = px["turnover"] >= p["turnover_min_cr"] * 1e7
    return px


# --------------------------------------------------------------------------- #
# Per-entry option setup + trade management
# --------------------------------------------------------------------------- #
def _entry_setup(conn, symbol, entry_date, spot, p):
    """Pick expiry (dte>=min), OTM+3 CE/PE strikes, check leg liquidity.
    Returns (expiry, ce_strike, pe_strike, entry_prem) or None."""
    exps = pd.read_sql_query(
        "SELECT DISTINCT expiry FROM options WHERE symbol=? AND date=? ORDER BY expiry",
        conn, params=(symbol, entry_date))["expiry"].tolist()
    ed = pd.Timestamp(entry_date)
    expiry = next((e for e in exps if (pd.Timestamp(e) - ed).days >= p["dte_min"]), None)
    if expiry is None:
        return None
    chain = pd.read_sql_query(
        "SELECT strike,opt_type,close,oi,volume FROM options "
        "WHERE symbol=? AND date=? AND expiry=?", conn, params=(symbol, entry_date, expiry))
    if chain.empty:
        return None
    strikes = np.sort(chain["strike"].unique())
    atm_i = int(np.abs(strikes - spot).argmin())
    ce_i, pe_i = atm_i + p["otm_steps"], atm_i - p["otm_steps"]
    if pe_i < 0 or ce_i >= len(strikes):
        return None
    ce_k, pe_k = float(strikes[ce_i]), float(strikes[pe_i])
    ce = chain[(chain.strike == ce_k) & (chain.opt_type == "CE")]
    pe = chain[(chain.strike == pe_k) & (chain.opt_type == "PE")]
    if ce.empty or pe.empty:
        return None
    ce, pe = ce.iloc[0], pe.iloc[0]
    if (ce.oi < p["leg_oi_min"] or pe.oi < p["leg_oi_min"] or
            ce.volume < p["leg_vol_min"] or pe.volume < p["leg_vol_min"]):
        return None
    entry_prem = float(ce.close) + float(pe.close)
    if entry_prem <= 0:
        return None
    return expiry, ce_k, pe_k, entry_prem


def _manage(conn, symbol, expiry, ce_k, pe_k, entry_date, entry_prem, p):
    """Walk the combined CE+PE premium from entry to exit. Returns dict."""
    rows = pd.read_sql_query(
        "SELECT date,strike,opt_type,close FROM options WHERE symbol=? AND expiry=? "
        "AND date>=? AND strike IN (?,?) ORDER BY date",
        conn, params=(symbol, expiry, entry_date, ce_k, pe_k))
    if rows.empty:
        return None
    piv = rows.pivot_table(index="date", columns=["opt_type", "strike"],
                           values="close", aggfunc="first")
    # combined = CE(ce_k) + PE(pe_k) per date
    try:
        ce_s = piv[("CE", ce_k)]
        pe_s = piv[("PE", pe_k)]
    except KeyError:
        return None
    comb = (ce_s.reindex(piv.index).ffill() + pe_s.reindex(piv.index).ffill()).dropna()
    dates = [d for d in comb.index if d > entry_date]
    if not dates:
        return None
    exp_cut = (pd.Timestamp(expiry) - pd.Timedelta(days=p["exit_before_expiry"]))
    peak = entry_prem
    for i, d in enumerate(dates, start=1):
        val = float(comb[d])
        peak = max(peak, val)
        pnl = (val / entry_prem - 1) * 100
        peak_pnl = (peak / entry_prem - 1) * 100
        reason = None
        if pnl <= -p["loss_exit_pct"]:
            reason = "loss"
        elif peak_pnl >= p["trail_activate_pct"] and val <= peak * (1 - p["trail_pullback_pct"] / 100):
            reason = "trail"
        elif i >= p["hold_days"]:
            reason = "time"
        elif pd.Timestamp(d) >= exp_cut:
            reason = "expiry"
        if reason:
            return dict(exit_date=d, exit_prem=val, pnl_pct=pnl,
                        pnl_points=val - entry_prem, days_held=i, exit_reason=reason)
    # ran out of data — exit at last available close
    d = dates[-1]
    val = float(comb[d])
    return dict(exit_date=d, exit_prem=val, pnl_pct=(val / entry_prem - 1) * 100,
                pnl_points=val - entry_prem, days_held=len(dates), exit_reason="dataend")


def run_symbol(conn, symbol, p, ban_dates=None):
    """Backtest one stock. Returns a list of trade dicts (no overlapping trades)."""
    px = pd.read_sql_query(
        "SELECT date,open,high,low,close,prev_close,volume,turnover,deliv_pct "
        "FROM prices WHERE symbol=? ORDER BY date", conn, params=(symbol,))
    if len(px) < 40:
        return []
    fut = pd.read_sql_query(
        "SELECT date, SUM(oi) oi FROM futures WHERE symbol=? GROUP BY date",
        conn, params=(symbol,))
    fut_oi = fut.set_index("date")["oi"] if not fut.empty else None
    px = prepare_signals(px, fut_oi, p)
    if ban_dates is None:
        ban_dates = set(pd.read_sql_query(
            "SELECT date FROM secban WHERE symbol=?", conn, params=(symbol,))["date"])

    trades, busy_until = [], ""
    for r in px.itertuples():
        if not (r.signal and r.turnover_ok) or r.date <= busy_until:
            continue
        if r.date in ban_dates:
            continue
        setup = _entry_setup(conn, symbol, r.date, float(r.close), p)
        if setup is None:
            continue
        expiry, ce_k, pe_k, entry_prem = setup
        res = _manage(conn, symbol, expiry, ce_k, pe_k, r.date, entry_prem, p)
        if res is None:
            continue
        trades.append(dict(symbol=symbol, entry_date=r.date, expiry=expiry,
                           ce_strike=ce_k, pe_strike=pe_k, entry_prem=round(entry_prem, 2),
                           **{k: (round(v, 2) if isinstance(v, float) else v)
                              for k, v in res.items()}))
        busy_until = res["exit_date"]      # no pyramiding
    return trades


# --------------------------------------------------------------------------- #
# Aggregation
# --------------------------------------------------------------------------- #
def summarize(trades_df):
    """Per-stock + overall summary from a trades DataFrame."""
    if trades_df.empty:
        return pd.DataFrame(), {}

    has_rup = "pnl_rupee" in trades_df.columns

    def _agg(g):
        wins = (g["pnl_points"] > 0).sum()
        out = {
            "trades": len(g),
            "win_rate": round(100 * wins / len(g), 1),
            "total_rupee": int(g["pnl_rupee"].sum()) if has_rup else 0,
            "total_pts": round(g["pnl_points"].sum(), 1),
            "avg_pnl_pct": round(g["pnl_pct"].mean(), 1),
            "best_pct": round(g["pnl_pct"].max(), 1),
            "worst_pct": round(g["pnl_pct"].min(), 1),
        }
        return pd.Series(out)

    per_stock = (trades_df.groupby("symbol", group_keys=False).apply(_agg)
                 .sort_values("total_rupee" if has_rup else "total_pts",
                              ascending=False).reset_index())
    n = len(trades_df)
    wins = int((trades_df["pnl_points"] > 0).sum())
    overall = dict(
        trades=n, stocks=trades_df["symbol"].nunique(),
        win_rate=round(100 * wins / n, 1),
        total_rupee=int(trades_df["pnl_rupee"].sum()) if has_rup else 0,
        total_pts=round(trades_df["pnl_points"].sum(), 1),
        avg_rupee=int(trades_df["pnl_rupee"].mean()) if has_rup else 0,
        avg_pnl_pct=round(trades_df["pnl_pct"].mean(), 1),
        best_pct=round(trades_df["pnl_pct"].max(), 1),
        worst_pct=round(trades_df["pnl_pct"].min(), 1),
        exits=trades_df["exit_reason"].value_counts().to_dict(),
    )
    return per_stock, overall


def equity_curve(trades_df):
    """Cumulative premium-points over time (by exit date)."""
    if trades_df.empty:
        return pd.DataFrame(columns=["exit_date", "cum_pts"])
    e = trades_df.sort_values("exit_date").copy()
    e["cum_pts"] = e["pnl_points"].cumsum()
    return e[["exit_date", "cum_pts"]].reset_index(drop=True)


def run(symbols=None, params=None, progress=None):
    """Run the Momentum-buying backtest across `symbols` (default: all F&O).
    Returns (trades_df, per_stock_df, overall_dict, equity_df)."""
    p = dict(MOMENTUM_PARAMS)
    if params:
        p.update(params)
    conn = db.connect()
    try:
        if symbols is None:
            symbols = pd.read_sql_query(
                "SELECT DISTINCT symbol FROM options ORDER BY symbol", conn)["symbol"].tolist()
        lots = lot_sizes(conn)
        all_trades = []
        for i, sym in enumerate(symbols):
            all_trades.extend(run_symbol(conn, sym, p))
            if progress:
                progress(i + 1, len(symbols), sym)
    finally:
        conn.close()
    trades_df = pd.DataFrame(all_trades)
    if not trades_df.empty:
        n_lots = p.get("lots", 2)
        trades_df["lot"] = trades_df["symbol"].map(lots).fillna(1).astype(int)
        trades_df["pnl_rupee"] = (trades_df["pnl_points"] * trades_df["lot"] * n_lots).round().astype(int)
    per_stock, overall = summarize(trades_df)
    return trades_df, per_stock, overall, equity_curve(trades_df)
