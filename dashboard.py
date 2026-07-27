# -*- coding: utf-8 -*-
"""
dashboard.py — date-wise NSE dashboard (Streamlit).

Run:  streamlit run dashboard.py

All data tables use st.dataframe (native, spreadsheet-like: sortable, resizable,
scrollable) so they render reliably on every Streamlit version, with green/red
colouring via pandas Styler.
"""
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go

import db
import analysis
from config import NIFTY50

st.set_page_config(page_title="NSE NIFTY 50 — date-wise", layout="wide")

GREEN, RED = "#1faa6e", "#e24b4a"

HELP_MD = """
## 👋 Dashboard kaise use karein

Ye dashboard **NIFTY 50 / F&O stocks** ka NSE data **date-wise** dikhata hai.
Upar header me **stock** + **kitne din** chuno. Tables **sheets jaisi** hain —
column header par click karke **sort**, kinaare kheench ke resize kar sakte ho.

> ⚠️ Educational / research tool — investment advice nahi.

**Tabs:**
- 📈 **Stock** — din-b-din OHLC, chg%, volume, turnover, delivery% + candle chart
- 🔮 **Futures** — teeno expiry ka total + changes + estimated participant split
- ⛓️ **Option chain** — sum chain + har expiry ka chain (ITM shaded, ATM highlight)
- 🏦 **FII/DII** — participant OI + Volume (net Long−Short positions)
- 🎯 **Positioning** — real OI buildup (Long/Short buildup scan)
- 📊 **Overview** — saare stocks ka math stats

Sab data roz market close ke baad auto-update hota hai.
"""


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
@st.cache_data(ttl=300)
def q(sql, params=()):
    conn = db.connect()
    try:
        return pd.read_sql_query(sql, conn, params=params)
    finally:
        conn.close()


def _fmt(n):
    """Compact Indian-style: 55000->55K, 180000->1.8L, 12000000->1.2Cr."""
    if n is None or (isinstance(n, float) and np.isnan(n)):
        return "—"
    n = float(n)
    a = abs(n)
    if a >= 1e7:
        return f"{n/1e7:.2f}Cr"
    if a >= 1e5:
        return f"{n/1e5:.1f}L"
    if a >= 1e3:
        return f"{n/1e3:.0f}K"
    return f"{n:.0f}"


def color_pos_neg(v):
    """Green for >=0, red for <0 (Styler text colour)."""
    try:
        if pd.isna(v):
            return ""
        return f"color:{GREEN}" if float(v) >= 0 else f"color:{RED}"
    except (TypeError, ValueError):
        return ""


def show_df(styler_or_df):
    st.dataframe(styler_or_df, width="stretch", hide_index=True)


def date_slider(label, dates_desc, key, window=60):
    """Slider over the most recent `window` trading days (default = latest)."""
    recent = list(reversed(dates_desc[:window]))
    if not recent:
        return None
    if len(recent) == 1:
        st.caption(f"{label}: {recent[0]}")
        return recent[0]
    return st.select_slider(label, options=recent, value=recent[-1], key=key)


@st.cache_data(ttl=300)
def all_symbols():
    df = q("SELECT DISTINCT symbol FROM prices ORDER BY symbol")
    return df["symbol"].tolist() if not df.empty else NIFTY50


def stock_history(symbol):
    df = q("SELECT date,open,high,low,close,prev_close,volume,turnover,"
           "num_trades,deliv_qty,deliv_pct FROM prices WHERE symbol=? ORDER BY date",
           (symbol,))
    if df.empty:
        return df
    df = df.sort_values("date").reset_index(drop=True)
    raw_first_close = float(df.loc[0, "close"])
    df = analysis.adjust_ohlc(df)
    df["chg_pct"] = df["close"].pct_change() * 100
    pc = df.loc[0, "prev_close"]
    if pd.notna(pc) and pc:
        df.loc[0, "chg_pct"] = (raw_first_close / pc - 1) * 100
    return df


def fno_dates(symbol):
    return q("SELECT DISTINCT date FROM options WHERE symbol=? ORDER BY date DESC",
             (symbol,))["date"].tolist()


