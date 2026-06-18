# -*- coding: utf-8 -*-
"""
多策略对比(入口2,阶段2)。

在同一份数据上,把所有策略各跑一遍回测,并排比较谁更好。
这是量化研究的日常:不是找"唯一神策略",而是理解每个策略适合什么行情。

运行:python run_compare.py
"""

import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import config
from src.data import get_data
from src.strategies import STRATEGIES, get_strategy
from src.backtest import run_backtest
from src.risk import RiskConfig


def main():
    print("=" * 64)
    print(f"  多策略对比  |  市场:{config.MARKET}  标的:{config.SYMBOL}  周期:{config.TIMEFRAME}")
    print("=" * 64)

    # 取一次数据,所有策略共用(公平对比)
    df = get_data(market=config.MARKET, symbol=config.SYMBOL,
                  timeframe=config.TIMEFRAME, limit=config.LIMIT)

    # 统一的风控(让对比只反映策略差异)
    risk = RiskConfig(stop_loss=0.05, take_profit=0.0, position_size=1.0)

    rows = []
    for name in STRATEGIES:
        strategy = get_strategy(name)
        signaled = strategy.generate(df)
        result = run_backtest(signaled, timeframe=config.TIMEFRAME, risk=risk)
        m = result["metrics"]
        rows.append((strategy.display_name, m))

    # 加一行"买入持有"基准
    buyhold_ret = rows[0][1]["买入持有收益率"]

    # 打印对比表
    print(f"\n{'策略':<14}{'总收益':>10}{'年化':>10}{'夏普':>8}{'最大回撤':>10}{'交易数':>8}{'胜率':>8}")
    print("-" * 64)
    for display_name, m in rows:
        print(f"{display_name:<14}{m['总收益率']:>9.2%}{m['年化收益率']:>10.2%}"
              f"{m['夏普比率']:>8.2f}{m['最大回撤']:>10.2%}"
              f"{m['交易次数']:>8}{m['胜率']:>8.1%}")
    print("-" * 64)
    print(f"{'买入持有(基准)':<14}{buyhold_ret:>9.2%}")
    print("=" * 64)
    print("\n💡 看点:")
    print("  · 哪个策略夏普最高(性价比最好)?哪个回撤最小(最稳)?")
    print("  · 有没有策略跑赢『买入持有』?跑不赢说明这段行情不适合它。")
    print("  · 趋势策略(双均线/突破)和逆势策略(RSI)在同一行情下表现往往相反。")


if __name__ == "__main__":
    main()
