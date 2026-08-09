# -*- coding: utf-8 -*-
"""
dashboard.py — date-wise NSE dashboard (Streamlit), QuantCalc-style dark theme.

Run:  streamlit run dashboard.py

Sidebar navigation = 3 groups (top segmented control) → sub-tabs (radio):
  📈 Per-stock   : Equity / Cash · Analysis · Futures · Options
  🌐 Market-wide : Participant · Market (NIFTY/sectoral indices + VIX + sector perf)
  📊 All-stocks  : Math stats · Compare · Data health
"""
import os
import json

import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import db
import analysis
import charts
import backtest
import sectors
from render import (  # presentation layer (HTML tables + CSS)
    _fmt, CHAIN_LEGEND, _seg_metrics,
    render_chain, render_stock_table, render_overview_table,
    render_futures_table, render_compare, render_sector_table,
)
from config import NIFTY50

# Watchlist — saved locally (per-machine, gitignored).
WATCHLIST_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "watchlist.json")


def load_watchlist():
    try:
        with open(WATCHLIST_FILE, encoding="utf-8") as f:
            wl = json.load(f)
        return [s for s in wl if isinstance(s, str)]
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return []


def save_watchlist(wl):
    try:
        with open(WATCHLIST_FILE, "w", encoding="utf-8") as f:
            json.dump(list(dict.fromkeys(wl)), f)      # de-dup, keep order
    except OSError:
        pass



st.set_page_config(page_title="NSE F&O — date-wise", layout="wide")

# QuantCalc Pro-inspired layout & polish. Font/colors come from
# .streamlit/config.toml; this adds the layout the reference uses — sidebar
# navigation, live ticker bar, glass cards, gradient headers. Styling only —
# data & logic unchanged.
THEME_CSS = """
<style>
:root{
  --qc-indigo:#6366f1; --qc-purple:#a855f7; --qc-cyan:#06b6d4;
  --qc-success:#10b981; --qc-danger:#f43f5e;
  --qc-card:rgba(18,26,47,.60); --qc-border:rgba(255,255,255,.08);
  --qc-text2:#9ca3af; --qc-muted:#6b7280;
}
/* radial glow on the page like the reference content-body */
[data-testid="stAppViewContainer"] > .main{
  background:radial-gradient(circle at top right,rgba(99,102,241,.05),transparent 60%);}
[data-testid="stHeader"]{background:transparent;}
.block-container{padding-top:3.2rem;}

/* ---------- Sidebar: logo + nav menu (QuantCalc style) ---------- */
[data-testid="stSidebar"]{border-right:1px solid var(--qc-border);}
.qc-logo{display:flex;align-items:center;gap:12px;margin:2px 0 22px;padding:2px;}
.qc-logo .ico{width:42px;height:42px;border-radius:12px;flex-shrink:0;
  background:linear-gradient(135deg,var(--qc-indigo),var(--qc-purple));
  display:flex;align-items:center;justify-content:center;color:#fff;
  box-shadow:0 4px 14px rgba(99,102,241,.4);font-size:22px;}
.qc-logo .txt{font-weight:800;font-size:18px;letter-spacing:.4px;line-height:1;}
.qc-logo .pill{font-size:10px;font-weight:800;letter-spacing:.8px;color:#fff;
  background:linear-gradient(90deg,var(--qc-indigo),var(--qc-purple));
  padding:2px 6px;border-radius:5px;margin-left:6px;vertical-align:middle;}
.qc-logo .sub{color:var(--qc-muted);font-size:11px;font-weight:500;margin-top:3px;}

/* Turn ONLY the nav radio (key="navmenu") into QuantCalc menu-items;
   the days radio (7/20/50/All) keeps normal Streamlit styling. */
[class*="st-key-navmenu"] div[role="radiogroup"]{gap:6px;}
[class*="st-key-navmenu"] label[data-testid="stRadioOption"]{
  display:flex;align-items:center;width:100%;
  padding:10px 14px;border-radius:10px;border:1px solid transparent;
  color:var(--qc-text2);cursor:pointer;transition:all .2s;}
[class*="st-key-navmenu"] label[data-testid="stRadioOption"] p{
  color:inherit;font-weight:600;font-size:.95rem;}
[class*="st-key-navmenu"] label[data-testid="stRadioOption"]:hover{
  color:#f3f4f6;background:rgba(255,255,255,.03);border-color:rgba(255,255,255,.05);}
/* hide the actual radio circle — keep only the label text */
[class*="st-key-navmenu"] label[data-testid="stRadioOption"] > div > div > div:first-child{
  display:none;}
/* active item — indigo glow (Streamlit marks it data-selected) */
[class*="st-key-navmenu"] label[data-testid="stRadioOption"][data-selected="true"]{
  color:#f3f4f6;background:rgba(99,102,241,.15);
  border-color:rgba(99,102,241,.35);box-shadow:0 2px 8px rgba(0,0,0,.15);}
/* ---- group selector (navgroup): 3 stacked category pills, distinct look ---- */
[class*="st-key-navgroup"] div[role="radiogroup"]{gap:5px;margin-bottom:8px;}
[class*="st-key-navgroup"] label[data-testid="stRadioOption"]{
  display:flex;align-items:center;width:100%;padding:9px 13px;border-radius:9px;
  border:1px solid rgba(255,255,255,.06);color:var(--qc-text2);cursor:pointer;
  transition:all .2s;text-transform:uppercase;letter-spacing:.4px;}
[class*="st-key-navgroup"] label[data-testid="stRadioOption"] p{
  color:inherit;font-weight:700;font-size:.8rem;}
[class*="st-key-navgroup"] label[data-testid="stRadioOption"] > div > div > div:first-child{
  display:none;}
[class*="st-key-navgroup"] label[data-testid="stRadioOption"]:hover{
  color:#f3f4f6;background:rgba(255,255,255,.04);}
[class*="st-key-navgroup"] label[data-testid="stRadioOption"][data-selected="true"]{
  color:#fff;border-color:rgba(99,102,241,.5);
  background:linear-gradient(90deg,rgba(99,102,241,.28),rgba(99,102,241,.10));}
/* sub-tabs slightly indented under the active group */
[class*="st-key-navmenu"] div[role="radiogroup"]{padding-left:8px;}
.qc-foot{margin-top:14px;padding-top:16px;border-top:1px solid var(--qc-border);
  color:var(--qc-muted);font-size:12px;}
.qc-foot .live{margin-top:8px;display:inline-block;background:rgba(16,185,129,.1);
  color:var(--qc-success);font-weight:600;padding:5px 11px;border-radius:6px;font-size:11px;}

/* ---------- Live ticker bar ---------- */
.qc-ticker{display:flex;align-items:center;gap:16px;background:#0c1020;
  border:1px solid var(--qc-border);border-radius:12px;padding:8px 14px;
  margin-bottom:8px;overflow-x:auto;white-space:nowrap;}
.qc-ticker:last-of-type{margin-bottom:16px;}
.qc-ticker .lbl{flex-shrink:0;color:#fff;font-weight:700;font-size:10px;
  letter-spacing:.6px;padding:3px 9px;border-radius:5px;}
.qc-ticker .lbl-up{background:linear-gradient(135deg,var(--qc-success),var(--qc-cyan));
  box-shadow:0 2px 8px rgba(16,185,129,.25);}
.qc-ticker .lbl-dn{background:linear-gradient(135deg,var(--qc-danger),var(--qc-purple));
  box-shadow:0 2px 8px rgba(244,63,94,.25);}
.qc-ticker .it{color:var(--qc-text2);font-size:12.5px;font-weight:500;flex-shrink:0;}
.qc-ticker .it b{color:#f3f4f6;font-weight:600;margin:0 5px;}
.qc-ticker .up{color:var(--qc-success);background:rgba(16,185,129,.1);
  padding:1px 6px;border-radius:4px;font-weight:700;font-size:11px;}
.qc-ticker .dn{color:var(--qc-danger);background:rgba(244,63,94,.1);
  padding:1px 6px;border-radius:4px;font-weight:700;font-size:11px;}

/* ---------- Headers / cards ---------- */
.qc-title{font-weight:800;font-size:29px;letter-spacing:-.5px;line-height:1.15;margin:0;
  background:linear-gradient(90deg,#f3f4f6,#99a5ff);
  -webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent;}
.qc-sub{color:var(--qc-text2);font-size:14px;margin:4px 0 6px;}
[data-testid="stMetric"]{
  background:var(--qc-card);border:1px solid var(--qc-border);
  border-radius:16px;padding:12px 14px;backdrop-filter:blur(12px);
  box-shadow:0 1px 0 rgba(255,255,255,.03) inset,0 8px 24px -12px rgba(0,0,0,.6);}
[data-testid="stMetric"]:hover{border-color:rgba(99,102,241,.45);}
[data-testid="stMetricLabel"] p{color:var(--qc-text2);font-weight:500;font-size:.78rem;
  text-transform:uppercase;letter-spacing:.4px;}
[data-testid="stMetricValue"]{font-size:1.55rem;line-height:1.2;font-weight:700;}
/* Section sub-headers get an accent bar */
h4{border-left:3px solid var(--qc-indigo);padding-left:10px;}
hr{border-color:var(--qc-border);}
</style>
"""
st.markdown(THEME_CSS, unsafe_allow_html=True)

# Help content — shown from the "❓ How to use" popover in the sidebar.
HELP_MD = """
## 👋 Dashboard kaise use karein

Ye dashboard **F&O stocks (~210)** ka NSE data **date-wise** (din-b-din) dikhata hai —
equity + futures + options + FII/DII, sab. Data seedha NSE se, roz auto-update. Saari
analysis **pure maths / stats** hai — **koi technical indicator nahi**.

> ⚠️ **Educational / research** tool hai — investment advice **nahi**.

---

### 🧭 Shuru kaise karein
1. **Left sidebar** me se ek **stock** choose karo (jaise RELIANCE).
2. **"Kitne din dekhne hain"** — 7 / 20 / 50 / All chuno.
3. Sidebar ke **menu** (6 sections) me data dekho (date-wale sections me **slider** se din badlo).

Upar **ticker** = us din ke **Top 5 gainers** (green) + **Top 5 losers** (red), EOD data se.

---

## 🗂️ Sections (6)

**📈 Equity / Cash** — Selected stock ka cash-market data, din-b-din: OHLC, **Chg%**
(green/red pill), **Volume & Delivery%** (bars), Turnover ₹Cr, Trades. Neeche **candle
chart** (hover = detail). 🟢 up din · 🔴 down din.

**🔮 Futures** — Teeno expiry (near/next/far) ka total + changes: OHLC, Settle,
**Premium** (future − spot), **OI + Chg OI**, Σ TOTAL. Plus estimated participant split.

**⛓️ Options** — **Σ Sum chain** (teeno expiry ka strike-wise total) + har expiry ka
apna chain (OHLC/Settle/Turnover chain ke andar hi). 🟧 CALLS ITM · 🟥 PUTS ITM ·
🔵 **ATM** row · ChgOI green = OI add, red = cut. **Strikes ± slider** + **max pain**.

**🏦 Participant** — FII / DII / Pro / Client ka F&O positioning (OI + Volume).
**Net = Long − Short**: 🟢 net long (bullish), 🔴 net short (bearish). Ye **market-wide** hai.

**📊 Math stats** — Saare ~210 stocks ka computed math ek table me. **Sort by** se compare
karo (+ **1D/1W/1M returns**). Symbol + header pinned; right scroll = saare columns.

**🌐 Market** — NIFTY 50 / BANK / FINNIFTY charts + India VIX + broad & sectoral index
table (official, 1D/1W/1M) + humare F&O stocks ka **sector performance** (avg 1D/1W/1M/1Y)
+ drill-down + day-by-day sector scrub.

**⚖️ Compare** — 2–5 stocks side-by-side, saare metrics ek saath.

**🩺 Data health** — pipeline status: latest dates, gaps, row counts, current F&O ban list.

---

## 🧮 Calculations — formula + matlab

Sab **split/bonus-adjusted**. Daily return `r = aaj close / kal close − 1`.

**Returns**

| Metric | Formula | Matlab |
|---|---|---|
| Daily return | `close_today/close_yest − 1` | Us din ka move |
| Cumulative return | `close_last/close_first − 1` | Poore period ka total |
| CAGR | `(last/first)^(365/days) − 1` | Per-year (annualized) growth |
| Mean return | daily returns ka average | Rozana average move |

**Risk / volatility**

| Metric | Formula | Matlab |
|---|---|---|
| Volatility | daily returns ka **std dev** | Roz kitna up-down (risk) |
| Ann. volatility | `daily vol × √252` | Saal-bhar swing %. **High = risky** |
| Sharpe | `mean return / vol` (rf=0) | Risk-adjusted return. Zyada = better |
| Max drawdown | `min(close/peak − 1)` | Peak se sabse bada gir (worst case) |
| Beta | `cov(stock,mkt)/var(mkt)` | β>1 = market se zyada swingy (mkt = ~210 stocks avg = NIFTY proxy) |

**Statistics**

| Metric | Formula | Matlab |
|---|---|---|
| Z-score | `(last − avg)/std` (close) | Price average se kitne SD door. +2 mehenga, −2 sasta (stat only) |
| 52-week %ile | 252 din me kitne % din close aaj se neeche | 90 = 52w-high paas · 10 = 52w-low paas |
| Skew | returns ka skewness | +ve = up moves zyada, −ve = crash-prone |
| Kurtosis | returns ka kurtosis | High = extreme moves (fat tails) |
| Delivery % | `deliv qty/total qty ×100` | High = real buying (intraday nahi) |

**F&O math**

| Metric | Formula | Matlab |
|---|---|---|
| PCR | `PE OI / CE OI` (total) | >1 puts zyada · <1 calls zyada (sentiment) |
| Max pain | writer payout min wala strike | Expiry price aksar yahan khinchti (theory) |
| Futures premium | `near future close − spot` | +ve bullish lean · −ve bearish lean |
| Total OI | futures OI sum (all expiry) | Kitne contracts open |
| OI change | Chg OI sum (all expiry) | Naye positions (+) ya band (−) |

**OI Buildup** (price + OI change)

| Price | OI | Buildup | Matlab |
|---|---|---|---|
| 🔼 | 🔼 | **Long Buildup** | Naye buyers — bullish |
| 🔽 | 🔼 | **Short Buildup** | Naye sellers — bearish |
| 🔼 | 🔽 | **Short Covering** | Sellers exit — up move |
| 🔽 | 🔽 | **Long Unwinding** | Buyers exit — weakness |

---

## ⚠️ Notes

- **Split/bonus**: NSE prev_close adjust nahi hota; dashboard auto-detect karke adjust
  karta hai (fake −90% move hataata). Ticker me `|move|>30%` drop hote hain.
- **Sharpe** yahan simple `mean/std` (daily, rf=0) — thumb-rule comparison ke liye.

## 🔄 Data update
Har trading din market close ke baad (~**9 PM IST**) naya data auto-add. Weekend/holiday
skip (late-publish par retry — koi gap nahi). Latest din upar.

**Bas! Stock chuno, din chuno, explore karo.** 🚀

*(Poori detailed guide project folder me `GUIDE.md` file me hai.)*
"""


# --------------------------------------------------------------------------- #
# Data helpers (cached)
# --------------------------------------------------------------------------- #
@st.cache_data(ttl=300)
def q(sql, params=()):
    conn = db.connect()
    try:
        return pd.read_sql_query(sql, conn, params=params)
    finally:
        conn.close()


def date_slider(label, dates_desc, key, window=60, default=None):
    """Slider over the most recent `window` trading days (default = latest, or
    `default` if given & in range). Slide left = older."""
    recent = list(reversed(dates_desc[:window]))     # ascending, latest last
    if not recent:
        return None
    if len(recent) == 1:
        st.caption(f"{label}: {recent[0]}")
        return recent[0]
    val = default if default in recent else recent[-1]
    return st.select_slider(label, options=recent, value=val, key=key)


