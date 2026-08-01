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
  6. Next-day shortlist — Momentum + Mean-reversion screener + backtest (educational)
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
    render_picks, render_chain, render_stock_table, render_overview_table,
    render_futures_table, render_participant_sentiment, render_est_split,
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


def download_csv(df, label, filename, key=None):
    """Small CSV download button for a DataFrame."""
    if df is None or df.empty:
        return
    st.download_button(label, df.to_csv(index=False).encode("utf-8"),
                       file_name=filename, mime="text/csv", key=key)

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

**🎯 Next-day shortlist** — Aaj ke data se **kal ke liye** shortlist. 2 strategies:
**Momentum** (continuation) + **Mean-reversion** (contrarian), har ek me top 3 UP/DOWN
(momentum + F&O + delivery% + PCR score, liquid stocks). **Backtest hit-rate** + date
slider (past picks ✓/✗). ⚠️ **Educational/research — trading advice nahi.**

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

- **Estimated participant split**: real per-stock FII/DII data publicly nahi milta, isliye
  market-wide % ko stock ke futures OI par **proportionally** lagaya — **rough estimate**,
  exact nahi. (FII/DII section ka data **real** hai, bas market-wide.)
- **Split/bonus**: NSE prev_close adjust nahi hota; dashboard auto-detect karke adjust
  karta hai (fake −90% move hataata). Ticker me `|move|>30%` drop hote hain.
- **Sharpe** yahan simple `mean/std` (daily, rf=0) — thumb-rule comparison ke liye.

## 🔄 Data update
Har trading din market close ke baad (~**6:30 PM IST**) naya data auto-add. Weekend/holiday
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
    df = analysis.adjust_ohlc(df)
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
def window_returns():
    """1-week (5 trading-day) and 1-month (20 trading-day) return % per stock,
    split/bonus-adjusted. Index = symbol."""
    px = q("SELECT symbol, date, close FROM prices")
    if px.empty:
        return pd.DataFrame(columns=["ret_1w", "ret_1m"])
    wide = px.pivot(index="date", columns="symbol", values="close").sort_index()
    wide = analysis.adjust_for_splits(wide)          # split-adjusted closes

    def wret(n):
        if len(wide) <= n:
            return pd.Series(index=wide.columns, dtype=float)
        return (wide.iloc[-1] / wide.iloc[-1 - n] - 1) * 100

    return pd.DataFrame({"ret_1w": wret(5), "ret_1m": wret(20)})


@st.cache_data(ttl=300)
def extra_stats():
    """Longer-window returns (3M/6M/1Y) + downside risk (Sortino, 5% VaR) per
    stock, from split-adjusted daily closes. Index = symbol. (Calmar is derived
    in the Math-stats view from cagr / |max_drawdown|.)"""
    px = q("SELECT symbol, date, close FROM prices")
    if px.empty:
        return pd.DataFrame(columns=["ret_3m", "ret_6m", "ret_1y", "sortino", "var5"])
    wide = analysis.adjust_for_splits(
        px.pivot(index="date", columns="symbol", values="close").sort_index())
    rets = wide.pct_change()
    n = len(wide)

    def wret(k):
        if n <= k:
            return pd.Series(index=wide.columns, dtype=float)
        return (wide.iloc[-1] / wide.iloc[-1 - k] - 1) * 100

    downside = rets[rets < 0].std()                       # std of negative days only
    return pd.DataFrame({
        "ret_3m": wret(63), "ret_6m": wret(126), "ret_1y": wret(252),
        "sortino": rets.mean() / downside,                # mean / downside deviation
        "var5": -rets.quantile(0.05) * 100,               # 5% historical VaR (loss %)
    })


@st.cache_data(ttl=300)
def vix_series():
    """India VIX daily series (market volatility / fear gauge)."""
    return q("SELECT date, open, high, low, close, chg_pct FROM vix ORDER BY date")


# --------------------------------------------------------------------------- #
# Next-day shortlist — statistical screener (educational, NOT advice)
# --------------------------------------------------------------------------- #


