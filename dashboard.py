# -*- coding: utf-8 -*-
"""
dashboard.py — date-wise NSE dashboard (Streamlit), QuantCalc-style dark theme.

Run:  streamlit run dashboard.py

Sidebar navigation = 6 sections (5 data-types + 1 screener):
  1. Equity / Cash      — daily OHLCV + delivery + candle chart
  2. Futures            — all expiries: OHLC/settle/OI/premium + Σ total
  3. Options            — Sensibull sum-chain + per-expiry chains (OHLC/settle inside)
  4. Participant        — FII/DII/Pro/Client sentiment (OI+Vol) + trend + flow
  5. Math stats         — all-stock statistics table (returns/vol/beta/… + 1W/1M)
  6. Sectors            — sector-wise performance + drill-down
  7. Index / Market     — NIFTY / sectoral indices + India VIX
  8. Compare            — multi-stock side-by-side
  9. Data health        — pipeline status, gaps, row counts
"""
import os
import json

import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go

import db
import analysis
import sectors
from render import (  # presentation layer (HTML tables + CSS)
    _fmt, CHAIN_LEGEND, _participant_nets,
    render_chain, render_stock_table, render_overview_table,
    render_futures_table, render_participant_sentiment,
    render_compare, render_sector_table,
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
.st-key-navmenu div[role="radiogroup"]{gap:6px;}
.st-key-navmenu label[data-testid="stRadioOption"]{
  display:flex;align-items:center;width:100%;
  padding:10px 14px;border-radius:10px;border:1px solid transparent;
  color:var(--qc-text2);cursor:pointer;transition:all .2s;}
.st-key-navmenu label[data-testid="stRadioOption"] p{
  color:inherit;font-weight:600;font-size:.95rem;}
.st-key-navmenu label[data-testid="stRadioOption"]:hover{
  color:#f3f4f6;background:rgba(255,255,255,.03);border-color:rgba(255,255,255,.05);}
/* hide the actual radio circle — keep only the label text */
.st-key-navmenu label[data-testid="stRadioOption"] > div > div > div:first-child{
  display:none;}
/* active item — indigo glow (Streamlit marks it data-selected) */
.st-key-navmenu label[data-testid="stRadioOption"][data-selected="true"]{
  color:#f3f4f6;background:rgba(99,102,241,.15);
  border-color:rgba(99,102,241,.35);box-shadow:0 2px 8px rgba(0,0,0,.15);}
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

**🏭 Sectors** — 17 macro-sectors ka avg performance (1D/1W/1M/1Y) + drill-down.

**📈 Index / Market** — NIFTY 50 / BANK / FINNIFTY charts + India VIX + broad & sectoral
index table (1D/1W/1M change). Market-wide view.

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


def date_slider(label, dates_desc, key, window=60):
    """Slider over the most recent `window` trading days (default = latest).
    Slide left = older. Falls back to a caption if only one date exists."""
    recent = list(reversed(dates_desc[:window]))     # ascending, latest last
    if not recent:
        return None
    if len(recent) == 1:
        st.caption(f"{label}: {recent[0]}")
        return recent[0]
    return st.select_slider(label, options=recent, value=recent[-1], key=key)


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


# Curated index lists for the Index / Market view (all verified present in DB).
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
    px = q("SELECT date, close, prev_close, volume, deliv_pct FROM prices "
           "WHERE symbol=? ORDER BY date", (symbol,))
    if px.empty:
        return px
    d = px.set_index("date")
    d["chg_pct"] = (d["close"] / d["prev_close"] - 1) * 100

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


# --------------------------------------------------------------------------- #
# Sidebar — QuantCalc-style logo + navigation menu + stock controls
# --------------------------------------------------------------------------- #
SECTIONS = ["📈 Equity / Cash", "🔬 Analysis", "🔮 Futures", "⛓️ Options",
            "🏦 Participant", "📊 Math stats", "🏭 Sectors", "📈 Index / Market",
            "⚖️ Compare", "🩺 Data health"]

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
    section = st.radio("Navigation", SECTIONS, index=0,
                       label_visibility="collapsed", key="navmenu")

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
        st.caption("Futures 🔮 aur Option chain ⛓️ sidebar ke alag sections me hain.")

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
        sel = date_slider("📅 Kis din ka analysis (slider se din badlo)",
                          dates[::-1], "an_date", window=len(dates))
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
        oi_val = ("—" if pd.isna(row.get("fut_oi"))
                  else f"OI {_fmt(row['fut_oi'])}" + (f" ({od:+.1f}%)" if od is not None else ""))
        reads = [
            ("Price", f"{row['close']:,.1f} ({row['chg_pct']:+.2f}%)"
                if pd.notna(row['chg_pct']) else f"{row['close']:,.1f}",
             _read_move(row.get("chg_pct"))),
            ("Delivery %", f"{row['deliv_pct']:.1f}%" if pd.notna(row.get("deliv_pct")) else "—",
             _read_deliv(row.get("deliv_pct"), ddv)),
            ("F&O buildup", oi_val, _read_buildup(row.get("chg_pct"), row.get("fut_chg_oi"))),
            ("Futures premium", f"{row['prem_pct']:+.2f}%" if pd.notna(row.get("prem_pct")) else "—",
             _read_prem(row.get("prem_pct"))),
            ("Options PCR", f"{row['pcr']:.2f}" if pd.notna(row.get("pcr")) else "—",
             _read_pcr(row.get("pcr"), pcr_d)),
        ]
        md = ["| Signal | Aaj | Matlab |", "|---|---|---|"]
        for name, val, (txt, cls) in reads:
            md.append(f"| **{name}** | {val} | {_EMO[cls]} {txt} |")
        st.markdown("\n".join(md))

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

        # --- 1. Futures — teeno expiry ka total + changes ---
        st.markdown("#### 1 · Futures — teeno expiry ka total + changes")
        fut = q("""SELECT expiry, open, high, low, close, settle,
                          contracts, value_lakh, oi, chg_oi
                   FROM futures WHERE symbol=? AND date=? ORDER BY expiry""",
                (symbol, fdate))
        st.markdown(render_futures_table(fut, fspot_px), unsafe_allow_html=True)


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

        _optraw = q("""SELECT expiry, strike, opt_type, open, high, low, close, settle,
                              volume, value_lakh, oi, chg_oi FROM options
                       WHERE symbol=? AND date=? ORDER BY expiry, strike, opt_type""",
                    (symbol, odate))
        st.markdown(CHAIN_LEGEND, unsafe_allow_html=True)

        # SUM CHAIN (upar) — Sensibull style
        st.markdown("**Σ SUM CHAIN — teeno expiry ka total (strike-wise)**")
        sc = analysis.sum_chain(symbol, odate)
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
            mp = analysis.max_pain(symbol, odate, exp)
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

    # --- FII/DII CASH-segment provisional flows (₹ crore) ---
    cash = q("SELECT date, category, buy, sell, net FROM fii_dii ORDER BY date")
    if not cash.empty:
        latest = cash["date"].max()
        today = cash[cash["date"] == latest]
        st.markdown(f"#### 💰 FII/DII cash flows — provisional (₹ Cr) · {latest}")
        mc = st.columns(2)
        for i, cat in enumerate(["FII/FPI", "DII"]):
            row = today[today["category"] == cat]
            if not row.empty:
                net = float(row["net"].iloc[0])
                mc[i].metric(f"{cat} net", f"₹{net:+,.0f} Cr",
                             delta="buying" if net >= 0 else "selling")
        ndays = cash["date"].nunique()
        if ndays >= 3:
            piv = cash.pivot_table(index="date", columns="category", values="net").sort_index()
            st.line_chart(piv.cumsum(), height=200)
            st.caption(f"Cumulative net over {ndays} din. Positive = net buying.")
        else:
            st.caption("ℹ️ NSE sirf latest din publish karta hai (no archive) — ye "
                       "aaj se aage roz accumulate hoga. History abhi ban rahi hai.")
        st.divider()

    pdates = q("SELECT DISTINCT date FROM participant ORDER BY date DESC")["date"].tolist()
    if not pdates:
        st.info("Participant data abhi nahi. `python fetch_participant.py` chalao "
                "(ya run_daily.py).")
    else:
        pdate = date_slider("Date", pdates, "fii_date")
        prevd = q("SELECT MAX(date) d FROM participant WHERE date<? AND metric='oi'",
                  (pdate,))["d"].iloc[0]
        oi = q("SELECT * FROM participant WHERE date=? AND metric='oi'", (pdate,))
        prev_oi = (q("SELECT * FROM participant WHERE date=? AND metric='oi'", (prevd,))
                   if prevd else None)

        st.caption("**Bearish ‹—› Bullish** = net long/short lean (OI). **Net OI** = net "
                   "position (futures L−S; options bullish−bearish). **Change** = pichhle "
                   "din se net ka change (aaj kya kiya).")
        # FII quick read
        cn = _participant_nets(oi)
        pn = _participant_nets(prev_oi) if prev_oi is not None else {}
        if "FII" in cn and "FII" in pn:
            dnet = cn["FII"]["tnet"] - pn["FII"]["tnet"]
            lean = "bullish 🟢" if dnet >= 0 else "bearish 🔴"
            _c = "#10b981" if dnet >= 0 else "#f43f5e"
            st.markdown(
                f"**FII ne aaj:** overall net **{dnet:+,.0f}** vs pichhla din → "
                f"<span style='color:{_c};font-weight:600'>{lean}</span>",
                unsafe_allow_html=True)

        vol = q("SELECT * FROM participant WHERE date=? AND metric='vol'", (pdate,))
        prev_vol = (q("SELECT * FROM participant WHERE date=? AND metric='vol'", (prevd,))
                    if prevd else None)
        st.markdown("#### 🎯 Positioning sentiment (participant × segment · OI + Volume)")
        st.caption("Har segment ki 2 lines — **OI** (standing position) + **Vol** (us din "
                   "ka traded direction). Bar = long/short lean · Net · Change (vs pichhla din).")
        st.markdown(render_participant_sentiment(oi, prev_oi, vol, prev_vol),
                    unsafe_allow_html=True)

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
    st.caption("Market-wide **India VIX** aur indices ab **📈 Index / Market** section me hain.")

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
# TAB — Sectors (sector-wise performance)
# =========================================================================== #
elif section == "🏭 Sectors":
    st.subheader("Sector-wise performance")

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

    st.divider()
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

# =========================================================================== #
# TAB — Index / Market (NIFTY + sectoral indices, VIX)
# =========================================================================== #
elif section == "📈 Index / Market":
    st.subheader("Index / Market — NIFTY & sectoral indices")
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