@st.cache_data(ttl=300)
def all_symbols():
    """Stock list for the dropdown — whatever is actually in the DB (NIFTY 50
    or full F&O universe), sorted. Falls back to the config list if empty."""
    df = q("SELECT DISTINCT symbol FROM prices ORDER BY symbol")
    return df["symbol"].tolist() if not df.empty else NIFTY50


@st.cache_data(ttl=300)
def corp_factors():
    """Exact split/bonus adjustment factors {symbol: {ex_date: factor}} from the
    corp_actions table — used to back-adjust prices precisely instead of guessing."""
    return analysis.load_corp_factors()


def stock_history(symbol):
    df = q("SELECT date,open,high,low,close,prev_close,settle,volume,turnover,"
           "num_trades,deliv_qty,deliv_pct FROM prices WHERE symbol=? ORDER BY date",
           (symbol,))
    if df.empty:
        return df
    df = df.sort_values("date").reset_index(drop=True)
    raw_first_close = float(df.loc[0, "close"])          # keep RAW before adjusting
    # Split/bonus-adjust OHLC so a split day (e.g. NESTLEIND 1:10) doesn't show a
    # fake -90% crash in the table/chart. chg% then comes from adjusted close.
    df = analysis.adjust_ohlc(df, factors=corp_factors().get(symbol, {}))
    df["chg_pct"] = df["close"].pct_change() * 100
    # first day has no prior in-series close -> use RAW close vs RAW prev_close
    # (both raw = consistent, correct even for split stocks).
    pc = df.loc[0, "prev_close"]
    if pd.notna(pc) and pc:
        df.loc[0, "chg_pct"] = (raw_first_close / pc - 1) * 100
    return df


def fno_dates(symbol):
    return q("SELECT DISTINCT date FROM options WHERE symbol=? ORDER BY date DESC",
             (symbol,))["date"].tolist()


@st.cache_data(ttl=300)
def participant_net_series():
    """Per-day total NET (Long − Short, OI) for each participant across all dates.
    Returns a date-indexed frame with FII/DII/Pro/Client columns."""
    df = q("""SELECT date, client_type, total_long, total_short
              FROM participant WHERE metric='oi'
              AND client_type IN ('FII','DII','Pro','Client') ORDER BY date""")
    if df.empty:
        return df
    df["net"] = df["total_long"] - df["total_short"]
    return df.pivot_table(index="date", columns="client_type", values="net")


@st.cache_data(ttl=300)
def adjusted_closes():
    """Split/bonus-adjusted daily close matrix (date × symbol), all stocks.
    Shared base for every return / volatility computation (computed once)."""
    px = q("SELECT symbol, date, close FROM prices")
    if px.empty:
        return pd.DataFrame()
    return analysis.adjust_for_splits(
        px.pivot(index="date", columns="symbol", values="close").sort_index(),
        corp_factors())


@st.cache_data(ttl=300)
def return_windows():
    """Per-stock return % over 1W/1M/3M/6M/1Y + Sortino + 5% VaR, from the
    split-adjusted close matrix. Index = symbol. (Calmar is derived in the
    Math-stats view from cagr / |max_drawdown|.)"""
    cols = ["ret_1w", "ret_1m", "ret_3m", "ret_6m", "ret_1y", "sortino", "var5"]
    wide = adjusted_closes()
    if wide.empty:
        return pd.DataFrame(columns=cols)
    rets = wide.pct_change()
    n = len(wide)

    def wret(k):
        if n <= k:
            return pd.Series(index=wide.columns, dtype=float)
        return (wide.iloc[-1] / wide.iloc[-1 - k] - 1) * 100

    downside = rets[rets < 0].std()                       # std of negative days only
    return pd.DataFrame({
        "ret_1w": wret(5), "ret_1m": wret(20), "ret_3m": wret(63),
        "ret_6m": wret(126), "ret_1y": wret(252),
        "sortino": rets.mean() / downside,                # mean / downside deviation
        "var5": -rets.quantile(0.05) * 100,               # 5% historical VaR (loss %)
    })


@st.cache_data(ttl=300)
def vix_series():
    """India VIX daily series (market volatility / fear gauge)."""
    return q("SELECT date, open, high, low, close, chg_pct FROM vix ORDER BY date")


# Curated index lists for the Market tab (all verified present in DB).
BROAD_IX = ("Nifty 50", "Nifty Next 50", "Nifty 500", "Nifty Midcap Select",
            "Nifty Bank", "Nifty Financial Services")
SECTORAL_IX = ("Nifty Auto", "Nifty IT", "Nifty Pharma", "Nifty FMCG", "Nifty Metal",
               "Nifty Realty", "Nifty Energy", "Nifty PSU Bank", "Nifty Private Bank",
               "Nifty Media", "Nifty Consumer Durables", "Nifty Oil & Gas",
               "Nifty Healthcare Index", "Nifty Infrastructure", "Nifty Commodities")


@st.cache_data(ttl=300)
def index_series(name):
    """Daily close + chg% for one index."""
    return q("SELECT date, close, chg_pct FROM indices WHERE name=? ORDER BY date", (name,))


@st.cache_data(ttl=300)
def index_snapshot(names):
    """Latest close + 1D/1W/1M % change for a set of indices (rows in input order)."""
    ph = ",".join("?" * len(names))
    df = q(f"SELECT date, name, close FROM indices WHERE name IN ({ph}) ORDER BY date",
           tuple(names))
    if df.empty:
        return pd.DataFrame(columns=["Index", "Close", "1D %", "1W %", "1M %"])
    wide = df.pivot(index="date", columns="name", values="close").sort_index()

    def chg(k):
        if len(wide) <= k:
            return pd.Series(index=wide.columns, dtype=float)
        return (wide.iloc[-1] / wide.iloc[-1 - k] - 1) * 100

    out = pd.DataFrame({"Close": wide.iloc[-1].round(1), "1D %": chg(1).round(2),
                        "1W %": chg(5).round(2), "1M %": chg(20).round(2)})
    out = out.reindex([n for n in names if n in out.index])
    out.index.name = "Index"
    return out.reset_index()


@st.cache_data(ttl=300)
def sector_daily_returns():
    """Per (date, sector) average 1-day return % — split-adjusted. Long frame:
    columns date, sector, n, avg_ret. Powers the day-by-day sector view."""
    wide = adjusted_closes()
    if wide.empty:
        return pd.DataFrame(columns=["date", "sector", "n", "avg_ret"])
    rets = wide.pct_change() * 100
    long = rets.stack().reset_index()
    long.columns = ["date", "symbol", "ret"]
    long["sector"] = long["symbol"].map(sectors.sector_of)
    return (long.groupby(["date", "sector"])
                .agg(n=("ret", "count"), avg_ret=("ret", "mean")).reset_index())



@st.cache_data(ttl=300)
def ticker_html():
    """Two-line movers ticker from the latest EOD NSE data:
    line 1 = top-5 gainers, line 2 = top-5 losers (of that day)."""
    latest = q("SELECT MAX(date) d FROM prices")["d"].iloc[0]
    if not latest:
        return ""
    df = q("SELECT symbol, close, prev_close FROM prices WHERE date=?", (latest,))
    df = df[(df["prev_close"] > 0) & df["close"].notna()].copy()
    if df.empty:
        return ""
    df["chg"] = (df["close"] / df["prev_close"] - 1) * 100
    # NSE prev_close isn't split/bonus-adjusted, so a split day shows a fake huge
    # move — drop |chg| > 30% so those artifacts don't hijack the movers list.
    df = df[df["chg"].abs() <= 30]
    ups = df.sort_values("chg", ascending=False).head(5)
    dns = df.sort_values("chg", ascending=True).head(5)

    def row(label, lbl_cls, rows, cls):
        items = [f'<span class="lbl {lbl_cls}">{label}</span>']
        for _, r in rows.iterrows():
            items.append(f'<span class="it">{r["symbol"]}<b>{r["close"]:,.1f}</b>'
                         f'<span class="{cls}">{r["chg"]:+.2f}%</span></span>')
        return '<div class="qc-ticker">' + "".join(items) + "</div>"

    return (row(f"EOD · {latest}  ▲ TOP GAINERS", "lbl-up", ups, "up")
            + row("▼ TOP LOSERS", "lbl-dn", dns, "dn"))


# --------------------------------------------------------------------------- #
# Analysis tab — one stock, day-by-day, with plain-language interpretation
# --------------------------------------------------------------------------- #
@st.cache_data(ttl=300)
def stock_daily(symbol):
    """One row per date for a stock — price, delivery, futures OI/premium, PCR —
    aligned by date. Powers the day-by-day Analysis tab."""
    px = q("SELECT date, open, high, low, close, prev_close, volume, turnover, "
           "num_trades, deliv_pct FROM prices WHERE symbol=? ORDER BY date", (symbol,))
    if px.empty:
        return px
    d = px.set_index("date")
    d["chg_pct"] = (d["close"] / d["prev_close"] - 1) * 100
    d["gap_pct"] = (d["open"] - d["prev_close"]) / d["prev_close"] * 100
    d["range_pct"] = (d["high"] - d["low"]) / d["prev_close"] * 100

    fut = q("SELECT date, expiry, close, oi, chg_oi FROM futures WHERE symbol=? "
            "ORDER BY date, expiry", (symbol,))
    if not fut.empty:
        g = fut.groupby("date")
        d["fut_oi"] = g["oi"].sum()
        d["fut_chg_oi"] = g["chg_oi"].sum()
        near = fut.sort_values("expiry").groupby("date")["close"].first()  # near-month close
        d["prem_pct"] = (near - d["close"]) / d["close"] * 100

    opt = q("SELECT date, opt_type, SUM(oi) oi FROM options WHERE symbol=? "
            "GROUP BY date, opt_type", (symbol,))
    if not opt.empty:
        p = opt.pivot(index="date", columns="opt_type", values="oi")
        if "PE" in p.columns and "CE" in p.columns:
            d["pcr"] = p["PE"] / p["CE"]
    return d


@st.cache_data(ttl=300)
def cached_max_pain(symbol, date, expiry):
    """Cached wrapper — max_pain hits the 17M-row options table + an O(strikes²)
    loop, so cache it (else every rerun/toggle recomputes)."""
    return analysis.max_pain(symbol, date, expiry)


@st.cache_data(ttl=300)
def cached_sum_chain(symbol, date):
    """Cached wrapper — sum_chain reads all strikes/expiries for a day."""
    return analysis.sum_chain(symbol, date)


@st.cache_data(ttl=1800, show_spinner=False)
def cached_backtest(strategy):
    """Run + cache a full-universe backtest (heavy: ~1-2 min first time)."""
    if strategy == "Momentum buying":
        return backtest.run()
    return None


@st.cache_data(ttl=300)
def nifty_daily():
    """Nifty 50 daily % change, indexed by date (for relative-strength reads)."""
    ix = q("SELECT date, chg_pct FROM indices WHERE name='Nifty 50' ORDER BY date")
    return ix.set_index("date")["chg_pct"] if not ix.empty else pd.Series(dtype=float)


_EMO = {"up": "🟢", "dn": "🔴", "neu": "🟡"}


def _read_move(chg):
    if pd.isna(chg):
        return ("—", "neu")
    mag = "Bada" if abs(chg) >= 3 else "Halka" if abs(chg) < 1 else "Theek-thaak"
    return ((f"{mag} up move — buyers haavi", "up") if chg >= 0
            else (f"{mag} down move — sellers haavi", "dn"))


def _read_deliv(deliv, dd):
    if pd.isna(deliv):
        return ("—", "neu")
    if deliv >= 60:
        base, c = "High delivery — real conviction (log actually shares le ja rahe)", "up"
    elif deliv >= 40:
        base, c = "Moderate delivery", "neu"
    else:
        base, c = "Low delivery — zyada intraday churn / speculation", "dn"
    if pd.notna(dd):
        base += f" · kal se {'badhi' if dd > 2 else 'ghati' if dd < -2 else 'flat'}"
    return (base, c)


def _read_buildup(chg, doi):
    if pd.isna(chg) or pd.isna(doi):
        return ("—", "neu")
    up = chg >= 0
    if up and doi > 0:
        return ("Long buildup — naye longs ban rahe, bullish conviction", "up")
    if up and doi <= 0:
        return ("Short covering — shorts exit (price↑ OI↓), bullish par weaker", "up")
    if not up and doi > 0:
        return ("Short buildup — naye shorts ban rahe, bearish conviction", "dn")
    return ("Long unwinding — longs exit (price↓ OI↓), bearish par weaker", "dn")


def _read_prem(prem):
    if pd.isna(prem):
        return ("—", "neu")
    if prem > 0.3:
        return (f"Premium ({prem:+.2f}%) — future spot se upar, bullish / carry", "up")
    if prem < -0.3:
        return (f"Discount ({prem:+.2f}%) — future spot se neeche, bearish lean", "dn")
    return (f"~Flat ({prem:+.2f}%) — future ≈ spot, neutral", "neu")


def _read_pcr(pcr, dp):
    if pd.isna(pcr):
        return ("—", "neu")
    lvl = ("High (puts > calls) — bearish hedging ya contrarian-bullish" if pcr > 1.2
           else "Low (calls > puts) — bullish tilt ya call-writing" if pcr < 0.7
           else "Balanced (puts ≈ calls)")
    if pd.notna(dp):
        lvl += f" · kal se {'put-OI badhi' if dp > 0.05 else 'call-OI badhi' if dp < -0.05 else 'flat'}"
    return (f"PCR {pcr:.2f} — {lvl}", "neu")


def _read_gap(gap, rng):
    if pd.isna(gap):
        return ("—", "neu")
    if abs(gap) < 0.3:
        base, c = "Flat open (koi gap nahi)", "neu"
    elif gap >= 0.3:
        base, c = f"Gap-up {gap:+.2f}% — positive overnight sentiment", "up"
    else:
        base, c = f"Gap-down {gap:+.2f}% — negative overnight sentiment", "dn"
    if pd.notna(rng):
        base += f" · din ka range {rng:.1f}%"
    return (base, c)


def _read_relstr(schg, nchg):
    if pd.isna(schg) or pd.isna(nchg):
        return ("—", "neu")
    diff = schg - nchg
    tail = f"(stock {schg:+.2f}% vs NIFTY {nchg:+.2f}%)"
    if diff > 0.3:
        return (f"Outperform — market se aage {tail} · relative strength", "up")
    if diff < -0.3:
        return (f"Underperform — market se piche {tail} · weakness", "dn")
    return (f"Market ke saath in-line {tail}", "neu")


def _read_sector(schg, savg, sname):
    if pd.isna(savg):
        return ("—", "neu")
    base = f"{sname}: sector avg {savg:+.2f}%"
    if pd.isna(schg):
        return (base, "neu")
    same_dir = (schg >= 0) == (savg >= 0)
    if abs(savg) >= 0.5 and same_dir:
        return (base + " — sector-led move (poora sector isi taraf)", "up" if savg >= 0 else "dn")
    if abs(schg - savg) >= 1.0:
        return (base + " — stock-specific (sector se alag chala, apni news)", "neu")
    return (base, "neu")


def _read_maxpain(price, mp):
    if mp is None or pd.isna(price) or not mp:
        return ("—", "neu")
    diff = (price - mp) / mp * 100
    tail = f"(max pain ₹{mp:,.0f}, price {diff:+.1f}%)"
    if diff > 1:
        return (f"Price max-pain se **upar** {tail} — expiry ke paas neeche pull ka jhukav", "dn")
    if diff < -1:
        return (f"Price max-pain se **neeche** {tail} — expiry ke paas upar pull ka jhukav", "up")
    return (f"Price ~max-pain pe pinned {tail}", "neu")


def _read_overall(chg, doi, deliv):
    sig = 0
    if pd.notna(chg):
        sig += 1 if chg >= 0 else -1
        if pd.notna(doi):                    # buildup adds conviction
            if chg >= 0 and doi > 0:
                sig += 1
            elif chg < 0 and doi > 0:
                sig -= 1
    if pd.notna(deliv):
        sig += 1 if deliv >= 55 else -1 if deliv < 40 else 0
    if sig >= 2:
        return ("🟢 Overall bullish lean", "up")
    if sig <= -2:
        return ("🔴 Overall bearish lean", "dn")
    return ("🟡 Mixed / neutral din", "neu")


