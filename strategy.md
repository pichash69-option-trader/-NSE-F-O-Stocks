# 📓 Backtest Strategies

User-defined option strategies backtested on our NSE EOD data
(1-Jan-2024 → today, ~210 F&O stocks). Each strategy is named and runs across
all stocks; results are shown per-stock in the **🎯 Backtest** tab.

> ⚠️ **Research / education only.** These are historical hypotheticals on daily
> (EOD) data — **not** trading advice, not a guarantee of future results.
> Data is end-of-day: entries/exits happen at the daily **close**, and the
> trailing stop is checked on daily closes (no intraday).

---

## 1. Momentum buying

A non-directional **long strangle** entered when a multi-factor momentum burst
suggests a large (~5–10%) move is starting. One leg explodes on the move; the
trailing stop lets winners run, a loss cap and a time exit bound the risk.

### Entry signal — need **≥ 4 of 5** on the same day
| # | Factor | Rule | Data |
|---|---|---|---|
| 1 | Price thrust | `abs(chg%) ≥ 2%` | `prices` |
| 2 | Volume surge | `volume ≥ 2 × its prior 20-day average` | `prices` |
| 3 | Delivery conviction | `delivery% ≥ 50%` | `prices` |
| 4 | S/R breakout | close breaks the nearest **swing high** (up) or **swing low** (down); OI-wall counts too | `charts.swing_levels`, `options` |
| 5 | OI commit | futures total **OI up** vs previous day | `futures` |

Non-directional: we buy **both** legs, so direction only needs a big move, not a side.

### Legs
- **BUY OTM+3 CE** and **BUY OTM+3 PE** (long strangle) — 3 strikes out-of-the-money each side
- Strikes on **round numbers**: ATM = the available strike nearest spot; CE = ATM +3 strikes, PE = ATM −3 strikes
- Size: **2 lots**, single exit (both legs together)

### Expiry
- **Near-month** with **days-to-expiry ≥ 15** at entry (else roll to next-month)

### Filters (trade skipped if any fails)
- Underlying **turnover ≥ ₹100 Cr** that day
- **Both legs**: option **OI ≥ 1000** and **volume ≥ 200** at entry (OTM+3 can be illiquid)
- Stock **not in F&O ban** that day
- One open position per stock at a time (no pyramiding)

### Exit — whichever comes first (measured on **combined CE+PE premium**)
| Exit | Rule |
|---|---|
| **Trailing stop** | activates once position ≥ **+100%**; then exit when it falls **−30% from its peak** (lets winners run past +150%) |
| **Loss exit** | position ≤ **−50%** |
| **Time exit** | held **10 trading days**, or the date reaches **expiry − 5 days** |

### P&L
- Reported in **premium points (₹/share)** and **%** — lot-size-independent.
  Multiply by lot size × 2 lots for rupee P&L.
- Per-stock: trades, win-rate, total/avg P&L, equity curve, max drawdown.
- Combined: all stocks aggregated + a sortable per-stock table.

### Tunable (defaults above; the backtest can sweep these)
`min_factors, price_move%, vol_mult, deliv_min, otm_steps, dte_min,
turnover_min, leg_oi_min, leg_vol_min, hold_days, exit_before_expiry,
trail_activate%, trail_pullback%, loss_exit%`
