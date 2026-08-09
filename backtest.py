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


# "Momentum directional spread" — same momentum entry, but a DEBIT SPREAD in the
# breakout direction (bull call / bear put): cheaper, less theta, defined risk.
SPREAD_PARAMS = dict(MOMENTUM_PARAMS)
SPREAD_PARAMS.update(dict(
    hold_days=7,              # momentum is fast — shorter hold
    exit_before_expiry=3,
    target_move_pct=7.0,      # exit when underlying moves +7% in the direction
    stop_move_pct=3.0,        # exit when it reverses -3% against
))

# "Momentum single buy" — directional single-leg long (up -> BUY CE, down ->
# BUY PE) at ATM. Same trailing/loss/time exit as the strangle, but one leg.
SINGLE_PARAMS = dict(MOMENTUM_PARAMS)
SINGLE_PARAMS.update(dict(strike_offset=0))   # 0 = ATM (OTM = +N steps away)

STRATEGIES = {
    "Momentum buying": MOMENTUM_PARAMS,
    "Momentum directional spread": SPREAD_PARAMS,
    "Momentum single buy": SINGLE_PARAMS,
}


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


def _setup_spread(conn, symbol, entry_date, spot, direction, p):
    """Debit spread: long ATM + short OTM+`otm_steps` (same option type).
    direction 'up' -> bull call (CE), 'down' -> bear put (PE).
    Returns (expiry, opt_type, long_k, short_k, entry_debit) or None."""
    exps = pd.read_sql_query(
        "SELECT DISTINCT expiry FROM options WHERE symbol=? AND date=? ORDER BY expiry",
        conn, params=(symbol, entry_date))["expiry"].tolist()
    ed = pd.Timestamp(entry_date)
    expiry = next((e for e in exps if (pd.Timestamp(e) - ed).days >= p["dte_min"]), None)
    if expiry is None:
        return None
    ot = "CE" if direction == "up" else "PE"
    chain = pd.read_sql_query(
        "SELECT strike,opt_type,close,oi,volume FROM options "
        "WHERE symbol=? AND date=? AND expiry=? AND opt_type=?",
        conn, params=(symbol, entry_date, expiry, ot))
    if chain.empty:
        return None
    strikes = np.sort(chain["strike"].unique())
    atm_i = int(np.abs(strikes - spot).argmin())
    short_i = atm_i + p["otm_steps"] if ot == "CE" else atm_i - p["otm_steps"]
    if short_i < 0 or short_i >= len(strikes):
        return None
    long_k, short_k = float(strikes[atm_i]), float(strikes[short_i])
    lo = chain[chain.strike == long_k]
    sh = chain[chain.strike == short_k]
    if lo.empty or sh.empty:
        return None
    lo, sh = lo.iloc[0], sh.iloc[0]
    if (lo.oi < p["leg_oi_min"] or sh.oi < p["leg_oi_min"] or
            lo.volume < p["leg_vol_min"] or sh.volume < p["leg_vol_min"]):
        return None
    debit = float(lo.close) - float(sh.close)   # long costs more -> net debit
    if debit <= 0:
        return None
    return expiry, ot, long_k, short_k, debit


def _manage_spread(conn, symbol, expiry, ot, long_k, short_k, entry_date,
                   debit, entry_spot, spots, p):
    """Walk the spread value (long − short) to a target/stop/time exit."""
    rows = pd.read_sql_query(
        "SELECT date,strike,close FROM options WHERE symbol=? AND expiry=? AND opt_type=? "
        "AND date>=? AND strike IN (?,?) ORDER BY date",
        conn, params=(symbol, expiry, ot, entry_date, long_k, short_k))
    if rows.empty:
        return None
    piv = rows.pivot_table(index="date", columns="strike", values="close", aggfunc="first")
    if long_k not in piv.columns or short_k not in piv.columns:
        return None
    spread = (piv[long_k].ffill() - piv[short_k].ffill()).dropna()
    dates = [d for d in spread.index if d > entry_date]
    if not dates:
        return None
    exp_cut = pd.Timestamp(expiry) - pd.Timedelta(days=p["exit_before_expiry"])
    for i, d in enumerate(dates, start=1):
        val = float(spread[d])
        pnl = (val / debit - 1) * 100
        spot_d = spots.get(d)
        fav = None
        if spot_d is not None and pd.notna(spot_d):
            mv = (spot_d / entry_spot - 1) * 100
            fav = mv if ot == "CE" else -mv     # favourable move (+ve = good)
        reason = None
        if fav is not None and fav >= p["target_move_pct"]:
            reason = "target"
        elif fav is not None and fav <= -p["stop_move_pct"]:
            reason = "stop"
        elif i >= p["hold_days"]:
            reason = "time"
        elif pd.Timestamp(d) >= exp_cut:
            reason = "expiry"
        if reason:
            return dict(exit_date=d, exit_prem=round(val, 2), pnl_pct=pnl,
                        pnl_points=val - debit, days_held=i, exit_reason=reason)
    d = dates[-1]
    val = float(spread[d])
    return dict(exit_date=d, exit_prem=round(val, 2), pnl_pct=(val / debit - 1) * 100,
                pnl_points=val - debit, days_held=len(dates), exit_reason="dataend")


