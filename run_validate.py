# -*- coding: utf-8 -*-
"""
多标的诚实验证(入口5)。

一个策略在单个币上回测好看,很可能是运气。真正的检验是:
  用【固定的、事先定好的参数】(不调参、不优化 → 杜绝过拟合),
  在【多个不同标的】上一起跑,看它是不是普遍有效,还是只在某个币上走运。

同时演示"分散投资"的价值:把多个币等权组合,
组合的最大回撤通常比单个币小 —— 这是风险管理里少有的"免费午餐"。

运行:python run_validate.py
"""

import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import numpy as np
import pandas as pd

from src.data import get_data
from src.strategies import get_strategy
from src.backtest import run_backtest, PERIODS_PER_YEAR
from src.risk import RiskConfig
import config

# 验证用的多个标的(gate.io 上都有)
ASSETS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT"]
TIMEFRAME = "1d"        # 日线,数据跨度长,更能说明问题
LIMIT = 1000            # 约 2.7 年

# 固定参数:事先定好,绝不根据结果回头调(这是杜绝过拟合的关键纪律)
STRATEGY = "trend_filter"
PARAMS = {"fast": 20, "slow": 50, "trend": 100}

# 保守风控:风险优先
RISK = RiskConfig(stop_loss=0.10, take_profit=0.0,
                  position_size=0.5, max_drawdown_stop=0.25)


def max_drawdown(equity: pd.Series) -> float:
    return (equity / equity.cummax() - 1).min()


def main():
    print("=" * 72)
    print(f"  多标的诚实验证  |  策略:{STRATEGY}{PARAMS}  周期:{TIMEFRAME}")
    print(f"  风控:{RISK.describe()}")
    print(f"  纪律:参数固定不优化,5个币用同一套参数 → 杜绝过拟合")
    print("=" * 72)

    strat = get_strategy(STRATEGY, **PARAMS)
    rows = []
    ret_series = {}   # 每个币的策略日收益,用于组合

    for asset in ASSETS:
        try:
            df = get_data(market="crypto", symbol=asset,
                          timeframe=TIMEFRAME, limit=LIMIT)
        except Exception as e:
            print(f"  {asset} 跳过(取数失败:{e})")
            continue

        result = run_backtest(strat.generate(df), timeframe=TIMEFRAME, risk=RISK)
        m = result["metrics"]
        rows.append((asset, m))
        ret_series[asset] = result["df"]["equity"].pct_change()

    if not rows:
        print("没有可用数据,退出。")
        return

    # ===== 各标的结果 =====
    print(f"\n  {'标的':<10}{'策略收益':>10}{'买入持有':>10}{'夏普':>8}{'最大回撤':>10}{'交易数':>8}{'胜率':>8}")
    print("  " + "-" * 64)
    for asset, m in rows:
        print(f"  {asset:<10}{m['总收益率']:>9.1%}{m['买入持有收益率']:>10.1%}"
              f"{m['夏普比率']:>8.2f}{m['最大回撤']:>10.1%}"
              f"{m['交易次数']:>8}{m['胜率']:>8.0%}")
    print("  " + "-" * 64)

    # ===== 汇总平均 =====
    avg_ret = np.mean([m["总收益率"] for _, m in rows])
    avg_bh = np.mean([m["买入持有收益率"] for _, m in rows])
    avg_sharpe = np.mean([m["夏普比率"] for _, m in rows])
    avg_dd = np.mean([m["最大回撤"] for _, m in rows])
    print(f"  {'平均':<10}{avg_ret:>9.1%}{avg_bh:>10.1%}{avg_sharpe:>8.2f}{avg_dd:>10.1%}")

    # ===== 等权组合(分散) =====
    port = pd.DataFrame(ret_series).mean(axis=1)   # 每天对可用标的等权平均
    port_equity = (1 + port.fillna(0)).cumprod() * config.INITIAL_CAPITAL
    port_total = port_equity.iloc[-1] / config.INITIAL_CAPITAL - 1
    port_dd = max_drawdown(port_equity)
    ppy = PERIODS_PER_YEAR.get(TIMEFRAME, 365)
    port_sharpe = port.mean() / port.std() * np.sqrt(ppy) if port.std() > 0 else 0.0

    print("  " + "=" * 64)
    print(f"  {'等权组合':<10}{port_total:>9.1%}{'':>10}{port_sharpe:>8.2f}{port_dd:>10.1%}")
    print("  " + "=" * 64)

    # ===== 解读 =====
    print("\n  📊 怎么看这张表:")
    print(f"     · 策略在 5 个币上是否【普遍】有正收益/正夏普?只有1-2个好 = 可能走运。")
    print(f"     · 组合最大回撤 {port_dd:.1%}  vs  单币平均回撤 {avg_dd:.1%}"
          f"  → {'组合更稳(分散有效)' if port_dd > avg_dd else '本次组合未明显降回撤'}")
    print(f"     · 趋势过滤策略通常在牛市跟得上、熊市靠空仓少亏,但震荡市会被反复止损。")
    print(f"     · 记住:这仍不是稳赚。固定参数+多标的+保守风控,是为了【活得久】而非暴富。")


if __name__ == "__main__":
    main()
