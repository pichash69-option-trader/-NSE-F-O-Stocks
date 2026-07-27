# -*- coding: utf-8 -*-
"""
config.py — central settings for the NSE NIFTY 50 data project.
"""
from pathlib import Path

# --- Paths ---
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "nse.db"

# --- History ---
START_DATE = "2024-01-01"   # fixed backfill start (1-Jan-2024)

# --- Which stocks to track ---
#   "NIFTY50" -> the 50 NIFTY constituents (below)
#   "FNO"     -> the full F&O stock universe (~210), auto-derived from the F&O
#                bhavcopy each run (see universe.py). Bigger: ~4x data, ~4 GB DB.
UNIVERSE = "FNO"

# --- Fetch behaviour ---
REQUEST_DELAY = 0.4         # seconds between date downloads (be polite to NSE)
REQUEST_TIMEOUT = 30        # per-request timeout (seconds)
MAX_RETRIES = 3

# Browser-like headers — NSE archive blocks plain requests without these.
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"),
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}

# --- NIFTY 50 constituents (symbols as used by NSE) ---
# Note: NSE rebalances this list ~twice a year; verify once from the official
# index factsheet if you need it exact for a given date.
NIFTY50 = [
    "RELIANCE", "TCS", "HDFCBANK", "ICICIBANK", "INFY",
    "BHARTIARTL", "SBIN", "LT", "ITC", "HINDUNILVR",
    "BAJFINANCE", "KOTAKBANK", "AXISBANK", "HCLTECH", "MARUTI",
    "SUNPHARMA", "M&M", "TITAN", "NTPC", "ULTRACEMCO",
    "ASIANPAINT", "POWERGRID", "TATAMOTORS", "ADANIENT", "WIPRO",
    "JSWSTEEL", "NESTLEIND", "BAJAJFINSV", "ONGC", "TATASTEEL",
    "COALINDIA", "ADANIPORTS", "HDFCLIFE", "GRASIM", "SBILIFE",
    "TECHM", "BAJAJ-AUTO", "HINDALCO", "DRREDDY", "CIPLA",
    "BRITANNIA", "EICHERMOT", "APOLLOHOSP", "INDUSINDBK", "TATACONSUM",
    "BPCL", "SHRIRAMFIN", "HEROMOTOCO", "LTIM", "TRENT",
]

# Fast membership check
NIFTY50_SET = set(NIFTY50)

# Index symbol for beta / benchmark (F&O uses "NIFTY")
INDEX_SYMBOL = "NIFTY 50"

assert len(NIFTY50) == 50, f"Expected 50 symbols, got {len(NIFTY50)}"