@st.cache_data(ttl=600)
def shortlist_data(n_liquid=40, window=60):
    """Per (symbol,date) signals + Momentum/Mean-reversion scores for the liquid
    universe over `window` trading days, plus next-day return (for backtesting).
    Signals: price momentum (1D/1W) · F&O positioning (OI buildup + premium) ·
    delivery% · options PCR. Pure statistics — no advice."""
    alldates = q("SELECT DISTINCT date FROM prices ORDER BY date")["date"].tolist()
    if len(alldates) < 30:
        return pd.DataFrame()
    win_dates = set(alldates[-window:])
    start = alldates[-(window + 30)] if len(alldates) > window + 30 else alldates[0]
    recent = alldates[-20]
    liq = q("""SELECT symbol, AVG(turnover) t FROM prices WHERE date >= ?
               GROUP BY symbol ORDER BY t DESC LIMIT ?""", (recent, n_liquid))
    syms = liq["symbol"].tolist()
    if not syms:
        return pd.DataFrame()
    ph = ",".join("?" * len(syms))

    px = q(f"""SELECT symbol,date,close,prev_close,deliv_pct FROM prices
               WHERE symbol IN ({ph}) AND date >= ? ORDER BY symbol,date""", (*syms, start))
    frames = []
    for _, g in px.groupby("symbol"):
        g = g.sort_values("date").reset_index(drop=True)
        ratio = g["close"] / g["close"].shift()
        factor = pd.Series(1.0, index=g.index)
        act = (ratio < 0.6) | (ratio > 1.6)
        factor[act] = ratio[act]
        ac = g["close"] * (factor[::-1].cumprod()[::-1] / factor)     # split-adjusted
        g["ret_1d"] = ac.pct_change() * 100
        g["ret_1w"] = ac.pct_change(5) * 100
        g["ret_next"] = ac.shift(-1) / ac - 1                          # next-day (backtest)
        frames.append(g)
    px = pd.concat(frames, ignore_index=True)

    fut = q(f"""SELECT symbol,date,expiry,close,chg_oi FROM futures
                WHERE symbol IN ({ph}) AND date >= ?""", (*syms, start))
    near = (fut.sort_values("expiry").groupby(["symbol", "date"]).first().reset_index()
              .rename(columns={"close": "fut_close"})[["symbol", "date", "fut_close"]])
    agg = fut.groupby(["symbol", "date"]).agg(chg_oi=("chg_oi", "sum")).reset_index()

    opt = q(f"""SELECT symbol,date,opt_type,SUM(oi) oi FROM options
                WHERE symbol IN ({ph}) AND date >= ? GROUP BY symbol,date,opt_type""",
            (*syms, start))
    pcr = opt.pivot_table(index=["symbol", "date"], columns="opt_type", values="oi").reset_index()
    pcr["pcr"] = pcr.get("PE", 0) / pcr.get("CE", np.nan)
    pcr = pcr[["symbol", "date", "pcr"]]

    df = (px.merge(agg, on=["symbol", "date"], how="left")
            .merge(near, on=["symbol", "date"], how="left")
            .merge(pcr, on=["symbol", "date"], how="left"))
    df["premium_pct"] = (df["fut_close"] - df["close"]) / df["close"] * 100
    up, oiup = df["ret_1d"] >= 0, df["chg_oi"].fillna(0) >= 0
    df["buildup_val"] = np.select([up & oiup, up & ~oiup, ~up & ~oiup, ~up & oiup],
                                  [2, 1, -1, -2], default=0)
    df["f_fno"] = df["buildup_val"] + df["premium_pct"].fillna(0)
    df["f_deliv"] = df["deliv_pct"].fillna(0) * np.sign(df["ret_1d"])
    df["f_stretch"] = 0.4 * df["ret_1d"] + 0.6 * df["ret_1w"]
    df = df[df["date"].isin(win_dates)].dropna(subset=["ret_1d", "ret_1w"]).copy()

    def zc(s):
        sd = s.std(ddof=0)
        return (s - s.mean()) / sd if sd else s * 0
    g = df.groupby("date")
    df["z_mom"] = g["ret_1d"].transform(zc) * 0.6 + g["ret_1w"].transform(zc) * 0.4
    df["z_fno"] = g["f_fno"].transform(zc)
    df["z_del"] = g["f_deliv"].transform(zc)
    df["z_pcr"] = -g["pcr"].transform(zc)                              # low PCR = bullish
    df["bull_mom"] = (df["z_mom"] + 0.8 * df["z_fno"].fillna(0)
                      + 0.6 * df["z_del"].fillna(0) + 0.3 * df["z_pcr"].fillna(0))
    df["bull_rev"] = -g["f_stretch"].transform(zc)                     # oversold → bounce
    return df


