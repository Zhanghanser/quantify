# -*- coding: utf-8 -*-
"""
walk-forward(滚动样本外)工具。
本策略参数固定不优化,所以这里做的是【滚动非重叠区块的样本外稳定性】:
把每个数据集切成连续区块,逐块算净收益,看正区块占比 + 区块收益的"稳定性夏普"。
口径:gate现货·成本0.0015·满仓·区块长度可调。
"""
import sys, math
if sys.platform == "win32":
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
import numpy as np
from src.data import get_data
from src.strategies import get_strategy
from src.backtest import run_backtest
from src.risk import RiskConfig, NO_RISK

SYMBOLS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT"]
COST = 0.0015
BLOCK = 150          # 每个样本外区块的K线数
BASE_RISK = RiskConfig(stop_loss=0.10, take_profit=0.0, position_size=1.0, max_drawdown_stop=0.0)

def block_returns(stratname, s, tf, risk, **params):
    df = get_data("crypto", s, tf, 1000)
    sig = get_strategy(stratname, **params).generate(df)
    res = run_backtest(sig, timeframe=tf, risk=risk, initial_capital=10000, cost=COST)
    eq = res["df"]["equity"].values
    n = len(eq)
    rets = []
    start = 200          # 跳过指标预热段
    for b in range(start, n - BLOCK, BLOCK):
        seg = eq[b:b + BLOCK + 1]
        if seg[0] > 0:
            rets.append(seg[-1] / seg[0] - 1)
    return rets

def summarize(name, stratname, risk, tfs, **params):
    allblk = []
    for s in SYMBOLS:
        for tf in tfs:
            allblk += block_returns(stratname, s, tf, risk, **params)
    arr = np.array(allblk)
    pos = float((arr > 0).mean()) if len(arr) else 0.0
    sharpe = float(arr.mean() / arr.std()) if len(arr) > 1 and arr.std() > 0 else 0.0
    print(f"  {name:<22} 区块数={len(arr):>3}  正区块占比={pos*100:>4.0f}%  "
          f"区块均收益={arr.mean()*100:+.2f}%  稳定性夏普={sharpe:+.2f}")
    return sharpe, pos

print(f"walk-forward 滚动样本外(区块={BLOCK}根,非重叠,参数固定不优化)")
for tfs, label in [(["4h"], "4h"), (["1d"], "1d"), (["4h", "1d"], "4h+1d合计")]:
    print(f"\n=== 周期 {label} ===")
    summarize("基准 区间过滤趋势", "regime_trend", BASE_RISK, tfs)
    summarize("改造 波动率门控趋势", "vol_trend", NO_RISK, tfs)
