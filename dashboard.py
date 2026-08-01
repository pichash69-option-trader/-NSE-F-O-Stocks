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


# --------------------------------------------------------------------------- #
# Next-day shortlist — statistical screener (educational, NOT advice)
# --------------------------------------------------------------------------- #
_BUILDUP_LBL = {2: "Long Buildup", 1: "Short Covering",
                -1: "Long Unwinding", -2: "Short Buildup", 0: "—"}


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


def render_picks(rows, score_col, side=None, show_result=False):
    """Compact themed table of shortlisted stocks with reasons. When show_result
    (a past day), also shows next-day actual move + ✓/✗ (was the pick right)."""
    if rows is None or rows.empty:
        return "<i>—</i>"
    r = []
    for _, x in rows.iterrows():
        d = x["ret_1d"]
        dcls = "up" if d >= 0 else "dn"
        prem = x["premium_pct"]
        prem_s = f"{prem:+.2f}" if pd.notna(prem) else "—"
        pcr_s = f"{x['pcr']:.2f}" if pd.notna(x["pcr"]) else "—"
        res = ""
        if show_result:
            nx = x.get("ret_next")
            if pd.notna(nx):
                nxp = nx * 100
                ncls = "up" if nxp >= 0 else "dn"
                hit = (nxp > 0) if side == "up" else (nxp < 0)
                mark = ('<span style="color:#10b981;font-weight:700">✓</span>' if hit
                        else '<span style="color:#f43f5e;font-weight:700">✗</span>')
                res = f'<td class="{ncls}">{nxp:+.2f}%</td><td>{mark}</td>'
            else:
                res = '<td>—</td><td>—</td>'
        r.append(
            f'<tr><td class="date" style="font-weight:600">{x["symbol"]}</td>'
            f'<td class="{dcls}">{d:+.2f}%</td>'
            f'<td style="font-size:11px">{_BUILDUP_LBL.get(int(x["buildup_val"]), "—")}</td>'
            f'<td>{prem_s}</td><td>{pcr_s}</td>'
            f'<td style="font-weight:600">{x[score_col]:+.2f}</td>{res}</tr>')
    extra_h = '<th>Kal%</th><th>✓/✗</th>' if show_result else ''
    return (STOCK_CSS +
            '<div style="overflow-x:auto"><table class="stbl" style="min-width:380px">'
            '<thead><tr><th class="l">Stock</th><th>1D%</th><th>Buildup</th>'
            '<th>Prem%</th><th>PCR</th><th>Score</th>' + extra_h + '</tr></thead><tbody>'
            + "".join(r) + '</tbody></table></div>')


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


