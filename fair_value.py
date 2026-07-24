"""
EUA fundamental fair value via the coal-to-gas FUEL-SWITCHING model.

Power generators switch between coal and gas plants. The CO2 price that makes coal
and gas equally economic to run is a fundamental anchor for EUA:

    switch(€/tCO2) = (Pgas/ηgas - Pcoal/ηcoal) / (EFcoal/ηcoal - EFgas/ηgas)

    Pgas  = TTF gas price (€/MWh_th)                     -> TTF=F
    Pcoal = API2 coal (€/MWh_th) = (USD/t / EURUSD)/6.978 -> MTF=F, EURUSD=X
    η     = plant efficiency (a range -> a band)
    EF    = emission factor (tCO2/MWh_th): gas 0.184, coal 0.34

Using a range of efficiencies gives a **switching band** [lo, hi]. EUA below the band
is fundamentally cheap (coal-competitive -> emissions/allowance demand rise -> mean-
revert up); above the band it is rich. Signal: LONG the EUA proxy below the band, exit
above it. Validated honestly (in-sample/out-of-sample + costs) — a fundamental anchor
is only useful if it actually predicts.

EUA proxy: CO2.L (SparkChange **physical** EUA ETC). Approx €/t = CO2.L / EURUSD.
NOTE: MTF=F (coal) history ends ~2025-12, so the backtest runs on the overlapping
window; a live model needs a current coal price (CSV drop).

Usage:  python fair_value.py
Outputs: out/fair_value.png + printed stats
"""

from __future__ import annotations

import os
import sys
import warnings

warnings.filterwarnings("ignore")

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yfinance as yf

OUT = "out"
EF_GAS, EF_COAL, COAL_MWH_PER_T = 0.184, 0.34, 6.978
EFF_COMBOS = [(0.50, 0.42), (0.55, 0.38)]  # (gas_eff, coal_eff) -> band edges


def _col(t: str, period: str = "3y") -> pd.Series:
    c = yf.download(t, period=period, interval="1d", auto_adjust=True, progress=False)["Close"]
    if isinstance(c, pd.DataFrame):
        c = c.iloc[:, 0]
    return c.dropna()


def fetch() -> pd.DataFrame:
    d = {
        "gas": _col("TTF=F"),
        "coal": _col("MTF=F"),
        "eua": _col("CO2.L"),
        "fx": _col("EURUSD=X"),
    }
    return pd.DataFrame(d).dropna()


def switch_price(gas, coal_usd_t, fx, geff, ceff):
    coal_eur = (coal_usd_t / fx) / COAL_MWH_PER_T
    return (gas / geff - coal_eur / ceff) / (EF_COAL / ceff - EF_GAS / geff)


def build(df: pd.DataFrame):
    edges = [switch_price(df["gas"], df["coal"], df["fx"], ge, ce) for ge, ce in EFF_COMBOS]
    band = pd.concat(edges, axis=1)
    lo, hi = band.min(axis=1), band.max(axis=1)
    eua = df["eua"] / df["fx"]  # approx €/tCO2
    return eua, lo, hi


def _positions(eua, lo, hi):
    """Long below band (cheap), exit above band (rich), hold in between (hysteresis)."""
    pos, out = 0, []
    for e, l, h in zip(eua.values, lo.values, hi.values):
        if pos == 0 and e < l:
            pos = 1
        elif pos == 1 and e > h:
            pos = 0
        out.append(pos)
    return pd.Series(out, index=eua.index, dtype=float)


def _sharpe(x):
    return float(x.mean() / x.std() * np.sqrt(252)) if x.std() > 0 else 0.0


def _stats(eq, daily):
    yrs = max(len(eq) / 252, 1e-9)
    return {
        "ret_%": round((eq.iloc[-1] - 1) * 100, 1),
        "CAGR_%": round((eq.iloc[-1] ** (1 / yrs) - 1) * 100, 1),
        "Sharpe": round(_sharpe(daily), 2),
        "maxDD_%": round(float((eq / eq.cummax() - 1).min()) * 100, 1),
    }