BUILDUP_COLOR = {"Long Buildup": GREEN, "Short Covering": "#5dcaa5",
                 "Short Buildup": RED, "Long Unwinding": "#f0997b"}


def classify_buildup(price_chg, oi_chg):
    if oi_chg > 0:
        return "Long Buildup" if price_chg >= 0 else "Short Buildup"
    return "Short Covering" if price_chg >= 0 else "Long Unwinding"


# --------------------------------------------------------------------------- #
# Table builders (return pandas Styler for st.dataframe)
# --------------------------------------------------------------------------- #
def stock_table(view):
    d = view.sort_values("date", ascending=False).copy()
    d["Turnover ₹Cr"] = d["turnover"] / 1e7
    disp = d[["date", "open", "high", "low", "close", "chg_pct",
              "volume", "Turnover ₹Cr", "num_trades", "deliv_pct"]].copy()
    disp.columns = ["Date", "Open", "High", "Low", "Close", "Chg%",
                    "Volume", "Turnover ₹Cr", "Trades", "Deliv%"]
    return (disp.style
            .map(color_pos_neg, subset=["Chg%"])
            .format({"Open": "{:.1f}", "High": "{:.1f}", "Low": "{:.1f}",
                     "Close": "{:.1f}", "Chg%": "{:+.2f}%", "Volume": "{:,.0f}",
                     "Turnover ₹Cr": "{:,.1f}", "Trades": "{:,.0f}",
                     "Deliv%": "{:.1f}"}, na_rep="—"))


def futures_table(fut, spot):
    d = fut.sort_values("expiry").reset_index(drop=True).copy()
    d["tag"] = ["near", "next", "far"][:len(d)] + [""] * max(0, len(d) - 3)
    d["Expiry"] = d["expiry"] + " (" + d["tag"] + ")"
    d["Premium"] = d["close"] - spot if spot is not None else np.nan
    d["Value ₹Cr"] = d["value_lakh"] / 1e7
    disp = d[["Expiry", "open", "high", "low", "close", "settle", "Premium",
              "oi", "chg_oi", "contracts", "Value ₹Cr"]].copy()
    disp.columns = ["Expiry", "Open", "High", "Low", "Close", "Settle",
                    "Premium", "Open Interest", "Chg OI", "Contracts", "Value ₹Cr"]
    total = {"Expiry": "Σ TOTAL", "Open": np.nan, "High": np.nan, "Low": np.nan,
             "Close": np.nan, "Settle": np.nan, "Premium": np.nan,
             "Open Interest": disp["Open Interest"].sum(),
             "Chg OI": disp["Chg OI"].sum(),
             "Contracts": disp["Contracts"].sum(), "Value ₹Cr": np.nan}
    disp = pd.concat([disp, pd.DataFrame([total])], ignore_index=True)
    return (disp.style
            .map(color_pos_neg, subset=["Premium", "Chg OI"])
            .format({"Open": "{:.1f}", "High": "{:.1f}", "Low": "{:.1f}",
                     "Close": "{:.1f}", "Settle": "{:.1f}", "Premium": "{:+.2f}",
                     "Open Interest": "{:,.0f}", "Chg OI": "{:+,.0f}",
                     "Contracts": "{:,.0f}", "Value ₹Cr": "{:,.1f}"}, na_rep="—"))


def participant_table(df):
    order = {"FII": 0, "DII": 1, "Pro": 2, "Client": 3, "TOTAL": 4}
    df = df.copy()
    df["_o"] = df["client_type"].map(order).fillna(9)
    df = df.sort_values("_o")
    out = pd.DataFrame({
        "Participant": df["client_type"],
        "Idx Fut net": df["fut_idx_long"] - df["fut_idx_short"],
        "Stk Fut net": df["fut_stk_long"] - df["fut_stk_short"],
        "Idx Opt net": (df["opt_idx_call_long"] + df["opt_idx_put_long"]
                        - df["opt_idx_call_short"] - df["opt_idx_put_short"]),
        "Stk Opt net": (df["opt_stk_call_long"] + df["opt_stk_put_long"]
                        - df["opt_stk_call_short"] - df["opt_stk_put_short"]),
        "Total Long": df["total_long"],
        "Total Short": df["total_short"],
        "Net": df["total_long"] - df["total_short"],
    })
    net_cols = ["Idx Fut net", "Stk Fut net", "Idx Opt net", "Stk Opt net", "Net"]
    return (out.style
            .map(color_pos_neg, subset=net_cols)
            .format("{:+,.0f}", subset=net_cols)
            .format("{:,.0f}", subset=["Total Long", "Total Short"]))