def shortlist_backtest(df, col, k=3):
    """Hit-rate of top-k / bottom-k picks by `col` against actual next-day move."""
    bt = df.dropna(subset=["ret_next"])
    cu = cd = nu = nd = 0
    su = sd = 0.0
    for _, gd in bt.groupby("date"):
        s = gd.sort_values(col, ascending=False)
        u, dn = s.head(k), s.tail(k)
        cu += int((u["ret_next"] > 0).sum()); nu += len(u); su += u["ret_next"].sum()
        cd += int((dn["ret_next"] < 0).sum()); nd += len(dn); sd += dn["ret_next"].sum()
    acc = (cu + cd) / (nu + nd) * 100 if (nu + nd) else 0
    spread = (su / nu - sd / nd) * 100 if nu and nd else 0
    return {"acc": acc, "up_hit": cu / nu * 100 if nu else 0,
            "down_hit": cd / nd * 100 if nd else 0, "spread": spread,
            "days": bt["date"].nunique()}


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
# Sidebar — QuantCalc-style logo + navigation menu + stock controls
# --------------------------------------------------------------------------- #
SECTIONS = ["📈 Equity / Cash", "🔮 Futures", "⛓️ Options", "🏦 Participant",
            "📊 Math stats", "🏭 Sectors", "⚖️ Compare", "🎯 Next-day shortlist"]

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

        # --- 1. Stock all-data table (glanceable, latest din upar) ---
        st.markdown("#### 1 · Stock — all data (din-b-din)")
        st.markdown(render_stock_table(view), unsafe_allow_html=True)
        download_csv(view, f"⬇️ Download {symbol} data (CSV)",
                     f"{symbol}_equity.csv", key="dl_equity")

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
        download_csv(fut, f"⬇️ Download {symbol} futures (CSV)",
                     f"{symbol}_futures_{fdate}.csv", key="dl_fut")

        # --- 2. Estimated participant split (proportional estimate) ---
        st.markdown("#### 2 · Estimated participant split")
        st.warning("⚠️ Ye ek **PROPORTIONAL ESTIMATE** hai — maan liya ki har stock me "
                   "market-wide jaisa hi FII/DII/Pro/Client mix hai. Real per-stock "
                   "participant data publicly milta nahi. Rough idea ke liye, exact nahi.")
        pmax = q("SELECT MAX(date) d FROM participant")["d"].iloc[0]
        part = q("SELECT client_type, fut_stk_long FROM participant WHERE date=? "
                 "AND metric='oi' AND client_type IN ('FII','DII','Pro','Client')", (pmax,))
        soi = q("SELECT SUM(oi) oi FROM futures WHERE symbol=? AND date=?", (symbol, fdate))
        stock_oi = float(soi["oi"].iloc[0]) if not soi.empty and pd.notna(soi["oi"].iloc[0]) else 0
        st.markdown(f"**{symbol}** — futures OI = **{_fmt(stock_oi)}** contracts. "
                    "Estimated split (market-wide Future-Stock % se):")
        st.markdown(render_est_split(part, stock_oi), unsafe_allow_html=True)

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
        download_csv(_optraw, f"⬇️ Download full option chain (CSV) — {odate}",
                     f"{symbol}_options_{odate}.csv", key="dl_opt")
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
            download_csv(raw, "⬇️ Download participant data (CSV)",
                         f"participant_{pdate}.csv", key="dl_part")

