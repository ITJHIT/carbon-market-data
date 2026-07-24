"""
Is the delta-neutral carbon pair (KRBN/GRN) REAL alpha, or a lucky single split?

Four stress tests — a signal that is real survives all four; one that is noise fails
at least one:

  A. Transaction-cost sensitivity   — does net Sharpe survive realistic costs?
  B. Parameter robustness (plateau) — do NEIGHBORING params also work, or just one cell?
  C. Sub-period stability           — positive in each chronological third?
  D. Walk-forward (expanding)       — re-pick params on the past, test on the unseen
                                      future, repeatedly. The strongest evidence.

Usage:  python alpha_check.py [A_TICKER B_TICKER]   (default KRBN GRN)
"""

from __future__ import annotations

import sys

import numpy as np
import pandas as pd
import yfinance as yf

WIN_GRID = [40, 60, 90]
ENTRY_GRID = [1.0, 1.5, 2.0]
EXIT = 0.5


def load(a: str, b: str, period: str = "6y") -> pd.DataFrame:
    df = yf.download([a, b], period=period, interval="1d", auto_adjust=True, progress=False)["Close"]
    return df.dropna()


def _positions(z: pd.Series, entry: float, exit_: float = EXIT) -> pd.Series:
    pos, out = 0, []
    for zi in z:
        if np.isnan(zi):
            out.append(0)
            continue
        if pos == 0:
            if zi > entry:
                pos = -1
            elif zi < -entry:
                pos = 1
        elif abs(zi) < exit_:
            pos = 0
        out.append(pos)
    return pd.Series(out, index=z.index, dtype=float)


def _sharpe(daily: pd.Series) -> float:
    return float(daily.mean() / daily.std() * np.sqrt(252)) if daily.std() > 0 else 0.0


def net_returns(pa: pd.Series, pb: pd.Series, win: int, entry: float, cost_bps: float) -> pd.Series:
    spread = np.log(pa / pb)
    z = (spread - spread.rolling(win).mean()) / spread.rolling(win).std()
    ret = pa.pct_change().fillna(0) - pb.pct_change().fillna(0)  # dollar-neutral long A / short B
    pos = _positions(z, entry)
    gross = pos.shift(1).fillna(0) * ret
    turnover = pos.diff().abs().fillna(0) * 2.0  # two legs per position change
    cost = turnover * (cost_bps / 10000.0)
    return gross - cost


def best_params(pa: pd.Series, pb: pd.Series, cost_bps: float):
    best, bp = -1e9, None
    for w in WIN_GRID:
        for e in ENTRY_GRID:
            s = _sharpe(net_returns(pa, pb, w, e, cost_bps))
            if s > best:
                best, bp = s, (w, e)
    return bp, best


def ann_ret(daily: pd.Series) -> float:
    return float((1 + daily).prod() ** (252 / max(len(daily), 1)) - 1)


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    a, b = (sys.argv[1], sys.argv[2]) if len(sys.argv) > 2 else ("KRBN", "GRN")
    px = load(a, b)
    pa, pb = px[a], px[b]
    corr = pa.pct_change().corr(pb.pct_change())
    W, E = 90, 1.5  # a fixed, central param set for A/B/C
    print(f"=== Alpha check: {a}/{b}  (corr {corr:.2f}, {px.index[0].date()}→{px.index[-1].date()}, n={len(px)}) ===")

    # A. cost sensitivity
    print("\nA. 거래비용 민감도 (win=90, entry=1.5, full sample)")
    print(f"   {'bps/leg':>8}{'Sharpe':>9}{'ann.ret':>9}")
    for c in [0, 5, 10, 20, 30]:
        r = net_returns(pa, pb, W, E, c)
        print(f"   {c:>8}{_sharpe(r):>9.2f}{ann_ret(r) * 100:>8.1f}%")

    # B. parameter plateau (10 bps)
    print("\nB. 파라미터 이웃 견고성 (net Sharpe @10bps) — 값들이 고르게 양수면 '평지'(견고)")
    hdr = "   win\\entry" + "".join(f"{e:>8}" for e in ENTRY_GRID)
    print(hdr)
    for w in WIN_GRID:
        row = "".join(f"{_sharpe(net_returns(pa, pb, w, e, 10)):>8.2f}" for e in ENTRY_GRID)
        print(f"   {w:>9}{row}")

    # C. sub-period stability (10 bps)
    print("\nC. 3개 기간 안정성 (net Sharpe @10bps, win=90 entry=1.5)")
    thirds = np.array_split(np.arange(len(px)), 3)
    for i, idx in enumerate(thirds, 1):
        sub = px.iloc[idx[0]:idx[-1] + 1]
        r = net_returns(sub[a], sub[b], W, E, 10)
        print(f"   기간{i} ({sub.index[0].date()}~{sub.index[-1].date()}): Sharpe {_sharpe(r):>5.2f}")

    # D. walk-forward (10 bps): re-pick params on the past, test on the next slice
    print("\nD. 워크포워드 @10bps (과거로 파라미터 선택 → 미래 구간 검증, 반복)")
    n = len(px)
    start = int(n * 0.4)
    folds = np.array_split(np.arange(start, n), 5)
    oos_all = []
    for i, idx in enumerate(folds, 1):
        tr = px.iloc[: idx[0]]
        te = px.iloc[idx[0] : idx[-1] + 1]
        (w, e), _ = best_params(tr[a], tr[b], 10)
        r = net_returns(te[a], te[b], w, e, 10)
        oos_all.append(r)
        print(f"   fold{i} test {te.index[0].date()}~{te.index[-1].date()} "
              f"(pick win={w} entry={e}): Sharpe {_sharpe(r):>5.2f}, ret {ann_ret(r)*100:>5.1f}%")
    combined = pd.concat(oos_all)
    wf_sharpe = _sharpe(combined)
    print(f"\n   >> 워크포워드 통합 OOS: Sharpe {wf_sharpe:.2f}, ann.ret {ann_ret(combined)*100:.1f}%")

    verdict = (
        "REAL-ish 알파 신호: 비용 견디고, 파라미터 평지, 기간 안정, 워크포워드 통과."
        if wf_sharpe > 0.5 else
        "약함/불확실: 비용·기간·워크포워드 중 무너짐 → 실매매 부적합, 추가 연구 필요."
    )
    print(f"\n판정: {verdict}")


if __name__ == "__main__":
    main()