def backtest(eua, lo, hi, cost_bps=10.0, split=0.6):
    ret = eua.pct_change().fillna(0)
    pos = _positions(eua, lo, hi)
    turn = pos.diff().abs().fillna(0)
    strat = pos.shift(1).fillna(0) * ret - turn * (cost_bps / 10000.0)
    n = len(eua)
    k = int(n * split)
    res = {}
    for name, sl in [("ALL", slice(None)), ("IS", slice(0, k)), ("OOS", slice(k, n))]:
        sr = strat.iloc[sl]
        rr = ret.iloc[sl]
        res[name] = {
            "strat": _stats((1 + sr).cumprod(), sr),
            "bh": _stats((1 + rr).cumprod(), rr),
            "exposure_%": round(float((pos.iloc[sl] != 0).mean()) * 100, 1),
        }
    return pos, strat, ret, res


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    os.makedirs(OUT, exist_ok=True)
    df = fetch()
    eua, lo, hi = build(df)
    pos, strat, ret, res = backtest(eua, lo, hi)

    last_e, last_lo, last_hi = float(eua.iloc[-1]), float(lo.iloc[-1]), float(hi.iloc[-1])
    mid = (last_lo + last_hi) / 2
    dev = (last_e / mid - 1) * 100
    state = "밴드 하단 이하 → 저평가(롱 후보)" if last_e < last_lo else \
            "밴드 상단 이상 → 고평가(청산)" if last_e > last_hi else "밴드 내부(중립)"

    print(f"=== EUA 연료전환 fair value  (window {df.index[0].date()}~{df.index[-1].date()}, n={len(df)}) ===")
    print(f"EUA≈{last_e:.1f} | 전환밴드 [{last_lo:.1f}, {last_hi:.1f}] €/t | 중앙 대비 {dev:+.1f}% | {state}")
    print("\n            전략(롱/무)         Buy&Hold        노출")
    for k in ["ALL", "IS", "OOS"]:
        s, b = res[k]["strat"], res[k]["bh"]
        print(f"  {k:4} ret {s['ret_%']:>6}%  Sh {s['Sharpe']:>5} | ret {b['ret_%']:>6}%  Sh {b['Sharpe']:>5} | {res[k]['exposure_%']:>5}%")

    oos = res["OOS"]
    verdict = ("OOS에서 buy&hold 상회 → 펀더멘털 앵커에 신호 있음(추가검증 가치)."
               if oos["strat"]["ret_%"] > oos["bh"]["ret_%"] and oos["strat"]["Sharpe"] > 0.3
               else "OOS에서 buy&hold 미달 → 이 단순 형태로는 엣지 불충분.")
    print(f"\n판정: {verdict}")

    fig, ax = plt.subplots(2, 1, figsize=(10, 7), sharex=True, height_ratios=[2, 1])
    ax[0].plot(eua.index, eua, label="EUA≈(€/t)", color="#111", lw=1.3)
    ax[0].fill_between(eua.index, lo, hi, color="#2e7d32", alpha=0.18, label="fuel-switch band")
    ax[0].set_title("EUA vs coal-to-gas switching band")
    ax[0].legend(); ax[0].grid(alpha=0.3)
    eq_s = (1 + strat).cumprod(); eq_b = (1 + ret).cumprod()
    ax[1].plot(eq_s.index, eq_s, label=f"signal (long/flat) Sh {res['ALL']['strat']['Sharpe']}", color="#1b7a1b", lw=1.5)
    ax[1].plot(eq_b.index, eq_b, label=f"buy&hold Sh {res['ALL']['bh']['Sharpe']}", color="#888", lw=1.2)
    ax[1].set_title("Growth of $1"); ax[1].legend(); ax[1].grid(alpha=0.3)
    fig.tight_layout()
    p = os.path.join(OUT, "fair_value.png")
    fig.savefig(p, dpi=120); plt.close(fig)
    print(f"\nWrote {p}")
    print("주의: 교육·리서치용. 비용 10bps 반영, 슬리피지·차입 미반영. 석탄(MTF=F) 최신치 없어 백테스트 구간 한정.")


if __name__ == "__main__":
    main()