def render_chain(df, spot, has_ltp, ltp_col_ce="close_CE", ltp_col_pe="close_PE",
                 extra=False):
    """Build a Sensibull-style HTML option chain from a per-strike DataFrame.

    Core columns: strike, oi_CE, chg_oi_CE, volume_CE, oi_PE, chg_oi_PE,
    volume_PE (+ optional close_CE/close_PE for LTP).
    With extra=True, also renders per-side Open/High/Low/Settle/Turnover
    (needs open_/high_/low_/settle_/value_lakh_ columns) — used for the
    per-expiry chains so the raw data lives INSIDE the chain, not a table below.
    """
    if df is None or df.empty:
        return "<i>—</i>"
    df = df.sort_values("strike")
    mx = float(pd.concat([df["oi_CE"], df["oi_PE"]]).abs().max() or 0)
    atm = df.iloc[(df["strike"] - spot).abs().argmin()]["strike"] if spot else None

    def _px(v):
        return f"{v:.1f}" if pd.notna(v) else "—"

    ex_head_ce = ("<th>Open</th><th>High</th><th>Low</th><th>Settle</th>"
                  "<th>Turnover</th>") if extra else ""
    ex_head_pe = ("<th>Turnover</th><th>Settle</th><th>Low</th><th>High</th>"
                  "<th>Open</th>") if extra else ""
    head_ce = ("<th>OI</th><th>Chg OI</th><th>Vol</th>"
               + ("<th>LTP</th>" if has_ltp else "") + ex_head_ce)
    head_pe = (ex_head_pe + ("<th>LTP</th>" if has_ltp else "")
               + "<th>Vol</th><th>Chg OI</th><th>OI</th>")
    rows = []
    for _, r in df.iterrows():
        strike = r["strike"]
        itm_ce = " itmce" if (spot and strike < spot) else ""
        itm_pe = " itmpe" if (spot and strike > spot) else ""
        atm_cls = " atm" if strike == atm else ""
        cc, pc = itm_ce.strip(), itm_pe.strip()
        ltp_ce = f'<td class="{cc}">{r.get(ltp_col_ce, float("nan")):.2f}</td>' if has_ltp and pd.notna(r.get(ltp_col_ce)) else ("<td></td>" if has_ltp else "")
        ltp_pe = f'<td class="{pc}">{r.get(ltp_col_pe, float("nan")):.2f}</td>' if has_ltp and pd.notna(r.get(ltp_col_pe)) else ("<td></td>" if has_ltp else "")
        ex_ce = ex_pe = ""
        if extra:
            ex_ce = (f'<td class="{cc}">{_px(r.get("open_CE"))}</td>'
                     f'<td class="{cc}">{_px(r.get("high_CE"))}</td>'
                     f'<td class="{cc}">{_px(r.get("low_CE"))}</td>'
                     f'<td class="{cc}">{_px(r.get("settle_CE"))}</td>'
                     f'<td class="{cc}">{_fmt(r.get("value_lakh_CE"))}</td>')
            ex_pe = (f'<td class="{pc}">{_fmt(r.get("value_lakh_PE"))}</td>'
                     f'<td class="{pc}">{_px(r.get("settle_PE"))}</td>'
                     f'<td class="{pc}">{_px(r.get("low_PE"))}</td>'
                     f'<td class="{pc}">{_px(r.get("high_PE"))}</td>'
                     f'<td class="{pc}">{_px(r.get("open_PE"))}</td>')
        strike_lbl = f"{strike:.0f}" + (" · ATM" if strike == atm else "")
        rows.append(
            f'<tr class="{atm_cls.strip()}">'
            f'<td class="{cc}">{_cell_oi(r["oi_CE"], mx, "ce")}</td>'
            f'<td class="{cc}">{_cell_chg(r["chg_oi_CE"])}</td>'
            f'<td class="{cc}">{_fmt(r["volume_CE"])}</td>'
            f'{ltp_ce}{ex_ce}'
            f'<td class="stk">{strike_lbl}</td>'
            f'{ex_pe}{ltp_pe}'
            f'<td class="{pc}">{_fmt(r["volume_PE"])}</td>'
            f'<td class="{pc}">{_cell_chg(r["chg_oi_PE"])}</td>'
            f'<td class="{pc}">{_cell_oi(r["oi_PE"], mx, "pe")}</td>'
            f'</tr>')
    span = 3 + (1 if has_ltp else 0) + (5 if extra else 0)
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
        pcl = f'{r["prev_close"]:.1f}' if pd.notna(r.get("prev_close")) else "—"
        stl = f'{r["settle"]:.1f}' if pd.notna(r.get("settle")) else "—"
        dqty = _fmt(r["deliv_qty"]) if pd.notna(r.get("deliv_qty")) else "—"
        rows.append(
            f'<tr><td class="date">{r["date"]}</td>'
            f'<td>{r["open"]:.1f}</td><td>{r["high"]:.1f}</td><td>{r["low"]:.1f}</td>'
            f'<td class="cl {"up" if up else "dn"}">{r["close"]:.1f}</td>'
            f'<td>{pcl}</td><td>{stl}</td>'
            f'<td>{pill}</td>'
            f'<td class="bar-cell">{volcell}</td>'
            f'<td>{turn}</td><td>{trades}</td>'
            f'<td>{dqty}</td>'
            f'<td class="bar-cell">{delcell}</td></tr>')
    legend = ('<div class="stlg">Close green/red = up/down din · '
              'bars = volume &amp; delivery% · turnover ₹Cr · prices split/bonus-adjusted '
              '(Prev Close &amp; Settle raw). Neeche candle chart me hover karo.</div>')
    return (STOCK_CSS + legend +
            '<div style="overflow-x:auto"><table class="stbl"><thead><tr>'
            '<th class="l">Date</th>'
            '<th>Open</th><th>High</th><th>Low</th><th>Close</th>'
            '<th>Prev Cl</th><th>Settle</th>'
            '<th>Chg%</th><th>Volume</th><th>Turnover ₹Cr</th><th>Trades</th>'
            '<th>Deliv Qty</th><th>Deliv%</th>'
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
            f'<td>{col(r.get("ret_1w"), "{:+.1f}")}%</td>'
            f'<td>{col(r.get("ret_1m"), "{:+.1f}")}%</td>'
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
            '<th>Day Ret%</th><th>1W%</th><th>1M%</th><th>Mean Ret%</th><th>PCR</th><th>Total OI</th>'
            '<th>OI Chg</th><th>Fut Prem</th>'
            '</tr></thead><tbody>' + "".join(rows) + '</tbody></table></div>')


