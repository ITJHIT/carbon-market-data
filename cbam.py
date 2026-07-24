"""
CBAM (EU 탄소국경조정제도) 비용 계산기 — 한국 수출기업용.

2026년부터 EU로 철강/알루미늄/시멘트/비료/수소/전력을 수출하면, 제품에 내재된
탄소배출량만큼 CBAM 인증서를 사야 합니다(가격 = EUA 연동). EU ETS 무상할당이
단계적으로 사라지면서 부담이 2026년 2.5% → 2034년 100%로 커집니다.

이 계산기는 "당신 회사가 EU에 X톤 수출하면 CBAM 비용이 연도별로 얼마인가"를 추정합니다.
중소 수출사 대상 무료 리드마그넷 + 유료 상세리포트/컨설팅의 씨앗.

주의: 배출계수(EF)는 공개 벤치마크 근사치입니다. 실제 신고는 검증된 실측 배출량이
필요합니다. 교육/영업용 추정 도구.

Usage:
    python cbam.py                       # 샘플(철강 수출사)
    python cbam.py steel 20000 1.9       # 품목 EU수출톤 배출계수(tCO2/t)
"""

from __future__ import annotations

import sys
import warnings

warnings.filterwarnings("ignore")

# CBAM 의무 반영 비율 (EU ETS 무상할당 단계 폐지 스케줄)
PHASE_IN = {
    2026: 0.025, 2027: 0.05, 2028: 0.10, 2029: 0.225, 2030: 0.485,
    2031: 0.61, 2032: 0.735, 2033: 0.86, 2034: 1.00,
}

# 품목별 지시적 배출계수 (tCO2 / 제품톤). 실측·검증값으로 교체 필요.
DEFAULT_EF = {
    "steel": 2.0,        # 조강(BF-BOF)
    "aluminium": 1.6,    # 1차 알루미늄(직접배출 근사)
    "cement": 0.66,      # 시멘트
    "fertilizer": 1.8,   # 질소비료/요소
    "hydrogen": 10.0,    # 그레이수소
    "electricity": 0.4,  # 전력(MWh당)
}
KO = {"steel": "철강", "aluminium": "알루미늄", "cement": "시멘트",
      "fertilizer": "비료", "hydrogen": "수소", "electricity": "전력"}


def eua_price_eur(default: float = 75.0) -> float:
    """실물 EUA ETC(CO2.L)로 현재가 근사(€/tCO2). 실패 시 기본값."""
    try:
        import pandas as pd
        import yfinance as yf

        def last(t):
            c = yf.download(t, period="1mo", interval="1d", auto_adjust=True, progress=False)["Close"]
            if isinstance(c, pd.DataFrame):
                c = c.iloc[:, 0]
            return float(c.dropna().iloc[-1])

        return round(last("CO2.L") / last("EURUSD=X"), 1)
    except Exception:
        return default


def project(product: str, tonnes_eu: float, ef: float, eua: float) -> list[dict]:
    embedded = tonnes_eu * ef  # 연간 내재배출 tCO2
    rows = []
    for yr, frac in PHASE_IN.items():
        cost_eur = embedded * frac * eua
        rows.append({
            "year": yr,
            "phase_%": round(frac * 100, 1),
            "billable_tCO2": round(embedded * frac),
            "cost_EUR": round(cost_eur),
            "cost_KRW_억": round(cost_eur * 1450 / 1e8, 2),  # €→₩ 근사
        })
    return rows, embedded


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = sys.argv[1:]
    product = args[0] if len(args) > 0 else "steel"
    tonnes = float(args[1]) if len(args) > 1 else 20000.0
    ef = float(args[2]) if len(args) > 2 else DEFAULT_EF.get(product, 2.0)
    eua = eua_price_eur()

    rows, embedded = project(product, tonnes, ef, eua)
    kname = KO.get(product, product)
    print(f"=== CBAM 비용 추정 — {kname} EU수출 {tonnes:,.0f}톤 ===")
    print(f"배출계수 {ef} tCO2/톤  →  연간 내재배출 {embedded:,.0f} tCO2")
    print(f"EUA 현재가 ≈ €{eua}/tCO2 (CBAM 인증서 가격 연동)\n")
    print(f"{'연도':>6}{'의무%':>7}{'과금tCO2':>11}{'비용(€)':>12}{'비용(억원)':>12}")
    for r in rows:
        print(f"{r['year']:>6}{r['phase_%']:>7}{r['billable_tCO2']:>11,}{r['cost_EUR']:>12,}{r['cost_KRW_억']:>12}")
    tot = sum(r["cost_EUR"] for r in rows)
    print(f"\n2026~2034 누적 CBAM 비용 ≈ €{tot:,.0f}  (약 {tot*1450/1e8:.1f}억원)")
    print("\n[해석] 무상할당이 사라질수록 부담 급증. 배출량 1톤 줄일 때마다 위 비용만큼 절감.")
    print("주의: 배출계수는 벤치마크 근사. 실제 신고는 검증 실측값 필요. 추정·영업용.")


if __name__ == "__main__":
    main()