def est_split_table(part, stock_oi):
    order = {"FII": 0, "DII": 1, "Pro": 2, "Client": 3}
    part = part.copy()
    part["_o"] = part["client_type"].map(order).fillna(9)
    part = part.sort_values("_o")
    tot = part["fut_stk_long"].sum() or 1
    out = pd.DataFrame({
        "Participant": part["client_type"],
        "Market share %": part["fut_stk_long"] / tot * 100,
        "Est. contracts (is stock me)": part["fut_stk_long"] / tot * stock_oi,
    })
    return out.style.format({"Market share %": "{:.1f}%",
                             "Est. contracts (is stock me)": "{:,.0f}"})


def buildup_table(scan):
    d = scan.sort_values("chg_oi", ascending=False).copy()
    out = pd.DataFrame({
        "Stock": d["symbol"], "Price chg%": d["price_chg_pct"],
        "Futures OI": d["oi"], "OI chg": d["chg_oi"], "Buildup": d["buildup"],
    })

    def bu_color(v):
        return f"color:{BUILDUP_COLOR.get(v, '#888')};font-weight:600"

    return (out.style
            .map(color_pos_neg, subset=["Price chg%", "OI chg"])
            .map(bu_color, subset=["Buildup"])
            .format({"Price chg%": "{:+.2f}%", "Futures OI": "{:,.0f}",
                     "OI chg": "{:+,.0f}"}, na_rep="—"))


def overview_table(df):
    d = df.reset_index(drop=True).copy()
    out = pd.DataFrame({
        "Symbol": d["symbol"], "Return%": d["cum_return"] * 100,
        "CAGR%": d["cagr"] * 100, "Ann Vol%": d["ann_volatility"] * 100,
        "Daily Vol%": d["volatility"] * 100, "Sharpe": d["sharpe"],
        "Max DD%": d["max_drawdown"] * 100, "Beta": d["beta"],
        "Z-score": d["zscore"], "52w %ile": d["pct_rank_52w"],
        "Skew": d["skew"], "Kurt": d["kurtosis"],
        "Day Ret%": d["daily_return"] * 100, "Mean Ret%": d["mean_return"] * 100,
        "PCR": d["put_call_ratio"], "Total OI": d["total_oi"],
        "OI Chg": d["oi_change"], "Fut Prem": d["futures_premium"],
    })
    signed = ["Return%", "CAGR%", "Sharpe", "Max DD%", "Z-score",
              "Day Ret%", "Mean Ret%", "OI Chg", "Fut Prem"]
    return (out.style
            .map(color_pos_neg, subset=signed)
            .format({"Return%": "{:+.1f}%", "CAGR%": "{:+.1f}%",
                     "Ann Vol%": "{:.1f}%", "Daily Vol%": "{:.2f}%",
                     "Sharpe": "{:+.2f}", "Max DD%": "{:.1f}%", "Beta": "{:.2f}",
                     "Z-score": "{:+.2f}", "52w %ile": "{:.0f}", "Skew": "{:.2f}",
                     "Kurt": "{:.2f}", "Day Ret%": "{:+.2f}%",
                     "Mean Ret%": "{:+.3f}%", "PCR": "{:.2f}",
                     "Total OI": "{:,.0f}", "OI Chg": "{:+,.0f}",
                     "Fut Prem": "{:+.1f}"}, na_rep="—"))