def _setup_single(conn, symbol, entry_date, spot, direction, p):
    """Single directional long: up -> CE, down -> PE, at ATM + strike_offset.
    Returns (expiry, opt_type, strike, entry_prem) or None."""
    exps = pd.read_sql_query(
        "SELECT DISTINCT expiry FROM options WHERE symbol=? AND date=? ORDER BY expiry",
        conn, params=(symbol, entry_date))["expiry"].tolist()
    ed = pd.Timestamp(entry_date)
    expiry = next((e for e in exps if (pd.Timestamp(e) - ed).days >= p["dte_min"]), None)
    if expiry is None:
        return None
    ot = "CE" if direction == "up" else "PE"
    chain = pd.read_sql_query(
        "SELECT strike,close,oi,volume FROM options "
        "WHERE symbol=? AND date=? AND expiry=? AND opt_type=?",
        conn, params=(symbol, entry_date, expiry, ot))
    if chain.empty:
        return None
    strikes = np.sort(chain["strike"].unique())
    atm_i = int(np.abs(strikes - spot).argmin())
    off = p.get("strike_offset", 0)
    k_i = atm_i + (off if ot == "CE" else -off)
    if k_i < 0 or k_i >= len(strikes):
        return None
    k = float(strikes[k_i])
    row = chain[chain.strike == k]
    if row.empty:
        return None
    row = row.iloc[0]
    if row.oi < p["leg_oi_min"] or row.volume < p["leg_vol_min"]:
        return None
    prem = float(row.close)
    if prem <= 0:
        return None
    return expiry, ot, k, prem


def _manage_single(conn, symbol, expiry, ot, k, entry_date, entry_prem, p):
    """Walk a single long option's premium (trailing / loss / time exit)."""
    rows = pd.read_sql_query(
        "SELECT date,close FROM options WHERE symbol=? AND expiry=? AND opt_type=? "
        "AND strike=? AND date>=? ORDER BY date",
        conn, params=(symbol, expiry, ot, k, entry_date))
    if rows.empty:
        return None
    s = rows.set_index("date")["close"].ffill().dropna()
    dates = [d for d in s.index if d > entry_date]
    if not dates:
        return None
    exp_cut = pd.Timestamp(expiry) - pd.Timedelta(days=p["exit_before_expiry"])
    peak = entry_prem
    for i, d in enumerate(dates, start=1):
        val = float(s[d])
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
            return dict(exit_date=d, exit_prem=round(val, 2), pnl_pct=pnl,
                        pnl_points=val - entry_prem, days_held=i, exit_reason=reason)
    d = dates[-1]
    val = float(s[d])
    return dict(exit_date=d, exit_prem=round(val, 2), pnl_pct=(val / entry_prem - 1) * 100,
                pnl_points=val - entry_prem, days_held=len(dates), exit_reason="dataend")


def run_symbol(conn, symbol, p, strategy="Momentum buying", ban_dates=None):
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
    spots = px.set_index("date")["close"]
    is_spread = strategy == "Momentum directional spread"
    is_single = strategy == "Momentum single buy"

    def _direction(r):
        if pd.notna(r.roll_hi) and r.close > r.roll_hi:
            return "up"
        if pd.notna(r.roll_lo) and r.close < r.roll_lo:
            return "down"
        return "up" if r.chg_pct >= 0 else "down"

    trades, busy_until = [], ""
    for r in px.itertuples():
        if not (r.signal and r.turnover_ok) or r.date <= busy_until:
            continue
        if r.date in ban_dates:
            continue
        if is_single:
            setup = _setup_single(conn, symbol, r.date, float(r.close), _direction(r), p)
            if setup is None:
                continue
            expiry, ot, k, prem = setup
            res = _manage_single(conn, symbol, expiry, ot, k, r.date, prem, p)
            if res is None:
                continue
            head = dict(symbol=symbol, entry_date=r.date, expiry=expiry,
                        structure="long CE" if ot == "CE" else "long PE",
                        strike1=k, strike2=None, entry_prem=round(prem, 2))
        elif is_spread:
            setup = _setup_spread(conn, symbol, r.date, float(r.close), _direction(r), p)
            if setup is None:
                continue
            expiry, ot, long_k, short_k, debit = setup
            res = _manage_spread(conn, symbol, expiry, ot, long_k, short_k, r.date,
                                 debit, float(r.close), spots, p)
            if res is None:
                continue
            head = dict(symbol=symbol, entry_date=r.date, expiry=expiry,
                        structure="bull call" if ot == "CE" else "bear put",
                        strike1=long_k, strike2=short_k, entry_prem=round(debit, 2))
        else:
            setup = _entry_setup(conn, symbol, r.date, float(r.close), p)
            if setup is None:
                continue
            expiry, ce_k, pe_k, entry_prem = setup
            res = _manage(conn, symbol, expiry, ce_k, pe_k, r.date, entry_prem, p)
            if res is None:
                continue
            head = dict(symbol=symbol, entry_date=r.date, expiry=expiry,
                        structure="strangle", strike1=ce_k, strike2=pe_k,
                        entry_prem=round(entry_prem, 2))
        trades.append(dict(**head, **{k: (round(v, 2) if isinstance(v, float) else v)
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


def run(strategy="Momentum buying", symbols=None, params=None, progress=None):
    """Run a named strategy across `symbols` (default: all F&O).
    Returns (trades_df, per_stock_df, overall_dict, equity_df)."""
    p = dict(STRATEGIES.get(strategy, MOMENTUM_PARAMS))
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
            all_trades.extend(run_symbol(conn, sym, p, strategy))
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