# =========================================================================== #
# TAB — overview (all-stock math stats)
# =========================================================================== #
elif section == "📊 Math stats":
    st.subheader("All F&O stocks — math stats")

    # --- India VIX — market fear gauge (market-wide context) ---
    _vix = vix_series()
    if not _vix.empty:
        _vl = _vix.iloc[-1]
        vc1, vc2 = st.columns([1, 3])
        vc1.metric("India VIX", f"{_vl['close']:.2f}",
                   f"{_vl['chg_pct']:+.2f}%" if pd.notna(_vl['chg_pct']) else None,
                   delta_color="inverse")          # VIX up = risk-off (red)
        _vw = _vix.tail(60)
        vfig = go.Figure(go.Scatter(
            x=_vw["date"], y=_vw["close"], mode="lines",
            line=dict(color="#f59e0b", width=2), fill="tozeroy",
            fillcolor="rgba(245,158,11,.08)", hoverinfo="x+y", name=""))
        vfig.update_layout(height=120, margin=dict(l=0, r=0, t=6, b=0),
                           showlegend=False, yaxis_title=None, xaxis_title=None)
        vfig.update_xaxes(type="category", nticks=6)
        vc2.plotly_chart(vfig, width="stretch")
        st.caption("**India VIX** = expected 30-day market volatility (fear gauge). "
                   "High = fear/uncertainty · low = calm. Trend = last 60 din.")

    stats = q("""SELECT symbol, cum_return, cagr, ann_volatility, volatility,
                        sharpe, max_drawdown, beta, zscore, pct_rank_52w,
                        skew, kurtosis, daily_return, mean_return,
                        put_call_ratio, total_oi, oi_change, futures_premium
                 FROM stats""")
    if stats.empty:
        st.info("Stats abhi nahi. `python analysis.py` chalao.")
    else:
        # Add-ons: multi-window returns (1W/1M/3M/6M/1Y) + downside risk
        # (Sortino/VaR) + Calmar (= CAGR / |max drawdown|).
        stats = (stats.merge(window_returns(), left_on="symbol", right_index=True, how="left")
                      .merge(extra_stats(), left_on="symbol", right_index=True, how="left"))
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
            "52w %ile (high → low)": ("pct_rank_52w", False),
            "PCR (zyada → kam)": ("put_call_ratio", False),
            "Symbol (A → Z)": ("symbol", True),
        }
        choice = st.selectbox("Sort by", list(sort_opts.keys()), index=0)
        col, asc = sort_opts[choice]
        stats = stats.sort_values(col, ascending=asc, na_position="last")
        st.markdown(render_overview_table(stats), unsafe_allow_html=True)
        download_csv(stats, "⬇️ Download math stats (CSV)", "nse_math_stats.csv",
                     key="dl_stats")
        st.caption("Green = up / positive, red = down / negative · **1D/1W/1M/3M/6M/1Y%** "
                   "= momentum across timeframes · **Sortino** = downside-adjusted return · "
                   "**Calmar** = CAGR ÷ max-drawdown · **VaR%** = 5% worst-day loss · bars = "
                   "volatility & 52-week position. Split/bonus-adjusted. Right scroll = saare columns.")

# =========================================================================== #
# TAB — Sectors (sector-wise performance)
# =========================================================================== #
elif section == "🏭 Sectors":
    st.subheader("Sector-wise performance")
    base = q("SELECT symbol, ann_volatility, put_call_ratio, daily_return FROM stats")
    if base.empty:
        st.info("Stats abhi nahi. `python analysis.py` chalao.")
    else:
        df = (base.merge(window_returns().reset_index(), on="symbol", how="left")
                  .merge(extra_stats().reset_index()[["symbol", "ret_1y"]],
                         on="symbol", how="left"))
        df["ret_1d"] = df["daily_return"] * 100
        df["ann_vol"] = df["ann_volatility"] * 100
        df["sector"] = df["symbol"].map(sectors.sector_of)
        agg = (df.groupby("sector").agg(
                   n=("symbol", "count"), ret_1d=("ret_1d", "mean"),
                   ret_1w=("ret_1w", "mean"), ret_1m=("ret_1m", "mean"),
                   ret_1y=("ret_1y", "mean"), ann_vol=("ann_vol", "mean"),
                   pcr=("put_call_ratio", "mean")).reset_index()
                 .sort_values("ret_1m", ascending=False))

        # avg 1-month return per sector (horizontal bar)
        st.markdown("#### 📊 Avg 1-month return by sector")
        bfig = go.Figure(go.Bar(
            x=agg["ret_1m"], y=agg["sector"], orientation="h",
            marker_color=["#10b981" if v >= 0 else "#f43f5e" for v in agg["ret_1m"]],
            text=[f"{v:+.1f}%" for v in agg["ret_1m"]], textposition="auto"))
        bfig.update_layout(height=420, margin=dict(l=0, r=0, t=8, b=0),
                           xaxis_title="Avg 1M return %", yaxis=dict(autorange="reversed"))
        st.plotly_chart(bfig, width="stretch")

        st.markdown("#### 📋 Sector summary")
        st.markdown(render_sector_table(agg), unsafe_allow_html=True)
        download_csv(agg, "⬇️ Download sector summary (CSV)", "sectors.csv", key="dl_sec")

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
                    .merge(window_returns().reset_index(), on="symbol", how="left")
                    .merge(extra_stats().reset_index(), on="symbol", how="left")
                    .set_index("symbol").reindex(picks))
        st.markdown("#### 📊 Side-by-side stats")
        st.markdown(render_compare(comp), unsafe_allow_html=True)
        download_csv(comp.reset_index(), "⬇️ Download compare (CSV)", "compare.csv",
                     key="dl_cmp")