def chain_table(df, spot, has_ltp):
    """Sheets-style option chain (CE | Strike | PE) with ITM shading + ATM row."""
    df = df.sort_values("strike").reset_index(drop=True)
    for c in ["oi_CE", "chg_oi_CE", "volume_CE", "close_CE",
              "oi_PE", "chg_oi_PE", "volume_PE", "close_PE"]:
        if c not in df.columns:
            df[c] = np.nan
    atm = df.iloc[(df["strike"] - spot).abs().argmin()]["strike"] if spot else None

    if has_ltp:
        out = pd.DataFrame({
            "CE OI": df["oi_CE"], "CE ChgOI": df["chg_oi_CE"], "CE LTP": df["close_CE"],
            "Strike": df["strike"],
            "PE LTP": df["close_PE"], "PE ChgOI": df["chg_oi_PE"], "PE OI": df["oi_PE"]})
        fmt = {"CE OI": "{:,.0f}", "CE ChgOI": "{:+,.0f}", "CE LTP": "{:.2f}",
               "Strike": "{:.0f}", "PE LTP": "{:.2f}", "PE ChgOI": "{:+,.0f}",
               "PE OI": "{:,.0f}"}
    else:
        out = pd.DataFrame({
            "CE OI": df["oi_CE"], "CE ChgOI": df["chg_oi_CE"], "CE Vol": df["volume_CE"],
            "Strike": df["strike"],
            "PE Vol": df["volume_PE"], "PE ChgOI": df["chg_oi_PE"], "PE OI": df["oi_PE"]})
        fmt = {"CE OI": "{:,.0f}", "CE ChgOI": "{:+,.0f}", "CE Vol": "{:,.0f}",
               "Strike": "{:.0f}", "PE Vol": "{:,.0f}", "PE ChgOI": "{:+,.0f}",
               "PE OI": "{:,.0f}"}
    names = list(out.columns)
    ce_cols = [n for n in names if n.startswith("CE")]
    pe_cols = [n for n in names if n.startswith("PE")]

    def style_row(row):
        s = pd.Series("", index=names)
        strike = row["Strike"]
        if spot and strike < spot:
            s[ce_cols] = "background-color:rgba(240,159,39,.16)"
        if spot and strike > spot:
            s[pe_cols] = "background-color:rgba(226,75,74,.13)"
        s["Strike"] = "font-weight:700;background-color:rgba(130,130,130,.18)"
        if atm is not None and strike == atm:
            s[:] = "background-color:rgba(55,138,221,.20);font-weight:600"
        return s

    return (out.style.apply(style_row, axis=1)
            .map(color_pos_neg, subset=["CE ChgOI", "PE ChgOI"])
            .format(fmt, na_rep="—"))


# --------------------------------------------------------------------------- #
# Header + tabs
# --------------------------------------------------------------------------- #
htitle, hqmark = st.columns([8, 1])
htitle.markdown("### NSE NIFTY 50 — date-wise")
with hqmark.popover("❓", help="How to use"):
    st.markdown(HELP_MD)

hc1, hc2 = st.columns([1, 2])
symbol = hc1.selectbox("Stock", all_symbols(), index=0)
lookback = hc2.radio("Kitne din dekhne hain", [7, 20, 50, "All"], index=1,
                     horizontal=True)
st.divider()

tab_stock, tab_fut, tab_chain, tab_fii, tab_pos, tab_overview = st.tabs(
    ["📈 Stock (date-wise)", "🔮 Futures", "⛓️ Option chain", "🏦 FII/DII",
     "🎯 Positioning", "📊 Overview"])

