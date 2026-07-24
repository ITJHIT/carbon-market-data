"""
Carbon SEASONALITY — the forced-flow calendar edge.

Carbon markets are dominated by price-insensitive flows: EU industry receives free
allowances at end-February (and often sells) -> February supply; compliance entities
buy into year-end -> Q4 demand. That is a *structural* reason for a calendar pattern,
unlike price-only momentum (which we already showed has no OOS edge).

This module:
  1. Monthly return table (mean, % positive, t-stat) for an EUA proxy.
  2. Year-by-year breakdown of the key months (pre-specified: Feb weak, Dec strong).
  3. A seasonal-overlay backtest vs buy & hold, with costs:
       - base         : buy & hold
       - ex-Feb       : hold, but sit OUT February
       - short-Feb    : hold, and SHORT February (retail: buy inverse ETF 459370)

HONEST LIMITS: only ~5-6 Februaries of free ETF history — low statistical power. The
defense is (a) a known structural cause and (b) recent 3-year consistency across two
instruments. Drop a longer EUA CSV (data/eua_long.csv: date,close) to firm it up.

Usage:  python seasonal.py
Outputs: out/seasonal.png + printed tables
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
KO = ["1월", "2월", "3월", "4월", "5월", "6월", "7월", "8월", "9월", "10월", "11월", "12월"]


def load(ticker: str = "KRBN") -> pd.Series:
    long_csv = os.path.join("data", "eua_long.csv")
    if ticker == "EUA_LONG" and os.path.exists(long_csv):
        df = pd.read_csv(long_csv)
        c = {x.lower(): x for x in df.columns}
        return pd.Series(pd.to_numeric(df[c["close"]], errors="coerce").values,
                         index=pd.to_datetime(df[c["date"]])).dropna().sort_index()
    c = yf.download(ticker, period="6y", interval="1d", auto_adjust=True, progress=False)["Close"]
    if isinstance(c, pd.DataFrame):
        c = c.iloc[:, 0]
    return c.dropna()


def monthly(px: pd.Series) -> pd.Series:
    return px.resample("ME").last().pct_change().dropna() * 100


def month_table(mr: pd.Series) -> list[dict]:
    rows = []
    for m in range(1, 13):
        v = mr[mr.index.month == m]
        if len(v) == 0:
            continue
        se = v.std() / np.sqrt(len(v)) if len(v) > 1 else np.nan
        t = v.mean() / se if se and se > 0 else np.nan
        rows.append({
            "month": KO[m - 1],
            "mean_%": round(float(v.mean()), 1),
            "pos/neg": f"{int((v > 0).sum())}/{int((v < 0).sum())}",
            "n": len(v),
            "t": round(float(t), 2) if t == t else None,
        })
    return rows


def seasonal_backtest(px: pd.Series, cost_bps: float = 10.0):
    """Daily long/flat/short by calendar month. Feb short, else long; ex-Feb sits out Feb."""
    ret = px.pct_change().fillna(0)
    mth = ret.index.month
    c = cost_bps / 10000.0

    # position series (held from prior close), long except February
    pos_base = pd.Series(1.0, index=ret.index)
    pos_exfeb = pd.Series(np.where(mth != 2, 1.0, 0.0), index=ret.index)
    pos_short = pd.Series(np.where(mth != 2, 1.0, -1.0), index=ret.index)

    def net(pos):
        turn = pos.diff().abs().fillna(0.0)
        return pos.shift(1).fillna(pos.iloc[0]) * ret - turn * c

    def eq(r):
        return (1 + r).cumprod()

    def stats(r):
        e = eq(r)
        sh = float(r.mean() / r.std() * np.sqrt(252)) if r.std() > 0 else 0.0
        dd = float((e / e.cummax() - 1).min()) * 100
        yrs = max(len(r) / 252, 1e-9)
        cagr = float(e.iloc[-1] ** (1 / yrs) - 1) * 100
        return {"CAGR_%": round(cagr, 1), "Sharpe": round(sh, 2), "maxDD_%": round(dd, 1)}

    r_base, r_exfeb, r_short = net(pos_base), net(pos_exfeb), net(pos_short)
    return {
        "base": stats(r_base),
        "ex_feb": stats(r_exfeb),
        "short_feb": stats(r_short),
    }, eq(r_base), eq(r_exfeb), eq(r_short)


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    os.makedirs(OUT, exist_ok=True)

    primary = "EUA_LONG" if os.path.exists(os.path.join("data", "eua_long.csv")) else "KRBN"
    px = load(primary)
    src = "data/eua_long.csv" if primary == "EUA_LONG" else "KRBN (EUA proxy)"
    mr = monthly(px)
    print(f"=== 월별 계절성  [{src}]  {px.index[0].date()}~{px.index[-1].date()} ===")
    print(f"{'월':>4}{'평균%':>8}{'pos/neg':>9}{'n':>4}{'t':>7}")
    for r in month_table(mr):
        print(f"{r['month']:>4}{r['mean_%']:>8}{r['pos/neg']:>9}{r['n']:>4}{str(r['t']):>7}")

    stats, eqb, eqe, eqs = seasonal_backtest(px)
    print("\n=== 계절 오버레이 백테스트 (비용 반영) ===")
    print(f"{'전략':>10}{'CAGR%':>9}{'Sharpe':>8}{'maxDD%':>9}")
    labels = {"base": "매수보유", "ex_feb": "2월제외", "short_feb": "2월숏"}
    for k in ["base", "ex_feb", "short_feb"]:
        s = stats[k]
        print(f"{labels[k]:>10}{s['CAGR_%']:>9}{s['Sharpe']:>8}{s['maxDD_%']:>9}")

    # confirm on CO2.L too if primary is proxy
    print("\n[확인] CO2.L(실물 EUA)로 2월/12월 재확인:")
    try:
        mr2 = monthly(load("CO2.L"))
        for m, lab in [(2, "2월"), (12, "12월")]:
            v = mr2[mr2.index.month == m]
            print(f"  {lab}: 평균 {v.mean():.1f}%  ({int((v>0).sum())}/{int((v<0).sum())})")
    except Exception as e:
        print("  (CO2.L 실패)", str(e)[:40])

    fig = plt.figure(figsize=(10, 5))
    plt.plot(eqb.index, eqb, label=f"매수보유 Sh {stats['base']['Sharpe']}", color="#888", lw=1.3)
    plt.plot(eqe.index, eqe, label=f"2월제외 Sh {stats['ex_feb']['Sharpe']}", color="#1565c0", lw=1.5)
    plt.plot(eqs.index, eqs, label=f"2월숏 Sh {stats['short_feb']['Sharpe']}", color="#1b7a1b", lw=1.7)
    plt.title(f"Carbon seasonal overlay — {src}")
    plt.ylabel("Growth of $1"); plt.legend(); plt.grid(alpha=0.3)
    plt.tight_layout()
    p = os.path.join(OUT, "seasonal.png")
    plt.savefig(p, dpi=120); plt.close()
    print(f"\nWrote {p}")
    print("주의: 5~6개 2월 샘플 — 통계력 낮음. 구조적 근거+최근 일관성이 방어선. 교육용, 투자자문 아님.")


if __name__ == "__main__":
    main()
