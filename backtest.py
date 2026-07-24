"""
Backtest the carbon trend/momentum signal on a carbon-allowance ETF (paper trading).

No broker, no money: this simulates the newsletter's own signal on historical data
to show whether it adds value versus simply buying and holding. This is the Phase 3
"paper trading" proof — run the signal on paper and track P&L before risking capital.

Strategy (long/flat, no leverage, no lookahead):
    LONG when price > 50-day MA AND 21-day momentum > 0, else FLAT.
    Signal is computed on data up to day t and applied to day t+1's return.

Usage:
    pip install -r requirements.txt
    python backtest.py            # default KRBN (global/EU carbon)
    python backtest.py KEUA       # any carbon ETF ticker

Outputs:
    out/backtest_<TICKER>.png     equity curve (strategy vs buy&hold)
    prints performance stats
"""

from __future__ import annotations

import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yfinance as yf

OUT = "out"


def load(ticker: str, period: str = "5y") -> pd.Series:
    raw = yf.download(ticker, period=period, interval="1d", auto_adjust=True, progress=False)
    s = raw["Close"]
    if isinstance(s, pd.DataFrame):
        s = s.iloc[:, 0]
    return s.dropna()


def signal(px: pd.Series) -> pd.Series:
    """1 = long, 0 = flat. No lookahead: decision from past data, acted next day."""
    ma50 = px.rolling(50).mean()
    mom = px / px.shift(21) - 1
    sig = ((px > ma50) & (mom > 0)).astype(int)
    return sig.shift(1).fillna(0)


def stats(eq: pd.Series, daily: pd.Series) -> dict:
    years = max(len(eq) / 252, 1e-9)
    cagr = eq.iloc[-1] ** (1 / years) - 1
    sharpe = (daily.mean() / daily.std() * np.sqrt(252)) if daily.std() > 0 else 0.0
    maxdd = (eq / eq.cummax() - 1).min()
    # time in market
    return {
        "total_return_%": round((eq.iloc[-1] - 1) * 100, 1),
        "CAGR_%": round(cagr * 100, 1),
        "Sharpe": round(float(sharpe), 2),
        "max_drawdown_%": round(float(maxdd) * 100, 1),
    }


def main() -> None:
    ticker = sys.argv[1] if len(sys.argv) > 1 else "KRBN"
    os.makedirs(OUT, exist_ok=True)
    px = load(ticker)
    if len(px) < 100:
        raise SystemExit(f"Not enough data for {ticker}.")

    ret = px.pct_change().fillna(0)
    sig = signal(px)
    strat_ret = sig * ret

    eq_strat = (1 + strat_ret).cumprod()
    eq_bh = (1 + ret).cumprod()

    s_strat = stats(eq_strat, strat_ret[sig == 1])  # risk stats while in market
    s_bh = stats(eq_bh, ret)
    exposure = round(float(sig.mean()) * 100, 1)

    print(f"== Backtest: {ticker}  ({px.index[0].date()} → {px.index[-1].date()}) ==")
    print(f"{'':16}{'Strategy':>12}{'Buy&Hold':>12}")
    for k in ["total_return_%", "CAGR_%", "Sharpe", "max_drawdown_%"]:
        print(f"{k:16}{s_strat[k]:>12}{s_bh[k]:>12}")
    print(f"{'time_in_market_%':16}{exposure:>12}{100.0:>12}")

    plt.figure(figsize=(10, 5))
    plt.plot(eq_strat.index, eq_strat, label=f"Signal (long/flat)  DD {s_strat['max_drawdown_%']}%", lw=1.7)
    plt.plot(eq_bh.index, eq_bh, label=f"Buy & Hold  DD {s_bh['max_drawdown_%']}%", lw=1.3, alpha=0.8)
    plt.title(f"{ticker} — carbon trend/momentum signal vs buy & hold (5Y, paper)")
    plt.ylabel("Growth of $1")
    plt.legend()
    plt.grid(alpha=0.3)
    plt.tight_layout()
    path = os.path.join(OUT, f"backtest_{ticker}.png")
    plt.savefig(path, dpi=130)
    plt.close()
    print(f"\nWrote {path}")
    print("\nNote: paper backtest, no costs/slippage modeled. Educational, not advice.")


if __name__ == "__main__":
    main()