# =========================================================================== #
# TAB — Stock (date-wise)
# =========================================================================== #
with tab_stock:
    hist = stock_history(symbol)
    if hist.empty:
        st.warning(f"{symbol}: koi data nahi.")
    else:
        view = hist if lookback == "All" else hist.tail(int(lookback))
        latest = view.iloc[-1]

        st.subheader(f"{symbol} — date-wise")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Close", f"{latest['close']:.2f}", f"{latest['chg_pct']:+.2f}%")
        c2.metric("Volume", f"{latest['volume']:,.0f}")
        c3.metric("Delivery %", f"{latest['deliv_pct']:.1f}"
                  if pd.notna(latest['deliv_pct']) else "—")
        c4.metric("Din (range me)", f"{len(view)}")

        st.markdown("#### Stock — all data (din-b-din)")
        st.caption("Column header par click → sort · prices split/bonus-adjusted · "
                   "Turnover ₹Cr.")
        show_df(stock_table(view))

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
        fig = go.Figure(go.Candlestick(
            x=cv["date"], open=cv["open"], high=cv["high"],
            low=cv["low"], close=cv["close"],
            increasing_line_color=GREEN, decreasing_line_color=RED,
            increasing_fillcolor=GREEN, decreasing_fillcolor=RED,
            text=hover, hoverinfo="text", name=""))
        fig.update_layout(height=380, margin=dict(l=0, r=0, t=10, b=0),
                          xaxis_rangeslider_visible=False,
                          xaxis_title=None, yaxis_title="Price")
        step = max(1, len(cv) // 10)
        fig.update_xaxes(type="category", tickmode="array",
                         tickvals=list(cv["date"])[::step])
        st.plotly_chart(fig, width="stretch")

# =========================================================================== #
# TAB — Futures
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

        st.markdown("#### 1 · Futures — teeno expiry ka total + changes")
        fut = q("""SELECT expiry, open, high, low, close, settle,
                          contracts, value_lakh, oi, chg_oi
                   FROM futures WHERE symbol=? AND date=? ORDER BY expiry""",
                (symbol, fdate))
        if fut.empty:
            st.write("—")
        else:
            show_df(futures_table(fut, fspot_px))

        st.markdown("#### 2 · Estimated participant split")
        st.warning("⚠️ **PROPORTIONAL ESTIMATE** — maan liya har stock me market-wide "
                   "jaisa FII/DII/Pro/Client mix. Real per-stock data publicly nahi milta.")
        pmax = q("SELECT MAX(date) d FROM participant")["d"].iloc[0]
        part = q("SELECT client_type, fut_stk_long FROM participant WHERE date=? "
                 "AND metric='oi' AND client_type IN ('FII','DII','Pro','Client')", (pmax,))
        soi = q("SELECT SUM(oi) oi FROM futures WHERE symbol=? AND date=?", (symbol, fdate))
        stock_oi = float(soi["oi"].iloc[0]) if not soi.empty and pd.notna(soi["oi"].iloc[0]) else 0
        st.caption(f"{symbol} futures OI = {_fmt(stock_oi)} contracts")
        if not part.empty and stock_oi:
            show_df(est_split_table(part, stock_oi))

# =========================================================================== #
# TAB — Option chain
# =========================================================================== #
with tab_chain:
    st.subheader(f"{symbol} — option chain")
    cdates = fno_dates(symbol)
    if not cdates:
        st.info(f"{symbol}: F&O data abhi nahi.")
    else:
        cc1, cc2 = st.columns([2, 1])
        with cc1:
            odate = date_slider("F&O date", cdates, "chain_date")
        strike_win = cc2.slider("Strikes around ATM (± count, 0 = all)", 0, 25, 10)
        spot = q("SELECT close FROM prices WHERE symbol=? AND date=?", (symbol, odate))
        spot_px = float(spot.iloc[0]["close"]) if not spot.empty else None

        def window_strikes(df):
            if strike_win == 0 or spot_px is None or df.empty:
                return df
            df = df.sort_values("strike").reset_index(drop=True)
            atm_i = int((df["strike"] - spot_px).abs().argmin())
            lo, hi = max(0, atm_i - strike_win), atm_i + strike_win + 1
            return df.iloc[lo:hi]

        st.caption("🟧 CALLS ITM shaded · 🟥 PUTS ITM shaded · 🔵 ATM row · "
                   "ChgOI green = OI add, red = OI reduce.")

        st.markdown("**Σ SUM CHAIN — teeno expiry ka total (strike-wise)**")
        sc = analysis.sum_chain(symbol, odate)
        if not sc.empty:
            for c in ["oi_CE", "chg_oi_CE", "volume_CE",
                      "oi_PE", "chg_oi_PE", "volume_PE"]:
                if c not in sc.columns:
                    sc[c] = 0
            tot = sc[["oi_CE", "oi_PE"]].sum()
            pcr = tot["oi_PE"] / tot["oi_CE"] if tot["oi_CE"] else float("nan")
            st.caption(f"spot **{spot_px:,.1f}** · Total CE OI {_fmt(tot['oi_CE'])} · "
                       f"PE OI {_fmt(tot['oi_PE'])} · PCR {pcr:.2f}")
            show_df(chain_table(window_strikes(sc), spot_px, has_ltp=False))

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
                show_df(chain_table(window_strikes(piv), spot_px, has_ltp=True))

        with st.expander("📋 Full option data (raw — saare columns)"):
            raw = q("""SELECT expiry, strike, opt_type, open, high, low, close,
                              settle, oi, chg_oi, volume, contracts, value_lakh
                       FROM options WHERE symbol=? AND date=?
                       ORDER BY expiry, strike, opt_type""", (symbol, odate))
            show_df(raw)

# =========================================================================== #
# TAB — FII / DII
# =========================================================================== #
with tab_fii:
    st.subheader("FII / DII / Pro / Client — F&O positions")
    pdates = q("SELECT DISTINCT date FROM participant ORDER BY date DESC")["date"].tolist()
    if not pdates:
        st.info("Participant data abhi nahi.")
    else:
        pdate = date_slider("Date", pdates, "fii_date")
        st.caption("Net = Long − Short (contracts). Green = net long (bullish), "
                   "red = net short (bearish).")

        st.markdown("#### Open Interest (positions held)")
        oi = q("SELECT * FROM participant WHERE date=? AND metric='oi'", (pdate,))
        if not oi.empty:
            show_df(participant_table(oi))

        st.markdown("#### Trading Volume (contracts traded)")
        vol = q("SELECT * FROM participant WHERE date=? AND metric='vol'", (pdate,))
        if not vol.empty:
            show_df(participant_table(vol))

        with st.expander("📋 Full raw data (saare 14 columns)"):
            raw = q("SELECT metric,client_type,fut_idx_long,fut_idx_short,"
                    "fut_stk_long,fut_stk_short,opt_idx_call_long,opt_idx_put_long,"
                    "opt_idx_call_short,opt_idx_put_short,opt_stk_call_long,"
                    "opt_stk_put_long,opt_stk_call_short,opt_stk_put_short,"
                    "total_long,total_short FROM participant WHERE date=? "
                    "ORDER BY metric,client_type", (pdate,))
            show_df(raw)

# =========================================================================== #
# TAB — Positioning (real OI buildup)
# =========================================================================== #
with tab_pos:
    st.subheader("Stock positioning")
    pos_dates = q("SELECT DISTINCT date FROM futures ORDER BY date DESC")["date"].tolist()
    if not pos_dates:
        st.info("F&O data abhi nahi.")
    else:
        ldate = date_slider("Date", pos_dates, "pos_date")
        st.markdown("#### Real OI buildup — price + OI change")
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
                        f":violet[**{b['buildup']}**]")

        counts = scan["buildup"].value_counts()
        cc = st.columns(4)
        for i, bname in enumerate(["Long Buildup", "Short Buildup",
                                   "Short Covering", "Long Unwinding"]):
            cc[i].metric(bname, int(counts.get(bname, 0)))

        st.markdown("**Market scan — kaunse stocks me kya positioning:**")
        pick = st.selectbox("Buildup filter", ["All", "Long Buildup", "Short Buildup",
                                               "Short Covering", "Long Unwinding"])
        show = scan if pick == "All" else scan[scan["buildup"] == pick]
        if not show.empty:
            show_df(buildup_table(show))

# =========================================================================== #
# TAB — Overview
# =========================================================================== #
with tab_overview:
    st.subheader("All stocks — math stats")
    stats = q("""SELECT symbol, cum_return, cagr, ann_volatility, volatility,
                        sharpe, max_drawdown, beta, zscore, pct_rank_52w,
                        skew, kurtosis, daily_return, mean_return,
                        put_call_ratio, total_oi, oi_change, futures_premium
                 FROM stats""")
    if stats.empty:
        st.info("Stats abhi nahi. `python analysis.py` chalao.")
    else:
        st.caption("Column header par click → sort (native). Green = positive, "
                   "red = negative. Stats split/bonus-adjusted.")
        show_df(overview_table(stats))
