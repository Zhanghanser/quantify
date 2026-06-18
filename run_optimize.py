# -*- coding: utf-8 -*-
"""
参数优化 + 防过拟合演示(入口3,阶段2)。

这是量化最大的坑:过拟合(overfitting)。
你可以把参数反复调到"历史回测特别赚钱",但那往往只是恰好拟合了历史的噪音,
换一段没见过的数据(=未来/实盘)就原形毕露。

本脚本用最经典的方法揭示这个陷阱:
  1) 网格搜索:在全部历史上试很多组参数,挑出"最赚钱"的一组(in-sample 最优)。
  2) 样本内/样本外检验:把数据切成"训练段"和"测试段",
     在训练段挑最优参数,再拿到从没见过的测试段上跑。
     如果测试段表现大幅变差 → 就是过拟合,这组参数不可信。

运行:python run_optimize.py
"""

import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import itertools
import config
from src.data import get_data
from src.strategies import get_strategy
from src.backtest import run_backtest
from src.risk import RiskConfig

# 优化目标:用夏普比率衡量"好坏"(兼顾收益和风险,比单看收益靠谱)
RISK = RiskConfig(stop_loss=0.05, position_size=1.0)

# 双均线的参数搜索网格
FAST_GRID = [5, 8, 10, 12, 15, 20]
SLOW_GRID = [20, 30, 40, 50, 60]


def evaluate(df, fast, slow):
    """用给定参数跑一次回测,返回夏普和总收益。"""
    strat = get_strategy("dual_ma", fast=fast, slow=slow)
    signaled = strat.generate(df)
    m = run_backtest(signaled, timeframe=config.TIMEFRAME, risk=RISK)["metrics"]
    return m["夏普比率"], m["总收益率"]


def grid_search(df):
    """遍历所有参数组合,返回按夏普排序的结果列表。"""
    results = []
    for fast, slow in itertools.product(FAST_GRID, SLOW_GRID):
        if fast >= slow:
            continue   # 快线必须比慢线短
        sharpe, ret = evaluate(df, fast, slow)
        results.append({"fast": fast, "slow": slow, "sharpe": sharpe, "ret": ret})
    results.sort(key=lambda r: r["sharpe"], reverse=True)
    return results


def main():
    print("=" * 60)
    print(f"  参数优化 + 防过拟合演示  |  {config.SYMBOL} {config.TIMEFRAME}")
    print("=" * 60)

    df = get_data(market=config.MARKET, symbol=config.SYMBOL,
                  timeframe=config.TIMEFRAME, limit=config.LIMIT)

    # ===== 第一部分:在全部历史上找"最优参数" =====
    print("\n【1】在全部历史数据上网格搜索最优参数 ...")
    full = grid_search(df)
    print("    夏普排名前 5 的参数组合:")
    print(f"    {'快线':>4}{'慢线':>6}{'夏普':>8}{'总收益':>10}")
    for r in full[:5]:
        print(f"    {r['fast']:>4}{r['slow']:>6}{r['sharpe']:>8.2f}{r['ret']:>10.2%}")
    best = full[0]
    print(f"\n    👉 全样本最优:快线={best['fast']} 慢线={best['slow']},"
          f"夏普 {best['sharpe']:.2f},收益 {best['ret']:.2%}")
    print("    ⚠️ 但这个『最优』是在全部历史上挑的——它已经偷看了所有答案!")

    # ===== 第二部分:样本内/样本外检验,揭示过拟合 =====
    print("\n【2】样本内(训练) / 样本外(测试)检验 ...")
    split = int(len(df) * 0.7)
    train, test = df.iloc[:split], df.iloc[split:]
    print(f"    训练段:前 70%({len(train)} 根)   测试段:后 30%({len(test)} 根)")

    # 只在训练段挑最优参数(模拟"我们只能看到过去")
    train_results = grid_search(train)
    bp = train_results[0]
    print(f"\n    在【训练段】挑出的最优参数:快线={bp['fast']} 慢线={bp['slow']}")

    # 用这组参数,分别看训练段 和 从没见过的测试段 表现
    in_sharpe, in_ret = evaluate(train, bp["fast"], bp["slow"])
    out_sharpe, out_ret = evaluate(test, bp["fast"], bp["slow"])

    print("\n    用这组参数的表现对比:")
    print(f"      训练段(样本内,见过)  : 夏普 {in_sharpe:>6.2f}   收益 {in_ret:>8.2%}")
    print(f"      测试段(样本外,没见过): 夏普 {out_sharpe:>6.2f}   收益 {out_ret:>8.2%}")

    print("\n" + "=" * 60)
    print("  📌 结论")
    print("=" * 60)
    if out_sharpe < in_sharpe:
        print("  样本外表现明显比样本内差 —— 这就是过拟合的典型信号。")
    else:
        print("  这次样本外没有明显变差,但样本量小,不能就此下结论。")
    print("  量化铁律:")
    print("    · 永远用『没见过的数据』检验策略,别只看全样本回测。")
    print("    · 参数越多、调得越细,越容易过拟合。简单稳健 > 复杂好看。")
    print("    · 进阶做法:滚动的 walk-forward(多段训练-测试)、样本外验证集。")


if __name__ == "__main__":
    main()
