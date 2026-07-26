# NSE Auto Data Analysis — Plan (NIFTY 50, Pure Math, No Indicators)

Locked-in decisions:
- **Stocks:** sirf NIFTY 50 (50 symbols)
- **Data source:** NSE **official archive** (nsearchives.nseindia.com) — daily bhavcopy CSVs,
  direct download (`requests` + proper headers). ✅ VERIFIED working (equity + delivery + F&O).
  Note: `nsepython` 0.1 ke historical functions NSE ke July-2024 URL change se toot gaye (404/KeyError),
  isliye direct archive use karenge. `nsepython` sirf helper (symbol/expiry list) ke liye optional.
  (reports pages reference: nseindia.com/all-reports + /all-reports-derivatives)
- **History start:** **1-Jan-2024** (fixed start date)
- **Ongoing:** us date se **aaj tak**, aur aage har din **automatically** naya data add hota rahe (Task Scheduler)
- **Segments:** Equity (cash) **+ F&O (derivatives)** dono
- **F&O scope:** **POORA data — saari expiries (near/next/far) + saare strikes (CE & PE)**, koi filter nahi
- **Extra data:** Delivery quantity + Delivery % (NSE free)
- **Analysis type:** sirf **mathematical / statistical** — NO technical indicators (no RSI/MACD/etc.)

---

## 0. Architecture

```
[FETCH from NSE]         [STORE]            [MATH ANALYSIS]        [SHOW]
 NSE archive CSVs     SQLite (nse.db)    numpy/pandas stats     Streamlit
 (bhavcopy: equity,                      returns, vol, beta,    date-wise tables
  delivery, F&O)                         correlation, PCR...      + charts
        │                                        │                 │
        └──────── Windows Task Scheduler daily 6:30 PM ────────────┘
```

### Fetch logic (incremental — ye important hai)
```
Pehli baar run:  1-Jan-2024 → aaj tak  ka poora data DB me bhar do (backfill)
Har agli baar:   DB me jo aakhri date hai uske BAAD se → aaj tak ka hi laao
                 (INSERT OR REPLACE → duplicate/gap nahi)
Result:          DB hamesha 1-Jan-2024 se latest tak up-to-date rehti hai, khud-b-khud
```
Iska matlab tumhe kabhi manually kuch nahi karna — pehli baar poora bhar jayega,
uske baad Task Scheduler roz sirf naya din add karega.

---

## 1. Tech Stack (free)

| Layer      | Tool                              |
|------------|-----------------------------------|
| Language   | Python 3.11+ (already installed)  |
| Fetch      | `requests` — NSE archive CSVs     |
| Storage    | SQLite (`nse.db`)                 |
| Math       | `pandas`, `numpy`                 |
| Dashboard  | `streamlit`, `plotly`             |
| Auto-run   | Windows Task Scheduler            |

Install:
```
pip install requests pandas numpy streamlit plotly
```
(nsepython optional — sirf symbol/expiry helper ke liye. Koi indicator library — pandas-ta — NAHI chahiye.)

---

## 2. Files (target)

```
NSE database/
├── nse.db              # SQLite DB (auto)
├── config.py           # 50 NIFTY symbols + settings
├── db.py               # SQLite schema setup + insert helpers
├── fetch_data.py       # NSE archive se equity + delivery + F&O → DB (1-Jan-2024 se, incremental)
├── analysis.py         # pure math stats compute
├── dashboard.py        # Streamlit UI (date-wise)
├── run_daily.py        # fetch + analysis ek saath
└── requirements.txt
```

---

## 3. Database Schema

