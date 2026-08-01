# 📈 NSE F&O Stocks — Date-wise Dashboard

A self-hosted, **date-wise** data analysis dashboard for the **entire NSE F&O universe
(~210 stocks)**, built entirely on **free official NSE data**. See how each stock has
changed **day by day** — prices, delivery, all futures expiries, a full **Sensibull-style
option chain**, and **FII/DII positioning** — with pure **statistical analysis
(no technical indicators)**, wrapped in a premium dark UI.

> ⚠️ **Educational / research use only.** This is not investment advice. Do your own
> research; trade at your own risk. The author is not a registered investment adviser.

---

## ✨ Features

- **~210 F&O stocks**, all data sourced directly from NSE (official bhavcopy archives) —
  the F&O universe is derived automatically from the latest F&O bhavcopy.
- **Date-wise / timeline view** — pick a stock and a window (7 / 20 / 50 / All days) and
  see how everything evolved, latest day on top. Date sliders for fast scrubbing.
- **6 sections** in a sidebar-navigation, glassmorphism UI (Outfit font, indigo/purple
  premium theme, live top-movers ticker) — each maps to a data type:

| Section | What it shows |
|---|---|
| 📈 **Equity / Cash** | Day-by-day OHLC, prev close, settle, % change, volume, turnover, trades, delivery qty/%; candlestick chart (hover for detail); split/bonus-adjusted |
| 🔮 **Futures** | All three expiries (near/next/far): OHLC, settle, premium, OI + change, contracts, value, Σ total + estimated participant split |
| ⛓️ **Options** | Sensibull-style — ITM shading, OI bars, ATM highlight, PCR, max pain; a combined "sum chain" across expiries + each expiry's own chain with OHLC/settle/turnover inside |
| 🏦 **Participant** | FII / DII / Pro / Client **sentiment** (OI + Volume, Bearish‹—›Bullish bars per segment) + net trend + cumulative-flow charts |
| 📊 **Math stats** | All ~210 stocks' statistics in one sortable table (18 metrics + 1W/1M returns), sticky header + symbol |
| 🎯 **Next-day shortlist** | Statistical screener — Momentum + Mean-reversion top-3 up/down for next day, with backtest hit-rate + date slider (past picks ✓/✗). *Educational only* |

- **Auto-updating** — one command backfills from 1-Jan-2024 to today, then daily incremental.
- **Holiday-aware fetching** — uses the NSE trading calendar, retries late-published data,
  so there are no permanent gaps.

## 📊 Analysis (pure math — no indicators)

Returns (daily / cumulative / CAGR / mean), volatility (daily + annualized), Sharpe-type
ratio, max drawdown, beta (vs an equal-weighted ~210-stock market proxy ≈ NIFTY),
z-score, 52-week percentile, skewness, kurtosis, delivery %, — and for F&O: Put-Call
Ratio, total OI, OI change, futures premium/discount, max pain, and a strike-wise
"sum chain". **Every formula and its meaning is documented in [`GUIDE.md`](GUIDE.md).**

## 🛠️ Tech stack

Python · `requests` (NSE archive) · SQLite · `pandas` / `numpy` · `streamlit` · `plotly`

---

## 🚀 First-time setup (from a fresh clone)

The repo ships **code only** — no database. On first use you build `nse.db` yourself.

**1. Install Python 3.11+**
Download from [python.org](https://www.python.org/downloads/). On Windows, tick
**“Add Python to PATH”** during install.

**2. Get the code**
```bash
git clone https://github.com/pichash69-option-trader/-NSE-F-O-Stocks.git
cd ./-NSE-F-O-Stocks
```
No git? Use the green **Code → Download ZIP** button on GitHub, extract it, and open a
terminal in that folder.

**3. Install dependencies (once)**
```bash
pip install -r requirements.txt
```

**4. Build the database (first run — required)**
```bash
python run_daily.py
```
A fresh clone has no data, so this downloads everything from 1-Jan-2024 to today and
creates `nse.db`.
- Takes roughly **1–2 hours** (options across ~210 stocks are the large part) and builds
  a **~4 GB** file.
- Needs internet. **Resume-safe** — if it stops, just run it again to continue.

**5. Launch the dashboard**
```bash
streamlit run dashboard.py
```
Opens at **http://localhost:8501**. (On Windows you can also double-click `run_dashboard.bat`.)

### Everyday use
| Task | Command |
|------|---------|
| Open the dashboard | `streamlit run dashboard.py` |
| Stop it | `Ctrl + C` in the terminal |
| Update to the latest day | `python run_daily.py` (fast — only new days) |

> Only `run_daily.py` needs internet (to fetch data). Viewing the dashboard is fully local.

## 🔄 Daily auto-update (optional)

- **Windows:** schedule `run_daily.bat` after market close (~6:30 PM IST) via **Task
  Scheduler** — see [`task_scheduler_setup.txt`](task_scheduler_setup.txt).
- **Linux / AWS EC2:** [`setup_server.sh`](setup_server.sh) sets up a venv + cron
  (`@reboot` + daily) so the dashboard stays live and self-updates.

## 📁 Project structure

```
config.py                 # universe (FNO) + settings
db.py                     # SQLite schema + helpers
universe.py               # derives the ~210 F&O symbols from the latest bhavcopy
holidays.py               # NSE trading-holiday calendar (holiday-aware fetching)
fetch_data.py             # equity + delivery (incremental)
fetch_fno.py              # futures + options, all expiry/strike (incremental)
fetch_participant.py      # FII / DII / Pro / Client OI & volume (incremental)
analysis.py               # pure-math stats + F&O math (+ split/bonus adjustment)
cleanup_orphans.py        # remove exited-F&O stocks' orphaned F&O data + shrink DB
dashboard.py              # Streamlit UI (date-wise, QuantCalc-style theme)
.streamlit/config.toml    # premium dark theme (Outfit font, indigo/purple palette)
run_daily.py              # fetch (equity→F&O→participant) + analyse in one command
run_daily.bat             # Task Scheduler entry point (Windows)
run_dashboard.bat         # one-click dashboard launcher (Windows)
setup_server.sh           # Linux/AWS venv + cron setup
task_scheduler_setup.txt  # Windows daily-automation guide
GUIDE.md                  # full user guide — sections + every calculation explained
PLAN.md                   # design notes
```

## 🗄️ Data source & licensing

Data comes from NSE's public daily archive files (equity bhavcopy, security delivery /
MTO, F&O bhavcopy, and NSCCL participant reports). These are free for **personal and
educational** use. **Redistributing NSE data commercially (e.g. as a paid service)
requires a separate licence/agreement with NSE** — this repo does not grant any rights to
NSE's data. It ships **code only**; you generate your own `nse.db` locally.

## 📜 License

Code licensed under the [MIT License](LICENSE) © 2026 pichash69-option-trader.
NSE data is **not** covered by this licence and remains subject to NSE's terms.
