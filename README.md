# NSE NIFTY 50 — Date-wise Dashboard

A self-hosted, date-wise data analysis dashboard for the **NIFTY 50** stocks, built
entirely on **free official NSE data**. See how each stock has changed **day by day** —
prices, delivery, futures, and a full **Sensibull-style option chain** — plus pure
statistical analysis (no technical indicators).

> ⚠️ **Educational / research use only.** This is not investment advice. Do your own
> research; trade at your own risk. The author is not a registered investment adviser.

---

## ✨ Features

- **50 NIFTY stocks**, all data sourced directly from NSE (official bhavcopy archives).
- **Date-wise / timeline view** — pick a stock and a window (7 / 20 / 50 / All days) and
  see how everything evolved, latest day on top.
- **Stock table + candlestick chart** — OHLC, % change, volume, turnover, trades,
  delivery %; hover any candle for full details. Split/bonus-adjusted automatically.
- **Futures** — all three expiries (near/next/far): OHLC, settle, premium, OI, change, value.
- **Option chain (Sensibull-style)** — ITM shading, OI bars, ATM highlight, PCR, max pain;
  a combined "sum chain" across expiries plus each expiry's own chain; raw full-data table.
- **Overview** — all 50 stocks' math stats in one sortable table.
- **Auto-updating** — one command backfills from 1-Jan-2024 to today, then daily incremental.

## 📊 Analysis (pure math — no indicators)

Returns (daily / log / cumulative), volatility (annualized), variance, Sharpe-type ratio,
max drawdown, beta (vs equal-weighted market proxy), correlation, z-score, 52-week
percentile, CAGR, skewness, kurtosis, delivery-ratio trend — and for F&O: Put-Call Ratio,
total OI, OI change, futures premium/discount, max pain, and a strike-wise "sum chain".

## 🛠️ Tech stack

Python · `requests` (NSE archive) · SQLite · `pandas` / `numpy` · `streamlit` · `plotly`

---

## 🚀 Quick start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Backfill the database (1-Jan-2024 -> today). First run takes a while
#    (downloads ~630 trading days of equity + F&O). Resume-safe if interrupted.
python run_daily.py

# 3. Launch the dashboard
streamlit run dashboard.py
```

The dashboard opens at `http://localhost:8501`.

> The first backfill can take ~40–70 minutes and builds a ~1 GB SQLite file (`nse.db`).
> After that, `run_daily.py` only fetches new days (fast).

## 🔄 Daily auto-update (optional, Windows)

Schedule `run_daily.bat` to run daily after market close (~6:30 PM IST) via **Windows
Task Scheduler** — step-by-step instructions in [`task_scheduler_setup.txt`](task_scheduler_setup.txt).

## 📁 Project structure

```
config.py                 # 50 NIFTY symbols + settings
db.py                     # SQLite schema + helpers
fetch_data.py             # equity + delivery (incremental)
fetch_fno.py              # futures + options, all expiry/strike (incremental)
analysis.py               # pure-math stats + F&O math (+ split/bonus adjustment)
dashboard.py              # Streamlit UI (date-wise)
run_daily.py              # fetch + analyse in one command (daily / backfill)
run_daily.bat             # Task Scheduler entry point
task_scheduler_setup.txt  # daily automation guide
PLAN.md                   # full design notes
```

## 🗄️ Data source & licensing

Data comes from NSE's public daily archive files (equity bhavcopy, security delivery /
MTO, and F&O bhavcopy). These are free for **personal and educational** use. **Redistributing
NSE data commercially (e.g. as a paid service) requires a separate licence/agreement with
NSE** — this repo does not grant any rights to NSE's data. It ships **code only**; you
generate your own `nse.db` locally.

## 📜 License

Code licensed under the [MIT License](LICENSE). Fill in your name in the `LICENSE` file.
NSE data is **not** covered by this licence and remains subject to NSE's terms.
