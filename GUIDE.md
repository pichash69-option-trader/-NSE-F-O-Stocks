# 📈 NSE F&O Stocks — Dashboard Guide

Ye dashboard **F&O stocks (~210)** ka **NSE data** **date-wise** (din-b-din) dikhata hai —
equity + futures + options + FII/DII, sab. Data seedha NSE se aata hai, roz market close
ke baad auto-update hota hai. Saari analysis **pure mathematics / statistics** hai —
**koi technical indicator nahi** (no RSI/MACD/moving averages).

> ⚠️ **Educational / research tool** hai — investment advice **nahi**. Trading apne risk par.

---

## 🧭 1. Basic use — kaise chalayein

Left **sidebar** me:

| Control | Kaam |
|---|---|
| **Stock** dropdown | Kaunsa stock dekhna hai (search bhi kar sakte ho) |
| **Kitne din dekhne hain** | 7 / 20 / 50 / All — kitne din ka data |
| **Menu (7 sections)** | Neeche explain kiye hain |
| **❓ How to use** | Ye guide |

Upar **ticker bar** — us din ke **Top 5 gainers** (green line) aur **Top 5 losers**
(red line), EOD data se.

---

## 📊 2. Data me kya-kya hai

| Dataset | Source (NSE) | Kya milta hai |
|---|---|---|
| **Equity** | CM Bhavcopy | Roz ka Open/High/Low/Close, Volume, Turnover, Trades |
| **Delivery** | MTO report | Delivery quantity + **Delivery %** |
| **Futures** | F&O Bhavcopy | Har expiry ka OHLC, Settle, OI, Chg OI |
| **Options** | F&O Bhavcopy | **Har strike + har expiry** (CE & PE): OHLC, OI, Chg OI, Volume |
| **Participant** | NSCCL report | **FII / DII / Pro / Client** ka OI & Volume |

---

## 🗂️ 3. Sections (5 — har ek ek data-type) — kya, kis liye, aur matlab

Navigation **data-type** ke hisaab se hai — sidebar me 5 sections, har ek DB ki ek table:

### 📈 Equity / Cash
Selected stock ka cash-market data, din-b-din. Har din ek **row**: OHLC, **Chg%**
(green/red pill), **Volume** & **Delivery %** (bars), Turnover ₹Cr, Trades. Neeche
**candle chart** — kisi candle par hover = poori detail.
- 🟢 up din · 🔴 down din
- **Matlab:** Delivery % high = **real buying** (log actually shares le ja rahe, sirf
  intraday speculation nahi). Volume high + delivery low = zyada tar intraday churn.

### 🔮 Futures
1. **Teeno expiry** (near / next / far) ka total + changes — OHLC, Settle,
   **Premium** (future − spot), **OI + Chg OI** (bars/colors), Σ TOTAL row.
2. **Estimated participant split** — ⚠️ *proportional estimate* (neeche note).
- **Matlab:** Premium +ve (future > spot) = market thoda **bullish** lean;
  OI badh raha + price badh raha = naye long positions.

### ⛓️ Options (Sensibull style)
- **Σ SUM CHAIN** — teeno expiry ka total, strike-wise (CALLS left, PUTS right)
- Har expiry ka apna chain (expandable) — **OHLC · Settle · Turnover chain ke andar hi** +
  **max pain**
- **Slider**: F&O date + strikes-around-ATM
- ITM shading, ATM row highlighted, OI bars, green = OI addition / red = OI reduction
- **Matlab:**
  - **CALL side me zyada OI** ek strike par = wo **resistance** (sellers wahan).
  - **PUT side me zyada OI** = **support**.
  - **PCR** aur **max pain** neeche glossary me.

### 🏦 Participant
**FII / DII / Pro / Client** ke F&O positions (Open Interest + Trading Volume).
- **Net = Long − Short** (contracts). 🟢 net long (bullish), 🔴 net short (bearish).
- **Matlab:** FII ka rukh **market sentiment** dikhata hai — FII net long badh raha =
  big money bullish. (Ye **market-wide** hai, single-stock nahi.)

### 📊 Math stats
Saare ~210 stocks ka **computed math ek table me** — sort karke compare karo (Volatility,
Return, Sharpe, Beta, PCR, etc.). Symbol column + header **pinned** rehte hain;
right scroll karke saare 18 columns dekho.

---

## 🧮 4. Calculations — formula + matlab (glossary)

Sab **split/bonus-adjusted** hai (neeche note). Daily return `r = aaj ka close / kal ka close − 1`.

### Returns
| Metric | Formula | Matlab |
|---|---|---|
| **Daily return** | `close_today / close_yesterday − 1` | Us ek din ka move |
| **Cumulative return** | `close_last / close_first − 1` | Poore period me total kitna badha/gira |
| **CAGR** | `(close_last / close_first)^(365 / days) − 1` | **Annualized** growth rate (per-year %) |
| **Mean return** | daily returns ka average | Rozana average move |

