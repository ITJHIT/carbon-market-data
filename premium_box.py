"""
Premium residual-box analyzer for a KRX-listed foreign-underlying ETF
(e.g. KODEX 유럽탄소배출권선물ICE(H), code 400570) — cross-venue premium mean
reversion applied to an ETF whose **market price** and **iNAV** behave like two
separate venues.

    premium   = close / NAV - 1            (rich = premium, cheap = discount)
    box_mid   = rolling mean of premium    (the slowly-moving fair band)
    residual  = premium - box_mid
    z         = residual / rolling std
    ENTER long-the-ETF at the box BOTTOM (deep discount, z < -entry)
    EXIT   near the raw-premium TOP (z > +exit)

Crucially we also estimate the **mean-reversion half-life** (AR(1)): if the residual
does not actually revert, the box is a mirage.

DATA: KRX-listed ETFs have no free API. Download daily 종가(close) + 순자산가치(NAV)
from data.krx.co.kr (ETF > 개별종목 시세추이) or Naver, save as data/krx_carbon.csv:
    date,close,nav
    2026-07-20,11450,11500
    ...
(see data/krx_carbon_sample.csv). File is gitignored; sample is committed.

Usage:  python premium_box.py
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

PATH = os.path.join("data", "krx_carbon.csv")


def load(path: str = PATH) -> pd.DataFrame | None:
    if not os.path.exists(path):
        return None
    df = pd.read_csv(path)
    cols = {c.lower(): c for c in df.columns}
    for need in ("date", "close", "nav"):
        if need not in cols:
            raise ValueError("krx_carbon.csv must have date,close,nav columns")
    out = pd.DataFrame(
        {
            "close": pd.to_numeric(df[cols["close"]], errors="coerce").values,
            "nav": pd.to_numeric(df[cols["nav"]], errors="coerce").values,
        },
        index=pd.to_datetime(df[cols["date"]]),
    ).dropna().sort_index()
    return out if len(out) else None


def half_life(prem: pd.Series) -> float:
    """AR(1) mean-reversion half-life in trading days (NaN if not mean-reverting)."""
    lag = prem.shift(1)
    d = (prem - lag).dropna()
    lag = lag.loc[d.index]
    if len(d) < 20 or lag.std() == 0:
        return float("nan")
    b = np.polyfit(lag.values, d.values, 1)[0]
    if not (-1 < b < 0):
        return float("nan")
    return float(-np.log(2) / np.log(1 + b))


def analyze(df: pd.DataFrame, window: int = 20, entry: float = 1.5, exit_: float = 0.3) -> dict:
    prem = df["close"] / df["nav"] - 1.0
    box_mid = prem.rolling(window).mean()
    box_sd = prem.rolling(window).std()
    z = (prem - box_mid) / box_sd
    last_p, last_z = float(prem.iloc[-1]), float(z.iloc[-1])
    hl = half_life(prem)

    if last_z < -entry:
        state = "진입 후보 (박스 하단, 할인)" if last_p < 0 else "진입 후보 (박스 하단)"
    elif last_z > exit_:
        state = "청산 구간 (박스 상단, 프리미엄)"
    else:
        state = "중립 (박스 내부)"

    return {
        "n": len(df),
        "premium_now_%": round(last_p * 100, 3),
        "z_now": round(last_z, 2),
        "premium_mean_%": round(float(prem.mean()) * 100, 3),
        "premium_std_%": round(float(prem.std()) * 100, 3),
        "pct_time_discount": round(float((prem < 0).mean()) * 100, 1),
        "half_life_days": round(hl, 1) if hl == hl else None,
        "state": state,
    }


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    df = load()
    if df is None:
        print("data/krx_carbon.csv 없음 — KRX/Naver에서 종가+NAV 받아 저장하세요 (파일 상단 설명).")
        print("샘플 실행: cp data/krx_carbon_sample.csv data/krx_carbon.csv")
        return
    r = analyze(df)
    print("=== KRX 탄소 ETF 프리미엄 잔차 박스 ===")
    for k, v in r.items():
        print(f"  {k:20} {v}")
    if r["half_life_days"] is None:
        print("\n주의: 잔차가 통계적으로 회귀하지 않음 → 박스 신호 신뢰 불가.")
    elif r["half_life_days"] <= 15:
        print(f"\n잔차 반감기 {r['half_life_days']}일 — 회귀성 있음. 단, 아래 체결 제약 필독.")
    else:
        print(f"\n잔차 반감기 {r['half_life_days']}일 — 느린 회귀. 보유비용/이월 위험 큼.")
    print(
        "\n[체결 현실] KRX ETF는 개인 공매도 불가 → 프리미엄(상단) 숏 실행 곤란. "
        "할인(하단) 롱만 가능하고 헤지 자산(KEUA 사실상 폐지)도 마땅치 않음. "
        "게다가 한국장·EU 선물 시간대 비중첩으로 '괴리'의 상당분은 체결 불가한 스테일 가격."
    )


if __name__ == "__main__":
    main()
