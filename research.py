"""
Honest signal research: parameter sweep across carbon assets with in-sample /
out-of-sample split, so we never fool ourselves with overfitting.

Method (per asset):
  1. Split history: first 60% = in-sample (IS), last 40% = out-of-sample (OOS).
  2. Sweep (MA window, momentum lookback) on IS, pick the best by Sharpe.
  3. Report that param set's OOS performance vs buy & hold.
  A signal only "works" if it also wins OOS — IS-only wins are curve-fitting.

Usage:
    python research.py

Outputs:
    out/research.md   comparison table (IS pick -> OOS result, per asset)
    prints the same table
Also importable: run_research() -> (rows, grid) for the dashboard.
"""

from __future__ import annotations

import os

import numpy as np
import pandas as pd
import yfinance as yf

OUT = "out"
ASSETS = ["KRBN", "KCCA", "GRN"]  # KEUA history too thin for a split
MA_GRID = [20, 50, 100]
MOM_GRID = [21, 63, 126]


def load(ticker: str, period: str = "6y") -> pd.Series:
    raw = yf.download(ticker, period=period, interval="1d", auto_adjust=True, progress=False)
    s = raw["Close"]
    if isinstance(s, pd.DataFrame):
        s = s.iloc[:, 0]
    return s.dropna()


def _signal(px: pd.Series, ma: int, mom_lb: int) -> pd.Series:
    ma_line = px.rolling(ma).mean()
    mom = px / px.shift(mom_lb) - 1
    return ((px > ma_line) & (mom > 0)).astype(int).shift(1).fillna(0)


def _sharpe(daily: pd.Series) -> float:
    return float(daily.mean() / daily.std() * np.sqrt(252)) if daily.std() > 0 else 0.0


def _perf(px: pd.Series, ma: int, mom_lb: int) -> dict:
    ret = px.pct_change().fillna(0)
    sig = _signal(px, ma, mom_lb)
    strat = sig * ret
    eq = (1 + strat).cumprod()
    bh = (1 + ret).cumprod()
    return {
        "sharpe": round(_sharpe(strat), 2),
        "ret_%": round((eq.iloc[-1] - 1) * 100, 1),
        "bh_ret_%": round((bh.iloc[-1] - 1) * 100, 1),
        "exposure_%": round(float(sig.mean()) * 100, 1),
    }


def run_research():
    """Return (rows, grid). rows = per-asset IS-pick -> OOS; grid = full sweep rows."""
    rows, grid = [], []
    for tk in ASSETS:
        px = load(tk)
        if len(px) < 400:
            continue
        split = int(len(px) * 0.6)
        px_is, px_oos = px.iloc[:split], px.iloc[split:]

        best, best_params = None, None
        for ma in MA_GRID:
            for mom in MOM_GRID:
                p_is = _perf(px_is, ma, mom)
                grid.append({"asset": tk, "MA": ma, "mom": mom, **{f"IS_{k}": v for k, v in p_is.items()}})
                if best is None or p_is["sharpe"] > best["sharpe"]:
                    best, best_params = p_is, (ma, mom)

        ma, mom = best_params
        p_oos = _perf(px_oos, ma, mom)
        verdict = "WIN" if p_oos["ret_%"] > p_oos["bh_ret_%"] else "LOSE"
        rows.append({
            "asset": tk,
            "best_MA": ma,
            "best_mom": mom,
            "IS_sharpe": best["sharpe"],
            "OOS_sharpe": p_oos["sharpe"],
            "OOS_strat_%": p_oos["ret_%"],
            "OOS_bh_%": p_oos["bh_ret_%"],
            "OOS_exposure_%": p_oos["exposure_%"],
            "verdict": verdict,
        })
    return rows, grid


def _md(rows: list[dict]) -> str:
    if not rows:
        return "(no data)"
    cols = list(rows[0].keys())
    out = ["| " + " | ".join(cols) + " |", "|" + "|".join(["---"] * len(cols)) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(r[c]) for c in cols) + " |")
    return "\n".join(out)


def main() -> None:
    import sys

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    os.makedirs(OUT, exist_ok=True)
    rows, _ = run_research()
    table = _md(rows)
    wins = sum(1 for r in rows if r["verdict"] == "WIN")
    verdict = (
        f"\n결론: {len(rows)}개 자산 중 {wins}개만 아웃샘플에서 buy&hold를 이김. "
        + ("시그널에 견고성 없음 — 정직하게 '분석 제품'으로 포지셔닝." if wins <= len(rows) // 2
           else "일부 자산에서 견고성 신호 — 추가 검증 가치 있음.")
    )
    print(table)
    print(verdict)
    with open(os.path.join(OUT, "research.md"), "w", encoding="utf-8") as f:
        f.write("# Signal Research — in-sample pick vs out-of-sample\n\n" + table + "\n" + verdict + "\n")
    print(f"\nWrote {OUT}/research.md")


if __name__ == "__main__":
    main()