### Risk / volatility
| Metric | Formula | Matlab |
|---|---|---|
| **Volatility** (daily) | daily returns ka **standard deviation** | Roz kitna up-down (risk) |
| **Ann. volatility** | `daily vol × √252` | Saal-bhar ka expected swing %. **High = zyada risky** |
| **Sharpe** | `mean daily return / daily vol` (risk-free = 0) | **Risk-adjusted return**. Zyada = better (kam risk me zyada return) |
| **Max drawdown** | `min(close / running-peak − 1)` | Peak se sabse bada gir — worst-case loss agar top par khareeda hota |
| **Beta** | `cov(stock, market) / var(market)` | Market ke saath kitna chalta hai. **β>1 = market se zyada swingy**, β<1 = kam. (Market = ~210 stocks ka equal-weighted average = NIFTY proxy) |

### Position / statistics
| Metric | Formula | Matlab |
|---|---|---|
| **Z-score** | `(latest close − avg close) / std close` | Price apne average se kitne "standard deviations" door. +2 = bahut upar (mehenga), −2 = bahut neeche (sasta) — sirf statistical, prediction nahi |
| **52-week %ile** | last 252 din me kitne % din ka close aaj se **neeche** tha | 90 = 52-week high ke paas · 10 = 52-week low ke paas |
| **Skew** | daily returns ka skewness | Returns ki asymmetry. +ve = kabhi-kabhi bade up moves, −ve = crash-prone (bade down moves) |
| **Kurtosis** | daily returns ka (excess) kurtosis | "Fat tails" — high = extreme moves (surprises) zyada aate hain |
| **Delivery %** | `delivery qty / total traded qty × 100` | Kitne % shares actually deliver hue (intraday nahi). **High = real conviction buying** |

### F&O math
| Metric | Formula | Matlab |
|---|---|---|
| **PCR** (Put-Call Ratio) | `total PE OI / total CE OI` (saare strikes+expiries) | >1 = puts zyada (often oversold/bullish contrarian) · <1 = calls zyada. Sentiment gauge |
| **Max pain** | wo strike jahan option **writers ka total payout minimum** ho | Expiry par price aksar max-pain ke aas-paas "khinchti" hai (theory) |
| **Futures premium** | `near-month future close − spot close` | +ve (premium) = bullish lean · −ve (discount) = bearish lean |
| **Total OI** | saare futures expiry ka OI sum | Kitne contracts open (participation) |
| **OI change** | saare expiry ka Chg OI sum | Naye positions ban rahe (+) ya band ho rahe (−) |

### OI Buildup (price + OI change se — reliable)
| Price | OI | Buildup | Matlab |
|---|---|---|---|
| 🔼 Up | 🔼 Up | **Long Buildup** | Naye buyers aa rahe — bullish |
| 🔽 Down | 🔼 Up | **Short Buildup** | Naye sellers aa rahe — bearish |
| 🔼 Up | 🔽 Down | **Short Covering** | Sellers exit kar rahe — up move (short-term bullish) |
| 🔽 Down | 🔽 Down | **Long Unwinding** | Buyers exit kar rahe — down move (weakness) |

---

## ⚠️ 5. Important notes

- **Estimated participant split** (Futures section me): Real **per-stock** FII/DII data
  publicly nahi milta. Isliye **market-wide** FII/DII/Pro/Client ka Future-Stock % lekar,
  us stock ke futures OI par **proportionally** laga diya. Ye ek **rough estimate** hai —
  exact nahi. FII/DII section ka data **real** hai (bas market-wide, single-stock nahi).

- **Split / Bonus adjustment**: NSE ka `prev_close` split-adjust nahi hota, to split wale
  din fake −90% jaisa move dikh sakta. Dashboard **auto-detect** karke (close ratio <0.6
  ya >1.6) puraane prices ko adjust kar deta — candle aur returns clean rehte hain.
  (Ticker me bhi `|move| > 30%` wale drop kiye jaate hain taaki split artifact top-movers
  me na aaye.)

- **Sharpe** yahan simple `mean/std` (daily, risk-free = 0) hai — comparison ke liye, thumb-rule.

---

## 🔄 6. Data update

- Har **trading din**, market close ke baad (~**6:30 PM IST**) naya data auto-add hota hai.
- **Weekend/holiday** skip (NSE calendar se). Late-publish hone par bhi retry hota hai —
  koi gap nahi.
- Latest din upar dikhta hai.

---

**Bas! Stock chuno, din chuno, explore karo.** 🚀

*Ye tool sirf educational/research ke liye hai. Investment decisions apne research aur
licensed advisor se lo.*
