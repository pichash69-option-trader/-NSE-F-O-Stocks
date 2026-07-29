# -*- coding: utf-8 -*-
"""
dashboard.py — date-wise NSE dashboard (Streamlit).

Run:  streamlit run dashboard.py

Design (per stock, date-wise / timeline):
  1. Stock — all data, day by day (OHLC, chg%, volume, delivery%) + close trend
  2. Option chain block:  SUM CHAIN (all expiries summed per strike)  +  each expiry chain
  3. Futures — all-expiry totals + change
Plus an Overview tab: all F&O stocks' math stats.
"""
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go

import db
import analysis
from config import NIFTY50

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
3. Sidebar ke **menu** (7 sections) me data dekho (date-wale sections me **slider** se din badlo).

Upar **ticker** = us din ke **Top 5 gainers** (green) + **Top 5 losers** (red), EOD data se.

---

## 🗂️ Sections (7)

**🔎 Full view** — Selected stock ka **saara data ek page par**: top metrics
(Close, Volume, Delivery %, Ann Vol, Beta) → OI buildup → Math stats → Futures →
Option chain → Estimated participant split. "Ek nazar me poori kahani."

**📈 Stock (date-wise)** — Har din ek row: OHLC, **Chg%** (green/red pill),
**Volume & Delivery%** (bars), Turnover ₹Cr, Trades. Neeche **candle chart** (hover = detail).
🟢 up din · 🔴 down din.

**🔮 Futures** — Teeno expiry (near/next/far) ka total + changes: OHLC, Settle,
**Premium** (future − spot), **OI + Chg OI**, Σ TOTAL. Plus estimated participant split.

**⛓️ Option chain** — **Σ Sum chain** (teeno expiry ka strike-wise total) + har expiry ka
apna chain. 🟧 CALLS ITM · 🟥 PUTS ITM · 🔵 **ATM** row · ChgOI green = OI add, red = cut.
**Strikes ± slider** + **max pain** heading me.

**🏦 FII/DII** — FII / DII / Pro / Client ka F&O positioning (OI + Volume).
**Net = Long − Short**: 🟢 net long (bullish), 🔴 net short (bearish). Ye **market-wide** hai.

**🎯 Positioning** — **Real OI buildup** (price + OI change se) har stock ka + market scan/filter.

