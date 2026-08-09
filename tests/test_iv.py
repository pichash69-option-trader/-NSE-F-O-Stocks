# -*- coding: utf-8 -*-
"""Tests for iv.py — Black-Scholes price, implied-vol inversion, and Greeks.
Pure math, no DB."""
import math

import pytest

import iv


def test_bs_price_roundtrip_call_and_put():
    S, K, T = 1000.0, 1000.0, 30 / 365
    for sigma in (0.15, 0.30, 0.55, 0.90):
        for call in (True, False):
            price = iv.bs_price(S, K, T, sigma, call=call)
            back = iv.implied_vol(price, S, K, T, call=call)
            assert back == pytest.approx(sigma, abs=1e-3)


def test_bs_price_intrinsic_when_no_time():
    assert iv.bs_price(1100, 1000, 0, 0.3, call=True) == pytest.approx(100)
    assert iv.bs_price(900, 1000, 0, 0.3, call=False) == pytest.approx(100)


def test_implied_vol_rejects_bad_prices():
    S, K, T = 1000.0, 1000.0, 30 / 365
    assert iv.implied_vol(0, S, K, T) is None            # non-positive
    assert iv.implied_vol(-5, S, K, T) is None
    # a call priced below intrinsic is unsolvable
    assert iv.implied_vol(5, 1200, 1000, T, call=True) is None


def test_atm_greeks_signs_and_magnitudes():
    S, K, T, sig = 1000.0, 1000.0, 30 / 365, 0.30
    g = iv.greeks(S, K, T, sig, call=True)
    assert 0.45 < g["delta"] < 0.60          # ATM call delta ~0.5
    assert g["gamma"] > 0
    assert g["vega"] > 0
    assert g["theta"] < 0                     # long option decays
    gp = iv.greeks(S, K, T, sig, call=False)
    assert -0.60 < gp["delta"] < -0.40        # ATM put delta ~ -0.5
    assert gp["theta"] < 0


def test_call_put_atm_iv_close():
    # by put-call parity, ATM call & put IV backed out from BS prices match
    S, K, T, sig = 1234.0, 1250.0, 25 / 365, 0.42
    cp = iv.bs_price(S, K, T, sig, call=True)
    pp = iv.bs_price(S, K, T, sig, call=False)
    assert iv.implied_vol(cp, S, K, T, call=True) == pytest.approx(
        iv.implied_vol(pp, S, K, T, call=False), abs=1e-3)


def test_higher_iv_costs_more():
    S, K, T = 500.0, 500.0, 20 / 365
    assert iv.bs_price(S, K, T, 0.5, call=True) > iv.bs_price(S, K, T, 0.2, call=True)