def _trend5(dd, key, sel, n=5):
    """Recent multi-day direction of `key` ending at `sel` (1-day change is noisy;
    a multi-day streak is more reliable). Returns e.g. '↑ 5d rising'."""
    if key not in dd.columns:
        return "—"
    idx = list(dd.index)
    win = dd[key].iloc[max(0, idx.index(sel) - n + 1): idx.index(sel) + 1].dropna()
    if len(win) < 3:
        return "—"
    net = win.iloc[-1] - win.iloc[0]
    ups, downs, d = int((win.diff() > 0).sum()), int((win.diff() < 0).sum()), len(win)
    if ups > downs and net > 0:
        return f"↑ {d}d rising"
    if downs > ups and net < 0:
        return f"↓ {d}d falling"
    return f"→ {d}d flat/mixed"


# --------------------------------------------------------------------------- #
# Sidebar — QuantCalc-style logo + navigation menu + stock controls
# --------------------------------------------------------------------------- #
GROUPS = {
    "📈 Per-stock": ["📈 Equity / Cash", "📉 Line chart", "🔬 Analysis", "🔮 Futures", "⛓️ Options"],
    "🌐 Market-wide": ["🏦 Participant", "🌐 Market"],
    "📊 All-stocks": ["📊 Math stats", "⚖️ Compare", "🎯 Backtest", "🩺 Data health"],
}
GROUP_KEYS = list(GROUPS)

with st.sidebar:
    st.markdown(
        '<div class="qc-logo"><div class="ico">📈</div>'
        '<div><div class="txt">NSE F&amp;O<span class="pill">PRO</span></div>'
        '<div class="sub">date-wise analytics</div></div></div>',
        unsafe_allow_html=True)

    # Stock controls — watchlist ⭐ pinned to top of the dropdown
    _wl = load_watchlist()
    _all = all_symbols()
    _starred = [s for s in _wl if s in _all]
    _opts = _starred + [s for s in _all if s not in _starred]
    symbol = st.selectbox("Stock", _opts, index=0, key="stock",
                          format_func=lambda s: f"⭐ {s}" if s in _wl else s)
    wc1, wc2 = st.columns([3, 2])
    if symbol in _wl:
        if wc1.button("★ Remove from watchlist", use_container_width=True):
            _wl.remove(symbol); save_watchlist(_wl); st.rerun()
    else:
        if wc1.button("☆ Add to watchlist", use_container_width=True):
            save_watchlist(_wl + [symbol]); st.rerun()
    wc2.caption(f"⭐ {len(_starred)} saved" if _starred else "no ⭐ yet")

    lookback = st.radio("Kitne din dekhne hain", [7, 20, 50, "All"], index=1,
                        horizontal=True)

    st.markdown('<div style="height:8px"></div>', unsafe_allow_html=True)
    group = st.radio("Section group", GROUP_KEYS, index=0,
                     label_visibility="collapsed", key="navgroup")
    gi = GROUP_KEYS.index(group)
    section = st.radio("Navigation", GROUPS[group], index=0,
                       label_visibility="collapsed", key=f"navmenu{gi}")

    with st.popover("❓ How to use", use_container_width=True):
        st.markdown(HELP_MD)

    st.markdown(
        '<div class="qc-foot">Designed for traders &amp; researchers'
        '<div class="live">● NSE data · auto-updated</div></div>',
        unsafe_allow_html=True)

# --------------------------------------------------------------------------- #
# Main content — live ticker (page title removed; each section has its own header)
# --------------------------------------------------------------------------- #
st.markdown(ticker_html(), unsafe_allow_html=True)

