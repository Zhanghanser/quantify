# -*- coding: utf-8 -*-
"""
实时信号监控(入口4,阶段3)—— 只读,绝不下单。

它会定时拉取最新行情,用你选的策略算出"现在该做多还是空仓",并打印出来。
⚠️ 重要:本脚本【只看不动手】,不会连接你的账户,不会下任何真实订单,
   它的作用是让你"盯着"策略在实盘行情里会发什么信号,先观察、建立信任。

为什么不直接自动下单?
  自动交易必须先在【交易所测试网(testnet)】用假钱跑很久、确认无 bug,
  再用极小真金白银试水。跳过这步直接实盘 = 把钱送人。下单接入方法见文末说明。

运行:
  python run_live.py            # 持续监控,每隔一段时间刷新(Ctrl+C 停止)
  python run_live.py once       # 只看一次当前信号就退出(用于测试)
"""

import sys
import time

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import config
from src.data import get_data
from src.strategies import get_strategy

# 每隔多少秒刷新一次(短线别太频繁,免得被交易所限流;1小时线可设 60~300 秒)
POLL_SECONDS = 60


def check_once(strategy):
    """拉一次最新数据,算出当前信号并打印。返回最新信号(1/0/-1)。"""
    # use_cache=False 强制拿最新行情(实盘必须用最新数据)
    df = get_data(market=config.MARKET, symbol=config.SYMBOL,
                  timeframe=config.TIMEFRAME, limit=config.LIMIT, use_cache=False)
    signaled = strategy.generate(df)

    last = signaled.iloc[-1]
    prev = signaled.iloc[-2]
    signal_now = int(last["position"])
    signal_prev = int(prev["position"])

    state = {1: "📈 做多/持有", 0: "⬜ 空仓观望", -1: "📉 做空"}[signal_now]
    price = last["close"]
    t = signaled.index[-1]

    print(f"\n[{t}]  {config.SYMBOL}  最新价 {price:,.2f}")
    print(f"    当前信号:{state}")

    # 信号刚发生变化 → 这就是"该操作"的时刻,重点提示
    if signal_now != signal_prev:
        action = {1: "🔔 出现【买入】信号!", 0: "🔔 出现【卖出/平仓】信号!",
                  -1: "🔔 出现【做空】信号!"}[signal_now]
        print(f"    {action}（上一根还是 {signal_prev}，现在变成 {signal_now}）")
        print("    ⚠️ 提醒:这只是策略信号,是否真下单由你自己手动决定。")
    else:
        print("    (信号无变化,继续持有当前状态)")

    return signal_now


def main():
    once = len(sys.argv) > 1 and sys.argv[1] == "once"

    print("=" * 56)
    print("  实时信号监控(只读 · 不下单)")
    print(f"  市场:{config.MARKET}  标的:{config.SYMBOL}  周期:{config.TIMEFRAME}  策略:{config.STRATEGY}")
    print("=" * 56)
    print("  ⚠️ 本程序不会下任何真实订单,只显示策略信号供你参考。")

    strategy = get_strategy(config.STRATEGY)

    if once:
        check_once(strategy)
        print("\n(单次模式结束)")
        return

    print(f"  每 {POLL_SECONDS} 秒刷新一次,按 Ctrl+C 停止。\n")
    try:
        while True:
            check_once(strategy)
            time.sleep(POLL_SECONDS)
    except KeyboardInterrupt:
        print("\n👋 已停止监控。")


if __name__ == "__main__":
    main()


# =====================================================================
# 【进阶】之后想接"自动下单"时,该怎么做(现在不要做!):
#
# 1) 先去交易所开通 API key,并务必用【测试网 / testnet】,例如币安测试网。
# 2) ccxt 支持下单,大致长这样(伪代码,仅示意,别在真账户跑):
#
#       import ccxt
#       ex = ccxt.binance({
#           "apiKey": "你的KEY", "secret": "你的SECRET",
#           "options": {"defaultType": "spot"},
#       })
#       ex.set_sandbox_mode(True)   # ← 关键!打开测试网,用假钱
#       if signal_now == 1:
#           ex.create_market_buy_order("BTC/USDT", amount)
#       elif signal_now == 0:
#           ex.create_market_sell_order("BTC/USDT", amount)
#
# 3) 自动交易上线前必须有的东西:下单失败重试、网络断线处理、
#    持仓与资金对账、日志、异常告警、风控强制止损。缺一不可。
# 4) 顺序铁律:测试网长期验证 → 极小真金白银 → 慢慢加仓。
# =====================================================================