# =========================================================================== #
# TAB — Next-day shortlist (statistical screener; educational, NOT advice)
# =========================================================================== #
elif section == "🎯 Next-day shortlist":
    st.subheader("Next-day shortlist — kal kis pe nazar rakhein")
    st.warning("⚠️ **Educational / research only — trading advice NAHI.** Ye aaj ke data se "
               "banaya **statistical shortlist** hai, guaranteed prediction nahi. Next-day "
               "move inherently uncertain hota hai. Har trade apne research + risk pe.")
    st.caption("2 strategies (opposite): **Momentum** = aaj strong up → kal continue · "
               "**Mean-reversion** = aaj bahut stretched → kal ulta. Signals: price momentum "
               "(1D/1W) · F&O positioning (OI buildup + premium) · delivery% · options PCR. "
               "Sirf liquid stocks.")

    c1, c2, c3 = st.columns(3)
    window = c1.slider("Backtest window (din)", 30, 120, 60, 10)
    nliq = c2.slider("Liquid stocks (top by turnover)", 20, 80, 40, 10)
    k = c3.slider("Kitne picks (up/down)", 3, 6, 3)

    data = shortlist_data(nliq, window)
    if data.empty or data["date"].nunique() < 5:
        st.info("Itna data nahi (window ya liquid count badhao).")
    else:
        mom = shortlist_backtest(data, "bull_mom", k)
        rev = shortlist_backtest(data, "bull_rev", k)
        st.markdown(f"#### 📊 Track record — last {mom['days']} din ka backtest")
        b1, b2 = st.columns(2)
        b1.metric("🚀 Momentum accuracy", f"{mom['acc']:.0f}%",
                  f"spread {mom['spread']:+.2f}%")
        b2.metric("↩️ Mean-reversion accuracy", f"{rev['acc']:.0f}%",
                  f"spread {rev['spread']:+.2f}%")
        better = "Momentum" if mom["acc"] >= rev["acc"] else "Mean-reversion"
        st.caption(f"Accuracy = shortlist ne kitni baar sahi direction pakdi (**50% = coin "
                   f"flip**). Spread = UP − DOWN picks ka avg next-day return (edge). Is "
                   f"window me **{better}** better chali. Guarantee nahi — sirf history.")

        latest = data["date"].max()
        dates_desc = sorted(data["date"].unique(), reverse=True)
        sel = date_slider("📅 Kis din ka shortlist dekhna hai (pichhle din bhi)",
                          dates_desc, "shortlist_date", window=len(dates_desc))
        td = data[data["date"] == sel]
        past = sel != latest
        if past:
            st.markdown(f"#### 🎯 {sel} ka shortlist — aur **kal (next day) actual result** ✓/✗")
        else:
            st.markdown(f"#### 🎯 Aaj ({sel}) ke data se — kal ke liye shortlist "
                        "(result abhi nahi aaya)")
        mc, rc = st.columns(2)
        with mc:
            st.markdown("**🚀 Momentum (continuation)**")
            st.markdown("🟢 **UP:**")
            st.markdown(render_picks(td.sort_values("bull_mom", ascending=False).head(k),
                                     "bull_mom", "up", past), unsafe_allow_html=True)
            st.markdown("🔴 **DOWN:**")
            st.markdown(render_picks(td.sort_values("bull_mom").head(k),
                                     "bull_mom", "down", past), unsafe_allow_html=True)
        with rc:
            st.markdown("**↩️ Mean-reversion (contrarian)**")
            st.markdown("🟢 **UP** (oversold):")
            st.markdown(render_picks(td.sort_values("bull_rev", ascending=False).head(k),
                                     "bull_rev", "up", past), unsafe_allow_html=True)
            st.markdown("🔴 **DOWN** (overbought):")
            st.markdown(render_picks(td.sort_values("bull_rev").head(k),
                                     "bull_rev", "down", past), unsafe_allow_html=True)
        _sl = td[["symbol", "ret_1d", "ret_1w", "buildup_val", "premium_pct", "pcr",
                  "bull_mom", "bull_rev", "ret_next"]].sort_values("bull_mom", ascending=False)
        download_csv(_sl, f"⬇️ Download {sel} scored list (CSV)",
                     f"shortlist_{sel}.csv", key="dl_shortlist")
        st.caption("Columns: **1D%** (us din ka move) · **Buildup** (OI se) · **Prem%** "
                   "(futures premium) · **PCR** · **Score** (composite). Past din pe **Kal%** "
                   "= agle din ka actual move · **✓** = shortlist sahi, **✗** = galat. "
                   "Slider se pichhle din scrub karke dekho strategy kaisa chala.")