# Compact + clearly-scrollable styling for the wide 18-column overview table.
OVERVIEW_CSS = """
<style>
.ovwrap{overflow-x:auto;
  border:1px solid rgba(255,255,255,.06);border-radius:10px;}
.ovwrap::-webkit-scrollbar{height:10px;width:10px;}
.ovwrap::-webkit-scrollbar-thumb{background:#6366f1;border-radius:6px;}
.ovwrap::-webkit-scrollbar-track{background:rgba(255,255,255,.04);}
.ovtbl{min-width:1200px;font-size:11.5px;}
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


def _participant_nets(df):
    """Return {client_type: dict of net positions} from a participant df.
    net = Long − Short for each segment."""
    out = {}
    for _, r in df.iterrows():
        out[r["client_type"]] = {
            "idxfut": r["fut_idx_long"] - r["fut_idx_short"],
            "stkfut": r["fut_stk_long"] - r["fut_stk_short"],
            "idxopt": ((r["opt_idx_call_long"] + r["opt_idx_put_long"])
                       - (r["opt_idx_call_short"] + r["opt_idx_put_short"])),
            "stkopt": ((r["opt_stk_call_long"] + r["opt_stk_put_long"])
                       - (r["opt_stk_call_short"] + r["opt_stk_put_short"])),
            "tnet": r["total_long"] - r["total_short"],
        }
    return out


_SEG_ORDER = ["Stock Futures", "Index Futures", "Index Options", "Stock Options"]


def _seg_metrics(r):
    """{segment: (net, gross)} for one participant row. Futures net = Long − Short;
    options net = bullish(call_long + put_short) − bearish(put_long + call_short)."""
    def n(k):
        v = r[k]
        return v if pd.notna(v) else 0
    io_b, io_be = n("opt_idx_call_long") + n("opt_idx_put_short"), n("opt_idx_put_long") + n("opt_idx_call_short")
    so_b, so_be = n("opt_stk_call_long") + n("opt_stk_put_short"), n("opt_stk_put_long") + n("opt_stk_call_short")
    return {
        "Stock Futures": (n("fut_stk_long") - n("fut_stk_short"),
                          n("fut_stk_long") + n("fut_stk_short")),
        "Index Futures": (n("fut_idx_long") - n("fut_idx_short"),
                          n("fut_idx_long") + n("fut_idx_short")),
        "Index Options": (io_b - io_be, io_b + io_be),
        "Stock Options": (so_b - so_be, so_b + so_be),
    }


def _senti(score):
    """(label, dirn, opacity) from a −1..+1 sentiment score (net / gross)."""
    a = abs(score)
    if a < 0.05:
        return ("Indecisive", "neu", 0.0)
    word = "Bullish" if score > 0 else "Bearish"
    dirn = "bull" if score > 0 else "bear"
    lvl, op = (("Strong", 0.95) if a >= 0.33 else
               ("Medium", 0.72) if a >= 0.15 else ("Mild", 0.5))
    return (f"{lvl} {word}", dirn, op)


PARTI_SENTI_CSS = """
<style>
.psent{width:100%;border-collapse:collapse;font-size:12px;min-width:720px;}
.psent th{font-size:11px;color:#9ca3af;font-weight:600;padding:7px 10px;text-align:right;
  border-bottom:1px solid rgba(148,163,184,.2);}
.psent th.l{text-align:left;}
.psent td{padding:6px 10px;text-align:right;border-top:1px solid rgba(148,163,184,.12);
  vertical-align:middle;}
