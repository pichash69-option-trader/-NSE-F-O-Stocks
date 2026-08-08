# -*- coding: utf-8 -*-
"""Tests for charts.py — the pure Line-chart helpers (swing S/R, volume
profile, trailing-average momentum read). No Streamlit / DB involved."""
import numpy as np
import pandas as pd
import pytest

import charts


# --------------------------------------------------------------------------- #
# swing_levels
# --------------------------------------------------------------------------- #
def test_swing_levels_finds_peak_and_trough():
    #            0  1  2  3  4   5  6  7  8  9 10 11 12 13 14
    highs = [10, 11, 12, 13, 20, 13, 12, 11, 12, 13, 14, 13, 12, 11, 10]
    lows = [9, 8, 7, 6, 7, 8, 9, 8, 7, 3, 7, 8, 9, 8, 9]
    res, sup = charts.swing_levels(highs, lows, last_close=11)
    res_levels = [r[0] for r in res]
    sup_levels = [s[0] for s in sup]
    # the 20 peak is a resistance; the 3 trough is a support
    assert 20.0 in res_levels
    assert 3.0 in sup_levels
    # sides are correct relative to the last close
    assert all(lv > 11 for lv, _ in res)
    assert all(lv < 11 for lv, _ in sup)
    # nearest-first ordering
    assert res_levels == sorted(res_levels)
    assert sup_levels == sorted(sup_levels, reverse=True)


def test_swing_levels_touch_count_clusters_near_equal_levels():
    # two highs ~equal (300 and 301, within 0.8% tol) should merge to 1 level, 2 touches
    highs = [290, 295, 298, 300, 298, 296, 298, 301, 298, 295, 290]
    lows = [280] * 11
    res, _ = charts.swing_levels(highs, lows, last_close=250)
    # strongest resistance cluster has >= 2 touches
    assert any(c >= 2 for _, c in res)


def test_swing_levels_too_short_returns_empty():
    assert charts.swing_levels([1, 2, 3], [1, 2, 3], last_close=2) == ([], [])


# --------------------------------------------------------------------------- #
# volume_profile
# --------------------------------------------------------------------------- #
def test_volume_profile_poc_at_high_volume_price():
    # middle day trades a narrow band around ~11 with huge volume -> POC ~ 11
    lows = [10.0, 10.9, 10.0]
    highs = [12.0, 11.1, 12.0]
    vol = [10, 1000, 10]
    out = charts.volume_profile(lows, highs, vol, lo=10.0, hi=12.0)
    assert out is not None
    poc, va_lo, va_hi = out
    assert 10.8 <= poc <= 11.2
    assert va_lo <= poc <= va_hi


def test_volume_profile_bad_range_returns_none():
    assert charts.volume_profile([10], [12], [100], lo=12, hi=10) is None
    assert charts.volume_profile([10], [12], [0], lo=10, hi=12) is None


# --------------------------------------------------------------------------- #
# trailing_read
# --------------------------------------------------------------------------- #
def test_trailing_read_uses_prior_windows_excluding_today():
    s = pd.Series([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
    today, a7, a20 = charts.trailing_read(s)
    assert today == 10
    assert a7 == pytest.approx(np.mean([3, 4, 5, 6, 7, 8, 9]))   # prior 7
    assert a20 == pytest.approx(np.mean([1, 2, 3, 4, 5, 6, 7, 8, 9]))  # all prior (<21)


def test_trailing_read_too_short_is_none():
    assert charts.trailing_read(pd.Series([1, 2, 3])) is None


def test_trailing_read_ignores_nans():
    s = pd.Series([np.nan, 1, 2, 3, 4, 5, 6, 7, 8])
    out = charts.trailing_read(s)
    assert out is not None
    assert out[0] == 8
