# -*- coding: utf-8 -*-
"""
单策略快速演示(入口1)。

跑通:取数据 → 跑策略 → 回测(可带风控)→ 报告 + 资金曲线图。
改 config.py 里的 MARKET / SYMBOL / STRATEGY 就能换市场、换标的、换策略。

运行:python run_demo.py
"""

import sys
import os

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import config
from src.data import get_data
from src.strategies import get_strategy
from src.backtest import run_backtest, print_report, plot_result
from src.risk import RiskConfig


def main():
    print("=" * 44)
    print("  量化回测演示")
    print(f"  市场: {config.MARKET}   标的: {config.SYMBOL}   周期: {config.TIMEFRAME}")
    print(f"  策略: {config.STRATEGY}")
    print("=" * 44 + "\n")

    # 1) 取数据(任意市场,统一接口)
    df = get_data(market=config.MARKET, symbol=config.SYMBOL,
                  timeframe=config.TIMEFRAME, limit=config.LIMIT)

    # 2) 跑策略,生成信号
    strategy = get_strategy(config.STRATEGY)
    signaled = strategy.generate(df)

    # 3) 回测。这里演示带一个简单风控(5%止损),想关掉用 RiskConfig() 默认或 NO_RISK
    risk = RiskConfig(stop_loss=0.05, take_profit=0.0, position_size=1.0)
    result = run_backtest(signaled, timeframe=config.TIMEFRAME, risk=risk)

    # 4) 报告 + 画图
    print_report(result, title=f"{strategy.display_name} 回测报告")
    chart = os.path.join(config.BASE_DIR, "equity_curve.png")
    plot_result(result, save_path=chart, title=f"({strategy.display_name})")

    print("\n✅ 完成!打开 equity_curve.png 看资金曲线。")
    print("💡 试试:改 config.py 的 STRATEGY 换策略,或 MARKET 换市场,再跑一次。")


if __name__ == "__main__":
    main()
