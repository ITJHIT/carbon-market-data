# Carbon Market Weekly — data pipeline

A tiny, free data pipeline that turns public carbon-allowance market data into a
**weekly intelligence report** (snapshot table + trend signal + chart) — the MVP
behind a paid carbon-market newsletter / dashboard.

It pulls carbon-allowance ETFs (a free, liquid proxy for the EU ETS and global
carbon markets), computes price / return / volatility / momentum metrics and a
simple MA-trend + momentum signal, renders a normalized-price chart, and writes a
Markdown newsletter draft.

## Run

```bash
pip install -r requirements.txt
python carbon_report.py
# -> out/carbon_prices.png  (chart)
# -> out/weekly_report.md   (newsletter draft)
```

## Example output

```
        last  ret_1w_%  ret_1m_%  vol_20d_ann_%  trend_vs_MA50   signal
GRN    33.52      6.16      4.28           32.8            UP     LONG
KCCA   16.81     -2.04     -1.12           10.0            UP  NEUTRAL
KRBN   33.75      1.81      0.78           24.1            UP     LONG
```

**Signal rule:** LONG when the 50-day trend is up and 1-month momentum is positive
(and the inverse → AVOID); otherwise NEUTRAL.

## Data

| Ticker | Market |
|--------|--------|
| KRBN | KraneShares Global Carbon (EU / global allowances) |
| KEUA | KraneShares European Carbon Allowance (pure EU ETS / EUA) |
| KCCA | KraneShares California Carbon (CCA) |
| GRN  | iPath Global Carbon ETN |

Source: Yahoo Finance (free, daily). The report also computes a **cross-market
relative-value read** (EU vs California, KEUA/KCCA ratio + 60-day z-score) and
flags stale/thin series as `STALE-DATA` instead of faking a signal.

A **GitHub Actions cron** (`.github/workflows/weekly.yml`) regenerates the report
every Monday and commits it to `reports/latest/`, so the repo stays a *living*
artifact.

## Korea K-ETS (KAU)

KRX has no free real-time carbon API, so Korea data uses a **local CSV drop**.
Download KAU daily prices from KRX (배출권시장 정보플랫폼 <https://ets.krx.co.kr> or
<https://data.krx.co.kr>), save as `data/kau.csv` (`date,close`; see
`data/kau_sample.csv`), and the weekly report adds a **Korea K-ETS section**
automatically. `data/kau.csv` is gitignored; the sample template is committed.

```bash
python kau.py            # preview the Korea section (or a "no data" hint)
```

## Backtest (paper trading, Phase 3)

`backtest.py` runs the newsletter's own trend/momentum signal against a carbon ETF
over 5 years and compares it to buy & hold — no broker, no money. It reports total
return, CAGR, Sharpe, and max drawdown, and writes an equity-curve chart.

```bash
python backtest.py KRBN  # -> out/backtest_KRBN.png + stats
```

Honesty note: on KRBN the naive long/flat momentum signal **underperformed** buy &
hold. That is the point — the engine gives an unfiltered verdict before any capital
is risked, and the product is positioned as market *intelligence*, not a magic signal.

## Signal research (in-sample / out-of-sample)

`research.py` sweeps (MA window × momentum lookback) across carbon assets, picks the
best parameters on the first 60% of history, then reports their performance on the
unseen last 40%. A signal only earns trust if it also wins **out-of-sample**.

```bash
python research.py       # -> out/research.md + verdict
```

Result (honest): IS Sharpe (0.5–0.9) collapses to OOS Sharpe (0.07–0.16), and only
1 of 3 assets beats buy & hold out-of-sample. Classic overfitting — the naive signal
is **not robust**, which is why the product is sold as analysis, not alpha.

## Delta-neutral pairs (the strongest edge found)

`pairs.py` applies "kimchi-premium" logic to carbon ETFs: two funds that should
track each other (e.g. **KRBN vs GRN**, correlation 0.92) occasionally diverge.
Trade the spread z-score — short the rich, long the cheap, equal dollars — so market
direction cancels (delta ~ 0) and you bet only on convergence. Same IS/OOS honesty.

