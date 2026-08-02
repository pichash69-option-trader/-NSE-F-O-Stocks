# -*- coding: utf-8 -*-
"""Sanity tests for the pure-math functions in analysis.py.
Run:  pytest -q   (from the project root)
DB-backed functions (fno_stats/max_pain/sum_chain/load_prices/run) are skipped —
these test the math on synthetic data with known outputs."""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import analysis


# --------------------------------------------------------------------------- #
# max_drawdown
# --------------------------------------------------------------------------- #
def test_max_drawdown_peak_to_trough():
    # 100 → 120 (peak) → 60 (trough) → 90 :  dd = 60/120 − 1 = −0.5
    close = pd.Series([100, 120, 60, 90], dtype=float)
    assert abs(analysis.max_drawdown(close) - (-0.5)) < 1e-9


def test_max_drawdown_monotonic_up_is_zero():
    close = pd.Series([100, 110, 120], dtype=float)
    assert analysis.max_drawdown(close) == 0.0


# --------------------------------------------------------------------------- #
# split/bonus adjustment
# --------------------------------------------------------------------------- #
def test_adjust_for_splits_halving():
    # 1:2 split — price halves on day 2 (ratio 0.5 < SPLIT_LO 0.6)
    idx = pd.date_range("2024-01-01", periods=4)
    wide = pd.DataFrame({"AAA": [100.0, 100.0, 50.0, 55.0]}, index=idx)
    adj = analysis.adjust_for_splits(wide)
    assert abs(adj["AAA"].iloc[-1] - 55.0) < 1e-9      # latest untouched
    assert abs(adj["AAA"].iloc[0] - 50.0) < 1e-9       # pre-split back-adjusted ×0.5
    # the split day's own return becomes ~0 (no fake −50% crash)
    assert abs(adj["AAA"].pct_change().iloc[2]) < 1e-9


def test_adjust_for_splits_normal_moves_unchanged():
    idx = pd.date_range("2024-01-01", periods=3)
    wide = pd.DataFrame({"AAA": [100.0, 105.0, 103.0]}, index=idx)
    adj = analysis.adjust_for_splits(wide)
    assert np.allclose(adj["AAA"].values, [100.0, 105.0, 103.0])


# --- real corp-action factors (exact split/bonus adjustment) --- #
def test_action_factor_parsing():
    assert abs(analysis._action_factor("Bonus", "Bonus 1:1") - 0.5) < 1e-9
    assert abs(analysis._action_factor("Bonus", "Bonus 4:1") - 0.2) < 1e-9
    assert abs(analysis._action_factor("Split", "From Rs 10/- To Rs 2/-") - 0.2) < 1e-9
    assert analysis._action_factor("Dividend", "Dividend Rs 5") is None


def test_adjust_for_splits_real_bonus_exact():
    idx = pd.date_range("2024-01-01", periods=4)
    # 1:1 bonus on day 3 (price ~halves) while the stock genuinely rose +2%
    wide = pd.DataFrame({"AAA": [100.0, 100.0, 51.0, 52.0]}, index=idx)
    adj = analysis.adjust_for_splits(wide, {"AAA": {idx[2]: 0.5}})
    assert abs(adj["AAA"].iloc[0] - 50.0) < 1e-9                 # pre-bonus ×0.5
    assert abs(adj["AAA"].pct_change().iloc[2] - 0.02) < 1e-9    # real +2% preserved


def test_adjust_for_splits_real_crash_untouched():
    # a genuine −45% crash with NO corp action must stay real (old heuristic wrongly adjusted it)
    idx = pd.date_range("2024-01-01", periods=4)
    wide = pd.DataFrame({"AAA": [100.0, 100.0, 55.0, 54.0]}, index=idx)
    adj = analysis.adjust_for_splits(wide, {"AAA": {}})
    assert np.allclose(adj["AAA"].values, [100.0, 100.0, 55.0, 54.0])


def test_adjust_for_splits_factor_mismatch_skipped():
    # corp action claims 0.2 but price is flat (e.g. NCRPS bonus) -> factor ignored
    idx = pd.date_range("2024-01-01", periods=4)
    wide = pd.DataFrame({"AAA": [100.0, 100.0, 100.0, 101.0]}, index=idx)
    adj = analysis.adjust_for_splits(wide, {"AAA": {idx[2]: 0.2}})
    assert np.allclose(adj["AAA"].values, [100.0, 100.0, 100.0, 101.0])


def test_adjust_ohlc_halving():
    df = pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=3),
        "open": [100.0, 100.0, 50.0], "high": [102.0, 101.0, 51.0],
        "low": [99.0, 99.0, 49.0], "close": [100.0, 100.0, 50.0],
    })
    out = analysis.adjust_ohlc(df)
    # last row untouched, earlier rows halved (continuous series)
    assert abs(out["close"].iloc[-1] - 50.0) < 1e-9
    assert abs(out["close"].iloc[0] - 50.0) < 1e-9


# --------------------------------------------------------------------------- #
# equity_stats (end-to-end on synthetic prices)
# --------------------------------------------------------------------------- #
def _synthetic_prices():
    dates = list(pd.date_range("2024-01-01", periods=12, freq="D"))
    up = np.linspace(100, 120, 12)          # AAA trends up
    down = np.linspace(200, 180, 12)        # BBB trends down
    return pd.DataFrame({
        "symbol": ["AAA"] * 12 + ["BBB"] * 12,
        "date": dates * 2,
        "close": list(up) + list(down),
        "volume": [1000] * 24,
        "deliv_pct": [50.0] * 24,
    })


def test_equity_stats_shape_and_signs():
    stats = analysis.equity_stats(_synthetic_prices())
    assert {"AAA", "BBB"} <= set(stats.index)
    # up-trend → positive cumulative return; down-trend → negative
    assert stats.loc["AAA", "cum_return"] > 0
    assert stats.loc["BBB", "cum_return"] < 0


def test_equity_stats_relationships():
    stats = analysis.equity_stats(_synthetic_prices())
    r = stats.loc["AAA"]
    # annualized vol = daily vol × √252  ≥ daily vol
    assert r["ann_volatility"] >= r["volatility"]
    assert abs(r["ann_volatility"] - r["volatility"] * np.sqrt(252)) < 1e-6
    # drawdown is never positive; 52w %ile within [0, 100]
    assert r["max_drawdown"] <= 0
    assert 0 <= r["pct_rank_52w"] <= 100


def test_equity_stats_beta_from_real_index():
    # AAA moves exactly 1.5× the index each day → beta must come out ≈ 1.5
    dates = pd.date_range("2024-01-01", periods=40, freq="D")
    rng = np.random.default_rng(0)
    idx_ret = rng.normal(0, 0.01, 40)
    index_level = 100 * np.cumprod(1 + idx_ret)
    aaa = 100 * np.cumprod(1 + 1.5 * idx_ret)
    prices = pd.DataFrame({
        "symbol": ["AAA"] * 40, "date": list(dates), "close": list(aaa),
        "volume": [1000] * 40, "deliv_pct": [50.0] * 40,
    })
    index_close = pd.Series(index_level, index=dates)
    stats = analysis.equity_stats(prices, index_close=index_close)
    assert abs(stats.loc["AAA", "beta"] - 1.5) < 0.05