```
-- EQUITY: raw daily data from NSE (cash segment)
prices(
  symbol TEXT, date TEXT,
  open REAL, high REAL, low REAL, close REAL,
  prev_close REAL, settle REAL,
  volume INTEGER, turnover REAL, num_trades INTEGER,
  deliv_qty INTEGER, deliv_pct REAL,
  UNIQUE(symbol, date)
)

-- F&O FUTURES: daily futures data — SAARI expiries (near/next/far)
futures(
  symbol TEXT, date TEXT, expiry TEXT,
  open REAL, high REAL, low REAL, close REAL, settle REAL,
  contracts INTEGER, value_lakh REAL,
  oi INTEGER, chg_oi INTEGER,
  UNIQUE(symbol, date, expiry)
)

-- F&O OPTIONS: daily data — SAARE strikes + SAARI expiries + CE & PE (poora, no filter)
options(
  symbol TEXT, date TEXT, expiry TEXT,
  strike REAL, opt_type TEXT,      -- CE / PE
  open REAL, high REAL, low REAL, close REAL, settle REAL,
  contracts INTEGER, volume INTEGER, value_lakh REAL,
  oi INTEGER, chg_oi INTEGER,
  UNIQUE(symbol, date, expiry, strike, opt_type)
)

-- computed math stats (per stock, latest)
stats(
  symbol TEXT, date TEXT,
  daily_return REAL, cum_return REAL,
  mean_return REAL, volatility REAL, ann_volatility REAL,
  sharpe REAL, max_drawdown REAL, beta REAL,
  zscore REAL, pct_rank_52w REAL, cagr REAL,
  skew REAL, kurtosis REAL,
  -- F&O derived math
  put_call_ratio REAL,             -- total PE OI / CE OI
  total_oi INTEGER, oi_change REAL,
  futures_premium REAL             -- (futures close − spot close)
)
```

---

## 4. NSE data — kya milega (VERIFIED, real archive columns)

Teen files roz download hongi (04-Jan-2024 par test kiya — sab HTTP 200):

**A. Equity Bhavcopy** (`.../content/cm/BhavCopy_NSE_CM_0_0_0_YYYYMMDD_F_0000.csv.zip`)
| NSE column | Matlab |
|-----------|--------|
| TradDt, TckrSymb | date, symbol |
| OpnPric/HghPric/LwPric/ClsPric | OHLC |
| LastPric, PrvsClsgPric, SttlmPric | last, prev close, settle |
| TtlTradgVol | volume |
| TtlTrfVal | turnover |
| TtlNbOfTxsExctd | no. of trades |

**B. Delivery (MTO)** (`.../archives/equities/mto/MTO_DDMMYYYY.DAT`)
| Field | Matlab |
|-------|--------|
| Deliverable Quantity | delivery qty |
| % of Deliverable Qty | delivery % |

**C. F&O Bhavcopy** (`.../content/fo/BhavCopy_NSE_FO_0_0_0_YYYYMMDD_F_0000.csv.zip`)
| NSE column | Matlab |
|-----------|--------|
| FinInstrmTp | STF/STO/IDF/IDO (stock/index future/option) |
| XpryDt | expiry |
| StrkPric, OptnTp | strike, CE/PE |
| OHLC, SttlmPric | prices |
| OpnIntrst, ChngInOpnIntrst | OI + OI change |
| TtlTradgVol, TtlTrfVal | volume, value |
| UndrlygPric | spot price |

> Note: purana "VWAP" column naye bhavcopy me nahi hai — chahiye to (turnover ÷ volume) se
> approx nikaal sakte hain. 52-week High/Low apne close history se compute honge.
> **Split/bonus adjustment:** NSE ka prev_close split-adjusted NAHI hai, isliye analysis.py
> close-to-close jump se corporate action auto-detect karke back-adjust karta hai (warna
> NESTLEIND jaise 1:10 split par fake -90% return aata hai). Raw close DB me waisa hi rehta hai;
> adjustment sirf math ke waqt lagta hai.

---

## 5. Mathematical Analysis (NO indicators)

Sab `numpy`/`pandas` se:

| Stat | Formula |
|------|---------|
| Daily return | (P_t − P_t-1) / P_t-1 |
| Log return | ln(P_t / P_t-1) |
| Cumulative return | ∏(1+r) − 1 |
| Mean return | average(returns) |
| Volatility (σ) | std(returns) |
| Annualized vol | σ × √252 |
| Variance | σ² |
| Sharpe-type | mean(r) / std(r) |
| Max Drawdown | max peak-to-trough drop % |
| Beta | cov(stock, NIFTY) / var(NIFTY) |
| Correlation matrix | 50×50 pairwise corr |
| Z-score | (price − mean) / std |
| 52-week percentile rank | position in yearly range |
| CAGR | (P_end/P_start)^(1/years) − 1 |
| Skewness / Kurtosis | distribution shape (tail risk) |
| Rolling mean/std (N-day) | pure rolling stat (indicator nahi) |
| Delivery ratio trend | deliv_pct ka average/rolling |

