# -*- coding: utf-8 -*-
"""Smoke tests for render.py — the presentation layer produces valid HTML and
formats numbers correctly (pure functions, no Streamlit/DB)."""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import render


# --------------------------------------------------------------------------- #
# _fmt — compact Indian number formatting
# --------------------------------------------------------------------------- #
def test_fmt_scales():
    assert render._fmt(55000) == "55K"        # thousands
    assert render._fmt(180000) == "1.8L"      # lakhs
    assert render._fmt(12000000) == "1.20Cr"  # crores
    assert render._fmt(500) == "500"          # small
    assert render._fmt(None) == "0"           # None-safe
    assert render._fmt(float("nan")) == "0"   # NaN-safe


def test_fmt_negative_keeps_sign():
    assert render._fmt(-55000) == "-55K"


# --------------------------------------------------------------------------- #
# render_stock_table — valid HTML with the data in it
# --------------------------------------------------------------------------- #
def test_render_stock_table_smoke():
    view = pd.DataFrame({
        "date": ["2026-07-30", "2026-07-29"],
        "open": [100.0, 98.0], "high": [102.0, 101.0], "low": [99.0, 97.0],
        "close": [101.0, 100.0], "prev_close": [100.0, 99.0], "settle": [101.0, 100.0],
        "chg_pct": [1.0, -0.5], "volume": [1_000_000, 900_000],
        "turnover": [1e8, 9e7], "num_trades": [5000, 4800],
        "deliv_qty": [500_000, 450_000], "deliv_pct": [55.0, 60.0],
    })
    html = render.render_stock_table(view)
    assert "<table" in html and "</table>" in html
    assert "2026-07-30" in html          # a row rendered
    assert "Prev Cl" in html and "Settle" in html   # new columns present


def test_render_stock_table_empty():
    # empty frame shouldn't crash
    html = render.render_stock_table(pd.DataFrame(
        columns=["date", "open", "high", "low", "close", "chg_pct",
                 "volume", "turnover", "num_trades", "deliv_qty", "deliv_pct",
                 "prev_close", "settle"]))
    assert "<table" in html


# --------------------------------------------------------------------------- #
# option-chain sentiment / picks helpers
# --------------------------------------------------------------------------- #
def test_senti_labels():
    # strong bullish, mild, indecisive, bearish
    assert render._senti(0.5) == ("Strong Bullish", "bull", 0.95)
    assert render._senti(0.2)[0] == "Medium Bullish"
    assert render._senti(0.08)[0] == "Mild Bullish"
    assert render._senti(0.0)[1] == "neu"          # indecisive
    assert render._senti(-0.5)[0] == "Strong Bearish"
