# -*- coding: utf-8 -*-
"""
iv.py — implied volatility + Greeks + IV-Rank, computed from our EOD option
prices (Black-Scholes). This is the piece an option BUYER most needs: "sell high
IV, buy low IV" — IV Rank < ~30 = options are cheap vs their own 52-week range.

We have no IV/Greeks in the data, but we can back them out from the option's
market (close) price given spot, strike, time-to-expiry and a risk-free rate.
Uses ATM options (liquid → reliable IV). European Black-Scholes is an
approximation for NSE stock options (American, but ATM/short-dated ≈ European,
dividends ignored). Research/education only — not advice.
"""
import math

import numpy as np
import pandas as pd

import db

R = 0.065            # risk-free rate (India ~6.5%); IV is insensitive to r short-dated
_SQRT2PI = math.sqrt(2 * math.pi)


def _cdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _pdf(x):
    return math.exp(-0.5 * x * x) / _SQRT2PI


def bs_price(S, K, T, sigma, r=R, call=True):
    """Black-Scholes European price."""
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return max(0.0, (S - K) if call else (K - S))
    sq = sigma * math.sqrt(T)
    d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / sq
    d2 = d1 - sq
    if call:
        return S * _cdf(d1) - K * math.exp(-r * T) * _cdf(d2)
    return K * math.exp(-r * T) * _cdf(-d2) - S * _cdf(-d1)


def implied_vol(price, S, K, T, r=R, call=True):
    """Back out IV from a market price via bisection. None if not solvable."""
    if price is None or price <= 0 or T <= 0 or S <= 0 or K <= 0:
        return None
    intrinsic = max(0.0, (S - K) if call else (K - S))
    if price < intrinsic - 1e-6:          # below intrinsic → bad/stale price
        return None
    lo, hi = 1e-4, 5.0
    plo = bs_price(S, K, T, lo, r, call) - price
    phi = bs_price(S, K, T, hi, r, call) - price
    if plo * phi > 0:                     # price outside solvable band
        return None
    for _ in range(64):
        mid = 0.5 * (lo + hi)
        pm = bs_price(S, K, T, mid, r, call) - price
        if abs(pm) < 1e-6:
            return mid
        if plo * pm < 0:
            hi, phi = mid, pm
        else:
            lo, plo = mid, pm
    return 0.5 * (lo + hi)


def greeks(S, K, T, sigma, r=R, call=True):
    """delta, gamma, vega (per 1% IV), theta (per calendar day)."""
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return dict(delta=np.nan, gamma=np.nan, vega=np.nan, theta=np.nan)
    sq = math.sqrt(T)
    d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * sq)
    d2 = d1 - sigma * sq
    nd1 = _pdf(d1)
    delta = _cdf(d1) if call else _cdf(d1) - 1.0
    gamma = nd1 / (S * sigma * sq)
    vega = S * nd1 * sq / 100.0           # ₹ per +1% IV
    disc = r * K * math.exp(-r * T)
    if call:
        theta = (-S * nd1 * sigma / (2 * sq) - disc * _cdf(d2)) / 365.0
    else:
        theta = (-S * nd1 * sigma / (2 * sq) + disc * _cdf(-d2)) / 365.0
    return dict(delta=delta, gamma=gamma, vega=vega, theta=theta)


def _t_years(date, expiry):
    return max((pd.Timestamp(expiry) - pd.Timestamp(date)).days, 0) / 365.0


def atm_iv_history(conn, symbol, dte_lo=10, dte_hi=45, target_dte=30):
    """Daily ATM implied-vol series (%) for a stock. Picks, per day, the expiry
    nearest `target_dte` (within [dte_lo, dte_hi]) and the strike nearest spot;
    IV = average of the ATM call & put IV."""
    px = pd.read_sql_query("SELECT date,close FROM prices WHERE symbol=? ORDER BY date",
                           conn, params=(symbol,))
    if px.empty:
        return pd.Series(dtype=float)
    spot = dict(zip(px["date"], px["close"]))
    # Only load near-month CALL options (dte band filtered in SQL — big speed-up;
    # ATM call IV is the conventional ATM IV by put-call parity).
    opt = pd.read_sql_query(
        "SELECT date,expiry,strike,close FROM options WHERE symbol=? AND opt_type='CE' "
        "AND close>0 AND expiry BETWEEN date(date, ?) AND date(date, ?)",
        conn, params=(symbol, f"+{dte_lo} days", f"+{dte_hi} days"))
    if opt.empty:
        return pd.Series(dtype=float)
    opt["dte"] = (pd.to_datetime(opt["expiry"]) - pd.to_datetime(opt["date"])).dt.days
    opt["spot"] = opt["date"].map(spot)
    opt = opt[opt["spot"].notna()]
    if opt.empty:
        return pd.Series(dtype=float)
    # --- vectorised ATM selection (no per-date python loop) ---
    opt["dte_dist"] = (opt["dte"] - target_dte).abs()
    exp_pick = opt.loc[opt.groupby("date")["dte_dist"].idxmin(), ["date", "expiry"]]
    opt = opt.merge(exp_pick, on=["date", "expiry"])
    opt["kdist"] = (opt["strike"] - opt["spot"]).abs()
    atm = opt.loc[opt.groupby("date")["kdist"].idxmin()].copy()   # one ATM call per date
    atm["T"] = atm["dte"].clip(lower=0) / 365.0
    ivs = [implied_vol(c, s, k, t, call=True)
           for c, s, k, t in zip(atm["close"], atm["spot"], atm["strike"], atm["T"])]
    atm["iv"] = ivs
    ser = atm.dropna(subset=["iv"]).set_index("date")["iv"] * 100.0
    return ser.sort_index()


