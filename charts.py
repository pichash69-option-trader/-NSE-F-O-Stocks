# -*- coding: utf-8 -*-
"""
charts.py — pure, testable helpers behind the "Line chart" tab.

These are deliberately free of Streamlit / plotly / DB so they can be unit
tested. They compute data-driven support/resistance and momentum reads — all
pure statistics on price / volume series (no technical indicators).
"""
import numpy as np
import pandas as pd


def swing_levels(high, low, last_close, k=3, tol=0.008, per_side=2):
    """Auto support/resistance from recent swing highs/lows.

    A swing high is a bar whose high is the max of the ±k window around it
    (swing low symmetric). Nearby swings are clustered within `tol` (fractional)
    and counted. Returns ``(resistances, supports)`` where each is a list of
    ``(level, touches)`` — resistances above `last_close` nearest-first, supports
    below nearest-first, at most `per_side` each.
    """
    h = np.asarray(high, dtype=float)
    l = np.asarray(low, dtype=float)
    n = len(h)
    if n < 2 * k + 1:
        return [], []
    sw_hi = [float(h[i]) for i in range(k, n - k) if h[i] == h[i - k:i + k + 1].max()]
    sw_lo = [float(l[i]) for i in range(k, n - k) if l[i] == l[i - k:i + k + 1].min()]

    def _cluster(vals):
        out = []
        for v in sorted(vals):
            if out and abs(v - out[-1][0]) / v <= tol:
                m, c = out[-1]
                out[-1] = ((m * c + v) / (c + 1), c + 1)
            else:
                out.append((v, 1))
        return out

    cur = float(last_close)
    res = sorted([(lv, c) for lv, c in _cluster(sw_hi) if lv > cur],
                 key=lambda t: t[0])[:per_side]
    sup = sorted([(lv, c) for lv, c in _cluster(sw_lo) if lv < cur],
                 key=lambda t: -t[0])[:per_side]
    return res, sup


def volume_profile(low, high, volume, lo, hi, nbins=24, va_frac=0.70):
    """Volume-by-price profile. Returns ``(poc, va_lo, va_hi)`` or ``None``.

    Each day's volume is spread evenly across the price bins its [low, high]
    range spans. POC = price bin with the most volume; the value area is the
    smallest set of bins (grown by descending volume) holding `va_frac` of the
    total volume, reported as its low/high price edges.
    """
    lo, hi = float(lo), float(hi)
    if not (np.isfinite(lo) and np.isfinite(hi)) or hi <= lo:
        return None
    edges = np.linspace(lo, hi, nbins + 1)
    centers = (edges[:-1] + edges[1:]) / 2
    vp = np.zeros(nbins)
    for lo_i, hi_i, v in zip(low, high, volume):
        if not (np.isfinite(lo_i) and np.isfinite(hi_i) and np.isfinite(v)) or hi_i <= lo_i:
            continue
        b0 = max(0, min(nbins - 1, int(np.searchsorted(edges, lo_i) - 1)))
        b1 = max(0, min(nbins - 1, int(np.searchsorted(edges, hi_i) - 1)))
        vp[b0:b1 + 1] += v / (b1 - b0 + 1)
    if vp.sum() <= 0:
        return None
    poc = float(centers[int(vp.argmax())])
    cum, total, sel = 0.0, vp.sum(), set()
    for b in sorted(range(nbins), key=lambda b: -vp[b]):
        sel.add(b)
        cum += vp[b]
        if cum >= va_frac * total:
            break
    return poc, float(edges[min(sel)]), float(edges[max(sel) + 1])


def trailing_read(series):
    """``(today, avg7, avg20)`` using the PRIOR 7 / 20 values (today excluded),
    or ``None`` when there is too little data (<8 points). Drives the momentum
    panel: today vs its own recent 7- and 20-day average.
    """
    s = pd.Series(series).dropna()
    if len(s) < 8:
        return None
    today = float(s.iloc[-1])
    a7 = float(s.iloc[-8:-1].mean())
    a20 = float(s.iloc[-21:-1].mean()) if len(s) >= 21 else float(s.iloc[:-1].mean())
    return today, a7, a20