**📊 Overview** — Saare ~210 stocks ka math ek table me. **Sort by** se compare karo.
Symbol + header pinned; right scroll = saare 18 columns.

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
    df = q("SELECT date,open,high,low,close,prev_close,volume,turnover,"
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
# Sensibull-style option chain (custom HTML/CSS)
# --------------------------------------------------------------------------- #
CHAIN_CSS = """
<style>
.oc{width:100%;border-collapse:collapse;font-size:12px;font-family:var(--font,sans-serif);}
.oc th{font-size:11px;color:#9ca3af;font-weight:600;padding:6px 8px;text-align:right;}
.oc td{padding:5px 8px;text-align:right;border-top:1px solid rgba(148,163,184,.18);position:relative;}
.oc .stk{text-align:center;font-weight:600;background:rgba(148,163,184,.14);}
.oc .itmce{background:rgba(245,158,11,.14);}
.oc .itmpe{background:rgba(244,63,94,.12);}
.oc tr.atm td{border-top:2px solid #6366f1;border-bottom:2px solid #6366f1;}
.oc .up{color:#10b981;} .oc .dn{color:#f43f5e;}
.oc .bar{position:absolute;top:3px;bottom:3px;opacity:.30;border-radius:3px;z-index:0;}
.oc .bce{right:0;background:#f43f5e;} .oc .bpe{left:0;background:#10b981;}
.oc .v{position:relative;z-index:1;}
.oc-h{display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px;font-size:12px;margin:2px 0 6px;}
.oc-lg{font-size:11px;color:#9ca3af;margin-bottom:6px;}
.oc-lg b{color:inherit;}
</style>
"""


def _fmt(n):
    """Compact Indian-style: 55000->55K, 180000->1.8L, 12000000->1.2Cr."""
    if n is None or (isinstance(n, float) and np.isnan(n)):
        return "0"
    n = float(n)
    a = abs(n)
    if a >= 1e7:
        return f"{n/1e7:.2f}Cr"
    if a >= 1e5:
        return f"{n/1e5:.1f}L"
    if a >= 1e3:
        return f"{n/1e3:.0f}K"
    return f"{n:.0f}"


def _cell_oi(oi, mx, side):
    """OI cell with a proportional background bar."""
    w = 0 if not mx else min(100, abs(oi) / mx * 100)
    bar = f'<span class="bar b{side}" style="width:{w:.0f}%"></span>'
    return f'{bar}<span class="v">{_fmt(oi)}</span>'


def _cell_chg(v):
    cls = "up" if (v or 0) > 0 else ("dn" if (v or 0) < 0 else "")
    sign = "+" if (v or 0) > 0 else ""
    return f'<span class="{cls}">{sign}{_fmt(v)}</span>'


def render_chain(df, spot, has_ltp, ltp_col_ce="close_CE", ltp_col_pe="close_PE"):
    """Build a Sensibull-style HTML option chain from a per-strike DataFrame.

    Expected columns: strike, oi_CE, chg_oi_CE, volume_CE, oi_PE, chg_oi_PE,
    volume_PE (+ optional close_CE/close_PE for LTP).
    """
    if df is None or df.empty:
        return "<i>—</i>"
    df = df.sort_values("strike")
    mx = float(pd.concat([df["oi_CE"], df["oi_PE"]]).abs().max() or 0)
    atm = df.iloc[(df["strike"] - spot).abs().argmin()]["strike"] if spot else None

    head_ce = "<th>OI</th><th>Chg OI</th><th>Vol</th>" + ("<th>LTP</th>" if has_ltp else "")
    head_pe = ("<th>LTP</th>" if has_ltp else "") + "<th>Vol</th><th>Chg OI</th><th>OI</th>"
    rows = []
    for _, r in df.iterrows():
        strike = r["strike"]
        itm_ce = " itmce" if (spot and strike < spot) else ""
        itm_pe = " itmpe" if (spot and strike > spot) else ""
        atm_cls = " atm" if strike == atm else ""
        ltp_ce = f'<td class="{itm_ce.strip()}">{r.get(ltp_col_ce, float("nan")):.2f}</td>' if has_ltp and pd.notna(r.get(ltp_col_ce)) else ("<td></td>" if has_ltp else "")
        ltp_pe = f'<td class="{itm_pe.strip()}">{r.get(ltp_col_pe, float("nan")):.2f}</td>' if has_ltp and pd.notna(r.get(ltp_col_pe)) else ("<td></td>" if has_ltp else "")
        strike_lbl = f"{strike:.0f}" + (" · ATM" if strike == atm else "")
        rows.append(
            f'<tr class="{atm_cls.strip()}">'
            f'<td class="{itm_ce.strip()}">{_cell_oi(r["oi_CE"], mx, "ce")}</td>'
            f'<td class="{itm_ce.strip()}">{_cell_chg(r["chg_oi_CE"])}</td>'
            f'<td class="{itm_ce.strip()}">{_fmt(r["volume_CE"])}</td>'
            f'{ltp_ce}'
            f'<td class="stk">{strike_lbl}</td>'
            f'{ltp_pe}'
            f'<td class="{itm_pe.strip()}">{_fmt(r["volume_PE"])}</td>'
            f'<td class="{itm_pe.strip()}">{_cell_chg(r["chg_oi_PE"])}</td>'
            f'<td class="{itm_pe.strip()}">{_cell_oi(r["oi_PE"], mx, "pe")}</td>'
            f'</tr>')
    span = 4 if has_ltp else 3
    return (CHAIN_CSS +
            '<div style="overflow-x:auto"><table class="oc"><thead>'
            f'<tr><th colspan="{span}" style="text-align:center;color:#f59e0b">CALLS</th>'
            '<th class="stk">STRIKE</th>'
            f'<th colspan="{span}" style="text-align:center;color:#f43f5e">PUTS</th></tr>'
            f'<tr>{head_ce}<th class="stk">Strike</th>{head_pe}</tr>'
            '</thead><tbody>' + "".join(rows) + '</tbody></table></div>')


CHAIN_LEGEND = ('<div class="oc-lg">'
                '<b style="color:#f59e0b">▎</b> CALLS ITM shaded &nbsp; '
                '<b style="color:#f43f5e">▎</b> PUTS ITM shaded &nbsp; '
                '<b style="color:#10b981">▎</b> OI addition &nbsp; '
                '<b style="color:#f43f5e">▎</b> OI reduction &nbsp; '
                '<b style="color:#6366f1">━</b> ATM</div>')


# --------------------------------------------------------------------------- #
# Rich "Stock — all data" table (glanceable, like the option chain)
# --------------------------------------------------------------------------- #
STOCK_CSS = """
<style>
.stbl{width:100%;border-collapse:collapse;font-size:12px;min-width:640px;}
.stbl th{font-size:11px;color:#9ca3af;font-weight:600;padding:6px 8px;text-align:right;}
.stbl th.l{text-align:left;} .stbl th.c{text-align:center;}
.stbl td{padding:5px 8px;text-align:right;border-top:1px solid rgba(148,163,184,.16);}
.stbl td.date{text-align:left;color:#cbd5e1;white-space:nowrap;}
.stbl .up{color:#10b981;} .stbl .dn{color:#f43f5e;}
.stbl .cl{font-weight:600;}
.stbl .pill{display:inline-block;padding:1px 7px;border-radius:10px;font-weight:600;}
.stbl .pu{background:rgba(16,185,129,.16);color:#10b981;}
.stbl .pd{background:rgba(244,63,94,.16);color:#f43f5e;}
.candle{position:relative;height:16px;width:150px;display:inline-block;vertical-align:middle;}
.wick{position:absolute;top:7px;height:2px;background:#6b7280;border-radius:2px;}
.body{position:absolute;top:3px;height:10px;border-radius:2px;}
.bar-cell{position:relative;}
.bar-bg{position:absolute;top:4px;bottom:4px;left:0;border-radius:3px;opacity:.28;}
.bar-vol{background:#6366f1;} .bar-del{background:#10b981;}
.bar-v{position:relative;z-index:1;}
.stlg{font-size:11px;color:#9ca3af;margin:2px 0 6px;}
</style>
"""


def render_stock_table(view):
    """Glanceable date-wise table: colored close/chg + volume & delivery% bars."""
    df = view.sort_values("date", ascending=False).reset_index(drop=True)
    vmax = float(view["volume"].max() or 1)

    rows = []
    for _, r in df.iterrows():
        up = r["close"] >= r["open"]
        chg = r["chg_pct"]
        pill = (f'<span class="pill {"pu" if chg>=0 else "pd"}">'
                f'{"▲" if chg>=0 else "▼"} {chg:+.2f}%</span>') if pd.notna(chg) else ""
        volw = r["volume"] / vmax * 100
        volcell = (f'<span class="bar-bg bar-vol" style="width:{volw:.0f}%"></span>'
                   f'<span class="bar-v">{_fmt(r["volume"])}</span>')
        dp = r["deliv_pct"]
        delcell = (f'<span class="bar-bg bar-del" style="width:{dp:.0f}%"></span>'
                   f'<span class="bar-v">{dp:.1f}</span>') if pd.notna(dp) else "—"
        turn = f'{r["turnover"]/1e7:,.1f}' if pd.notna(r.get("turnover")) else "—"
        trades = _fmt(r["num_trades"]) if pd.notna(r.get("num_trades")) else "—"
        rows.append(
            f'<tr><td class="date">{r["date"]}</td>'
            f'<td>{r["open"]:.1f}</td><td>{r["high"]:.1f}</td><td>{r["low"]:.1f}</td>'
            f'<td class="cl {"up" if up else "dn"}">{r["close"]:.1f}</td>'
            f'<td>{pill}</td>'
            f'<td class="bar-cell">{volcell}</td>'
            f'<td>{turn}</td><td>{trades}</td>'
            f'<td class="bar-cell">{delcell}</td></tr>')
    legend = ('<div class="stlg">Close green/red = up/down din · '
              'bars = volume &amp; delivery% · turnover ₹Cr · prices split/bonus-adjusted. '
              'Neeche candle chart me hover karo.</div>')
    return (STOCK_CSS + legend +
            '<div style="overflow-x:auto"><table class="stbl"><thead><tr>'
            '<th class="l">Date</th>'
            '<th>Open</th><th>High</th><th>Low</th><th>Close</th>'
            '<th>Chg%</th><th>Volume</th><th>Turnover ₹Cr</th><th>Trades</th>'
            '<th>Deliv%</th>'
            '</tr></thead><tbody>' + "".join(rows) + '</tbody></table></div>')


def render_overview_table(df):
    """Themed 50-stock stats table (matches our dark theme): colored values + bars."""
    if df is None or df.empty:
        return "<i>—</i>"
    df = df.reset_index(drop=True)
    volmax = float(df["ann_volatility"].abs().max() or 1)

    def col(v, fmt="{:+.2f}"):
        cls = "up" if (v or 0) >= 0 else "dn"
        return f'<span class="{cls}">{fmt.format(v)}</span>' if pd.notna(v) else "—"

    def num(v, fmt="{:.2f}"):
        return fmt.format(v) if pd.notna(v) else "—"

    rows = []
    for _, r in df.iterrows():
        cr = r["cum_return"] * 100
        dd = r["max_drawdown"] * 100
        volw = abs(r["ann_volatility"]) / volmax * 100
        volcell = (f'<span class="bar-bg bar-vol" style="width:{volw:.0f}%"></span>'
                   f'<span class="bar-v">{r["ann_volatility"]*100:.1f}%</span>')
        p52 = r["pct_rank_52w"]
        p52cell = (f'<span class="bar-bg bar-del" style="width:{p52:.0f}%"></span>'
                   f'<span class="bar-v">{p52:.0f}</span>') if pd.notna(p52) else "—"
        pcr = num(r["put_call_ratio"])
        rows.append(
            f'<tr><td class="date" style="font-weight:600">{r["symbol"]}</td>'
            f'<td>{col(cr)}%</td>'
            f'<td>{col(r["cagr"]*100 if pd.notna(r["cagr"]) else None, "{:+.1f}")}%</td>'
            f'<td class="bar-cell">{volcell}</td>'
            f'<td>{num(r["volatility"]*100, "{:.2f}")}%</td>'
            f'<td>{col(r["sharpe"], "{:+.2f}")}</td>'
            f'<td><span class="dn">{dd:.1f}%</span></td>'
            f'<td>{num(r["beta"])}</td>'
            f'<td>{col(r["zscore"], "{:+.2f}")}</td>'
            f'<td class="bar-cell">{p52cell}</td>'
            f'<td>{num(r["skew"])}</td>'
            f'<td>{num(r["kurtosis"])}</td>'
            f'<td>{col(r["daily_return"]*100 if pd.notna(r["daily_return"]) else None)}%</td>'
            f'<td>{col(r["mean_return"]*100 if pd.notna(r["mean_return"]) else None, "{:+.3f}")}%</td>'
            f'<td>{pcr}</td>'
            f'<td>{_fmt(r["total_oi"])}</td>'
            f'<td>{col(r["oi_change"], "{:+.0f}")}</td>'
            f'<td>{col(r["futures_premium"], "{:+.1f}")}</td></tr>')
    return (STOCK_CSS + OVERVIEW_CSS +
            '<div class="ovwrap"><table class="stbl ovtbl">'
            '<thead><tr>'
            '<th class="l">Symbol</th><th>Return%</th><th>CAGR%</th><th>Ann Vol</th>'
            '<th>Daily Vol</th><th>Sharpe</th><th>Max DD</th><th>Beta</th>'
            '<th>Z-score</th><th>52w %ile</th><th>Skew</th><th>Kurt</th>'
            '<th>Day Ret%</th><th>Mean Ret%</th><th>PCR</th><th>Total OI</th>'
            '<th>OI Chg</th><th>Fut Prem</th>'
            '</tr></thead><tbody>' + "".join(rows) + '</tbody></table></div>')


# Compact + clearly-scrollable styling for the wide 18-column overview table.
OVERVIEW_CSS = """
<style>
.ovwrap{overflow-x:auto;overflow-y:auto;max-height:70vh;
  border:1px solid rgba(255,255,255,.06);border-radius:10px;}
.ovwrap::-webkit-scrollbar{height:10px;width:10px;}
.ovwrap::-webkit-scrollbar-thumb{background:#6366f1;border-radius:6px;}
.ovwrap::-webkit-scrollbar-track{background:rgba(255,255,255,.04);}
.ovtbl{min-width:1080px;font-size:11.5px;}
.ovtbl th{position:sticky;top:0;z-index:2;background:#0c1020;padding:6px 7px;}
.ovtbl th.l{left:0;z-index:3;}
.ovtbl td{padding:4px 7px;}
.ovtbl td.date{position:sticky;left:0;background:#0c1020;z-index:1;}
</style>
"""


def render_futures_table(fut, spot):
    """Themed futures table (like section 1): OI bars, colored Chg OI, premium, total row."""
    if fut is None or fut.empty:
        return "<i>—</i>"
    fut = fut.sort_values("expiry").reset_index(drop=True)
    omax = float(fut["oi"].abs().max() or 1)

    def chg_pill(v):
        cls = "pu" if (v or 0) >= 0 else "pd"
        return (f'<span class="pill {cls}">{"▲" if (v or 0)>=0 else "▼"} '
                f'{"+" if (v or 0)>=0 else ""}{_fmt(v)}</span>')

    rows = []
    for i, r in fut.iterrows():
        prem = (r["close"] - spot) if spot is not None else None
        prem_cls = "up" if (prem or 0) >= 0 else "dn"
        prem_txt = (f'<span class="{prem_cls}">{prem:+.2f}</span>'
                    if prem is not None else "—")
        oiw = r["oi"] / omax * 100
        oicell = (f'<span class="bar-bg bar-vol" style="width:{oiw:.0f}%"></span>'
                  f'<span class="bar-v">{_fmt(r["oi"])}</span>')
        tag = " (near)" if i == 0 else (" (next)" if i == 1 else " (far)")
        val = f'{r["value_lakh"]/1e7:,.1f}' if pd.notna(r.get("value_lakh")) else "—"
        rows.append(
            f'<tr><td class="date">{r["expiry"]}{tag}</td>'
            f'<td>{r["open"]:.1f}</td><td>{r["high"]:.1f}</td><td>{r["low"]:.1f}</td>'
            f'<td class="cl">{r["close"]:.1f}</td><td>{r["settle"]:.1f}</td>'
            f'<td>{prem_txt}</td>'
            f'<td class="bar-cell">{oicell}</td>'
            f'<td>{chg_pill(r["chg_oi"])}</td>'
            f'<td>{_fmt(r["contracts"])}</td><td>{val}</td></tr>')
    # TOTAL row
    toi, tchg, tcon = fut["oi"].sum(), fut["chg_oi"].sum(), fut["contracts"].sum()
    rows.append(
        f'<tr class="tot"><td class="date">Σ TOTAL (3 expiry)</td>'
        f'<td>—</td><td>—</td><td>—</td><td>—</td><td>—</td><td>—</td>'
        f'<td class="cl">{_fmt(toi)}</td>'
        f'<td>{chg_pill(tchg)}</td>'
        f'<td>{_fmt(tcon)}</td><td>—</td></tr>')
    return (STOCK_CSS +
            '<style>.stbl tr.tot td{border-top:2px solid #6366f1;font-weight:600;'
            'background:rgba(99,102,241,.10);}</style>'
            '<div style="overflow-x:auto"><table class="stbl"><thead><tr>'
            '<th class="l">Expiry</th><th>Open</th><th>High</th><th>Low</th>'
            '<th>Close</th><th>Settle</th><th>Premium</th>'
            '<th>Open Interest</th><th>Chg OI</th><th>Contracts</th><th>Value ₹Cr</th>'
            '</tr></thead><tbody>' + "".join(rows) + '</tbody></table></div>')


def render_participant(df):
    """Themed net-position table for participant OI/Vol (FII/DII/Pro/Client)."""
    if df is None or df.empty:
        return "<i>—</i>"
    order = {"FII": 0, "DII": 1, "Pro": 2, "Client": 3, "TOTAL": 4}
    df = df.copy()
    df["_o"] = df["client_type"].map(order).fillna(9)
    df = df.sort_values("_o")

    def net(v):
        cls = "up" if (v or 0) >= 0 else "dn"
        sign = "+" if (v or 0) >= 0 else ""
        return f'<span class="{cls}">{sign}{_fmt(v)}</span>'

    rows = []
    for _, r in df.iterrows():
        idxfut = r["fut_idx_long"] - r["fut_idx_short"]
        stkfut = r["fut_stk_long"] - r["fut_stk_short"]
        optidx = ((r["opt_idx_call_long"] + r["opt_idx_put_long"])
                  - (r["opt_idx_call_short"] + r["opt_idx_put_short"]))
        optstk = ((r["opt_stk_call_long"] + r["opt_stk_put_long"])
                  - (r["opt_stk_call_short"] + r["opt_stk_put_short"]))
        tnet = r["total_long"] - r["total_short"]
        tot = " tot" if r["client_type"] == "TOTAL" else ""
        rows.append(
            f'<tr class="{tot.strip()}"><td class="date">{r["client_type"]}</td>'
            f'<td>{net(idxfut)}</td><td>{net(stkfut)}</td>'
            f'<td>{net(optidx)}</td><td>{net(optstk)}</td>'
            f'<td>{_fmt(r["total_long"])}</td><td>{_fmt(r["total_short"])}</td>'
            f'<td>{net(tnet)}</td></tr>')
    return (STOCK_CSS +
            '<style>.stbl tr.tot td{border-top:2px solid #6366f1;font-weight:600;'
            'background:rgba(99,102,241,.10);}</style>'
            '<div style="overflow-x:auto"><table class="stbl"><thead><tr>'
            '<th class="l">Participant</th><th>Idx Fut net</th><th>Stk Fut net</th>'
            '<th>Idx Opt net</th><th>Stk Opt net</th>'
            '<th>Total Long</th><th>Total Short</th><th>Net</th>'
            '</tr></thead><tbody>' + "".join(rows) + '</tbody></table></div>')


def render_est_split(part, stock_oi):
    """PROPORTIONAL ESTIMATE: split a stock's futures OI among FII/DII/Pro/Client
    using their market-wide Future-Stock long share. NOT real per-stock data."""
    if part is None or part.empty or not stock_oi:
        return "<i>—</i>"
    order = {"FII": 0, "DII": 1, "Pro": 2, "Client": 3}
    part = part.copy()
    part["_o"] = part["client_type"].map(order).fillna(9)
    part = part.sort_values("_o")
    tot = part["fut_stk_long"].sum() or 1
    rows = []
    for _, r in part.iterrows():
        pct = r["fut_stk_long"] / tot * 100
        est = pct / 100 * stock_oi
        w = min(100, pct)
        bar = (f'<span class="bar-bg bar-vol" style="width:{w:.0f}%"></span>'
               f'<span class="bar-v">{pct:.1f}%</span>')
        rows.append(
            f'<tr><td class="date">{r["client_type"]}</td>'
            f'<td class="bar-cell">{bar}</td>'
            f'<td class="cl">{_fmt(est)}</td></tr>')
    return (STOCK_CSS +
            '<div style="overflow-x:auto"><table class="stbl" style="min-width:360px">'
            '<thead><tr><th class="l">Participant</th>'
            '<th>Market share (Fut Stock)</th><th>Est. contracts (is stock me)</th>'
            '</tr></thead><tbody>' + "".join(rows) + '</tbody></table></div>')


BUILDUP_COLOR = {"Long Buildup": "#10b981", "Short Covering": "#34d399",
                 "Short Buildup": "#f43f5e", "Long Unwinding": "#fb923c"}


def classify_buildup(price_chg, oi_chg):
    if oi_chg > 0:
        return "Long Buildup" if price_chg >= 0 else "Short Buildup"
    return "Short Covering" if price_chg >= 0 else "Long Unwinding"


def render_buildup_scan(df):
    """Themed table: per-stock OI buildup (price + OI change). Real, reliable."""
    if df is None or df.empty:
        return "<i>—</i>"
    df = df.sort_values("chg_oi", ascending=False)
    rows = []
    for _, r in df.iterrows():
        col = BUILDUP_COLOR.get(r["buildup"], "#888")
        pchg = r["price_chg_pct"]
        pcls = "up" if pchg >= 0 else "dn"
        rows.append(
            f'<tr><td class="date" style="font-weight:600">{r["symbol"]}</td>'
            f'<td class="{pcls}">{pchg:+.2f}%</td>'
            f'<td>{_fmt(r["oi"])}</td>'
            f'<td class="{"up" if r["chg_oi"]>=0 else "dn"}">'
            f'{"+" if r["chg_oi"]>=0 else ""}{_fmt(r["chg_oi"])}</td>'
            f'<td><span style="color:{col};font-weight:600">{r["buildup"]}</span></td>'
            f'</tr>')
    return (STOCK_CSS +
            '<div style="overflow-x:auto"><table class="stbl" style="min-width:460px">'
            '<thead><tr><th class="l">Stock</th><th>Price chg</th>'
            '<th>Futures OI</th><th>OI chg</th><th>Buildup</th>'
            '</tr></thead><tbody>' + "".join(rows) + '</tbody></table></div>')


# --------------------------------------------------------------------------- #
# Sidebar — QuantCalc-style logo + navigation menu + stock controls
# --------------------------------------------------------------------------- #
SECTIONS = ["🔎 Full view", "📈 Stock (date-wise)", "🔮 Futures", "⛓️ Option chain",
            "🏦 FII/DII", "🎯 Positioning", "📊 Overview"]

with st.sidebar:
    st.markdown(
        '<div class="qc-logo"><div class="ico">📈</div>'
        '<div><div class="txt">NSE F&amp;O<span class="pill">PRO</span></div>'
        '<div class="sub">date-wise analytics</div></div></div>',
        unsafe_allow_html=True)

    # Stock controls — on top, above the navigation menu
    symbol = st.selectbox("Stock", all_symbols(), index=0)
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
# TAB — Full view (selected stock ka SAB data ek page par)
# =========================================================================== #
if section == "🔎 Full view":
    st.subheader(f"🔎 {symbol} — poora data (ek jagah)")
    st.caption("Sidebar se stock badlo — is page ke sab sections update ho jayenge.")
    _hist = stock_history(symbol)
    if _hist.empty:
        st.warning(f"{symbol}: koi data nahi.")
    else:
        _lt = _hist.iloc[-1]                         # latest day (for metrics)
        _fdates = q("SELECT DISTINCT date FROM futures WHERE symbol=? "
                    "ORDER BY date DESC", (symbol,))["date"].tolist()
        _srow = q("SELECT * FROM stats WHERE symbol=?", (symbol,))

        # --- Top metrics (latest) ---
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Close", f"{_lt['close']:.2f}", f"{_lt['chg_pct']:+.2f}%")
        m2.metric("Volume", f"{_lt['volume']:,.0f}")
        m3.metric("Delivery %", f"{_lt['deliv_pct']:.1f}"
                  if pd.notna(_lt['deliv_pct']) else "—")
        if not _srow.empty:
            r0 = _srow.iloc[0]
            m4.metric("Ann Vol", f"{r0['ann_volatility']*100:.1f}%")
            m5.metric("Beta", f"{r0['beta']:.2f}")

        # --- F&O date slider (futures / option chain / buildup / split ke liye) ---
        _fd = _spot = None
        if _fdates:
            _fd = date_slider("📅 F&O date (futures / option chain / buildup)",
                              _fdates, "fullview_fdate")
            _sp = q("SELECT close FROM prices WHERE symbol=? AND date=?", (symbol, _fd))
            _spot = float(_sp.iloc[0]["close"]) if not _sp.empty else None

        # --- 🎯 OI buildup (real) — metrics ke turant neeche ---
        if _fd:
            _p2 = q("SELECT close, prev_close FROM prices WHERE symbol=? AND date=?",
                    (symbol, _fd))
            _tchg = q("SELECT SUM(chg_oi) c, SUM(oi) o FROM futures "
                      "WHERE symbol=? AND date=?", (symbol, _fd))
            if not _p2.empty and not _tchg.empty and pd.notna(_p2.iloc[0]["prev_close"]):
                _pc = (_p2.iloc[0]["close"] / _p2.iloc[0]["prev_close"] - 1) * 100
                _oc = _tchg.iloc[0]["c"] or 0
                _bu = classify_buildup(_pc, _oc)
                _col = BUILDUP_COLOR.get(_bu, "#888")
                st.markdown("#### 🎯 OI buildup (real)")
                st.markdown(f"price **{_pc:+.2f}%** · OI chg **{_oc:+,.0f}** · "
                            f"OI **{_fmt(_tchg.iloc[0]['o'])}** → "
                            f"<span style='color:{_col};font-weight:600;font-size:18px'>"
                            f"{_bu}</span>", unsafe_allow_html=True)

        # --- 📊 Math stats — metrics ke neeche ---
        st.markdown("#### 📊 Math stats (poore period ke)")
        if _srow.empty:
            st.write("—")
        else:
            r = _srow.iloc[0]

            def _sc_txt(v, f="{:+.2f}"):
                if pd.isna(v):
                    return "—"
                c = "#10b981" if v >= 0 else "#f43f5e"
                return f"<span style='color:{c}'>{f.format(v)}</span>"
            st.markdown(
                "<div style='font-size:13px;line-height:2'>"
                f"Cumulative return: {_sc_txt(r['cum_return']*100, '{:+.1f}')}% · "
                f"CAGR: {_sc_txt(r['cagr']*100, '{:+.1f}')}% · "
                f"Ann volatility: {r['ann_volatility']*100:.1f}% · "
                f"Sharpe: {_sc_txt(r['sharpe'])} · "
                f"Max drawdown: <span style='color:#f43f5e'>{r['max_drawdown']*100:.1f}%</span> · "
                f"Beta: {r['beta']:.2f} · "
                f"Z-score: {_sc_txt(r['zscore'])} · "
                f"52w %ile: {r['pct_rank_52w']:.0f} · "
                f"Skew: {r['skew']:.2f} · Kurtosis: {r['kurtosis']:.2f} · "
                f"PCR: {r['put_call_ratio']:.2f} · "
                f"Futures premium: {_sc_txt(r['futures_premium'], '{:+.1f}')}"
                "</div>", unsafe_allow_html=True)

        st.divider()

        if not _fd:
            st.info("Is stock ka F&O data nahi (option chain / futures skip).")
        else:
            # --- 🔮 Futures ---
            st.markdown(f"#### 🔮 Futures (teeno expiry) — {_fd}")
            _fut = q("""SELECT expiry, open, high, low, close, settle,
                              contracts, value_lakh, oi, chg_oi
                       FROM futures WHERE symbol=? AND date=? ORDER BY expiry""",
                     (symbol, _fd))
            st.markdown(render_futures_table(_fut, _spot), unsafe_allow_html=True)

            # --- ⛓️ Option chain (sum, ATM ± 8 strikes) ---
            st.markdown("#### ⛓️ Option chain (sum — ATM ke aas-paas)")
            _sc = analysis.sum_chain(symbol, _fd)
            if not _sc.empty:
                for _c in ["oi_CE", "chg_oi_CE", "volume_CE",
                           "oi_PE", "chg_oi_PE", "volume_PE"]:
                    if _c not in _sc.columns:
                        _sc[_c] = 0
                _tot = _sc[["oi_CE", "oi_PE"]].sum()
                _pcr = _tot["oi_PE"] / _tot["oi_CE"] if _tot["oi_CE"] else float("nan")
                if _spot is not None:
                    _s2 = _sc.sort_values("strike").reset_index(drop=True)
                    _ai = int((_s2["strike"] - _spot).abs().argmin())
                    _sc = _s2.iloc[max(0, _ai - 8):_ai + 9]
                st.caption(f"spot {_spot:,.1f} · PCR {_pcr:.2f} · "
                           f"CE OI {_fmt(_tot['oi_CE'])} · PE OI {_fmt(_tot['oi_PE'])}")
                st.markdown(render_chain(_sc, _spot, has_ltp=False),
                            unsafe_allow_html=True)

            # --- 🏦 Estimated participant split ---
            st.markdown("#### 🏦 Estimated participant split "
                        "*(⚠️ proportional estimate)*")
            _pmax = q("SELECT MAX(date) d FROM participant")["d"].iloc[0]
            _part = q("SELECT client_type, fut_stk_long FROM participant WHERE date=? "
                      "AND metric='oi' AND client_type IN ('FII','DII','Pro','Client')",
                      (_pmax,))
            _soi = q("SELECT SUM(oi) oi FROM futures WHERE symbol=? AND date=?",
                     (symbol, _fd))
            _stoi = float(_soi["oi"].iloc[0]) if not _soi.empty and pd.notna(_soi["oi"].iloc[0]) else 0
            if not _part.empty and _stoi:
                st.markdown(render_est_split(_part, _stoi), unsafe_allow_html=True)

# =========================================================================== #
# TAB 1 — date-wise stock view
# =========================================================================== #
elif section == "📈 Stock (date-wise)":
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
elif section == "⛓️ Option chain":
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
                ch = q("""SELECT strike, opt_type, oi, chg_oi, volume, close
                          FROM options WHERE symbol=? AND date=? AND expiry=?""",
                       (symbol, odate, exp))
                if ch.empty:
                    st.write("—")
                    continue
                piv = ch.pivot_table(index="strike", columns="opt_type",
                                     values=["oi", "chg_oi", "volume", "close"])
                piv.columns = [f"{a}_{b}" for a, b in piv.columns]
                piv = piv.reset_index()
                for c in ["oi_CE", "chg_oi_CE", "volume_CE",
                          "oi_PE", "chg_oi_PE", "volume_PE"]:
                    if c not in piv.columns:
                        piv[c] = 0
                st.markdown(render_chain(window_strikes(piv), spot_px, has_ltp=True),
                            unsafe_allow_html=True)

        # Full raw option data (all columns: OHLC, settle, contracts, value…)
        with st.expander("📋 Full option data (raw — saare columns)"):
            raw = q("""SELECT expiry, strike, opt_type, open, high, low, close,
                              settle, oi, chg_oi, volume, contracts, value_lakh
                       FROM options WHERE symbol=? AND date=?
                       ORDER BY expiry, strike, opt_type""", (symbol, odate))
            st.dataframe(raw, width="stretch", hide_index=True)
            st.caption(f"{len(raw)} rows · value_lakh column = turnover in raw ₹")

# =========================================================================== #
# TAB — FII / DII / Pro / Client participant OI & Volume
# =========================================================================== #
elif section == "🏦 FII/DII":
    st.subheader("FII / DII / Pro / Client — F&O positions")
    pdates = q("SELECT DISTINCT date FROM participant ORDER BY date DESC")["date"].tolist()
    if not pdates:
        st.info("Participant data abhi nahi. `python fetch_participant.py` chalao "
                "(ya run_daily.py).")
    else:
        pdate = date_slider("Date", pdates, "fii_date")
        st.caption("Net = Long − Short (contracts). "
                   "Green = net long (bullish), red = net short (bearish). "
                   "FII/DII ka rukh market sentiment dikhata hai.")

        st.markdown("#### Open Interest (positions held)")
        oi = q("SELECT * FROM participant WHERE date=? AND metric='oi'", (pdate,))
        st.markdown(render_participant(oi), unsafe_allow_html=True)

        st.markdown("#### Trading Volume (contracts traded)")
        vol = q("SELECT * FROM participant WHERE date=? AND metric='vol'", (pdate,))
        st.markdown(render_participant(vol), unsafe_allow_html=True)

        with st.expander("📋 Full raw data (saare 14 columns)"):
            raw = q("SELECT metric,client_type,fut_idx_long,fut_idx_short,"
                    "fut_stk_long,fut_stk_short,opt_idx_call_long,opt_idx_put_long,"
                    "opt_idx_call_short,opt_idx_put_short,opt_stk_call_long,"
                    "opt_stk_put_long,opt_stk_call_short,opt_stk_put_short,"
                    "total_long,total_short FROM participant WHERE date=? "
                    "ORDER BY metric,client_type", (pdate,))
            st.dataframe(raw, width="stretch", hide_index=True)

# =========================================================================== #
# TAB — Positioning (estimated split + real OI buildup)
# =========================================================================== #
elif section == "🎯 Positioning":
    st.subheader("Stock positioning")
    pos_dates = q("SELECT DISTINCT date FROM futures ORDER BY date DESC")["date"].tolist()
    if not pos_dates:
        st.info("F&O data abhi nahi.")
    else:
        ldate = date_slider("Date", pos_dates, "pos_date")

        # --- Real OI buildup ---
        st.markdown("#### Real OI buildup — price + OI change (reliable)")
        st.caption("Price ↑ + OI ↑ = Long Buildup · Price ↓ + OI ↑ = Short Buildup · "
                   "Price ↑ + OI ↓ = Short Covering · Price ↓ + OI ↓ = Long Unwinding")
        pr = q("SELECT symbol, close, prev_close FROM prices WHERE date=?", (ldate,))
        fu = q("SELECT symbol, SUM(oi) oi, SUM(chg_oi) chg_oi FROM futures "
               "WHERE date=? GROUP BY symbol", (ldate,))
        scan = pr.merge(fu, on="symbol")
        scan = scan[scan["prev_close"] > 0].copy()
        scan["price_chg_pct"] = (scan["close"] / scan["prev_close"] - 1) * 100
        scan["buildup"] = [classify_buildup(p, o)
                           for p, o in zip(scan["price_chg_pct"], scan["chg_oi"])]

        sel = scan[scan["symbol"] == symbol]
        if not sel.empty:
            b = sel.iloc[0]
            col = BUILDUP_COLOR.get(b["buildup"], "#888")
            st.markdown(f"**{symbol}:** price {b['price_chg_pct']:+.2f}% · "
                        f"OI chg {b['chg_oi']:+,.0f} → "
                        f"<span style='color:{col};font-weight:600;font-size:18px'>"
                        f"{b['buildup']}</span>", unsafe_allow_html=True)

        counts = scan["buildup"].value_counts()
        cc = st.columns(4)
        for i, b in enumerate(["Long Buildup", "Short Buildup",
                               "Short Covering", "Long Unwinding"]):
            cc[i].metric(b, int(counts.get(b, 0)))

        st.markdown("**Market scan — kaunse stocks me kya positioning:**")
        pick = st.selectbox("Buildup filter", ["All", "Long Buildup", "Short Buildup",
                                               "Short Covering", "Long Unwinding"])
        show = scan if pick == "All" else scan[scan["buildup"] == pick]
        st.markdown(render_buildup_scan(show), unsafe_allow_html=True)

# =========================================================================== #
# TAB — overview (all-stock math stats)
# =========================================================================== #
elif section == "📊 Overview":
    st.subheader("All F&O stocks — math stats")
    stats = q("""SELECT symbol, cum_return, cagr, ann_volatility, volatility,
                        sharpe, max_drawdown, beta, zscore, pct_rank_52w,
                        skew, kurtosis, daily_return, mean_return,
                        put_call_ratio, total_oi, oi_change, futures_premium
                 FROM stats""")
    if stats.empty:
        st.info("Stats abhi nahi. `python analysis.py` chalao.")
    else:
        sort_opts = {
            "Volatility (zyada → kam)": ("ann_volatility", False),
            "Return (zyada → kam)": ("cum_return", False),
            "Sharpe (best → worst)": ("sharpe", False),
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
        st.caption("Green = up / positive, red = down / negative · bars = "
                   "volatility & 52-week position. Stats split/bonus-adjusted.")

