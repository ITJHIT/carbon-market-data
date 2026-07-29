"""
Delta-neutral pairs trading on carbon assets — cross-venue premium mean reversion
applied to carbon ETFs.

Idea: two carbon ETFs that should track each other (e.g. KRBN vs GRN) occasionally
diverge. Trade the *spread*, not the direction:
    spread = log(A / B);  z = rolling z-score of spread
    z > +entry  -> spread is stretched  -> SHORT A / LONG B  (dollar-neutral)
    z < -entry  -> SHORT B / LONG A
    |z| < exit  -> flat (convergence captured)
Because we are long one and short the other in equal dollars, market direction
cancels out (delta ~ 0). We only bet on convergence — like arbitraging a price
gap between two venues for the same underlying.

Honesty: parameters are chosen on the first 60% (in-sample) and judged on the
unseen last 40% (out-of-sample). Costs/slippage/borrow are NOT modeled.

Usage:
    python pairs.py
Outputs:
    out/pairs.md          correlation + IS/OOS results per pair
    out/pairs_best.png    spread z-score + equity curve for the best pair
Also importable: run_pairs() -> (corr, rows, best) for the dashboard.
"""

from __future__ import annotations

import itertools
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yfinance as yf

OUT = "out"
ASSETS = ["KRBN", "GRN", "KCCA"]
WIN_GRID = [40, 60, 90]
ENTRY_GRID = [1.0, 1.5, 2.0]
EXIT = 0.5


def load_panel(period: str = "6y") -> pd.DataFrame:
    df = yf.download(ASSETS, period=period, interval="1d", auto_adjust=True, progress=False)["Close"]
    if isinstance(df, pd.Series):
        df = df.to_frame()
    return df.dropna()


def _positions(z: pd.Series, entry: float, exit_: float = EXIT) -> pd.Series:
    """Hysteresis: enter at |z|>entry (short spread if z>0), exit at |z|<exit."""
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


def pair_perf(pa: pd.Series, pb: pd.Series, win: int, entry: float):
    spread = np.log(pa / pb)
    z = (spread - spread.rolling(win).mean()) / spread.rolling(win).std()
    ret = pa.pct_change().fillna(0) - pb.pct_change().fillna(0)  # long A / short B, dollar-neutral
    pos = _positions(z, entry)
    strat = pos.shift(1).fillna(0) * ret
    eq = (1 + strat).cumprod()
    trades = int((pos.diff().abs() > 0).sum())
    return {
        "sharpe": round(_sharpe(strat), 2),
        "ret_%": round((eq.iloc[-1] - 1) * 100, 1),
        "exposure_%": round(float((pos != 0).mean()) * 100, 1),
        "trades": trades,
    }, z, strat


def run_pairs():
    px = load_panel()
    corr = px.pct_change().corr().round(2)
    rows = []
    best = None  # (label, oos_sharpe, series...)
    for a, b in itertools.combinations([c for c in ASSETS if c in px.columns], 2):
        pa, pb = px[a], px[b]
        split = int(len(px) * 0.6)
        is_a, is_b = pa.iloc[:split], pb.iloc[:split]
        oos_a, oos_b = pa.iloc[split:], pb.iloc[split:]

        pick, pick_params = None, None
        for win in WIN_GRID:
            for entry in ENTRY_GRID:
                p_is, _, _ = pair_perf(is_a, is_b, win, entry)
                if pick is None or p_is["sharpe"] > pick["sharpe"]:
                    pick, pick_params = p_is, (win, entry)

        win, entry = pick_params
        p_oos, z_oos, strat_oos = pair_perf(oos_a, oos_b, win, entry)
        rows.append({
            "pair": f"{a}/{b}",
            "corr": corr.loc[a, b],
            "win": win,
            "entry": entry,
            "IS_sharpe": pick["sharpe"],
            "OOS_sharpe": p_oos["sharpe"],
            "OOS_ret_%": p_oos["ret_%"],
            "OOS_exp_%": p_oos["exposure_%"],
            "trades": p_oos["trades"],
            "verdict": "WIN" if p_oos["sharpe"] > 0.5 else "WEAK",
        })
        if best is None or p_oos["sharpe"] > best[1]:
            eq = (1 + strat_oos).cumprod()
            best = (f"{a}/{b}", p_oos["sharpe"], z_oos, eq, (win, entry))
    return corr, rows, best


def _md(rows):
    if not rows:
        return "(no data)"
    cols = list(rows[0].keys())
    out = ["| " + " | ".join(cols) + " |", "|" + "|".join(["---"] * len(cols)) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(r[c]) for c in cols) + " |")
    return "\n".join(out)


def _best_chart(best, path):
    label, sharpe, z, eq, params = best
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(9, 6), sharex=True)
    ax1.plot(z.index, z, lw=1, color="#444")
    ax1.axhline(params[1], ls="--", color="#b00020", lw=0.8)
    ax1.axhline(-params[1], ls="--", color="#b00020", lw=0.8)
    ax1.axhline(0, color="#aaa", lw=0.6)
    ax1.set_title(f"{label} spread z-score (OOS)  win={params[0]} entry={params[1]}")
    ax2.plot(eq.index, eq, color="#1b7a1b", lw=1.6)
    ax2.set_title(f"Delta-neutral equity (OOS)  Sharpe {sharpe}")
    ax2.set_ylabel("Growth of $1")
    for ax in (ax1, ax2):
        ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def main() -> None:
    import sys

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    os.makedirs(OUT, exist_ok=True)
    corr, rows, best = run_pairs()
    table = _md(rows)
    print("Correlation (daily returns):")
    print(corr.to_string())
    print("\nPairs — in-sample pick -> out-of-sample:")
    print(table)
    if best:
        _best_chart(best, os.path.join(OUT, "pairs_best.png"))
        print(f"\nBest pair OOS: {best[0]}  Sharpe {best[1]}  -> out/pairs_best.png")
    wins = sum(1 for r in rows if r["verdict"] == "WIN")
    verdict = f"\n결론: {wins}/{len(rows)} 페어가 OOS Sharpe>0.5. " + (
        "델타뉴트럴 스프레드가 방향성 시그널보다 견고 — 추가 검증 가치 있음."
        if wins >= 1 else "이 자산군에선 페어 수렴도 약함."
    )
    print(verdict)
    with open(os.path.join(OUT, "pairs.md"), "w", encoding="utf-8") as f:
        f.write("# Delta-neutral pairs — correlation + IS/OOS\n\n```\n" + corr.to_string()
                + "\n```\n\n" + table + "\n" + verdict + "\n")
    print(f"\nWrote {OUT}/pairs.md")


if __name__ == "__main__":
    main()
