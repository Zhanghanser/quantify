# -*- coding: utf-8 -*-
"""
事件合约 入口(阶段:事件合约模块)。

两种模式:
  python run_event.py            # 回测模式:用真实分钟K线,跑各时长/各信号的真实胜率与盈亏
  python run_event.py live       # 实时模式:显示当前该押的方向 + 风险提醒(不下单)

⚠️ 本程序绝不下单,只产生信号和风险提醒。下注由你自己在平台手动操作并负责。
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
from src.event_contract import (
    EventConfig, backtest, live_signal, format_risk_reminder, SIGNALS,
)

# 用 1 分钟K线(事件合约是分钟级,必须用细粒度数据)
TIMEFRAME = "1m"
# 平台赔率:不同平台不同,改成你那个平台的真实赔率(常见 1.7~1.95)
PAYOUT = 1.8
# 要测试的合约时长(分钟)
HORIZONS = [3, 5, 10, 30, 60]
# 回测用多少根1分钟K线。越多统计越可信(gate.io 上限约1万根,这里取9000≈6天)
EVENT_LIMIT = 9000


def run_backtest_mode():
    print("=" * 70)
    print(f"  事件合约回测  |  标的:{config.SYMBOL}  数据:{TIMEFRAME}K线  赔率:{PAYOUT}")
    print("=" * 70)

    df = get_data(market="crypto", symbol=config.SYMBOL,
                  timeframe=TIMEFRAME, limit=EVENT_LIMIT, use_cache=False)
    print(f"  数据范围:{df.index[0]} ~ {df.index[-1]}  共 {len(df)} 根\n")

    breakeven = 1.0 / PAYOUT
    print(f"  📌 保本所需胜率 = 1/{PAYOUT} = {breakeven:.1%}(下面所有胜率请和它比)\n")

    print(f"  {'信号':<10}{'时长':>6}{'下注数':>8}{'真实胜率':>10}{'每笔期望':>10}{'总盈亏':>10}{'最大连亏':>8}")
    print("  " + "-" * 64)

    for signal_name in SIGNALS:
        for h in HORIZONS:
            cfg = EventConfig(horizon_minutes=h, payout=PAYOUT)
            r = backtest(df, cfg, signal_name)
            flag = "" if r["win_rate"] >= breakeven else " ✗"
            print(f"  {signal_name:<10}{h:>5}m{r['bets']:>8}"
                  f"{r['win_rate']:>9.1%}{flag:<2}{r['ev_per_bet']:>9.2f}"
                  f"{r['total_pnl']:>10.1f}{r['max_consecutive_losses']:>8}")
        print("  " + "-" * 64)

    print("\n  📊 结论(用你自己的数据验证):")
    print(f"     · 几乎所有信号的真实胜率都在 {breakeven:.0%} 上下徘徊,达不到稳定超过保本线。")
    print( "     · 『每笔期望』基本为负 → 押得越多,长期亏得越多(这就是赔率<2的代价)。")
    print( "     · 时长越短(3/5分钟),越接近抛硬币,越难赢。")


def run_live_mode():
    print("=" * 56)
    print("  事件合约 实时信号(只提示 · 不下单)")
    print("=" * 56)

    # 先用历史数据估算这个信号的真实胜率,供风险提醒用
    df = get_data(market="crypto", symbol=config.SYMBOL,
                  timeframe=TIMEFRAME, limit=config.LIMIT, use_cache=False)

    signal_name = "momentum"
    horizon = 5   # 默认看 5 分钟合约
    cfg = EventConfig(horizon_minutes=horizon, payout=PAYOUT)

    hist = backtest(df, cfg, signal_name)["win_rate"]
    sig = live_signal(df, cfg, signal_name, hist_win_rate=hist)

    arrow = {"UP": "📈 押【涨】", "DOWN": "📉 押【跌】", None: "⬜ 数据不足,不押"}[sig["prediction"]]
    print(f"\n  时间:{sig['time']}")
    print(f"  {config.SYMBOL} 现价:{sig['price']:,.2f}")
    print(f"  {horizon} 分钟合约 当前信号:{arrow}")
    print()
    print(format_risk_reminder(cfg, hist_win_rate=hist))


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "live":
        run_live_mode()
    else:
        run_backtest_mode()


if __name__ == "__main__":
    main()