# =========================================================================== #
# TAB 1 — date-wise stock view
# =========================================================================== #
if section == "📈 Equity / Cash":
    hist = stock_history(symbol)
    if hist.empty:
        st.warning(f"{symbol}: koi data nahi. Pehle fetch_data / fetch_fno chalao.")
    else:
        view = hist if lookback == "All" else hist.tail(int(lookback))
        latest = view.iloc[-1]

        st.subheader(f"{symbol} — date-wise")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Close", f"{latest['close']:.2f}",
                  f"{latest['chg_pct']:+.2f}%")
        c2.metric("Volume", f"{latest['volume']:,.0f}")
        c3.metric("Delivery %", f"{latest['deliv_pct']:.1f}"
                  if pd.notna(latest['deliv_pct']) else "—")
        c4.metric("Din (range me)", f"{len(view)}")

        # --- F&O ban flag (MWPL >95% = no fresh F&O positions) ---
        bstats = q("SELECT COUNT(*) n, MAX(date) last FROM secban WHERE symbol=?", (symbol,))
        bn = int(bstats["n"].iloc[0])
        blast = bstats["last"].iloc[0]
        latest_ok = q("SELECT MAX(date) d FROM ingest_log "
                      "WHERE dataset='secban' AND status='ok'")["d"].iloc[0]
        if blast and latest_ok and blast == latest_ok:
            st.error(f"🚫 **{symbol} abhi F&O BAN me hai** ({blast}) — fresh F&O "
                     "positions allowed nahi (open interest MWPL ka 95% cross).")
        elif bn:
            st.caption(f"🚫 F&O ban history: **{bn} din** ban me raha (aakhri: {blast}). "
                       "Zyada ban days = high-OI/volatile risk flag.")

        # --- 1. Stock all-data table (glanceable, latest din upar) ---
        st.markdown("#### 1 · Stock — all data (din-b-din)")
        st.markdown(render_stock_table(view), unsafe_allow_html=True)

        # --- Day range (candle) chart — hover par saari details ---
        st.markdown("**Day range (candle)** — kisi bhi candle par hover karo")
        cv = view.copy()
        hover = [
            (f"{d}<br>Open {o:.1f} · High {h:.1f}<br>Low {l:.1f} · Close {c:.1f}"
             f"<br>Chg {ch:+.2f}%<br>Volume {_fmt(vol)}"
             f"<br>Turnover ₹{tv/1e7:,.1f}Cr · Trades {_fmt(nt)}"
             + (f"<br>Delivery {dp:.1f}%" if pd.notna(dp) else ""))
            for d, o, h, l, c, ch, vol, tv, nt, dp in zip(
                cv["date"], cv["open"], cv["high"], cv["low"], cv["close"],
                cv["chg_pct"], cv["volume"], cv["turnover"], cv["num_trades"],
                cv["deliv_pct"])]
        candle = go.Candlestick(
            x=cv["date"], open=cv["open"], high=cv["high"],
            low=cv["low"], close=cv["close"],
            increasing_line_color="#10b981", decreasing_line_color="#f43f5e",
            increasing_fillcolor="#10b981", decreasing_fillcolor="#f43f5e",
            text=hover, hoverinfo="text", name="")
        fig = go.Figure(candle)
        fig.update_layout(height=380, margin=dict(l=0, r=0, t=10, b=0),
                          xaxis_rangeslider_visible=False,
                          xaxis_title=None, yaxis_title="Price")
        # Category axis: trading-day candles sit next to each other (no
        # weekend/holiday gaps). Thin out labels so they stay readable.
        step = max(1, len(cv) // 10)
        fig.update_xaxes(type="category",
                         tickmode="array",
                         tickvals=list(cv["date"])[::step])
        st.plotly_chart(fig, width="stretch")

        # --- Bulk / block deals for this stock (institutional activity) ---
        deals = q("SELECT date, deal_type, client, buy_sell, qty, price "
                  "FROM deals WHERE symbol=? ORDER BY date DESC LIMIT 200", (symbol,))
        if not deals.empty:
            deals["Value ₹Cr"] = (deals["qty"] * deals["price"] / 1e7).round(2)
            nbuy = int((deals["buy_sell"].str.upper() == "BUY").sum())
            nsell = int((deals["buy_sell"].str.upper() == "SELL").sum())
            with st.expander(f"🏦 Bulk / block deals — {len(deals)} "
                             f"(BUY {nbuy} · SELL {nsell}) · bade disclosed trades"):
                show = deals.rename(columns={"date": "Date", "deal_type": "Type",
                                             "client": "Client", "buy_sell": "Side",
                                             "qty": "Qty", "price": "Price"})
                st.dataframe(show[["Date", "Type", "Side", "Client", "Qty", "Price", "Value ₹Cr"]],
                             hide_index=True, width="stretch")
        else:
            st.caption("🏦 Is stock ke koi bulk/block deals record me nahi (is period me).")

        # --- Short selling for this stock (daily short-sold quantity) ---
        ss = q("SELECT date, qty FROM short_selling WHERE symbol=? "
               "ORDER BY date DESC LIMIT 200", (symbol,))
        if not ss.empty:
            with st.expander(f"📉 Short selling — {len(ss)} din "
                             "(us din kitni quantity short hui)"):
                st.dataframe(ss.rename(columns={"date": "Date", "qty": "Shorted Qty"}),
                             hide_index=True, width="stretch")
        else:
            st.caption("📉 Is stock ka koi short-selling record nahi (is period me).")

        # --- Corporate actions for this stock (dividend/split/bonus/rights) ---
        ca = q("SELECT ex_date, action_type, subject FROM corp_actions "
               "WHERE symbol=? ORDER BY ex_date DESC LIMIT 80", (symbol,))
        if not ca.empty:
            today_iso = pd.Timestamp.today().strftime("%Y-%m-%d")
            upcoming = ca[ca["ex_date"] >= today_iso]
            if not upcoming.empty:
                st.info("📢 **Upcoming corp actions:** " + " · ".join(
                    f"{r.ex_date} — {r.action_type}" for r in upcoming.itertuples()))
            with st.expander(f"💼 Corporate actions — {len(ca)} "
                             "(dividend / split / bonus / rights)"):
                st.dataframe(ca.rename(columns={"ex_date": "Ex-date",
                                                "action_type": "Type", "subject": "Details"}),
                             hide_index=True, width="stretch")
        else:
            st.caption("💼 Is stock ke koi corporate action record me nahi (is period me).")
        st.caption("Futures 🔮 aur Option chain ⛓️ sidebar ke alag sections me hain.")

# =========================================================================== #
# TAB — Line chart (interactive price chart: type switch, scale, zoom, crosshair)
# NOTE: chart TOOLS only — no technical indicators (RSI/MACD/MA), by project rule.
# =========================================================================== #
elif section == "📉 Line chart":
    hist = stock_history(symbol)
    if hist.empty:
        st.warning(f"{symbol}: koi data nahi. Pehle fetch_data / fetch_fno chalao.")
    else:
        # Header + metrics render at the TOP; we fill this container after the
        # toolbar has told us the timeframe (metrics depend on the chosen range).
        header_box = st.container()

        # --- Chart toolbar (right above the chart): timeframe / type / overlays ---
        tb1, tb2, tb3 = st.columns([3, 2, 2])
        tf = tb1.segmented_control(
            "Timeframe", ["20", "50", "100", "250", "All"], default="50",
            key="lc_tf", label_visibility="collapsed")
        ctype = tb2.segmented_control(
            "Chart type", ["Line", "Candle"], default="Line",
            key="lc_type", label_visibility="collapsed")
        with tb3.popover("⚙️ Overlays", use_container_width=True):
            st.caption("Default view saaf rakha hai — jo chahiye woh yahan se on karo.")
            st.caption("**Support / Resistance**")
            show_sr = st.checkbox("Swing S/R (auto pivots)", value=True, key="lc_sr")
            show_oiwall = st.checkbox("Option OI walls (top-3)", value=False, key="lc_oiwall")
            show_poc = st.checkbox("Volume POC + value area", value=False, key="lc_poc")
            show_mp = st.checkbox("Max-pain line (F&O)", value=True, key="lc_mp")
            st.caption("**Stat overlays (price pane)**")
            show_bands = st.checkbox("Mean ±σ bands (z-score)", value=False, key="lc_bands")
            show_hilo = st.checkbox("52w High / Low levels", value=False, key="lc_hilo")
            st.caption("**Event markers (price pane)**")
            show_deals = st.checkbox("Bulk/block deal markers", value=True, key="lc_deals")
            show_gap = st.checkbox("Gap + hi-volume markers", value=False, key="lc_gap")
            show_ca = st.checkbox("Corp-action lines", value=False, key="lc_ca")
            show_ban = st.checkbox("F&O ban markers", value=False, key="lc_ban")
            st.caption("**Extra panes (below)**")
            show_vol = st.checkbox("Volume pane", value=True, key="lc_vol")
            show_deliv = st.checkbox("Delivery % pane", value=True, key="lc_deliv")
            show_futoi = st.checkbox("Futures OI pane (buildup)", value=False, key="lc_futoi")
            show_pcr = st.checkbox("PCR pane", value=False, key="lc_pcr")
            show_prem = st.checkbox("Futures premium % pane", value=False, key="lc_prem")
            show_tsize = st.checkbox("Avg trade-size pane", value=False, key="lc_tsize")
            show_short = st.checkbox("Short-selling pane", value=False, key="lc_short")
        tf = tf or "50"
        ctype = ctype or "Line"

        view = hist if tf == "All" else hist.tail(int(tf))
        latest = view.iloc[-1]
        cv = view.copy()

        # --- Window statistics (all pure math over the visible range) ---
        mean_p = float(cv["close"].mean())
        sd_p = float(cv["close"].std() or 0.0)
        z_now = (latest["close"] - mean_p) / sd_p if sd_p else 0.0
        avg_vol = float(cv["volume"].mean())
        avg_del = float(cv["deliv_pct"].dropna().mean()) if cv["deliv_pct"].notna().any() else None
        avg_rng = float(((cv["high"] - cv["low"]) / cv["close"] * 100).mean())
        avg_to = float(cv["turnover"].mean())
        p_hi, p_lo = float(cv["high"].max()), float(cv["low"].min())
        # 52-week (≈252 trading days) high/low from the FULL history
        w = hist.tail(252)
        hi52, lo52 = float(w["high"].max()), float(w["low"].min())

        # --- Full-history stats (from the computed stats table) ---
        srow = q("SELECT ann_volatility, sharpe, beta, max_drawdown, skew, "
                 "kurtosis, cagr, zscore, pct_rank_52w FROM stats "
                 "WHERE symbol=? ORDER BY date DESC LIMIT 1", (symbol,))

        # --- Per-stock F&O daily (OI / change-OI / premium% / PCR) → align to chart ---
        sd = stock_daily(symbol)
        for _c in ("fut_oi", "fut_chg_oi", "prem_pct", "pcr"):
            cv[_c] = (cv["date"].map(sd[_c]) if (not sd.empty and _c in sd.columns)
                      else np.nan)

        # --- Current max-pain strike (latest option day, near expiry) ---
        mp_line = None
        _od = q("SELECT MAX(date) d FROM options WHERE symbol=?", (symbol,))["d"].iloc[0]
        if _od:
            _ne = q("SELECT MIN(expiry) e FROM options WHERE symbol=? AND date=?",
                    (symbol, _od))["e"].iloc[0]
            if _ne:
                mp_line = cached_max_pain(symbol, _od, _ne)

        # --- Events within the visible window: corp actions · ban · deals · short ---
        d0, d1 = cv["date"].iloc[0], cv["date"].iloc[-1]
        ca_ev = q("SELECT ex_date, action_type FROM corp_actions WHERE symbol=? "
                  "AND ex_date BETWEEN ? AND ? ORDER BY ex_date", (symbol, d0, d1))
        ban_ev = q("SELECT date FROM secban WHERE symbol=? AND date BETWEEN ? AND ? "
                   "ORDER BY date", (symbol, d0, d1))
        deals_ev = q("SELECT date, buy_sell, qty, price, client FROM deals WHERE symbol=? "
                     "AND date BETWEEN ? AND ? ORDER BY date", (symbol, d0, d1))
        short_ev = q("SELECT date, qty FROM short_selling WHERE symbol=? "
                     "AND date BETWEEN ? AND ?", (symbol, d0, d1))
        cv["short_qty"] = (cv["date"].map(short_ev.set_index("date")["qty"])
                           if not short_ev.empty else np.nan)
        cv["trade_size"] = cv["turnover"] / cv["num_trades"].replace(0, np.nan)

        # --- Fill the top header + metrics + stat strip now that view is known ---
        with header_box:
            st.subheader(f"{symbol} — chart")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Close", f"{latest['close']:.2f}", f"{latest['chg_pct']:+.2f}%")
            c2.metric("High (range)", f"{p_hi:.2f}")
            c3.metric("Low (range)", f"{p_lo:.2f}")
            c4.metric("Din (range me)", f"{len(view)}")

            # Stat strip — full-history stats (pure math, no indicators)
            if not srow.empty:
                s = srow.iloc[0]
                def _sv(x, mul=1, suf="", dp=2):
                    return f"{x*mul:.{dp}f}{suf}" if pd.notna(x) else "—"
                st.caption(
                    "📊 **Stats:** "
                    f"Ann.Vol {_sv(s['ann_volatility'],100,'%',0)} · "
                    f"Sharpe {_sv(s['sharpe'])} · "
                    f"Beta {_sv(s['beta'])} · "
                    f"MaxDD {_sv(s['max_drawdown'],100,'%',0)} · "
                    f"CAGR {_sv(s['cagr'],100,'%',0)} · "
                    f"z {_sv(s['zscore'])} · 52w %ile {_sv(s['pct_rank_52w'],1,'',0)}")
            # Window averages — "data ka average"
            st.caption(
                f"📈 **{tf}-din average:** Close ₹{mean_p:,.2f} · "
                f"Vol {_fmt(avg_vol)} · "
                + (f"Delivery {avg_del:.1f}% · " if avg_del is not None else "")
                + f"Range {avg_rng:.2f}% · Turnover ₹{avg_to/1e7:,.1f}Cr · "
                f"aaj z-score {z_now:+.2f}")

        UP, DN = "#10b981", "#f43f5e"
        up = latest["close"] >= view.iloc[0]["close"]
        color = UP if up else DN
        GRID = "rgba(255,255,255,.05)"
        SPIKE = "#6c6c8a"

        # --- Dynamic panes: price (always, weight 3) + each extra pane (weight 1) ---
        _has_oi = bool(cv["fut_oi"].notna().any())
        _has_pcr = bool(cv["pcr"].notna().any())
        extras = ([("vol",)] if show_vol else []) + \
                 ([("deliv",)] if show_deliv else []) + \
                 ([("futoi",)] if show_futoi and _has_oi else []) + \
                 ([("pcr",)] if show_pcr and _has_pcr else []) + \
                 ([("prem",)] if show_prem and cv["prem_pct"].notna().any() else []) + \
                 ([("tsize",)] if show_tsize and cv["trade_size"].notna().any() else []) + \
                 ([("short",)] if show_short and cv["short_qty"].notna().any() else [])
        extras = [e[0] for e in extras]
        n_extra = len(extras)
        weights = [3.0] + [1.0] * n_extra
        heights = [x / sum(weights) for x in weights]
        fig = make_subplots(rows=1 + n_extra, cols=1, shared_xaxes=True,
                            vertical_spacing=0.045, row_heights=heights)
        row_of = {name: 2 + i for i, name in enumerate(extras)}   # pane -> row
        vol_row = row_of.get("vol")
        deliv_row = row_of.get("deliv")
        bottom_row = 1 + n_extra

        # --- Price pane: the trace depends on the chosen chart type ---
        if ctype == "Candle":
            fig.add_trace(go.Candlestick(
                x=cv["date"], open=cv["open"], high=cv["high"],
                low=cv["low"], close=cv["close"], name="",
                increasing_line_color=UP, decreasing_line_color=DN,
                increasing_fillcolor=UP, decreasing_fillcolor=DN,
                line_width=1.2, whiskerwidth=0.4),
                row=1, col=1)
        else:                                   # Line (default) — soft glow fill
            fig.add_trace(go.Scatter(
                x=cv["date"], y=cv["close"], name="Close", mode="lines",
                line=dict(color=color, width=2.4, shape="spline", smoothing=0.5),
                fill="tozeroy",
                fillcolor=("rgba(16,185,129,.08)" if up else "rgba(244,63,94,.08)"),
                hovertemplate="<b>%{x}</b><br>Close ₹%{y:.2f}<extra></extra>"),
                row=1, col=1)

        # --- Overlay: mean ±1σ / ±2σ bands (z-score context, not a moving avg) ---
        if show_bands and sd_p:
            fig.add_hline(y=mean_p, line=dict(color="#8b8ba7", width=1, dash="solid"),
                          annotation_text="mean", annotation_position="right",
                          annotation_font_size=10, row=1, col=1)
            for k, dash in [(1, "dash"), (2, "dot")]:
                for sign in (+1, -1):
                    yv = mean_p + sign * k * sd_p
                    # only label the outer ±2σ lines to cut annotation clutter
                    txt = f"{'+' if sign > 0 else '−'}{k}σ" if k == 2 else None
                    fig.add_hline(y=yv, line=dict(color="rgba(139,139,167,.4)",
                                  width=1, dash=dash), row=1, col=1,
                                  annotation_text=txt, annotation_position="right",
                                  annotation_font_size=9)

        # --- Overlay: period + 52-week high/low reference levels ---
        if show_hilo:
            fig.add_hline(y=hi52, line=dict(color="rgba(16,185,129,.5)", width=1, dash="dash"),
                          annotation_text="52w High", annotation_position="left",
                          annotation_font_size=9, row=1, col=1)
            fig.add_hline(y=lo52, line=dict(color="rgba(244,63,94,.5)", width=1, dash="dash"),
                          annotation_text="52w Low", annotation_position="left",
                          annotation_font_size=9, row=1, col=1)

        # --- Overlay: gap up/down + highest-volume markers ---
        if show_gap:
            prev_c = cv["close"].shift(1)
            gap = (cv["open"] / prev_c - 1.0) * 100
            gu = cv[gap >= 2.0]
            gd = cv[gap <= -2.0]
            if not gu.empty:
                fig.add_trace(go.Scatter(
                    x=gu["date"], y=gu["high"] * 1.012, mode="markers", name="Gap up",
                    marker=dict(symbol="triangle-up", size=10, color=UP),
                    hovertemplate="<b>%{x}</b><br>Gap-up<extra></extra>"), row=1, col=1)
            if not gd.empty:
                fig.add_trace(go.Scatter(
                    x=gd["date"], y=gd["low"] * 0.988, mode="markers", name="Gap down",
                    marker=dict(symbol="triangle-down", size=10, color=DN),
                    hovertemplate="<b>%{x}</b><br>Gap-down<extra></extra>"), row=1, col=1)
            hv = cv.loc[cv["volume"].idxmax()]
            fig.add_trace(go.Scatter(
                x=[hv["date"]], y=[hv["high"] * 1.02], mode="markers", name="Peak vol",
                marker=dict(symbol="star", size=13, color="#f59e0b"),
                hovertemplate="<b>%{x}</b><br>Highest volume "
                              f"({_fmt(hv['volume'])})<extra></extra>"), row=1, col=1)

        # --- Overlay: current max-pain strike (F&O writers' expiry magnet) ---
        if show_mp and mp_line:
            fig.add_hline(y=mp_line, line=dict(color="#a78bfa", width=1.4, dash="dashdot"),
                          annotation_text=f"max pain ₹{mp_line:,.0f}",
                          annotation_position="left", annotation_font_size=10,
                          annotation_font_color="#a78bfa", row=1, col=1)

        # --- Overlay: corporate-action ex-dates (vertical dotted lines) ---
        if show_ca and not ca_ev.empty:
            dset = list(cv["date"])
            for ev in ca_ev.itertuples():
                xd = (ev.ex_date if ev.ex_date in dset else
                      next((d for d in reversed(dset) if d <= ev.ex_date), None))
                if xd is None:
                    continue
                fig.add_vline(x=xd, line=dict(color="rgba(167,139,250,.5)", width=1, dash="dot"),
                              annotation_text=(ev.action_type or "?")[:1].upper(),
                              annotation_position="top", annotation_font_size=9,
                              annotation_font_color="#a78bfa", row=1, col=1)

        # --- Overlay: F&O ban days (red squares along the bottom of the price pane) ---
        if show_ban and not ban_ev.empty:
            bd = [d for d in ban_ev["date"] if d in set(cv["date"])]
            if bd:
                fig.add_trace(go.Scatter(
                    x=bd, y=[p_lo] * len(bd), mode="markers", name="F&O ban",
                    marker=dict(symbol="square", size=7, color="rgba(244,63,94,.85)"),
                    hovertemplate="<b>%{x}</b><br>F&O BAN day (MWPL >95%)<extra></extra>"),
                    row=1, col=1)

        # --- Overlay: bulk/block deal markers (buy ▲ / sell ▼, institutional) ---
        if show_deals and not deals_ev.empty:
            dset = set(cv["date"])
            de = deals_ev[deals_ev["date"].isin(dset)]
            if not de.empty:
                lowmap, highmap = cv.set_index("date")["low"], cv.set_index("date")["high"]
                for side, msym, mcol, ymap, yf, nm in [
                    ("BUY", "triangle-up", "#22d3ee", lowmap, 0.985, "Deal BUY"),
                    ("SELL", "triangle-down", "#fb923c", highmap, 1.015, "Deal SELL")]:
                    s = de[de["buy_sell"].str.upper() == side]
                    if s.empty:
                        continue
                    g = s.groupby("date").agg(
                        qty=("qty", "sum"), n=("qty", "size"),
                        cl=("client", lambda x: " · ".join(list(x.astype(str))[:3])))
                    xs = list(g.index)
                    ys = [float(ymap.get(d)) * yf for d in xs]
                    txt = [f"{side} {_fmt(qt)} ({int(nn)} deal)"
                           + (f"<br>{c}" if c else "")
                           for qt, nn, c in zip(g["qty"], g["n"], g["cl"])]
                    fig.add_trace(go.Scatter(
                        x=xs, y=ys, mode="markers", name=nm,
                        marker=dict(symbol=msym, size=11, color=mcol,
                                    line=dict(width=1, color="#0b0b14")),
                        text=txt, hovertemplate="%{text}<extra></extra>"), row=1, col=1)

        # --- S/R 1: Swing high/low pivots (recent local highs/lows, clustered) ---
        if show_sr and len(cv) >= 7:
            res, sup = charts.swing_levels(cv["high"].values, cv["low"].values,
                                           latest["close"])
            for lvl, c in res:
                fig.add_hline(y=lvl, line=dict(color="rgba(244,63,94,.5)", width=1, dash="dash"),
                              annotation_text=f"R {lvl:,.0f}" + (f"·{c}x" if c > 1 else ""),
                              annotation_position="right", annotation_font_size=9,
                              annotation_font_color="#f87171", row=1, col=1)
            for lvl, c in sup:
                fig.add_hline(y=lvl, line=dict(color="rgba(16,185,129,.5)", width=1, dash="dash"),
                              annotation_text=f"S {lvl:,.0f}" + (f"·{c}x" if c > 1 else ""),
                              annotation_position="right", annotation_font_size=9,
                              annotation_font_color="#34d399", row=1, col=1)

        # --- S/R 2: Volume-profile POC + 70% value area (volume-by-price) ---
        if show_poc and len(cv) >= 5:
            _vp = charts.volume_profile(cv["low"].values, cv["high"].values,
                                        cv["volume"].values, p_lo, p_hi)
            if _vp:
                poc, va_lo, va_hi = _vp
                fig.add_hrect(y0=va_lo, y1=va_hi, fillcolor="rgba(245,158,11,.07)",
                              line_width=0, layer="below", row=1, col=1)
                fig.add_hline(y=poc, line=dict(color="#f59e0b", width=1.6),
                              annotation_text=f"POC ₹{poc:,.0f}", annotation_position="left",
                              annotation_font_size=10, annotation_font_color="#f59e0b",
                              row=1, col=1)

        # --- S/R 3: Option OI walls — top-3 Put-OI supports / top-3 Call-OI
        #     resistances. OI summed across ALL expiries via sum_chain. Rank 1
        #     is bold/opaque, ranks 2-3 thinner/fainter. ---
        if show_oiwall and _od:
            sc = cached_sum_chain(symbol, _od)
            if not sc.empty:
                def _walls(col):
                    if col not in sc.columns:
                        return []
                    d = sc[["strike", col]].dropna()
                    d = d[d[col] > 0].sort_values(col, ascending=False).head(3)
                    return [float(s) for s in d["strike"]]
                _sty = [(1.7, .8), (1.2, .5), (1.0, .32)]      # rank -> (width, alpha)
                for rk, kv in enumerate(_walls("oi_PE")):       # supports (Put OI)
                    w, a = _sty[rk]
                    fig.add_hline(y=kv, line=dict(color=f"rgba(16,185,129,{a})", width=w,
                                  dash="dashdot"), row=1, col=1, annotation_position="left",
                                  annotation_text=("★Put " if rk == 0 else "") + f"{kv:,.0f}",
                                  annotation_font_size=9, annotation_font_color="#34d399")
                for rk, kv in enumerate(_walls("oi_CE")):       # resistances (Call OI)
                    w, a = _sty[rk]
                    fig.add_hline(y=kv, line=dict(color=f"rgba(244,63,94,{a})", width=w,
                                  dash="dashdot"), row=1, col=1, annotation_position="left",
                                  annotation_text=("★Call " if rk == 0 else "") + f"{kv:,.0f}",
                                  annotation_font_size=9, annotation_font_color="#f87171")

        # --- Volume pane (green up-day / red down-day) + avg-volume line ---
        if show_vol:
            vcol = [("rgba(16,185,129,.55)" if pd.notna(ch) and ch >= 0
                     else "rgba(244,63,94,.55)") for ch in cv["chg_pct"]]
            fig.add_trace(go.Bar(
                x=cv["date"], y=cv["volume"], name="Volume",
                marker_color=vcol, marker_line_width=0,
                hovertemplate="<b>%{x}</b><br>Volume %{y:,.0f}<extra></extra>"),
                row=vol_row, col=1)
            fig.add_hline(y=avg_vol, line=dict(color="#8b8ba7", width=1, dash="dot"),
                          annotation_text="avg", annotation_position="right",
                          annotation_font_size=9, row=vol_row, col=1)
            fig.update_yaxes(title_text="Vol", row=vol_row, col=1, showgrid=False,
                             zeroline=False, tickfont_size=10)

        # --- Delivery % pane (conviction — real buying vs speculation) + avg line ---
        if show_deliv:
            fig.add_trace(go.Scatter(
                x=cv["date"], y=cv["deliv_pct"], name="Delivery %", mode="lines",
                line=dict(color="#38bdf8", width=1.8),
                hovertemplate="<b>%{x}</b><br>Delivery %{y:.1f}%<extra></extra>"),
                row=deliv_row, col=1)
            if avg_del is not None:
                fig.add_hline(y=avg_del, line=dict(color="#8b8ba7", width=1, dash="dot"),
                              annotation_text=f"avg {avg_del:.0f}%", annotation_position="right",
                              annotation_font_size=9, row=deliv_row, col=1)
            fig.update_yaxes(title_text="Del%", row=deliv_row, col=1, showgrid=False,
                             zeroline=False, tickfont_size=10)

        # --- Futures OI pane (bars coloured by buildup read) ---
        if "futoi" in row_of:
            fr = row_of["futoi"]

            def _bu_color(ch, doi):
                if pd.isna(ch) or pd.isna(doi):
                    return "rgba(139,139,167,.5)"
                if ch >= 0 and doi > 0:
                    return "rgba(16,185,129,.75)"    # long buildup
                if ch >= 0 and doi <= 0:
                    return "rgba(45,212,191,.65)"    # short covering
                if ch < 0 and doi > 0:
                    return "rgba(244,63,94,.75)"     # short buildup
                return "rgba(245,158,11,.65)"        # long unwinding
            bcol = [_bu_color(c, o) for c, o in zip(cv["chg_pct"], cv["fut_chg_oi"])]
            fig.add_trace(go.Bar(
                x=cv["date"], y=cv["fut_oi"], name="Fut OI", marker_color=bcol,
                marker_line_width=0,
                hovertemplate="<b>%{x}</b><br>Futures OI %{y:,.0f}<extra></extra>"),
                row=fr, col=1)
            fig.update_yaxes(title_text="Fut OI", row=fr, col=1, showgrid=False,
                             zeroline=False, tickfont_size=10)

        # --- PCR pane (put/call OI ratio, 1.0 reference) ---
        if "pcr" in row_of:
            pr = row_of["pcr"]
            fig.add_trace(go.Scatter(
                x=cv["date"], y=cv["pcr"], name="PCR", mode="lines",
                line=dict(color="#c084fc", width=1.8),
                hovertemplate="<b>%{x}</b><br>PCR %{y:.2f}<extra></extra>"),
                row=pr, col=1)
            fig.add_hline(y=1.0, line=dict(color="#8b8ba7", width=1, dash="dot"),
                          annotation_text="1.0", annotation_position="right",
                          annotation_font_size=9, row=pr, col=1)
            fig.update_yaxes(title_text="PCR", row=pr, col=1, showgrid=False,
                             zeroline=False, tickfont_size=10)

        # --- Futures premium/discount % pane (near-future vs spot basis) ---
        if "prem" in row_of:
            pm = row_of["prem"]
            fig.add_trace(go.Scatter(
                x=cv["date"], y=cv["prem_pct"], name="Prem%", mode="lines",
                line=dict(color="#f472b6", width=1.8),
                hovertemplate="<b>%{x}</b><br>Premium %{y:+.2f}%<extra></extra>"),
                row=pm, col=1)
            fig.add_hline(y=0, line=dict(color="#8b8ba7", width=1), row=pm, col=1)
            fig.update_yaxes(title_text="Prem%", row=pm, col=1, showgrid=False,
                             zeroline=False, tickfont_size=10)

        # --- Avg trade-size pane (turnover ÷ trades — institutional footprint) ---
        if "tsize" in row_of:
            tz = row_of["tsize"]
            fig.add_trace(go.Scatter(
                x=cv["date"], y=cv["trade_size"], name="₹/trade", mode="lines",
                line=dict(color="#60a5fa", width=1.8),
                hovertemplate="<b>%{x}</b><br>Avg trade ₹%{y:,.0f}<extra></extra>"),
                row=tz, col=1)
            fig.update_yaxes(title_text="₹/trade", row=tz, col=1, showgrid=False,
                             zeroline=False, tickfont_size=10)

        # --- Short-selling pane (daily short-sold quantity — bearish pressure) ---
        if "short" in row_of:
            sh = row_of["short"]
            fig.add_trace(go.Bar(
                x=cv["date"], y=cv["short_qty"], name="Short qty",
                marker_color="rgba(244,63,94,.6)", marker_line_width=0,
                hovertemplate="<b>%{x}</b><br>Short qty %{y:,.0f}<extra></extra>"),
                row=sh, col=1)
            fig.update_yaxes(title_text="Short", row=sh, col=1, showgrid=False,
                             zeroline=False, tickfont_size=10)

        # --- Layout: dark, subtle grid, crosshair spikes, unified hover ---
        fig.update_layout(
            height=520 + 90 * n_extra, margin=dict(l=6, r=6, t=14, b=0),
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#b8b8cc", size=12),
            hovermode="x unified", showlegend=False, bargap=0.25,
            xaxis_rangeslider_visible=False, dragmode="zoom",
            hoverlabel=dict(bgcolor="#1c1c2b", bordercolor="#3a3a55",
                            font_size=12))
        step = max(1, len(cv) // 12)
        fig.update_xaxes(type="category", showgrid=False, showspikes=True,
                         spikemode="across", spikethickness=1, spikedash="dot",
                         spikecolor=SPIKE, showticklabels=False)
        # Only label the bottom-most axis (shared x); thin + angle the ticks.
        fig.update_xaxes(showticklabels=True, tickmode="array",
                         tickvals=list(cv["date"])[::step], tickangle=-30,
                         tickfont_size=10, row=bottom_row, col=1)
        # Tighten the price axis to the data (a tozeroy fill would otherwise pull
        # the axis toward 0). Widen to include the ±2σ bands when shown so they
        # stay visible.
        axis_lo, axis_hi = p_lo, p_hi
        if show_bands and sd_p:
            axis_lo = min(axis_lo, mean_p - 2 * sd_p)
            axis_hi = max(axis_hi, mean_p + 2 * sd_p)
        pad = (axis_hi - axis_lo) * 0.06 or 1.0
        fig.update_yaxes(title_text="Price ₹", row=1, col=1, side="right",
                         range=[axis_lo - pad, axis_hi + pad],
                         gridcolor=GRID, zeroline=False, showspikes=True,
                         spikemode="across", spikethickness=1, spikedash="dot",
                         spikecolor=SPIKE)
        st.plotly_chart(fig, width="stretch",
                        config={"scrollZoom": True, "displaylogo": False,
                                "modeBarButtonsToRemove": ["select2d", "lasso2d"]})
        st.caption(
            "⚙️ Overlays me on-off: **Swing S/R** (R red / S green) · **Option OI walls** "
            "(top-3 Put=support / Call=resist, ★=strongest) · **Volume POC** · **max-pain** · "
            "σ-bands · 52w hi-lo · **deal markers** (▲buy / ▼sell) · gap · corp / ban · "
            "panes: volume · delivery · **Fut-OI** (buildup) · **PCR** · **premium%** · "
            "**₹/trade** · **short**. "
            "Fut-OI bars ka rang = buildup: 🟢 long buildup · 🩵 short covering · "
            "🔴 short buildup · 🟠 long unwinding. "
            "Sab pure data/statistics — koi technical indicator nahi (project rule).")

        # ------------------------------------------------------------------- #
        # Momentum panel — har NON-price data aaj apne trailing 7d/20d average
        # se upar hai ya neeche (activity vs normal). Price ka MA nahi (rule).
        # Full history se compute hota hai — chart timeframe se independent.
        # ------------------------------------------------------------------- #
        def _mom(series):    # today vs prior 7/20-day average (charts.trailing_read)
            return None if series is None else charts.trailing_read(series)

        if not sd.empty:
            rng_s = (sd["high"] - sd["low"]) / sd["prev_close"] * 100
            _oi = sd["fut_oi"] if "fut_oi" in sd.columns else None
            _doi = sd["fut_chg_oi"].abs() if "fut_chg_oi" in sd.columns else None
            _pcr = sd["pcr"] if "pcr" in sd.columns else None
            # (label, series, kind) — kind drives formatting
            scored = [
                ("Volume", sd["volume"], "cnt"),
                ("Delivery %", sd["deliv_pct"], "pct"),
                ("Turnover", sd["turnover"], "cr"),
                ("Range % (H-L)", rng_s, "pct"),
                ("Futures OI", _oi, "cnt"),
                ("OI change (abs)", _doi, "cnt"),
                ("|Daily return| %", sd["chg_pct"].abs(), "pct"),
            ]

            def _fv(v, kind):
                if kind == "cnt":
                    return _fmt(v)
                if kind == "cr":
                    return f"₹{v/1e7:,.1f}Cr"
                return f"{v:.1f}%"

            rows_md, n_above, n_tot = [], 0, 0
            for lbl, ser, kind in scored:
                res = _mom(ser)
                if res is None:
                    continue
                today, a7, a20 = res
                n_tot += 1
                if today > a7 and today > a20:
                    emo, read = "🟢", "above"; n_above += 1
                elif today < a7 and today < a20:
                    emo, read = "🔴", "below"
                else:
                    emo, read = "🟡", "mixed"
                rows_md.append(
                    f"| {lbl} | {_fv(today,kind)} | {_fv(a7,kind)} | {_fv(a20,kind)} | {emo} {read} |")

            if n_tot:
                pct_above = round(100 * n_above / n_tot)
                state = ("🔥 ACTIVE" if pct_above >= 70 else
                         "⚡ MIXED" if pct_above >= 40 else "😴 QUIET")
                # PCR shown as context only (direction-neutral → not scored)
                pctx = ""
                pres = _mom(_pcr)
                if pres:
                    pt, p7, p20 = pres
                    pd_read = ("put-heavy vs norm" if pt > p7 and pt > p20 else
                               "call-heavy vs norm" if pt < p7 and pt < p20 else "near norm")
                    pctx = (f"\n\n**PCR (context, not scored):** aaj {pt:.2f} · "
                            f"7d {p7:.2f} · 20d {p20:.2f} → {pd_read}")
                with st.expander(f"⚡ Momentum — {n_above}/{n_tot} data above their 7d & 20d "
                                 f"average · {state} ({pct_above}%)"):
                    st.markdown(
                        "Aaj ka value apne **trailing 7-din aur 20-din average** se upar (🟢) / "
                        "neeche (🔴) / mixed (🟡). Zyada 🟢 ek saath = activity/momentum high.\n\n"
                        "| Data | Aaj | 7d avg | 20d avg | Read |\n"
                        "|---|--:|--:|--:|:--|\n" + "\n".join(rows_md) + pctx)
                    st.caption(
                        "⚠️ Yeh sirf **statistical observation** hai (activity vs recent norm) — "
                        "koi **prediction ya buy/sell advice nahi**. Price ka moving-average "
                        "jaan-boojh ke nahi liya (project rule). Above-average cluster ka matlab "
                        "sirf itna: abhi normal se zyada participation/positioning ho raha hai.")

# =========================================================================== #
# TAB — Analysis (one stock, day-by-day, with plain-language interpretation)
# =========================================================================== #
elif section == "🔬 Analysis":
    st.subheader(f"🔬 {symbol} — deep analysis (din-by-din)")
    dd = stock_daily(symbol)
    if dd.empty:
        st.info(f"{symbol}: koi data nahi.")
    else:
        dates = list(dd.index)                       # ascending date strings
        # F&O bhavcopy lags prices by ~1-2 days, so default to the latest day
        # that actually has futures data (else F&O rows would show "—").
        if "fut_oi" in dd.columns and dd["fut_oi"].notna().any():
            default_day = dd.index[dd["fut_oi"].notna()][-1]
        else:
            default_day = dates[-1]
        sel = date_slider("📅 Kis din ka analysis (slider se din badlo)",
                          dates[::-1], "an_date", window=len(dates), default=default_day)
        i = dates.index(sel)
        row = dd.loc[sel]
        prev = dd.iloc[i - 1] if i > 0 else None

        def _d(key, pct=False):
            """change of `key` today vs previous day (abs, or % if pct)."""
            if prev is None or key not in dd.columns:
                return None
            pv, cv = prev.get(key), row.get(key)
            if pd.isna(pv) or pd.isna(cv):
                return None
            return (cv / pv - 1) * 100 if (pct and pv) else (cv - pv)

        vd, ddv, od, pcr_d = _d("volume", True), _d("deliv_pct"), _d("fut_oi", True), _d("pcr")

        # ---- overall read + headline metrics ----
        otxt, _ = _read_overall(row.get("chg_pct"), row.get("fut_chg_oi"), row.get("deliv_pct"))
        st.markdown(f"### {otxt} · {sel}")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Close", f"{row['close']:,.1f}",
                  f"{row['chg_pct']:+.2f}%" if pd.notna(row['chg_pct']) else None)
        c2.metric("Volume", _fmt(row["volume"]) if pd.notna(row["volume"]) else "—",
                  f"{vd:+.0f}%" if vd is not None else None)
        c3.metric("Delivery %", f"{row['deliv_pct']:.1f}" if pd.notna(row.get("deliv_pct")) else "—",
                  f"{ddv:+.1f}pp" if ddv is not None else None)
        if pd.notna(row.get("fut_oi")):
            c4.metric("Futures OI", _fmt(row["fut_oi"]), f"{od:+.1f}%" if od is not None else None)

        # ---- kal -> aaj: every signal + its matlab ----
        st.markdown("#### Kal → Aaj · har signal ka **matlab**")
        if "fut_oi" not in dd.columns or pd.isna(row.get("fut_oi")):
            st.caption("ℹ️ Is din ka **F&O data abhi nahi aaya** (futures/options bhavcopy prices "
                       "se 1–2 din late aati hai) — isliye buildup / premium% / PCR '—' hai. "
                       "Slider ko pichhle din pe le jao, poora F&O interpretation dikhega.")
        oi_val = ("—" if pd.isna(row.get("fut_oi"))
                  else f"OI {_fmt(row['fut_oi'])}" + (f" ({od:+.1f}%)" if od is not None else ""))
        # extra context: gap/range · vs NIFTY · sector · max pain
        gap, rng = row.get("gap_pct"), row.get("range_pct")
        schg, nchg = row.get("chg_pct"), nifty_daily().get(sel)
        sname = sectors.sector_of(symbol)
        _sec = sector_daily_returns()
        _srow = _sec[(_sec["date"] == sel) & (_sec["sector"] == sname)]
        savg = _srow["avg_ret"].iloc[0] if not _srow.empty else np.nan
        _ne = q("SELECT MIN(expiry) e FROM options WHERE symbol=? AND date=?",
                (symbol, sel))["e"].iloc[0]
        mp = cached_max_pain(symbol, sel, _ne) if _ne else None

        reads = [
            ("Price", f"{row['close']:,.1f} ({schg:+.2f}%)"
                if pd.notna(schg) else f"{row['close']:,.1f}",
             _trend5(dd, "close", sel), _read_move(schg)),
            ("Gap & range", f"{gap:+.2f}% gap" if pd.notna(gap) else "—", "", _read_gap(gap, rng)),
            ("vs NIFTY", f"NIFTY {nchg:+.2f}%" if pd.notna(nchg) else "—", "",
             _read_relstr(schg, nchg)),
            ("Sector", f"{savg:+.2f}%" if pd.notna(savg) else "—", "",
             _read_sector(schg, savg, sname)),
            ("Delivery %", f"{row['deliv_pct']:.1f}%" if pd.notna(row.get("deliv_pct")) else "—",
             _trend5(dd, "deliv_pct", sel), _read_deliv(row.get("deliv_pct"), ddv)),
            ("F&O buildup", oi_val, _trend5(dd, "fut_oi", sel),
             _read_buildup(schg, row.get("fut_chg_oi"))),
            ("Futures premium", f"{row['prem_pct']:+.2f}%" if pd.notna(row.get("prem_pct")) else "—",
             _trend5(dd, "prem_pct", sel), _read_prem(row.get("prem_pct"))),
            ("Max pain", f"₹{mp:,.0f}" if mp else "—", "", _read_maxpain(row.get("close"), mp)),
            ("Options PCR", f"{row['pcr']:.2f}" if pd.notna(row.get("pcr")) else "—",
             _trend5(dd, "pcr", sel), _read_pcr(row.get("pcr"), pcr_d)),
        ]
        md = ["| Signal | Aaj | 5-day trend | Matlab |", "|---|---|---|---|"]
        for name, val, trend, (txt, cls) in reads:
            md.append(f"| **{name}** | {val} | {trend or '—'} | {_EMO[cls]} {txt} |")
        st.markdown("\n".join(md))
        st.caption("**5-day trend** = signal kitne din se ek direction me (streak = reliable, "
                   "1-din blip = noise).")

        # ---- extra context (secondary — collapsed) ----
        with st.expander("📎 Extra context — turnover · rollover · VIX · FII/DII"):
            lines = []
            tv, nt = row.get("turnover"), row.get("num_trades")
            if pd.notna(tv):
                lines.append(f"- **Turnover:** ₹{tv/1e7:,.1f} Cr · **Trades:** {_fmt(nt)} "
                             "(us din ki activity / liquidity)")
            fexp = q("SELECT expiry, SUM(oi) oi FROM futures WHERE symbol=? AND date=? "
                     "GROUP BY expiry ORDER BY expiry", (symbol, sel))
            if len(fexp) >= 2:
                near_oi, next_oi = fexp["oi"].iloc[0], fexp["oi"].iloc[1]
                roll = next_oi / (near_oi + next_oi) * 100 if (near_oi + next_oi) else 0
                lines.append(f"- **Rollover:** next-month me **{roll:.0f}%** OI "
                             f"(near {_fmt(near_oi)} / next {_fmt(next_oi)}) — high = positions "
                             "roll ho rahe (trend continue), low = unwinding (expiry ke paas useful)")
            vx = q("SELECT close FROM vix WHERE date=?", (sel,))
            if not vx.empty and pd.notna(vx["close"].iloc[0]):
                lines.append(f"- **India VIX (us din):** {vx['close'].iloc[0]:.2f} "
                             "(market fear level — high = risk-off)")
            fd = q("SELECT category, net FROM fii_dii WHERE date=?", (sel,))
            if not fd.empty:
                lines.append("- **FII/DII cash (market-wide, us din):** " +
                             " · ".join(f"{r.category} net ₹{r.net:+,.0f} Cr" for r in fd.itertuples()))
            st.markdown("\n".join(lines) if lines else "Is din ka extra data nahi.")
            st.caption("Ye market-wide / secondary signals hain — single-stock ke liye context, "
                       "primary nahi.")

        # ---- events that day ----
        st.markdown("#### Us din ke events")
        ev = False
        if not q("SELECT 1 FROM secban WHERE symbol=? AND date=?", (symbol, sel)).empty:
            st.error("🚫 Is din stock **F&O ban** me tha (koi fresh F&O position nahi)."); ev = True
        ca = q("SELECT action_type, subject FROM corp_actions WHERE symbol=? AND ex_date=?",
               (symbol, sel))
        if not ca.empty:
            st.warning("💼 **Corp action ex-date:** " +
                       " · ".join(f"{r.action_type} ({r.subject[:45]})" for r in ca.itertuples()))
            ev = True
        dl = q("SELECT deal_type, buy_sell, qty, price, client FROM deals "
               "WHERE symbol=? AND date=?", (symbol, sel))
        if not dl.empty:
            st.info(f"🏦 **{len(dl)} bulk/block deal(s)** is din:")
            st.dataframe(dl, hide_index=True, width="stretch")
            ev = True
        ssq = q("SELECT qty FROM short_selling WHERE symbol=? AND date=?", (symbol, sel))
        if not ssq.empty and pd.notna(ssq["qty"].iloc[0]):
            st.caption(f"📉 Short selling is din: **{_fmt(ssq['qty'].iloc[0])}** shares short hui.")
            ev = True
        if not ev:
            st.caption("Koi special event nahi is din (na deal, na ban, na corp-action).")

        st.caption("⚠️ Ye interpretations **typical meaning** batate hain (educational/research) — "
                   "guaranteed prediction ya **trading advice NAHI**. Apne research + risk pe.")

# =========================================================================== #
# TAB — Futures (totals + estimated participant split)
# =========================================================================== #
elif section == "🔮 Futures":
    st.subheader(f"{symbol} — futures")
    ffdates = q("SELECT DISTINCT date FROM futures WHERE symbol=? ORDER BY date DESC",
                (symbol,))["date"].tolist()
    if not ffdates:
        st.info(f"{symbol}: F&O data abhi nahi.")
    else:
        fdate = date_slider("F&O date", ffdates, "fut_tab_date")
        fspot = q("SELECT close FROM prices WHERE symbol=? AND date=?", (symbol, fdate))
        fspot_px = float(fspot.iloc[0]["close"]) if not fspot.empty else None

        dd = stock_daily(symbol)
        drow = dd.loc[fdate] if (not dd.empty and fdate in dd.index) else None
        fexp = q("SELECT expiry, SUM(oi) oi FROM futures WHERE symbol=? AND date=? "
                 "GROUP BY expiry ORDER BY expiry", (symbol, fdate))

        # --- Futures read (aaj): buildup · premium · OI · rollover · days-to-expiry ---
        if drow is not None and not fexp.empty:
            near_exp = fexp["expiry"].iloc[0]
            dte = (pd.Timestamp(near_exp) - pd.Timestamp(fdate)).days
            m1, m2, m3 = st.columns(3)
            m1.metric("Premium (near)",
                      f"{drow.get('prem_pct'):+.2f}%" if pd.notna(drow.get("prem_pct")) else "—")
            m2.metric("Total OI", _fmt(drow.get("fut_oi")) if pd.notna(drow.get("fut_oi")) else "—",
                      f"{drow.get('fut_chg_oi'):+,.0f}" if pd.notna(drow.get("fut_chg_oi")) else None)
            m3.metric("Near expiry", near_exp, f"{dte} din baaki", delta_color="off")
            btxt, bcls = _read_buildup(drow.get("chg_pct"), drow.get("fut_chg_oi"))
            st.markdown(f"**Buildup (aaj):** {_EMO[bcls]} {btxt}  ·  "
                        f"5-day OI trend: **{_trend5(dd, 'fut_oi', fdate)}**")
            if len(fexp) >= 2:
                near_oi, next_oi = fexp["oi"].iloc[0], fexp["oi"].iloc[1]
                roll = next_oi / (near_oi + next_oi) * 100 if (near_oi + next_oi) else 0
                rtxt = ("**high** — positions next-month me roll ho rahe (trend continue)"
                        if roll > 25 else
                        "**low** — abhi near-month me concentrated (early cycle)" if roll < 10
                        else "**building** — rollover shuru")
                st.caption(f"🔄 **Rollover:** next-month me {roll:.0f}% OI "
                           f"(near {_fmt(near_oi)} / next {_fmt(next_oi)}) — {rtxt}. "
                           "Expiry ke paas rollover% zyada matter karta hai.")

        # --- 1. Futures — teeno expiry ka total + changes (raw table) ---
        st.markdown("#### 1 · Futures — teeno expiry ka total + changes")
        fut = q("""SELECT expiry, open, high, low, close, settle,
                          contracts, value_lakh, oi, chg_oi
                   FROM futures WHERE symbol=? AND date=? ORDER BY expiry""",
                (symbol, fdate))
        st.markdown(render_futures_table(fut, fspot_px), unsafe_allow_html=True)

        # --- 2. OI + Price trend · 3. Premium/basis trend ---
        fdd = dd[dd["fut_oi"].notna()].tail(90) if "fut_oi" in dd.columns else pd.DataFrame()
        if not fdd.empty:
            st.markdown("#### 2 · OI + Price trend (last ~90 F&O din)")
            fig = go.Figure()
            fig.add_trace(go.Bar(x=fdd.index, y=fdd["fut_oi"], name="Futures OI",
                                 marker_color="rgba(99,102,241,.45)"))
            fig.add_trace(go.Scatter(x=fdd.index, y=fdd["close"], name="Price",
                                     line=dict(color="#10b981", width=2), yaxis="y2"))
            fig.update_layout(height=320, margin=dict(l=0, r=0, t=10, b=0),
                              legend=dict(orientation="h", y=1.12), yaxis=dict(title="OI"),
                              yaxis2=dict(title="Price", overlaying="y", side="right", showgrid=False))
            fig.update_xaxes(type="category", nticks=8)
            st.plotly_chart(fig, width="stretch", key="fut_oi_price")
            st.caption("OI ↑ + price ↑ = long buildup · OI ↑ + price ↓ = short buildup · "
                       "OI ↓ = unwinding / covering.")

            st.markdown("#### 3 · Premium / basis trend (%)")
            fig2 = go.Figure(go.Scatter(
                x=fdd.index, y=fdd["prem_pct"], name="Premium %",
                line=dict(color="#f59e0b", width=2), fill="tozeroy",
                fillcolor="rgba(245,158,11,.08)"))
            fig2.add_hline(y=0, line_dash="dot", line_color="#888")
            fig2.update_layout(height=220, margin=dict(l=0, r=0, t=10, b=0), showlegend=False,
                               yaxis_title="Premium %")
            fig2.update_xaxes(type="category", nticks=8)
            st.plotly_chart(fig2, width="stretch", key="fut_prem")
            st.caption("+ve = premium (contango — bullish/carry) · −ve = discount "
                       "(backwardation — bearish) · 0 line = future ≈ spot.")


# =========================================================================== #
# TAB — Option chain (Sensibull style)
# =========================================================================== #
elif section == "⛓️ Options":
    st.subheader(f"{symbol} — option chain")
    cdates = fno_dates(symbol)
    if not cdates:
        st.info(f"{symbol}: F&O data abhi nahi (Phase 2 backfill ke baad aayega).")
    else:
        cc1, cc2 = st.columns([2, 1])
        with cc1:
            odate = date_slider("F&O date", cdates, "chain_date")
        strike_win = cc2.slider("Strikes around ATM (± count, 0 = all)", 0, 25, 10)
        spot = q("SELECT close FROM prices WHERE symbol=? AND date=?",
                 (symbol, odate))
        spot_px = float(spot.iloc[0]["close"]) if not spot.empty else None

        def window_strikes(df):
            """Keep only ± strike_win strikes around ATM (0 = all)."""
            if strike_win == 0 or spot_px is None or df.empty:
                return df
            df = df.sort_values("strike").reset_index(drop=True)
            atm_i = int((df["strike"] - spot_px).abs().argmin())
            lo, hi = max(0, atm_i - strike_win), atm_i + strike_win + 1
            return df.iloc[lo:hi]

        # ---- OI SUMMARY (top): support/resistance · fresh OI · max pain + PCR · profile ----
        expiries_all = q("SELECT DISTINCT expiry FROM options WHERE symbol=? AND date=? "
                         "ORDER BY expiry", (symbol, odate))["expiry"].tolist()
        near_exp = expiries_all[0] if expiries_all else None
        nch = (q("SELECT strike, opt_type, oi, chg_oi FROM options WHERE symbol=? AND date=? "
                 "AND expiry=?", (symbol, odate, near_exp)) if near_exp else pd.DataFrame())
        if not nch.empty and spot_px:
            ce = nch[nch.opt_type == "CE"].groupby("strike")[["oi", "chg_oi"]].sum()
            pe = nch[nch.opt_type == "PE"].groupby("strike")[["oi", "chg_oi"]].sum()
            if not ce.empty and not pe.empty:
                st.markdown(f"#### 📊 OI summary — near expiry ({near_exp})")
                sup, res = pe["oi"].idxmax(), ce["oi"].idxmax()
                m1, m2, m3 = st.columns(3)
                m1.metric("🟢 Support (max PE OI)", f"{sup:,.0f}",
                          f"{_fmt(pe['oi'].max())} OI", delta_color="off")
                m2.metric("Spot", f"{spot_px:,.1f}")
                m3.metric("🔴 Resistance (max CE OI)", f"{res:,.0f}",
                          f"{_fmt(ce['oi'].max())} OI", delta_color="off")
                st.caption(f"Spot **{spot_px:,.1f}** ka expected range: **{sup:,.0f} (support) — "
                           f"{res:,.0f} (resistance)**. Max PE OI = neeche cushion · max CE OI = upar wall.")

                pea, cea = pe["chg_oi"].idxmax(), ce["chg_oi"].idxmax()
                st.markdown(
                    f"**Aaj ki fresh OI:** 🟢 PE **{pea:,.0f}** me {_fmt(pe['chg_oi'].max())} add "
                    f"(support ban rahi) · 🔴 CE **{cea:,.0f}** me {_fmt(ce['chg_oi'].max())} add "
                    "(resistance ban rahi)")

                mp_rows = []
                for e in expiries_all:
                    ech = q("SELECT opt_type, SUM(oi) oi FROM options WHERE symbol=? AND date=? "
                            "AND expiry=? GROUP BY opt_type", (symbol, odate, e))
                    dct = dict(zip(ech["opt_type"], ech["oi"]))
                    pcr_e = dct.get("PE", 0) / dct.get("CE", 1) if dct.get("CE") else float("nan")
                    mp = cached_max_pain(symbol, odate, e)
                    mp_rows.append({"Expiry": e, "Max pain": f"{mp:,.0f}" if mp else "—",
                                    "PCR": round(pcr_e, 2)})
                st.markdown("**Max pain + PCR (per expiry):**")
                st.dataframe(pd.DataFrame(mp_rows), hide_index=True, width="stretch")

                allk = sorted(set(ce.index) | set(pe.index))
                atm = min(range(len(allk)), key=lambda j: abs(allk[j] - spot_px))
                ks = allk[max(0, atm - 14): atm + 15]
                fig = go.Figure()
                fig.add_trace(go.Bar(x=ks, y=[float(ce["oi"].get(k, 0)) for k in ks],
                                     name="CE OI (resistance)", marker_color="rgba(244,63,94,.75)"))
                fig.add_trace(go.Bar(x=ks, y=[float(pe["oi"].get(k, 0)) for k in ks],
                                     name="PE OI (support)", marker_color="rgba(16,185,129,.75)"))
                fig.add_vline(x=spot_px, line_dash="dash", line_color="#facc15")
                fig.update_layout(barmode="group", height=300, margin=dict(l=0, r=0, t=10, b=0),
                                  legend=dict(orientation="h", y=1.12),
                                  xaxis_title="Strike", yaxis_title="OI")
                st.markdown("**OI profile** — CE (red) vs PE (green) walls · pili line = spot")
                st.plotly_chart(fig, width="stretch", key="oi_profile")
                st.divider()

        _optraw = q("""SELECT expiry, strike, opt_type, open, high, low, close, settle,
                              volume, value_lakh, oi, chg_oi FROM options
                       WHERE symbol=? AND date=? ORDER BY expiry, strike, opt_type""",
                    (symbol, odate))
        st.markdown(CHAIN_LEGEND, unsafe_allow_html=True)

        # SUM CHAIN (upar) — Sensibull style
        st.markdown("**Σ SUM CHAIN — teeno expiry ka total (strike-wise)**")
        sc = cached_sum_chain(symbol, odate)
        if not sc.empty:
            for col in ["oi_CE", "chg_oi_CE", "volume_CE",
                        "oi_PE", "chg_oi_PE", "volume_PE"]:
                if col not in sc.columns:
                    sc[col] = 0
            tot = sc[["oi_CE", "oi_PE"]].sum()
            pcr = tot["oi_PE"] / tot["oi_CE"] if tot["oi_CE"] else float("nan")
            st.markdown(
                f'<div class="oc-h"><span>spot <b>{spot_px:,.1f}</b></span>'
                f'<span>Total CE OI <b>{_fmt(tot["oi_CE"])}</b> · '
                f'PE OI <b>{_fmt(tot["oi_PE"])}</b> · PCR <b>{pcr:.2f}</b></span></div>',
                unsafe_allow_html=True)
            st.markdown(render_chain(window_strikes(sc), spot_px, has_ltp=False),
                        unsafe_allow_html=True)

        # Teen alag expiry chains — Sensibull style
        st.markdown("**Har expiry ka apna chain**")
        expiries = q("SELECT DISTINCT expiry FROM options WHERE symbol=? AND date=? "
                     "ORDER BY expiry", (symbol, odate))["expiry"].tolist()
        for i, exp in enumerate(expiries):
            mp = cached_max_pain(symbol, odate, exp)
            label = (f"Expiry {i+1} — {exp}" + (" (near)" if i == 0 else "")
                     + (f"   ·   max pain {mp:.0f}" if mp else ""))
            with st.expander(label, expanded=(i == 0)):
                # Pull the full per-strike data — the extra columns (OHLC, settle,
                # turnover) now render INSIDE the chain itself (extra=True), so no
                # separate raw table below. 'contracts' skipped (== volume).
                ch = q("""SELECT strike, opt_type, oi, chg_oi, volume, close,
                                 open, high, low, settle, value_lakh
                          FROM options WHERE symbol=? AND date=? AND expiry=?""",
                       (symbol, odate, exp))
                if ch.empty:
                    st.write("—")
                    continue
                piv = ch.pivot_table(index="strike", columns="opt_type",
                                     values=["oi", "chg_oi", "volume", "close",
                                             "open", "high", "low", "settle",
                                             "value_lakh"])
                piv.columns = [f"{a}_{b}" for a, b in piv.columns]
                piv = piv.reset_index()
                for c in ["oi_CE", "chg_oi_CE", "volume_CE",
                          "oi_PE", "chg_oi_PE", "volume_PE"]:
                    if c not in piv.columns:
                        piv[c] = 0
                st.markdown(
                    render_chain(window_strikes(piv), spot_px, has_ltp=True, extra=True),
                    unsafe_allow_html=True)
                st.caption("CALLS aur PUTS dono taraf: OI · Chg OI · Vol · LTP · "
                           "Open · High · Low · Settle · Turnover (₹) — ek hi chain me.")

# =========================================================================== #
# TAB — FII / DII / Pro / Client participant OI & Volume
# =========================================================================== #
elif section == "🏦 Participant":
    st.subheader("FII / DII / Pro / Client — F&O positions")

    # --- FII/DII CASH-segment provisional flows (₹ crore) — profile charts ---
    cash = q("SELECT date, category, buy, sell, net FROM fii_dii ORDER BY date")
    if not cash.empty:
        latest = cash["date"].max()
        today = cash[cash["date"] == latest]
        st.markdown(f"#### 💰 FII/DII cash flows — provisional (₹ Cr) · {latest}")
        CATS = [c for c in ["FII/FPI", "DII"] if c in today["category"].values]

        def _v(cat, col):
            r = today[today["category"] == cat]
            return float(r[col].iloc[0]) if not r.empty else 0.0

        fc1, fc2 = st.columns(2)
        with fc1:
            st.caption("**Buy / Sell / Net — aaj (₹ Cr)**")
            bfig = go.Figure()
            bfig.add_trace(go.Bar(x=CATS, y=[_v(c, "buy") for c in CATS],
                                  name="Buy", marker_color="#10b981"))
            bfig.add_trace(go.Bar(x=CATS, y=[_v(c, "sell") for c in CATS],
                                  name="Sell", marker_color="#f43f5e"))
            bfig.add_trace(go.Bar(x=CATS, y=[_v(c, "net") for c in CATS],
                                  name="Net", marker_color="#6366f1"))
            bfig.update_layout(barmode="group", height=250, margin=dict(l=0, r=0, t=6, b=0),
                               legend=dict(orientation="h", y=1.2), yaxis_title="₹ Cr")
            st.plotly_chart(bfig, width="stretch", key="fd_bsn")
        with fc2:
            st.caption("**Daily net flow (accumulating din)**")
            piv = cash.pivot_table(index="date", columns="category", values="net").sort_index()
            nfig = go.Figure()
            for cat, color in [("FII/FPI", "#6366f1"), ("DII", "#f59e0b")]:
                if cat in piv.columns:
                    nfig.add_trace(go.Bar(x=piv.index, y=piv[cat], name=cat, marker_color=color))
            nfig.add_hline(y=0, line_color="#6b7280")
            nfig.update_layout(barmode="group", height=250, margin=dict(l=0, r=0, t=6, b=0),
                               legend=dict(orientation="h", y=1.2), yaxis_title="Net ₹Cr")
            nfig.update_xaxes(type="category")
            st.plotly_chart(nfig, width="stretch", key="fd_flow")

        st.caption("🟢 Net **+** = **buying** · 🔴 net **−** = **selling**. NSE sirf latest din "
                   "publish karta hai (no archive) — history roz accumulate hoti hai.")
        if cash["date"].nunique() >= 3:
            st.caption("**🌊 Cumulative net** (window start se):")
            st.line_chart(piv.cumsum(), height=180)
        st.divider()

    pdates = q("SELECT DISTINCT date FROM participant ORDER BY date DESC")["date"].tolist()
    if not pdates:
        st.info("Participant data abhi nahi. `python fetch_participant.py` chalao "
                "(ya run_daily.py).")
    else:
        pdate = date_slider("Date", pdates, "fii_date")
        oi = q("SELECT * FROM participant WHERE date=? AND metric='oi'", (pdate,))

        # --- 🧠 Smart-money read: FII vs Client · L/S · per-participant (ALL segments) ---
        st.markdown("#### 🧠 Smart-money read (saare segments)")
        cm = {r["client_type"]: _seg_metrics(r) for _, r in oi.iterrows()}
        SEGS = ["Index Futures", "Stock Futures", "Index Options", "Stock Options"]
        # FII futures L/S ratios
        fut_ls, fr = {}, oi[oi["client_type"] == "FII"]
        if not fr.empty:
            for seg, lk, sk in [("Index Futures", "fut_idx_long", "fut_idx_short"),
                                ("Stock Futures", "fut_stk_long", "fut_stk_short")]:
                L, S = float(fr[lk].iloc[0] or 0), float(fr[sk].iloc[0] or 0)
                fut_ls[seg] = (L / S) if S else None

        st.markdown("**FII vs Client** — divergence + FII L/S (futures):")
        for seg in SEGS:
            fnet = cm.get("FII", {}).get(seg, (0, 0))[0]
            cnet = cm.get("Client", {}).get(seg, (0, 0))[0]
            fut = "Futures" in seg
            fw = ("🟢 long" if fnet >= 0 else "🔴 short") if fut else \
                 ("🟢 bullish" if fnet >= 0 else "🔴 bearish")
            cw = ("🟢 long" if cnet >= 0 else "🔴 short") if fut else \
                 ("🟢 bullish" if cnet >= 0 else "🔴 bearish")
            div = "**⚔️ divergence**" if (fnet >= 0) != (cnet >= 0) else "aligned"
            lst = ""
            if fut and fut_ls.get(seg):
                r_ = fut_ls[seg]
                lst = (f" · FII L/S **{r_:.2f}** "
                       f"({'heavily short' if r_ < 0.6 else 'heavily long' if r_ > 1.7 else 'balanced'})")
            st.markdown(f"- **{seg}:** FII {fw} vs Client {cw} — {div}{lst}")

        st.markdown("**Har participant ka net lean** (🟢 long/bullish · 🔴 short/bearish):")
        for ct in ["FII", "DII", "Pro", "Client"]:
            if ct not in cm:
                continue
            cells = [f"{sh} {'🟢' if cm[ct][seg][0] >= 0 else '🔴'}"
                     for seg, sh in zip(SEGS, ["IdxFut", "StkFut", "IdxOpt", "StkOpt"])]
            st.markdown(f"- **{ct}:** " + " · ".join(cells))
        st.divider()

        vol = q("SELECT * FROM participant WHERE date=? AND metric='vol'", (pdate,))
        st.markdown("#### 🎯 Positioning profile (participant × segment)")
        mchoice = st.radio("Metric", ["OI (standing positions)", "Volume (aaj traded)"],
                           horizontal=True, key="psent_metric")
        psrc = oi if mchoice.startswith("OI") else vol
        pm = {r["client_type"]: _seg_metrics(r) for _, r in psrc.iterrows()}
        SEGS = ["Index Futures", "Stock Futures", "Index Options", "Stock Options"]
        SHORT = ["IdxFut", "StkFut", "IdxOpt", "StkOpt"]
        PARTIS = [p for p in ["FII", "DII", "Pro", "Client"] if p in pm]
        PCOL = {"FII": "#6366f1", "DII": "#f59e0b", "Pro": "#a855f7", "Client": "#10b981"}

        # --- Top: combined "sum" chart (all participants, all segments) ---
        st.markdown("**Σ Sum view — sab participants, sab segments**")
        cfig = go.Figure()
        for p in PARTIS:
            cfig.add_trace(go.Bar(x=SHORT, y=[pm[p][s][0] for s in SEGS], name=p,
                                  marker_color=PCOL[p]))
        cfig.add_hline(y=0, line_color="#6b7280")
        cfig.update_layout(barmode="group", height=300, margin=dict(l=0, r=0, t=8, b=0),
                           legend=dict(orientation="h", y=1.15),
                           yaxis_title="Net (long+ / short−)")
        st.plotly_chart(cfig, width="stretch", key="psent_sum")
        st.caption("Har segment me kaun kitna **net long(+) / short(−)** "
                   "(options: bullish+ / bearish−). 0 line ke upar = bullish lean.")

        # --- Per-participant profile charts (alag-alag) ---
        st.markdown("**Har participant ka profile (alag-alag)**")
        cols = st.columns(len(PARTIS)) if PARTIS else []
        for col, p in zip(cols, PARTIS):
            nets = [pm[p][s][0] for s in SEGS]
            bcol = ["#10b981" if n >= 0 else "#f43f5e" for n in nets]
            pf = go.Figure(go.Bar(x=SHORT, y=nets, marker_color=bcol))
            pf.add_hline(y=0, line_color="#6b7280")
            pf.update_layout(height=230, margin=dict(l=0, r=0, t=28, b=0), showlegend=False,
                             title=dict(text=p, x=0.5, font=dict(size=14)))
            pf.update_xaxes(tickangle=-40)
            col.plotly_chart(pf, width="stretch", key=f"psent_{p}")
        st.caption("🟢 net long/bullish · 🔴 net short/bearish · bar height = strength. "
                   "Exact numbers neeche **Full raw data** me.")

        # --- Add-on: multi-day trend + cumulative flow (FII/DII net over time) ---
        series = participant_net_series()
        if not series.empty:
            win = series if lookback == "All" else series.tail(int(lookback))
            st.markdown(f"#### 📈 FII / DII trend — net F&O position (last {len(win)} din)")
            st.caption("Net = Long − Short (OI). Line 0 ke upar = net long (bullish), "
                       "niche = net short (bearish). Kitne din = sidebar slider se.")
            tfig = go.Figure()
            for ct, color in [("FII", "#6366f1"), ("DII", "#f59e0b")]:
                if ct in win.columns:
                    tfig.add_trace(go.Scatter(x=win.index, y=win[ct], name=ct,
                                   mode="lines", line=dict(color=color, width=2)))
            tfig.add_hline(y=0, line_dash="dot", line_color="#6b7280")
            tfig.update_layout(height=260, margin=dict(l=0, r=0, t=8, b=0),
                               legend=dict(orientation="h", y=1.15),
                               yaxis_title="Net (contracts)")
            tfig.update_xaxes(type="category", nticks=8)
            st.plotly_chart(tfig, width="stretch")

            st.markdown("#### 🌊 Cumulative flow — window start se net change")
            st.caption("Har participant ne window ke pehle din se ab tak net kitna "
                       "banaya/kata. Upar ja raha = longs accumulate kar raha.")
            flow = win - win.iloc[0]
            ffig = go.Figure()
            for ct, color in [("FII", "#6366f1"), ("DII", "#f59e0b"),
                              ("Pro", "#a855f7"), ("Client", "#10b981")]:
                if ct in flow.columns:
                    ffig.add_trace(go.Scatter(x=flow.index, y=flow[ct], name=ct,
                                   mode="lines", line=dict(color=color, width=2)))
            ffig.add_hline(y=0, line_dash="dot", line_color="#6b7280")
            ffig.update_layout(height=260, margin=dict(l=0, r=0, t=8, b=0),
                               legend=dict(orientation="h", y=1.15),
                               yaxis_title="Cumulative Δ net")
            ffig.update_xaxes(type="category", nticks=8)
            st.plotly_chart(ffig, width="stretch")

        with st.expander("📋 Full raw data (OI + Volume — saare 14 columns)"):
            raw = q("SELECT metric,client_type,fut_idx_long,fut_idx_short,"
                    "fut_stk_long,fut_stk_short,opt_idx_call_long,opt_idx_put_long,"
                    "opt_idx_call_short,opt_idx_put_short,opt_stk_call_long,"
                    "opt_stk_put_long,opt_stk_call_short,opt_stk_put_short,"
                    "total_long,total_short FROM participant WHERE date=? "
                    "ORDER BY metric,client_type", (pdate,))
            st.dataframe(raw, width="stretch", hide_index=True)

# =========================================================================== #
# TAB — overview (all-stock math stats)
# =========================================================================== #
elif section == "📊 Math stats":
    st.subheader("All F&O stocks — math stats")
    st.caption("Market-wide **India VIX** aur indices ab **🌐 Market** section me hain.")

    stats = q("""SELECT symbol, cum_return, cagr, ann_volatility, volatility,
                        sharpe, max_drawdown, beta, correlation, avg_deliv_pct,
                        zscore, pct_rank_52w, skew, kurtosis, daily_return, mean_return,
                        put_call_ratio, total_oi, oi_change, futures_premium,
                        futures_premium_pct
                 FROM stats""")
    if stats.empty:
        st.info("Stats abhi nahi. `python analysis.py` chalao.")
    else:
        # Add-ons: multi-window returns (1W/1M/3M/6M/1Y) + downside risk
        # (Sortino/VaR) + Calmar (= CAGR / |max drawdown|).
        stats = stats.merge(return_windows(), left_on="symbol", right_index=True, how="left")
        stats["calmar"] = stats["cagr"] / stats["max_drawdown"].abs().replace(0, np.nan)
        sort_opts = {
            "1-day return (zyada → kam)": ("daily_return", False),
            "1-week return (zyada → kam)": ("ret_1w", False),
            "1-month return (zyada → kam)": ("ret_1m", False),
            "3-month return (zyada → kam)": ("ret_3m", False),
            "6-month return (zyada → kam)": ("ret_6m", False),
            "1-year return (zyada → kam)": ("ret_1y", False),
            "Volatility (zyada → kam)": ("ann_volatility", False),
            "Return — poora period (zyada → kam)": ("cum_return", False),
            "Sharpe (best → worst)": ("sharpe", False),
            "Sortino (best → worst)": ("sortino", False),
            "Calmar (best → worst)": ("calmar", False),
            "VaR 5% (zyada risk → kam)": ("var5", False),
            "Max drawdown (bada → chhota)": ("max_drawdown", True),
            "Beta (zyada → kam)": ("beta", False),
            "Correlation vs Nifty (zyada → kam)": ("correlation", False),
            "Avg delivery % (zyada → kam)": ("avg_deliv_pct", False),
            "52w %ile (high → low)": ("pct_rank_52w", False),
            "PCR (zyada → kam)": ("put_call_ratio", False),
            "Futures premium % (premium → discount)": ("futures_premium_pct", False),
            "Symbol (A → Z)": ("symbol", True),
        }
        choice = st.selectbox("Sort by", list(sort_opts.keys()), index=0)
        col, asc = sort_opts[choice]
        stats = stats.sort_values(col, ascending=asc, na_position="last")
        st.markdown(render_overview_table(stats), unsafe_allow_html=True)
        st.caption("Green = up / positive, red = down / negative · **1D/1W/1M/3M/6M/1Y%** "
                   "= momentum across timeframes · **Sortino** = downside-adjusted return · "
                   "**Calmar** = CAGR ÷ max-drawdown · **VaR%** = 5% worst-day loss · bars = "
                   "volatility & 52-week position. Split/bonus-adjusted. Right scroll = saare columns.")

# =========================================================================== #
# TAB — Market (NIFTY / sectoral indices + VIX + our-stocks sector performance)
# =========================================================================== #
elif section == "🌐 Market":
    st.subheader("Market — indices, VIX & sector performance")
    st.caption("Poore market ka view — jo index data (NIFTY / BANK / sectoral) roz "
               "aata hai. Charts last 60 trading din ke.")

    # --- headline index charts ---
    headline = ["Nifty 50", "Nifty Bank", "Nifty Financial Services"]
    hcols = st.columns(3)
    for hc, nm in zip(hcols, headline):
        s = index_series(nm)
        if s.empty:
            continue
        last = s.iloc[-1]
        hc.metric(nm, f"{last['close']:,.1f}",
                  f"{last['chg_pct']:+.2f}%" if pd.notna(last["chg_pct"]) else None)
        w = s.tail(60)
        up = w["close"].iloc[-1] >= w["close"].iloc[0]
        col = "#10b981" if up else "#f43f5e"
        fig = go.Figure(go.Scatter(
            x=w["date"], y=w["close"], mode="lines",
            line=dict(color=col, width=2), fill="tozeroy",
            fillcolor=("rgba(16,185,129,.08)" if up else "rgba(244,63,94,.08)"),
            hoverinfo="x+y", name=""))
        fig.update_layout(height=140, margin=dict(l=0, r=0, t=6, b=0), showlegend=False)
        fig.update_xaxes(type="category", nticks=4, showticklabels=False)
        hc.plotly_chart(fig, width="stretch", key=f"ixchart_{nm}")

    # --- India VIX ---
    _vix = vix_series()
    if not _vix.empty:
        vl = _vix.iloc[-1]
        st.markdown(f"#### India VIX — {vl['close']:.2f} "
                    f"({vl['chg_pct']:+.2f}%)" if pd.notna(vl["chg_pct"]) else "#### India VIX")
        vw = _vix.tail(60)
        vfig = go.Figure(go.Scatter(
            x=vw["date"], y=vw["close"], mode="lines",
            line=dict(color="#f59e0b", width=2), fill="tozeroy",
            fillcolor="rgba(245,158,11,.08)", hoverinfo="x+y", name=""))
        vfig.update_layout(height=130, margin=dict(l=0, r=0, t=6, b=0), showlegend=False)
        vfig.update_xaxes(type="category", nticks=6)
        st.plotly_chart(vfig, width="stretch", key="ixchart_vix")
        st.caption("**India VIX** = expected 30-day volatility (fear gauge). "
                   "High = fear/uncertainty · low = calm.")

    # --- broad + sectoral snapshot tables ---
    st.markdown("#### Broad indices")
    st.dataframe(index_snapshot(BROAD_IX), hide_index=True, width="stretch")

    st.markdown("#### Sectoral indices — kaunsa sector chala (1D / 1W / 1M %)")
    sec_snap = index_snapshot(SECTORAL_IX)
    if not sec_snap.empty:
        sec_snap = sec_snap.sort_values("1D %", ascending=False)
    st.dataframe(sec_snap, hide_index=True, width="stretch")
    st.caption("1D se sorted — aaj ka sector rotation. Green = up. NSE index data (roz update).")

    st.divider()
    st.markdown("### 🏭 Sector performance — our F&O stocks (avg per sector)")
    base = q("SELECT symbol, ann_volatility, put_call_ratio, daily_return FROM stats")
    if base.empty:
        st.info("Stats abhi nahi. `python analysis.py` chalao.")
    else:
        df = base.merge(return_windows().reset_index(), on="symbol", how="left")
        df["ret_1d"] = df["daily_return"] * 100
        df["ann_vol"] = df["ann_volatility"] * 100
        df["sector"] = df["symbol"].map(sectors.sector_of)
        agg = (df.groupby("sector").agg(
                   n=("symbol", "count"), ret_1d=("ret_1d", "mean"),
                   ret_1w=("ret_1w", "mean"), ret_1m=("ret_1m", "mean"),
                   ret_1y=("ret_1y", "mean"), ann_vol=("ann_vol", "mean"),
                   pcr=("put_call_ratio", "mean")).reset_index()
                 .sort_values("ret_1m", ascending=False))

        st.markdown("#### 📋 Trailing performance (as of latest — avg 1D/1W/1M/1Y)")
        st.markdown(render_sector_table(agg), unsafe_allow_html=True)

        # drill-down — stocks in a sector
        st.markdown("#### 🔎 Sector drill-down")
        sec = st.selectbox("Sector chuno", agg["sector"].tolist())
        show = (df[df["sector"] == sec]
                [["symbol", "ret_1d", "ret_1w", "ret_1m", "ret_1y", "ann_vol",
                  "put_call_ratio"]]
                .rename(columns={"ret_1d": "1D%", "ret_1w": "1W%", "ret_1m": "1M%",
                                 "ret_1y": "1Y%", "ann_vol": "Ann Vol%",
                                 "put_call_ratio": "PCR"})
                .sort_values("1M%", ascending=False).round(2))
        st.caption(f"**{sec}** — {len(show)} stocks (1M return se sorted)")
        st.dataframe(show, width="stretch", hide_index=True)

    st.divider()
    # --- Day-by-day: slider picks a date → that day's sector returns ---
    pdates = q("SELECT DISTINCT date FROM prices ORDER BY date DESC")["date"].tolist()
    seld = date_slider("📅 Kis din ka sector performance (din-b-din)", pdates, "sector_date")
    dayagg = sector_daily_returns()
    dayagg = dayagg[dayagg["date"] == seld].sort_values("avg_ret", ascending=False)
    st.markdown(f"#### 📊 {seld} — us din har sector ka avg 1-day return")
    if dayagg.empty:
        st.info("Us din ka sector data nahi.")
    else:
        dfig = go.Figure(go.Bar(
            x=dayagg["avg_ret"], y=dayagg["sector"], orientation="h",
            marker_color=["#10b981" if v >= 0 else "#f43f5e" for v in dayagg["avg_ret"]],
            text=[f"{v:+.2f}%" for v in dayagg["avg_ret"]], textposition="auto"))
        dfig.update_layout(height=420, margin=dict(l=0, r=0, t=8, b=0),
                           xaxis_title=f"Avg 1-day return on {seld} %",
                           yaxis=dict(autorange="reversed"))
        st.plotly_chart(dfig, width="stretch")
        st.caption("Slider se **pichhle din scrub** karo — us din kaunsa sector chala/gira "
                   "(din-b-din sector rotation).")


# =========================================================================== #
# TAB — Compare (multi-stock side-by-side)
# =========================================================================== #
elif section == "⚖️ Compare":
    st.subheader("Multi-stock compare — side by side")
    picks = st.multiselect("Stocks compare karo (2–5)", all_symbols(),
                           default=[symbol], max_selections=5)
    if len(picks) < 2:
        st.info("Kam se kam **2 stocks** chuno compare ke liye (upar dropdown se).")
    else:
        # --- Normalized price chart (rebased to 100 at window start) ---
        win = None if lookback == "All" else int(lookback)
        palette = ["#6366f1", "#f59e0b", "#10b981", "#f43f5e", "#a855f7"]
        fig = go.Figure()
        for i, s in enumerate(picks):
            h = stock_history(s)
            if h.empty:
                continue
            v = h if win is None else h.tail(win)
            if v.empty or v["close"].iloc[0] == 0:
                continue
            fig.add_trace(go.Scatter(
                x=v["date"], y=v["close"] / v["close"].iloc[0] * 100, name=s,
                mode="lines", line=dict(color=palette[i % len(palette)], width=2)))
        fig.add_hline(y=100, line_dash="dot", line_color="#6b7280")
        fig.update_layout(height=340, margin=dict(l=0, r=0, t=10, b=0),
                          legend=dict(orientation="h", y=1.12),
                          yaxis_title="Rebased to 100")
        fig.update_xaxes(type="category", nticks=8)
        st.plotly_chart(fig, width="stretch")
        st.caption("Price **rebased to 100** at window start — upar wali line = zyada return "
                   "(window = sidebar 'Kitne din dekhne hain').")

        # --- Side-by-side stats table ---
        ph = ",".join("?" * len(picks))
        comp = q(f"""SELECT symbol, daily_return, cagr, ann_volatility, sharpe, beta,
                            max_drawdown, pct_rank_52w, put_call_ratio
                     FROM stats WHERE symbol IN ({ph})""", tuple(picks))
        cl = q(f"SELECT symbol, close FROM prices WHERE date=(SELECT MAX(date) FROM prices) "
               f"AND symbol IN ({ph})", tuple(picks))
        comp = (comp.merge(cl, on="symbol", how="left")
                    .merge(return_windows().reset_index(), on="symbol", how="left")
                    .set_index("symbol").reindex(picks))
        st.markdown("#### 📊 Side-by-side stats")
        st.markdown(render_compare(comp), unsafe_allow_html=True)


# =========================================================================== #
# TAB — Backtest (user-defined option strategies, across all stocks)
# =========================================================================== #
elif section == "🎯 Backtest":
    st.subheader("🎯 Strategy backtest")
    strat = st.selectbox("Strategy", ["Momentum buying"], key="bt_strat")
    st.caption("Long strangle (OTM+3 CE+PE) on a multi-factor momentum burst · "
               "trailing +100%/−30% · loss −50% · time min(10d, expiry−5). "
               "Full rules: **strategy.md**. ⚠️ Research/education only — daily (EOD) "
               "data, **koi trading advice nahi**.")

    if st.button("▶️ Run backtest (all ~210 stocks · pehli baar ~1–2 min)", key="bt_run"):
        st.session_state["bt_done"] = True
    if not st.session_state.get("bt_done"):
        st.info("Upar **Run backtest** dabao — sab F&O stocks pe strategy chalegi "
                "(result cache ho jayega, dobara instant).")
    else:
        with st.spinner("Backtest chal raha hai (sab stocks)…"):
            trades, per_stock, overall, eq = cached_backtest(strat)

        if trades is None or trades.empty:
            st.warning("Koi trade nahi bana (data adhoora ho sakta hai — options build "
                       "poora hone ke baad phir chalao).")
        else:
            # --- Overall summary cards ---
            st.markdown(f"#### 📊 Overall — *{strat}*")
            lots = backtest.MOMENTUM_PARAMS.get("lots", 2)
            m = st.columns(6)
            m[0].metric(f"Total P&L (₹ · {lots} lot)", f"₹{overall['total_rupee']:,}")
            m[1].metric("Avg ₹ / trade", f"₹{overall['avg_rupee']:,}")
            m[2].metric("Trades", f"{overall['trades']:,}")
            m[3].metric("Win rate", f"{overall['win_rate']}%")
            m[4].metric("Avg P&L", f"{overall['avg_pnl_pct']}%")
            m[5].metric("Best / Worst", f"{overall['best_pct']:.0f}% / {overall['worst_pct']:.0f}%")
            st.caption(f"{overall['stocks']} stocks · exit breakdown: " + " · ".join(
                f"**{k}** {v}" for k, v in overall["exits"].items())
                + f". ₹ = premium-points × derived NSE lot-size × {lots} lots "
                "(approximate — points/% exact hain).")

            # --- Combined equity curve (cumulative rupee P&L) ---
            eq2 = eq.copy()
            eq2["cum_rupee"] = (trades.sort_values("exit_date")["pnl_rupee"].cumsum().values
                                if "pnl_rupee" in trades.columns else eq2["cum_pts"])
            st.markdown(f"**📈 Equity curve** — cumulative ₹ P&L ({lots} lot, exit-date wise)")
            st.line_chart(eq2.set_index("exit_date")["cum_rupee"], height=260)

            # --- Per-stock drill-down ---
            st.markdown("#### 🔎 Per-stock")
            syms = per_stock["symbol"].tolist()
            sel = st.selectbox("Stock", syms, key="bt_sym")
            srow = per_stock[per_stock["symbol"] == sel].iloc[0]
            c = st.columns(5)
            c[0].metric("Total ₹", f"₹{int(srow['total_rupee']):,}")
            c[1].metric("Trades", int(srow["trades"]))
            c[2].metric("Win rate", f"{srow['win_rate']}%")
            c[3].metric("Avg P&L", f"{srow['avg_pnl_pct']}%")
            c[4].metric("Best / Worst", f"{srow['best_pct']:.0f}% / {srow['worst_pct']:.0f}%")
            st_t = trades[trades["symbol"] == sel].copy()
            steq = st_t.sort_values("exit_date")
            steq["cum_rupee"] = steq["pnl_rupee"].cumsum()
            st.line_chart(steq.set_index("exit_date")["cum_rupee"], height=200)
            st.caption("Trade log (is stock ke sab trades):")
            st.dataframe(st_t[["entry_date", "exit_date", "expiry", "ce_strike", "pe_strike",
                               "entry_prem", "exit_prem", "pnl_pct", "pnl_rupee", "days_held",
                               "exit_reason"]]
                         .rename(columns={"entry_date": "Entry", "exit_date": "Exit",
                                          "expiry": "Expiry", "ce_strike": "CE", "pe_strike": "PE",
                                          "entry_prem": "In₹", "exit_prem": "Out₹",
                                          "pnl_pct": "P&L%", "pnl_rupee": f"₹({lots}lot)",
                                          "days_held": "Days", "exit_reason": "Why"}),
                         hide_index=True, width="stretch")

            # --- All-stocks sortable table ---
            st.markdown("#### 🗂️ All stocks (sortable — column header click karo)")
            st.dataframe(per_stock[["symbol", "trades", "win_rate", "total_rupee",
                                    "avg_pnl_pct", "best_pct", "worst_pct"]].rename(columns={
                "symbol": "Stock", "trades": "Trades", "win_rate": "Win%",
                "total_rupee": f"Total ₹ ({lots}lot)", "avg_pnl_pct": "Avg%",
                "best_pct": "Best%", "worst_pct": "Worst%"}),
                hide_index=True, width="stretch", height=420)


# =========================================================================== #
# TAB — Data health (pipeline status, gaps, row counts, nulls)
# =========================================================================== #
elif section == "🩺 Data health":
    st.subheader("Data health — kya data hai, kahan gap")
    st.caption("Data pipeline status — latest dates, gaps (pending/error), row counts, nulls.")

    dsmap = {"equity": "Equity", "fno": "F&O", "participant": "Participant",
             "vix": "India VIX", "indices": "Indices", "fiidii": "FII/DII cash",
             "secban": "F&O ban"}
    cols = st.columns(len(dsmap))
    for i, (ds, label) in enumerate(dsmap.items()):
        d = q("SELECT MAX(date) d FROM ingest_log WHERE dataset=? AND status='ok'", (ds,))
        cols[i].metric(f"{label} — latest", d["d"].iloc[0] or "—")

    # Current F&O ban list (latest checked day)
    sbday = q("SELECT MAX(date) d FROM ingest_log WHERE dataset='secban' AND status='ok'")["d"].iloc[0]
    if sbday:
        banned = q("SELECT symbol FROM secban WHERE date=? ORDER BY symbol", (sbday,))["symbol"].tolist()
        if banned:
            st.error(f"🚫 **F&O ban ({sbday})** — {len(banned)} stock: {', '.join(banned)}")
        else:
            st.success(f"✅ F&O ban ({sbday}) — NIL (koi stock ban me nahi).")

    st.markdown("#### Ingest status (per dataset)")
    st.caption("ok = data hai · holiday = market band · **pending/error = gap (agle run pe retry)**")
    srows = []
    for ds, label in dsmap.items():
        cnt = q("SELECT status, COUNT(*) n FROM ingest_log WHERE dataset=? GROUP BY status", (ds,))
        cd = dict(zip(cnt["status"], cnt["n"]))
        srows.append({"Dataset": label, "ok": cd.get("ok", 0), "holiday": cd.get("holiday", 0),
                      "pending": cd.get("pending", 0), "error": cd.get("error", 0)})
    st.dataframe(pd.DataFrame(srows), hide_index=True, width="stretch")

    gaps = q("SELECT dataset, date, status FROM ingest_log "
             "WHERE status IN ('pending','error') ORDER BY date DESC")
    if gaps.empty:
        st.success("✅ Koi gap nahi — saara data ok/holiday. Pipeline clean.")
    else:
        st.warning(f"⚠️ {len(gaps)} din pending/error — agle `python run_daily.py` pe auto-retry honge.")
        st.dataframe(gaps, hide_index=True, width="stretch")

    st.markdown("#### Tables & data quality")
    checks = []
    for t in ["prices", "futures", "participant", "stats", "vix", "indices",
              "fii_dii", "secban", "deals", "short_selling", "corp_actions"]:
        n = q(f"SELECT COUNT(*) n FROM {t}")["n"].iloc[0]
        checks.append({"Table": t, "rows": int(n)})
    st.dataframe(pd.DataFrame(checks), hide_index=True, width="stretch")
    nc = q("SELECT COUNT(*) n FROM prices WHERE close IS NULL")["n"].iloc[0]
    nb = q("SELECT COUNT(*) n FROM stats WHERE beta IS NULL")["n"].iloc[0]
    st.caption(f"Null checks — **prices.close** nulls: {nc} · **stats.beta** nulls: {nb} "
               "(0 = clean). `options` table (~18M rows) ka count skip kiya (slow scan). "
               "Backup ke liye: `python backup_db.py`.")
