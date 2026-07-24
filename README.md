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
| KCCA | KraneShares California Carbon (CCA) |
| GRN  | iPath Global Carbon ETN |

Source: Yahoo Finance (free, daily). Roadmap: add **EU ETS (EUA) spot/futures**
and **Korea K-ETS (KAU, from KRX)** direct series, plus a weekly auto-publish job.

## Why

Phase 2 of the carbon roadmap ([carbon-credit-token](../carbon-token/ROADMAP.md)):
turn quant analysis into a subscription product. Revenue comes from the newsletter
/ dashboard — **not** a token. Educational/research only; not investment advice.
