"""
Carbon market weekly intelligence — MVP data pipeline.

Pulls carbon-allowance ETFs (a free, liquid proxy for the EU ETS / global carbon
markets), computes price/return/vol/momentum metrics and a simple trend signal,
renders a normalized-price chart, and writes a Markdown weekly report you can
paste into a newsletter.

Usage:
    pip install -r requirements.txt
    python carbon_report.py

Outputs:
    out/carbon_prices.png      normalized price chart
    out/weekly_report.md       the newsletter draft
"""

from __future__ import annotations

import os
from datetime import date

import matplotlib

matplotlib.use("Agg")  # headless
import matplotlib.pyplot as plt
import pandas as pd
import yfinance as yf

# Carbon-allowance ETFs. KRBN is EU/global carbon heavy; KCCA = California (CCA);
# GRN = iPath global carbon. Free daily data via Yahoo Finance.
TICKERS = {
    "KRBN": "KraneShares Global Carbon (EU/global allowances)",
    "KEUA": "KraneShares European Carbon Allowance (pure EU ETS / EUA)",
    "KCCA": "KraneShares California Carbon (CCA)",
    "GRN": "iPath Global Carbon ETN",
}

OUT = "out"


def fetch(period: str = "1y") -> pd.DataFrame:
    """Return a DataFrame of daily adjusted close, one column per ticker."""
    raw = yf.download(
        list(TICKERS), period=period, interval="1d", auto_adjust=True, progress=False
    )
    close = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw[["Close"]]
    close = close.dropna(how="all").ffill()
    return close


def metrics(close: pd.DataFrame) -> pd.DataFrame:
    """Per-ticker snapshot: last price, 1w/1m return, 20d annualized vol, trend."""
    rows = []
    rets = close.pct_change()
    for t in close.columns:
        s = close[t].dropna()
        if len(s) < 60:
            continue
        last = s.iloc[-1]
        r_1w = s.iloc[-1] / s.iloc[-6] - 1 if len(s) > 6 else float("nan")
        r_1m = s.iloc[-1] / s.iloc[-22] - 1 if len(s) > 22 else float("nan")
        vol = rets[t].tail(20).std() * (252 ** 0.5)
        ma50 = s.tail(50).mean()
        trend = "UP" if last > ma50 else "DOWN"
        # Data-quality guard: a flat recent series (stale Yahoo feed for thin
        # ETFs) yields meaningless momentum — flag it instead of faking a signal.
        stale = (vol == 0) or pd.isna(vol) or (r_1m == 0 and r_1w == 0)
        if stale:
            trend, signal = "n/a", "STALE-DATA"
        elif trend == "UP" and r_1m > 0:
            signal = "LONG"
        elif trend == "DOWN" and r_1m < 0:
            signal = "SHORT/AVOID"
        else:
            signal = "NEUTRAL"
        rows.append(
            {
                "ticker": t,
                "last": round(float(last), 2),
                "ret_1w_%": round(float(r_1w) * 100, 2),
                "ret_1m_%": round(float(r_1m) * 100, 2),
                "vol_20d_ann_%": round(float(vol) * 100, 1),
                "trend_vs_MA50": trend,
                "signal": signal,
            }
        )
    return pd.DataFrame(rows).set_index("ticker")


def chart(close: pd.DataFrame, path: str) -> None:
    """Normalized (=100 at start) price lines."""
    norm = close / close.iloc[0] * 100
    plt.figure(figsize=(10, 5))
    for t in norm.columns:
        plt.plot(norm.index, norm[t], label=t, linewidth=1.6)
    plt.title("Carbon-allowance ETFs — normalized to 100 (1Y)")
    plt.ylabel("Indexed price")
    plt.legend()
    plt.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(path, dpi=130)
    plt.close()


def _df_to_md(df: pd.DataFrame) -> str:
    """Render a DataFrame as a Markdown table without the tabulate dependency."""
    cols = [df.index.name or "index"] + list(df.columns)
    out = ["| " + " | ".join(str(c) for c in cols) + " |",
           "| " + " | ".join("---" for _ in cols) + " |"]
    for idx, row in df.iterrows():
        vals = [str(idx)] + [str(row[c]) for c in df.columns]
        out.append("| " + " | ".join(vals) + " |")
    return "\n".join(out)


def spread_analytics(close: pd.DataFrame):
    """EU (KEUA) vs California (KCCA) carbon relative value: ratio + 60d z-score.

    A classic cross-market relative-value read: when the EU/California price ratio
    is far from its recent mean, the two carbon markets have diverged.
    """
    if "KEUA" not in close.columns or "KCCA" not in close.columns:
        return None
    df = close[["KEUA", "KCCA"]].dropna()
    if len(df) < 60:
        return None
    ratio = df["KEUA"] / df["KCCA"]
    z = (ratio.iloc[-1] - ratio.tail(60).mean()) / ratio.tail(60).std()
    return {"ratio_last": round(float(ratio.iloc[-1]), 4), "z60": round(float(z), 2)}


def write_report(m: pd.DataFrame, spread, chart_path: str, path: str) -> None:
    today = date.today().isoformat()
    lines = [
        f"# Carbon Market Weekly — {today}",
        "",
        "탄소배출권 시장 주간 브리핑 (EU ETS / 글로벌 / 캘리포니아 CCA 프록시).",
        "",
        f"![prices]({os.path.basename(chart_path)})",
        "",
        "## Snapshot",
        "",
        _df_to_md(m),
        "",
        "## Cross-market — EU vs California (relative value)",
        "",
        (
            "- KEUA/KCCA 비율 {}, 60일 z-score {} → {}".format(
                spread["ratio_last"],
                spread["z60"],
                "EU 상대적 고평가"
                if spread["z60"] > 1
                else "EU 상대적 저평가"
                if spread["z60"] < -1
                else "중립 범위",
            )
            if spread
            else "- (KEUA/KCCA 데이터 부족)"
        ),
        "",
        "## This week (draft)",
        "- KRBN(글로벌/EU 배출권): {} — 추세 {}, 1개월 {}%".format(
            m.loc["KRBN", "signal"] if "KRBN" in m.index else "n/a",
            m.loc["KRBN", "trend_vs_MA50"] if "KRBN" in m.index else "n/a",
            m.loc["KRBN", "ret_1m_%"] if "KRBN" in m.index else "n/a",
        ),
        "- (여기에 뉴스/정책 코멘트 2~3줄: EU ETS 정책, MSR, 경매 결과, K-ETS 동향 등)",
        "",
        "> Signal 규칙: 50일 이동평균 추세 + 1개월 모멘텀 동조 시 LONG/AVOID, 불일치 시 NEUTRAL.",
        "> 교육/리서치용. 투자 자문 아님.",
        "",
        "---",
        "*Data: Yahoo Finance (carbon-allowance ETFs). Free MVP pipeline — `carbon_report.py`.*",
    ]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    close = fetch()
    if close.empty:
        raise SystemExit("No data returned — check network / tickers.")
    m = metrics(close)
    chart_path = os.path.join(OUT, "carbon_prices.png")
    report_path = os.path.join(OUT, "weekly_report.md")
    chart(close, chart_path)
    spread = spread_analytics(close)
    write_report(m, spread, chart_path, report_path)
    print(m.to_string())
    print(f"\nWrote {chart_path} and {report_path}")


if __name__ == "__main__":
    main()
