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

# Help content — shown from the "?" icon in the top corner (popover).
HELP_MD = """
## 👋 Dashboard kaise use karein

Ye dashboard **F&O stocks (~210)** ka NSE data **date-wise** (din-b-din) dikhata hai —
equity + futures + options + FII/DII, sab. Sab data seedha NSE se, roz auto-update.

> ⚠️ Ye **educational / research** tool hai — investment advice nahi.

---

### 🧭 Shuru kaise karein
1. **Upar header** me se ek **stock** choose karo (jaise RELIANCE).
2. **"Kitne din dekhne hain"** — 7 / 20 / 50 / All chuno.
3. Neeche **6 tabs** me apna data dekho (date-wale tabs me **slider** se din badlo — fast scrub).

---

### 📈 Stock (date-wise)
Har din ek row: **OHLC, Chg%** (green/red pill), **Volume & Delivery%** (bars),
**Turnover ₹Cr, Trades**. Neeche **candle chart** — kisi candle par hover = poori detail.
🟢 up din · 🔴 down din. (Delivery% high = real buying, sirf speculation nahi.)

### 🔮 Futures
1. **Teeno expiry** (near/next/far) ka total + changes — OHLC, Settle, **Premium**
   (future − spot; +ve = bullish hint), **OI + Chg OI** (bars/colors), Σ TOTAL row.
2. **Estimated participant split** — ⚠️ ye *estimate* hai (real per-stock FII/DII data
   publicly nahi milta), rough idea ke liye.

### ⛓️ Option chain (Sensibull style)
- **Σ Sum chain** — teeno expiry ka har strike par total. Phir **har expiry ka apna chain**.
- 🟧 CALLS ITM shaded · 🟥 PUTS ITM shaded · 🔵 **ATM** row · ChgOI green = OI add, red = cut.
- **Strikes ± slider** se kitne strikes dikhane control karo. **Max pain** heading me.
- **PCR** = Put OI ÷ Call OI (>1 = zyada puts/bearish, <1 = bullish).

### 🏦 FII/DII
**FII / DII / Pro / Client** ka F&O positioning (OI + Volume). **Net = Long − Short**:
🟢 net long (bullish), 🔴 net short (bearish). Ye market ka **overall** rukh dikhata hai
(saare stocks ka jod — per-stock nahi).

### 🎯 Positioning
**Real OI buildup** (price + OI change se) — har stock ka:
- Price ↑ + OI ↑ = **Long Buildup** (bulls) · Price ↓ + OI ↑ = **Short Buildup** (bears)
- Price ↑ + OI ↓ = **Short Covering** · Price ↓ + OI ↓ = **Long Unwinding**
Market scan + filter — kaunse stocks me kaunsa buildup ho raha, ek nazar me.

### 📊 Overview
Saare stocks ka **math** ek table me — Return, Volatility, Sharpe, Max DD, Beta,
Z-score, 52w %ile, Skew/Kurtosis, PCR, OI. **"Sort by"** se sort karo.
(Sab stats **split/bonus-adjusted** hain.)

---

### 🔄 Data update
Har trading din **market close ke baad (~6:30 PM IST)** naya data auto-add hota hai.
Weekend/holiday skip. Latest din upar.

**Bas! Stock chuno, din chuno, explore karo.** 🚀
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


# --------------------------------------------------------------------------- #
# Sensibull-style option chain (custom HTML/CSS)
# --------------------------------------------------------------------------- #
CHAIN_CSS = """
<style>
.oc{width:100%;border-collapse:collapse;font-size:12px;font-family:var(--font,sans-serif);}
.oc th{font-size:11px;color:#9aa0a6;font-weight:600;padding:6px 8px;text-align:right;}
.oc td{padding:5px 8px;text-align:right;border-top:1px solid rgba(150,150,150,.18);position:relative;}
.oc .stk{text-align:center;font-weight:600;background:rgba(130,130,130,.14);}
.oc .itmce{background:rgba(240,159,39,.14);}
.oc .itmpe{background:rgba(226,75,74,.12);}
.oc tr.atm td{border-top:2px solid #378add;border-bottom:2px solid #378add;}
.oc .up{color:#1faa6e;} .oc .dn{color:#e24b4a;}
.oc .bar{position:absolute;top:3px;bottom:3px;opacity:.30;border-radius:3px;z-index:0;}
.oc .bce{right:0;background:#e24b4a;} .oc .bpe{left:0;background:#1faa6e;}
.oc .v{position:relative;z-index:1;}
.oc-h{display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px;font-size:12px;margin:2px 0 6px;}
.oc-lg{font-size:11px;color:#9aa0a6;margin-bottom:6px;}
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
            f'<tr><th colspan="{span}" style="text-align:center;color:#ef9f27">CALLS</th>'
            '<th class="stk">STRIKE</th>'
            f'<th colspan="{span}" style="text-align:center;color:#e24b4a">PUTS</th></tr>'
            f'<tr>{head_ce}<th class="stk">Strike</th>{head_pe}</tr>'
            '</thead><tbody>' + "".join(rows) + '</tbody></table></div>')


CHAIN_LEGEND = ('<div class="oc-lg">'
                '<b style="color:#ef9f27">▎</b> CALLS ITM shaded &nbsp; '
                '<b style="color:#e24b4a">▎</b> PUTS ITM shaded &nbsp; '
                '<b style="color:#1faa6e">▎</b> OI addition &nbsp; '
                '<b style="color:#e24b4a">▎</b> OI reduction &nbsp; '
                '<b style="color:#378add">━</b> ATM</div>')


# --------------------------------------------------------------------------- #
# Rich "Stock — all data" table (glanceable, like the option chain)
# --------------------------------------------------------------------------- #
STOCK_CSS = """
<style>
.stbl{width:100%;border-collapse:collapse;font-size:12px;min-width:640px;}
.stbl th{font-size:11px;color:#9aa0a6;font-weight:600;padding:6px 8px;text-align:right;}
.stbl th.l{text-align:left;} .stbl th.c{text-align:center;}
.stbl td{padding:5px 8px;text-align:right;border-top:1px solid rgba(150,150,150,.16);}
.stbl td.date{text-align:left;color:#c9cdd3;white-space:nowrap;}
.stbl .up{color:#1faa6e;} .stbl .dn{color:#e24b4a;}
.stbl .cl{font-weight:600;}
.stbl .pill{display:inline-block;padding:1px 7px;border-radius:10px;font-weight:600;}
.stbl .pu{background:rgba(31,170,110,.16);color:#1faa6e;}
.stbl .pd{background:rgba(226,75,74,.16);color:#e24b4a;}
.candle{position:relative;height:16px;width:150px;display:inline-block;vertical-align:middle;}
.wick{position:absolute;top:7px;height:2px;background:#8a8f98;border-radius:2px;}
.body{position:absolute;top:3px;height:10px;border-radius:2px;}
.bar-cell{position:relative;}
.bar-bg{position:absolute;top:4px;bottom:4px;left:0;border-radius:3px;opacity:.28;}
.bar-vol{background:#6f9fd8;} .bar-del{background:#1faa6e;}
.bar-v{position:relative;z-index:1;}
.stlg{font-size:11px;color:#9aa0a6;margin:2px 0 6px;}
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
    return (STOCK_CSS +
            '<div style="overflow-x:auto"><table class="stbl" style="min-width:1150px">'
            '<thead><tr>'
            '<th class="l">Symbol</th><th>Return%</th><th>CAGR%</th><th>Ann Vol</th>'
            '<th>Daily Vol</th><th>Sharpe</th><th>Max DD</th><th>Beta</th>'
            '<th>Z-score</th><th>52w %ile</th><th>Skew</th><th>Kurt</th>'
            '<th>Day Ret%</th><th>Mean Ret%</th><th>PCR</th><th>Total OI</th>'
            '<th>OI Chg</th><th>Fut Prem</th>'
            '</tr></thead><tbody>' + "".join(rows) + '</tbody></table></div>')


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
            '<style>.stbl tr.tot td{border-top:2px solid #378add;font-weight:600;'
            'background:rgba(55,138,221,.10);}</style>'
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
            '<style>.stbl tr.tot td{border-top:2px solid #378add;font-weight:600;'
            'background:rgba(55,138,221,.10);}</style>'
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


BUILDUP_COLOR = {"Long Buildup": "#1faa6e", "Short Covering": "#5dcAa5",
                 "Short Buildup": "#e24b4a", "Long Unwinding": "#f0997b"}


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
# Top header (controls moved here from the sidebar)
# --------------------------------------------------------------------------- #
htitle, hqmark = st.columns([8, 1])
htitle.markdown("### NSE F&O Stocks — date-wise")
with hqmark.popover("❓", help="How to use — click karo"):
    st.markdown(HELP_MD)

hc1, hc2 = st.columns([1, 2])
symbol = hc1.selectbox("Stock", all_symbols(), index=0)
lookback = hc2.radio("Kitne din dekhne hain", [7, 20, 50, "All"], index=1,
                     horizontal=True)
st.divider()

tab_all, tab_stock, tab_fut, tab_chain, tab_fii, tab_pos, tab_overview = st.tabs(
    ["🔎 Full view", "📈 Stock (date-wise)", "🔮 Futures", "⛓️ Option chain",
     "🏦 FII/DII", "🎯 Positioning", "📊 Overview"])

# =========================================================================== #
# TAB — Full view (selected stock ka SAB data ek page par)
# =========================================================================== #
with tab_all:
    st.subheader(f"🔎 {symbol} — poora data (ek jagah)")
    st.caption("Upar header se stock badlo — sab sections isi tab me update honge.")
    _hist = stock_history(symbol)
    if _hist.empty:
        st.warning(f"{symbol}: koi data nahi.")
    else:
        _lt = _hist.iloc[-1]                         # latest day (for metrics)
        _fd = q("SELECT MAX(date) d FROM futures WHERE symbol=?", (symbol,))["d"].iloc[0]
        _spot = None
        if _fd:
            _sp = q("SELECT close FROM prices WHERE symbol=? AND date=?", (symbol, _fd))
            _spot = float(_sp.iloc[0]["close"]) if not _sp.empty else None
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
                c = "#1faa6e" if v >= 0 else "#e24b4a"
                return f"<span style='color:{c}'>{f.format(v)}</span>"
            st.markdown(
                "<div style='font-size:13px;line-height:2'>"
                f"Cumulative return: {_sc_txt(r['cum_return']*100, '{:+.1f}')}% · "
                f"CAGR: {_sc_txt(r['cagr']*100, '{:+.1f}')}% · "
                f"Ann volatility: {r['ann_volatility']*100:.1f}% · "
                f"Sharpe: {_sc_txt(r['sharpe'])} · "
                f"Max drawdown: <span style='color:#e24b4a'>{r['max_drawdown']*100:.1f}%</span> · "
                f"Beta: {r['beta']:.2f} · "
                f"Z-score: {_sc_txt(r['zscore'])} · "
                f"52w %ile: {r['pct_rank_52w']:.0f} · "
                f"Skew: {r['skew']:.2f} · Kurtosis: {r['kurtosis']:.2f} · "
                f"PCR: {r['put_call_ratio']:.2f} · "
                f"Futures premium: {_sc_txt(r['futures_premium'], '{:+.1f}')}"
                "</div>", unsafe_allow_html=True)

        st.divider()

        # --- Days slider — kitne din ka price data (fast scrub) ---
        _maxd = len(_hist)
        _days = st.slider("📅 Kitne din ka price data dekhna hai", 5,
                          min(250, _maxd), min(20, _maxd), key="fullview_days")
        _view = _hist.tail(_days)

        # --- 📈 Price (date-wise) + candle ---
        st.markdown("#### 📈 Price — date-wise")
        st.markdown(render_stock_table(_view), unsafe_allow_html=True)
        _cv = _view.copy()
        _hover = [
            (f"{d}<br>O {o:.1f} H {h:.1f} L {l:.1f} C {c:.1f}"
             f"<br>Chg {ch:+.2f}% · Vol {_fmt(vol)}"
             + (f"<br>Deliv {dp:.1f}%" if pd.notna(dp) else ""))
            for d, o, h, l, c, ch, vol, dp in zip(
                _cv["date"], _cv["open"], _cv["high"], _cv["low"], _cv["close"],
                _cv["chg_pct"], _cv["volume"], _cv["deliv_pct"])]
        _fig = go.Figure(go.Candlestick(
            x=_cv["date"], open=_cv["open"], high=_cv["high"], low=_cv["low"],
            close=_cv["close"], increasing_line_color="#1faa6e",
            decreasing_line_color="#e24b4a", increasing_fillcolor="#1faa6e",
            decreasing_fillcolor="#e24b4a", text=_hover, hoverinfo="text", name=""))
        _fig.update_layout(height=320, margin=dict(l=0, r=0, t=10, b=0),
                           xaxis_rangeslider_visible=False, yaxis_title="Price")
        _st = max(1, len(_cv) // 10)
        _fig.update_xaxes(type="category", tickmode="array",
                          tickvals=list(_cv["date"])[::_st])
        st.plotly_chart(_fig, width="stretch")

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
with tab_stock:
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
            increasing_line_color="#1faa6e", decreasing_line_color="#e24b4a",
            increasing_fillcolor="#1faa6e", decreasing_fillcolor="#e24b4a",
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
        st.caption("Futures 🔮 aur Option chain ⛓️ ab alag tabs me hain (upar).")

# =========================================================================== #
# TAB — Futures (totals + estimated participant split)
# =========================================================================== #
with tab_fut:
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
with tab_chain:
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
with tab_fii:
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
with tab_pos:
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
with tab_overview:
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

