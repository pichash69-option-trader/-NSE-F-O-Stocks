# -*- coding: utf-8 -*-
"""
render.py — presentation layer: HTML-table renderers, their CSS, and small
formatting helpers. Pure functions (pandas/numpy only, no Streamlit/DB) that
return HTML strings. Split out of dashboard.py for maintainability.
"""
import numpy as np
import pandas as pd


_BUILDUP_LBL = {2: "Long Buildup", 1: "Short Covering",
                -1: "Long Unwinding", -2: "Short Buildup", 0: "—"}


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
            f'<td>{col(r.get("sortino"), "{:+.2f}")}</td>'
            f'<td>{col(r.get("calmar"), "{:+.2f}")}</td>'
            f'<td><span class="dn">{dd:.1f}%</span></td>'
            f'<td><span class="dn">{num(r.get("var5"), "{:.2f}")}%</span></td>'
            f'<td>{num(r["beta"])}</td>'
            f'<td>{col(r["zscore"], "{:+.2f}")}</td>'
            f'<td class="bar-cell">{p52cell}</td>'
            f'<td>{num(r["skew"])}</td>'
            f'<td>{num(r["kurtosis"])}</td>'
            f'<td>{col(r["daily_return"]*100 if pd.notna(r["daily_return"]) else None)}%</td>'
            f'<td>{col(r.get("ret_1w"), "{:+.1f}")}%</td>'
            f'<td>{col(r.get("ret_1m"), "{:+.1f}")}%</td>'
            f'<td>{col(r.get("ret_3m"), "{:+.1f}")}%</td>'
            f'<td>{col(r.get("ret_6m"), "{:+.1f}")}%</td>'
            f'<td>{col(r.get("ret_1y"), "{:+.1f}")}%</td>'
            f'<td>{col(r["mean_return"]*100 if pd.notna(r["mean_return"]) else None, "{:+.3f}")}%</td>'
            f'<td>{pcr}</td>'
            f'<td>{_fmt(r["total_oi"])}</td>'
            f'<td>{col(r["oi_change"], "{:+.0f}")}</td>'
            f'<td>{col(r["futures_premium"], "{:+.1f}")}</td></tr>')
    return (STOCK_CSS + OVERVIEW_CSS +
            '<div class="ovwrap"><table class="stbl ovtbl">'
            '<thead><tr>'
            '<th class="l">Symbol</th><th>Return%</th><th>CAGR%</th><th>Ann Vol</th>'
            '<th>Daily Vol</th><th>Sharpe</th><th>Sortino</th><th>Calmar</th>'
            '<th>Max DD</th><th>VaR%</th><th>Beta</th>'
            '<th>Z-score</th><th>52w %ile</th><th>Skew</th><th>Kurt</th>'
            '<th>Day Ret%</th><th>1W%</th><th>1M%</th><th>3M%</th><th>6M%</th><th>1Y%</th>'
            '<th>Mean Ret%</th><th>PCR</th><th>Total OI</th>'
            '<th>OI Chg</th><th>Fut Prem</th>'
            '</tr></thead><tbody>' + "".join(rows) + '</tbody></table></div>')


OVERVIEW_CSS = """
<style>
.ovwrap{overflow-x:auto;
  border:1px solid rgba(255,255,255,.06);border-radius:10px;}
.ovwrap::-webkit-scrollbar{height:10px;width:10px;}
.ovwrap::-webkit-scrollbar-thumb{background:#6366f1;border-radius:6px;}
.ovwrap::-webkit-scrollbar-track{background:rgba(255,255,255,.04);}
.ovtbl{min-width:1560px;font-size:11.5px;}
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
# Multi-stock compare — transposed table (metrics as rows, stocks as columns)
# --------------------------------------------------------------------------- #
_COMPARE_ROWS = [
    ("Last close", "close", 1, "{:.2f}", False),
    ("1D %", "daily_return", 100, "{:+.2f}", True),
    ("1W %", "ret_1w", 1, "{:+.1f}", True),
    ("1M %", "ret_1m", 1, "{:+.1f}", True),
    ("3M %", "ret_3m", 1, "{:+.1f}", True),
    ("1Y %", "ret_1y", 1, "{:+.1f}", True),
    ("CAGR %", "cagr", 100, "{:+.1f}", True),
    ("Ann Vol %", "ann_volatility", 100, "{:.1f}", False),
    ("Sharpe", "sharpe", 1, "{:+.2f}", True),
    ("Sortino", "sortino", 1, "{:+.2f}", True),
    ("Beta", "beta", 1, "{:.2f}", False),
    ("Max DD %", "max_drawdown", 100, "{:.1f}", False),
    ("VaR %", "var5", 1, "{:.2f}", False),
    ("52w %ile", "pct_rank_52w", 1, "{:.0f}", False),
    ("PCR", "put_call_ratio", 1, "{:.2f}", False),
]


def render_compare(comp):
    """Side-by-side comparison: metrics as rows, selected stocks as columns."""
    if comp is None or comp.empty:
        return "<i>—</i>"
    stocks = list(comp.index)
    head = "".join(f"<th>{s}</th>" for s in stocks)
    body = []
    for label, col, scale, fmt, colored in _COMPARE_ROWS:
        cells = []
        for s in stocks:
            v = comp.loc[s, col] if col in comp.columns else None
            if v is None or pd.isna(v):
                cells.append("<td>—</td>")
                continue
            v = v * scale
            cls = ("up" if v >= 0 else "dn") if colored else ("dn" if col == "max_drawdown" else "")
            cells.append(f'<td class="{cls}">{fmt.format(v)}</td>')
        body.append(f'<tr><td class="date" style="font-weight:600">{label}</td>{"".join(cells)}</tr>')
    return (STOCK_CSS +
            '<div style="overflow-x:auto"><table class="stbl" style="min-width:360px">'
            f'<thead><tr><th class="l">Metric</th>{head}</tr></thead>'
            f'<tbody>{"".join(body)}</tbody></table></div>')


# --------------------------------------------------------------------------- #
# Sector-wise aggregate table
# --------------------------------------------------------------------------- #
def render_sector_table(agg):
    """Sector rows: # stocks + avg returns (1D/1W/1M/1Y) + avg vol + avg PCR."""
    if agg is None or agg.empty:
        return "<i>—</i>"

    def c(v, fmt="{:+.1f}"):
        cls = "up" if (v or 0) >= 0 else "dn"
        return f'<span class="{cls}">{fmt.format(v)}</span>' if pd.notna(v) else "—"

    rows = []
    for _, r in agg.iterrows():
        rows.append(
            f'<tr><td class="date" style="font-weight:600">{r["sector"]}</td>'
            f'<td>{int(r["n"])}</td>'
            f'<td>{c(r["ret_1d"])}%</td><td>{c(r["ret_1w"])}%</td>'
            f'<td>{c(r["ret_1m"])}%</td><td>{c(r["ret_1y"])}%</td>'
            f'<td>{r["ann_vol"]:.1f}%</td><td>{r["pcr"]:.2f}</td></tr>')
    return (STOCK_CSS +
            '<div style="overflow-x:auto"><table class="stbl" style="min-width:520px">'
            '<thead><tr><th class="l">Sector</th><th># stocks</th>'
            '<th>Avg 1D%</th><th>Avg 1W%</th><th>Avg 1M%</th><th>Avg 1Y%</th>'
            '<th>Avg Vol%</th><th>Avg PCR</th></tr></thead><tbody>'
            + "".join(rows) + '</tbody></table></div>')
