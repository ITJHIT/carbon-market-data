"""
K-ETS (Korea Emissions Trading Scheme) data loader.

Korea's KRX carbon market (KAU — Korean Allowance Unit) has no free real-time API,
so this reads a locally-dropped CSV. Download the price history from KRX and save it
as data/kau.csv, then the weekly report includes a Korea section automatically.

Where to get the data (free):
  - KRX 배출권시장 정보플랫폼: https://ets.krx.co.kr  (일별시세 → CSV/Excel 다운로드)
  - or 한국거래소 정보데이터시스템: https://data.krx.co.kr
  Export daily KAU close prices, then map to the format below.

CSV format (data/kau.csv), header required:
    date,close
    2026-07-20,8900
    2026-07-21,8950
    ...
(date = YYYY-MM-DD, close = KRW per tCO2)

If data/kau.csv is absent, the report simply skips the Korea section.
"""

from __future__ import annotations

import os

import pandas as pd

DEFAULT_PATH = os.path.join("data", "kau.csv")


def load_kau(path: str = DEFAULT_PATH) -> pd.Series | None:
    """Return a date-indexed KAU close series, or None if the file is missing/empty."""
    if not os.path.exists(path):
        return None
    df = pd.read_csv(path)
    cols = {c.lower(): c for c in df.columns}
    if "date" not in cols or "close" not in cols:
        raise ValueError("data/kau.csv must have 'date' and 'close' columns")
    s = pd.Series(
        pd.to_numeric(df[cols["close"]], errors="coerce").values,
        index=pd.to_datetime(df[cols["date"]]),
    ).dropna().sort_index()
    return s if len(s) else None


def _pct(a: float, b: float) -> str:
    if b == 0 or pd.isna(b):
        return "n/a"
    return f"{round((a / b - 1) * 100, 1)}%"


def kau_section(path: str = DEFAULT_PATH) -> str | None:
    """Markdown block for the Korea K-ETS section, or None if no data."""
    s = load_kau(path)
    if s is None:
        return None
    last = float(s.iloc[-1])
    d1w = _pct(last, float(s.iloc[-6])) if len(s) >= 6 else "n/a"
    d1m = _pct(last, float(s.iloc[-22])) if len(s) >= 22 else "n/a"
    trend = "n/a"
    if len(s) >= 20:
        ma20 = s.rolling(20).mean().iloc[-1]
        trend = "▲ 상승" if last > ma20 else "▼ 하락"
    return (
        "## Korea K-ETS (KAU)\n\n"
        f"- KAU 종가: **{last:,.0f}원/tCO2**  |  1주 {d1w}  |  1개월 {d1m}  |  추세(20일) {trend}\n"
        f"- 데이터: KRX 배출권시장 (data/kau.csv, 수기 업데이트)  |  최신일 {s.index[-1].date()}\n"
        "- EU-한국 프리미엄: EUA(유로) 대비 KAU(원) — 환율·정책 상이로 직접 재정거래 불가, 상대 동향 참고용."
    )


if __name__ == "__main__":
    import sys

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # Windows console: allow Korean/em-dash
    sec = kau_section()
    print(sec if sec else "data/kau.csv 없음 — KRX에서 받아서 저장하세요 (kau.py 상단 설명 참고).")