### F&O ka math (pure numbers, no indicators)
| Stat | Meaning |
|------|---------|
| Put-Call Ratio (PCR) | total PE OI / total CE OI |
| Total Open Interest | market position size |
| OI change % | daily OI ka % change |
| Futures premium/discount | futures close − spot close |
| Rollover % (near expiry) | next-expiry OI / total OI |
| Max Pain (strike) | strike jahan total option value min (pure calc) |

---

## 6. Dashboard — DATE-WISE / TIMELINE focus (primary design)

Main idea: snapshot nahi — **din-b-din view**. Ek nazar me: "aaj se N din pehle kaisa tha,
aur kaise badal raha hai." Upar ek **date-range control** (7 / 20 / 50 / custom din),
jo saari tables ko usi range me din-wise bhar de.

Sections (sab date-wise, latest din upar) — is EXACT order me:
- **1. Stock — all data:** har din ek row → Open, High, Low, Close, Chg%, Volume, Deliv%
  + close ka trend line. Up/down arrow = badha ya gira.
- **2. Option chain block — teeno expiry ka layout (upar→neeche):**
  1. **SUM CHAIN (sabse upar):** ek POORA option chain, par har strike par teeno expiry
     (near/next/far) ke values **jod** diye — Σ CE OI, Σ ChgOI, Σ Vol │ Strike │ Σ Vol,
     Σ ChgOI, Σ PE OI. ATM highlight. Sabse neeche ek grand **TOTAL** row (+ changes).
     (Ye strike-wise sum hai — chain ke format me, sirf summary metrics nahi.)
  2. **Teen alag option chains:** Expiry-1, Expiry-2, Expiry-3 — har ek ka poora chain
     (strikes × CE|PE: OI, ChgOI, LTP), ATM highlight. (collapse/expand)
- **3. Futures — teeno expiry ka total + changes (option chain block ke NEECHE):**
  Total OI, contracts, close + 1-day change (three expiries aggregate).

Do compare modes:
- **Time direction:** ek stock/expiry, kai din neeche-neeche → trend.
- **Compare 2 dates:** "25 Jul vs 5 Jul" side-by-side → OI kahan build hua, price shift.

Secondary (math tabs, baad me): risk-return scatter, 50×50 correlation, per-stock stats table.

---

## 7. Build Roadmap

- **Phase 1:** config.py + db.py + fetch_data.py (equity) → 1-Jan-2024 se aaj tak OHLCV + delivery, incremental backfill
- **Phase 2:** F&O fetch (futures + options, all expiry/strike) → futures/options tables
- **Phase 3:** analysis.py — equity math stats + F&O math (PCR, sum chain, premium) → stats table
- **Phase 4:** dashboard.py — DATE-WISE view: stock table → sum chain + 3 expiry chains → futures totals
- **Phase 5:** run_daily.py + Task Scheduler (daily 6:30 PM auto)

---

## 8. Notes / Cautions
- NSE archive ko proper browser headers chahiye (User-Agent etc.) — warna block. ✅ test me handle kiya.
- NSE rate-limit: har din ki file ke beech chhota delay (0.3–0.5s) rakhenge.
- Pehli baar backfill slow hoga (1-Jan-2024 se aaj tak ~630 trading din × 3 files download);
  ye download-bound hai, ek baar ka kaam. Uske baad daily incremental fast (ek din).
- F&O options poora rakhne se DB bada hoga (~lakhon rows) — normal, SQLite handle karega.
- Ye **educational/research** analysis hai — investment advice nahi.

---

## Next step
Phase 1 code: config.py (50 symbols) + db.py (schema) + fetch_data.py (NSE archive se
1-Jan-2024 se equity + delivery download, incremental). Run karke DB me data aata dekhoge.