def compute_all(window=252):
    """Per-stock buyer snapshot: current ATM IV, IV-Rank & IV-percentile (vs last
    `window` days), realized vol, ATM Greeks, days-to-expiry. Returns a DataFrame
    indexed by symbol, sorted by IV-Rank ascending (cheapest first)."""
    conn = db.connect()
    try:
        syms = pd.read_sql_query(
            "SELECT DISTINCT symbol FROM options ORDER BY symbol", conn)["symbol"].tolist()
        px_all = pd.read_sql_query("SELECT symbol,date,close FROM prices ORDER BY symbol,date", conn)
        rows = []
        for sym in syms:
            hist = atm_iv_history(conn, sym)
            if hist.empty:
                continue
            cur = float(hist.iloc[-1])
            w = hist.tail(window)
            lo, hi = float(w.min()), float(w.max())
            iv_rank = (cur - lo) / (hi - lo) * 100 if hi > lo else np.nan
            iv_pct = float((w < cur).mean() * 100)
            # realized (historical) vol from the underlying, annualised
            pr = px_all[px_all.symbol == sym].tail(21)["close"]
            rv = float(pr.pct_change().std() * math.sqrt(252) * 100) if len(pr) > 5 else np.nan
            # ATM greeks on the latest option day
            gk = _latest_atm_greeks(conn, sym)
            rows.append(dict(symbol=sym, iv=round(cur, 1),
                             iv_rank=round(iv_rank, 0) if pd.notna(iv_rank) else np.nan,
                             iv_pctile=round(iv_pct, 0), hv=round(rv, 1) if pd.notna(rv) else np.nan,
                             iv_hv=round(cur / rv, 2) if pd.notna(rv) and rv else np.nan,
                             **gk))
        df = pd.DataFrame(rows).set_index("symbol")
        return df.sort_values("iv_rank")
    finally:
        conn.close()


def _latest_atm_greeks(conn, symbol):
    """ATM call Greeks + days-to-expiry on the latest option day (near expiry)."""
    d = pd.read_sql_query(
        "SELECT MAX(date) d FROM options WHERE symbol=?", conn, params=(symbol,))["d"].iloc[0]
    blank = dict(delta=np.nan, theta=np.nan, gamma=np.nan, vega=np.nan, dte=np.nan)
    if not d:
        return blank
    S = pd.read_sql_query("SELECT close FROM prices WHERE symbol=? AND date=?",
                          conn, params=(symbol, d))
    if S.empty:
        return blank
    S = float(S["close"].iloc[0])
    exps = pd.read_sql_query(
        "SELECT DISTINCT expiry FROM options WHERE symbol=? AND date=? ORDER BY expiry",
        conn, params=(symbol, d))["expiry"].tolist()
    exp = next((e for e in exps if (pd.Timestamp(e) - pd.Timestamp(d)).days >= 7), exps[0] if exps else None)
    if exp is None:
        return blank
    ch = pd.read_sql_query(
        "SELECT strike,close FROM options WHERE symbol=? AND date=? AND expiry=? AND opt_type='CE'",
        conn, params=(symbol, d, exp))
    if ch.empty:
        return blank
    strikes = np.sort(ch["strike"].unique())
    k = float(strikes[np.abs(strikes - S).argmin()])
    price = float(ch[ch.strike == k]["close"].iloc[0])
    T = _t_years(d, exp)
    iv = implied_vol(price, S, k, T, call=True)
    if not iv:
        return dict(**blank, )
    g = greeks(S, k, T, iv, call=True)
    return dict(delta=round(g["delta"], 2), theta=round(g["theta"], 1),
                gamma=round(g["gamma"], 4), vega=round(g["vega"], 1),
                dte=int((pd.Timestamp(exp) - pd.Timestamp(d)).days))