.psent td.part{font-weight:700;color:#e5e7eb;white-space:nowrap;}
.psent td.seg{text-align:left;color:#cbd5e1;white-space:nowrap;}
.psent tr.grp td{border-top:2px solid rgba(148,163,184,.3);}
.psent .up{color:#10b981;} .psent .dn{color:#f43f5e;}
.strack{position:relative;height:24px;min-width:240px;}
.strack::before{content:"";position:absolute;left:50%;top:1px;bottom:1px;
  border-left:1px dashed rgba(148,163,184,.35);}
.spill{position:absolute;top:3px;height:18px;line-height:18px;padding:0 9px;border-radius:4px;
  font-size:10.5px;font-weight:700;color:#fff;white-space:nowrap;
  text-shadow:0 1px 2px rgba(0,0,0,.4);}
.spill.bull{left:50%;} .spill.bear{right:50%;}
.sneu{position:absolute;left:0;right:0;top:0;line-height:24px;text-align:center;
  color:#9ca3af;font-size:11px;}
.psent .mtag{font-size:9.5px;font-weight:700;padding:1px 5px;border-radius:3px;margin-left:6px;}
.psent .mtag.oi{background:rgba(99,102,241,.18);color:#a5b4fc;}
.psent .mtag.vol{background:rgba(245,158,11,.18);color:#fcd34d;}
.psent tr.vrow td{background:rgba(255,255,255,.014);}
.psent tr.vrow td.seg{color:#9ca3af;}
</style>
"""


def _senti_row(ct_show, seg_label, cm, pm, ct, seg, tr_cls):
    """One sentiment row: bar + net + day-over-day change for a participant/segment."""
    net, gross = cm[ct][seg]
    score = net / gross if gross else 0.0
    label, dirn, op = _senti(score)
    if dirn == "neu":
        bar = f'<div class="strack"><span class="sneu">{label}</span></div>'
    else:
        rgb = "16,185,129" if dirn == "bull" else "244,63,94"
        side = "left" if dirn == "bull" else "right"
        bar = (f'<div class="strack"><span class="spill {dirn}" '
               f'style="{side}:50%;background:rgba({rgb},{op:.2f})">{label}</span></div>')
    chg = "—"
    if ct in pm:
        dnet = net - pm[ct][seg][0]
        c = "up" if dnet >= 0 else "dn"
        chg = f'<span class="{c}">{"+" if dnet>=0 else ""}{_fmt(dnet)}</span>'
    return (f'<tr class="{tr_cls}"><td class="part">{ct_show}</td>'
            f'<td class="seg">{seg_label}</td>'
            f'<td>{bar}</td><td>{_fmt(net)}</td><td>{chg}</td></tr>')


def render_participant_sentiment(oi, prev_oi, vol, prev_vol):
    """Sensibull-style sentiment table. Per participant × segment, TWO stacked
    lines: (OI) standing position + (Vol) that day's traded direction — each with
    a Bearish‹—›Bullish bar, Net, and day-over-day Change."""
    if oi is None or oi.empty:
        return "<i>—</i>"
    keep = ("FII", "DII", "Pro", "Client")

    def mm(df):
        return ({r["client_type"]: _seg_metrics(r) for _, r in df.iterrows()
                 if r["client_type"] in keep}
                if df is not None and not df.empty else {})
    oim, poim, volm, pvolm = mm(oi), mm(prev_oi), mm(vol), mm(prev_vol)

    rows = []
    for ct in keep:
        if ct not in oim:
            continue
        first = True
        for seg in _SEG_ORDER:
            rows.append(_senti_row(
                ct if first else "", f'{seg} <span class="mtag oi">OI</span>',
                oim, poim, ct, seg, "grp" if first else ""))
            first = False
            if ct in volm:
                rows.append(_senti_row(
                    "", f'{seg} <span class="mtag vol">Vol</span>',
                    volm, pvolm, ct, seg, "vrow"))
    return (PARTI_SENTI_CSS +
            '<div style="overflow-x:auto"><table class="psent"><thead><tr>'
            '<th class="l">Participant</th><th class="l">Segment</th>'
            '<th>Bearish&nbsp;‹—›&nbsp;Bullish</th><th>Net</th><th>Change</th>'
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


# --------------------------------------------------------------------------- #
# Sidebar — QuantCalc-style logo + navigation menu + stock controls
# --------------------------------------------------------------------------- #
SECTIONS = ["📈 Equity / Cash", "🔮 Futures", "⛓️ Options",
            "🏦 Participant", "📊 Math stats", "🎯 Next-day shortlist"]

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

# =========================================================================== #
# TAB — overview (all-stock math stats)
# =========================================================================== #
elif section == "📊 Math stats":
    st.subheader("All F&O stocks — math stats")
    stats = q("""SELECT symbol, cum_return, cagr, ann_volatility, volatility,
                        sharpe, max_drawdown, beta, zscore, pct_rank_52w,
                        skew, kurtosis, daily_return, mean_return,
                        put_call_ratio, total_oi, oi_change, futures_premium
                 FROM stats""")
    if stats.empty:
        st.info("Stats abhi nahi. `python analysis.py` chalao.")
    else:
        # Add-on: multi-window returns (trend) — 1D already = Day Ret%; add 1W + 1M.
        stats = stats.merge(window_returns(), left_on="symbol",
                            right_index=True, how="left")
        sort_opts = {
            "1-day return (zyada → kam)": ("daily_return", False),
            "1-week return (zyada → kam)": ("ret_1w", False),
            "1-month return (zyada → kam)": ("ret_1m", False),
            "Volatility (zyada → kam)": ("ann_volatility", False),
            "Return — poora period (zyada → kam)": ("cum_return", False),
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
        st.caption("Green = up / positive, red = down / negative · **Day Ret% · 1W% · 1M%** "
                   "= trend across timeframes (momentum) · bars = volatility & 52-week "
                   "position. Split/bonus-adjusted. Right scroll = saare columns.")

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
        st.caption("Columns: **1D%** (us din ka move) · **Buildup** (OI se) · **Prem%** "
                   "(futures premium) · **PCR** · **Score** (composite). Past din pe **Kal%** "
                   "= agle din ka actual move · **✓** = shortlist sahi, **✗** = galat. "
                   "Slider se pichhle din scrub karke dekho strategy kaisa chala.")