```bash
python pairs.py          # -> out/pairs.md + out/pairs_best.png
```

Result — honest and important: a single 60/40 split looked great (KRBN/GRN OOS
Sharpe ~1.0), but that was a **lucky split**. Rigorous validation (`alpha_check.py`:
cost sensitivity + parameter plateau + sub-period + expanding walk-forward) shows the
edge **does not hold**: after 10 bps/leg costs the walk-forward combined OOS Sharpe is
**~ -0.07** (essentially zero). So there is **no reliable alpha** here yet — the naive
pair is not tradeable. This is exactly why single-split backtests must never be trusted.

## Alpha check (does the edge survive rigorous testing?)

`alpha_check.py` subjects a pair to four tests that a real edge must pass:
transaction-cost sensitivity, parameter-plateau robustness, sub-period stability,
and an expanding **walk-forward** (re-pick params on the past, test on the unseen
future, repeatedly).

```bash
python alpha_check.py KRBN GRN
```

Verdict for KRBN/GRN: **fails** — walk-forward combined OOS Sharpe ≈ -0.07 after
costs. No reliable alpha. Use this before ever trusting a backtest.

## KRX carbon-ETF premium residual box (why cross-broker "arb" is a mirage)

A common idea: long the carbon ETF at a Korean broker, short it at IBKR. **It is not
arbitrage** — KRBN/KEUA are single US-listed securities; a Korean "해외주식" order is
routed to the *same* NYSE Arca book, so both legs get the same price (you just pay
double fees + FX). Kimchi premium works only because Upbit and Binance are *separate*
order books (capital controls segment them).

The real analog is a **KRX-listed** carbon ETF (KRW, e.g. KODEX 400570) vs its own
**iNAV** — two genuinely separate "venues". `premium_box.py` builds the residual box:

    premium = close/NAV - 1;  residual = premium - rolling_mean;  z = residual/std

It also estimates the **mean-reversion half-life** (AR(1)) — if the residual does not
revert, the box is noise. Data drop: `data/krx_carbon.csv` (`date,close,nav` from
data.krx.co.kr / Naver; sample in `data/krx_carbon_sample.csv`, gitignored real file).

```bash
python premium_box.py
```

Honest frictions (why it is a *monitor*, not a retail arb): (1) retail **cannot short
KRX ETFs**, so the premium (top) leg is unexecutable; (2) no clean hedge — KEUA is
effectively delisted; (3) KRX and ICE EUA-futures hours barely overlap, so much of the
"gap" is a **stale-price artifact** that cannot be captured. Useful as a Korean-retail
sentiment gauge / newsletter content, not a tradeable edge.

## EUA fundamental fair value (fuel-switching model)

`fair_value.py` computes EUA's coal-to-gas **fuel-switching band** from real EU data
(TTF gas `TTF=F`, API2 coal `MTF=F`, physical-EUA ETC `CO2.L`, `EURUSD=X`) and tests a
"long when EUA is below the band" signal (IS/OOS + costs).

```bash
python fair_value.py     # -> out/fair_value.png + stats
```

Findings (honest): (1) as a trade it **fails out-of-sample** (OOS +1.2% vs buy&hold
+3.0%) — no reliable timing edge, consistent with momentum/pairs/premium. (2) The real
value is descriptive: EUA trades **~40% above** its fuel-switching fair value, i.e. a
large **policy scarcity premium** (MSR, cap tightening) is priced in — premium
newsletter content, not a push-button trade. Coal history ends ~2025-12, so the live
fair value needs a current coal price (CSV drop).

## Dashboard (view it in a browser)

`dashboard.py` builds a single self-contained `out/dashboard.html` (charts embedded
as base64 — no server, no cost) with the snapshot, per-asset backtest equity curves,
the IS/OOS research verdict, and the delta-neutral pairs section. Double-click to open.

```bash
python dashboard.py      # -> out/dashboard.html
```

## Why

Phase 2 of the carbon roadmap ([carbon-credit-token](../carbon-token/ROADMAP.md)):
turn quant analysis into a subscription product. Revenue comes from the newsletter
/ dashboard — **not** a token. Educational/research only; not investment advice.
