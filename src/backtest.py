# -*- coding: utf-8 -*-
"""
回测引擎(升级版,阶段4)。

相比第一版,这一版升级为"逐根K线模拟"(事件驱动),支持:
  1) 做多 / 做空 / 空仓(position = 1 / -1 / 0)
  2) 止损 / 止盈(在K线内用最高最低价判断是否触发)
  3) 仓位管理(每笔只投入部分资金)
  4) 总回撤熔断(亏太多就停手)

关键的"防未来函数"做法不变:第 t 根K线用的是第 t-1 根收盘时算出的信号
(signals[t-1]),即"今天收盘决策,下一根才执行"。
"""

import numpy as np
import pandas as pd

import config
from src.risk import RiskConfig, NO_RISK


# 不同K线周期一年约有多少根,用于年化
PERIODS_PER_YEAR = {
    "1m": 525600, "3m": 175200, "5m": 105120, "15m": 35040, "30m": 17520,
    "1h": 8760, "2h": 4380, "4h": 2190, "8h": 1095,
    "1d": 365, "1w": 52, "1M": 12,
}


def run_backtest(df: pd.DataFrame, timeframe=None, risk: RiskConfig = None,
                 initial_capital: float = None, cost: float = None) -> dict:
    """
    输入:带 'position'(目标信号 -1/0/1)和 OHLC 列的表。
    risk:风控配置;不传则默认无风控(NO_RISK)。
    initial_capital:本金;不传则用 config.INITIAL_CAPITAL(显式传参 → 引擎无全局副作用,
        多请求并发时不会相互覆盖)。
    cost:单边成本(手续费+滑点);不传则用 config 里的值。显式传参方便做"手续费敏感度"。
    输出:字典,含资金曲线表、绩效指标、逐笔交易记录。
    """
    timeframe = timeframe or config.TIMEFRAME
    risk = risk if risk is not None else NO_RISK
    cap = float(initial_capital) if initial_capital is not None else config.INITIAL_CAPITAL
    df = df.copy()

    opens = df["open"].values
    highs = df["high"].values
    lows = df["low"].values
    closes = df["close"].values
    signals = df["position"].values
    n = len(df)

    times = df.index           # 时间索引,用于给每笔交易打开/平仓时间戳
    cost = cost if cost is not None else config.FEE_RATE + config.SLIPPAGE   # 单边成本(手续费+滑点)
    size = risk.position_size                  # 每笔投入资金比例

    equity = cap
    peak = equity
    trading_halted = False     # 回撤熔断后变 True,停止开新仓
    pos = 0                    # 当前持仓方向 -1/0/1
    entry_price = None         # 开仓价(用于算止损止盈线)
    entry_time = None          # 开仓时间(用于在图上标注买卖点配对)

    equity_curve = [equity]    # 每根K线收盘后的资金
    exec_pos = [0]             # 每根K线实际持仓(用于画买卖点)
    trades = []                # 每笔已平仓交易的记录

    for t in range(1, n):
        o, h, l, c = opens[t], highs[t], lows[t], closes[t]
        pc = closes[t - 1]
        target = 0 if trading_halted else signals[t - 1]

        exit_price = None
        exit_reason = None

        # --- 1) 先检查本根K线内是否触发止损/止盈 ---
        if pos != 0 and (risk.stop_loss > 0 or risk.take_profit > 0):
            if pos == 1:   # 多头
                sl = entry_price * (1 - risk.stop_loss) if risk.stop_loss > 0 else None
                tp = entry_price * (1 + risk.take_profit) if risk.take_profit > 0 else None
                if sl is not None and l <= sl:
                    exit_price, exit_reason = sl, "止损"
                elif tp is not None and h >= tp:
                    exit_price, exit_reason = tp, "止盈"
            else:          # 空头
                sl = entry_price * (1 + risk.stop_loss) if risk.stop_loss > 0 else None
                tp = entry_price * (1 - risk.take_profit) if risk.take_profit > 0 else None
                if sl is not None and h >= sl:
                    exit_price, exit_reason = sl, "止损"
                elif tp is not None and l <= tp:
                    exit_price, exit_reason = tp, "止盈"

        if exit_price is not None:
            # 触发止损/止盈:从上一根收盘价 mark 到触发价,然后平仓
            equity *= (1 + pos * (exit_price / pc - 1) * size)
            equity *= (1 - cost)
            trades.append({
                "dir": pos,
                "entry_time": entry_time, "exit_time": times[t],
                "entry_price": entry_price, "exit_price": exit_price,
                "ret": pos * (exit_price / entry_price - 1) * size - 2 * cost * size,
                "reason": exit_reason,
            })
            pos, entry_price, entry_time = 0, None, None
            # 当根触发后不再立刻开新仓,等下一个信号
        else:
            # --- 2) 正常持仓:按收盘价 mark to market ---
            if pos != 0:
                equity *= (1 + pos * (c / pc - 1) * size)

            # --- 3) 按目标信号调整仓位(在本根收盘价成交) ---
            if target != pos:
                if pos != 0:   # 先平掉旧仓
                    equity *= (1 - cost)
                    trades.append({
                        "dir": pos,
                        "entry_time": entry_time, "exit_time": times[t],
                        "entry_price": entry_price, "exit_price": c,
                        "ret": pos * (c / entry_price - 1) * size - 2 * cost * size,
                        "reason": "信号",
                    })
                    entry_price, entry_time = None, None
                if target != 0:  # 再开新仓
                    equity *= (1 - cost)
                    entry_price = c
                    entry_time = times[t]
                pos = target

        # --- 4) 更新资金峰值 & 回撤熔断 ---
        if equity > peak:
            peak = equity
        if (risk.max_drawdown_stop > 0 and not trading_halted
                and equity <= peak * (1 - risk.max_drawdown_stop)):
            trading_halted = True
            if pos != 0:   # 熔断时强制平仓
                equity *= (1 - cost)
                trades.append({
                    "dir": pos,
                    "entry_time": entry_time, "exit_time": times[t],
                    "entry_price": entry_price, "exit_price": c,
                    "ret": pos * (c / entry_price - 1) * size - 2 * cost * size,
                    "reason": "回撤熔断",
                })
                pos, entry_price, entry_time = 0, None, None

        equity_curve.append(equity)
        exec_pos.append(pos)

    df["equity"] = equity_curve
    df["exec_pos"] = exec_pos
    # 基准:买入持有
    df["buy_hold"] = cap * closes / closes[0]

    metrics = _calc_metrics(df, trades, timeframe, cap)
    return {"df": df, "metrics": metrics, "trades": trades, "risk": risk}


def _calc_metrics(df: pd.DataFrame, trades: list, timeframe: str,
                  initial_capital: float = None) -> dict:
    """根据资金曲线和交易记录计算绩效指标。"""
    cap = float(initial_capital) if initial_capital is not None else config.INITIAL_CAPITAL
    ppy = PERIODS_PER_YEAR.get(timeframe, 252)
    equity = df["equity"]
    rets = equity.pct_change().dropna()

    total_return = equity.iloc[-1] / cap - 1
    buyhold_return = df["buy_hold"].iloc[-1] / cap - 1

    n_periods = len(rets)
    # 年化:把整段盈亏复利外推到一年。短样本会被极度放大,且 total_return<=-1(本金亏光)
    # 时底数为非正,幂运算会得到 nan/复数 → 必须就地兜底,否则后续 JSON 序列化会产出非法值。
    if n_periods <= 0 or total_return <= -1:
        annual_return = -1.0
    else:
        try:
            annual_return = (1.0 + total_return) ** (ppy / n_periods) - 1.0
        except (OverflowError, ValueError):
            annual_return = float("inf") if total_return > 0 else -1.0
        if not np.isfinite(annual_return):
            annual_return = -1.0 if total_return <= 0 else annual_return

    sharpe = rets.mean() / rets.std() * np.sqrt(ppy) if rets.std() > 0 else 0.0

    cummax = equity.cummax()
    max_drawdown = (equity / cummax - 1).min()

    n_trades = len(trades)
    wins = sum(1 for t in trades if t["ret"] > 0)
    win_rate = wins / n_trades if n_trades > 0 else 0.0

    # 测试区间元信息:让前端能标注"这段只有 X 天",并在样本太短时给年化降权
    start, end = df.index[0], df.index[-1]
    days = max(1, int((end - start).total_seconds() // 86400))
    # 年化要有统计意义,至少需要约一个季度的数据;短于此则标记为"不可靠"
    is_annual_reliable = days >= 90

    return {
        "总收益率": total_return,
        "买入持有收益率": buyhold_return,
        "年化收益率": annual_return,
        "夏普比率": sharpe,
        "最大回撤": max_drawdown,
        "交易次数": n_trades,
        "胜率": win_rate,
        "最终资金": equity.iloc[-1],
        # ↓ 以下为元信息(前端用,不作为指标卡片展示)
        "盈利笔数": wins,
        "亏损笔数": n_trades - wins,
        "测试天数": days,
        "周期根数": n_periods,
        "测试起始": str(start),
        "测试结束": str(end),
        "年化可靠": bool(is_annual_reliable),
    }


def print_report(result: dict, title: str = "回测绩效报告"):
    """打印绩效报告。"""
    m = result["metrics"]
    print("\n" + "=" * 44)
    print(f"        {title}")
    if "risk" in result:
        print(f"  风控: {result['risk'].describe()}")
    print("=" * 44)
    print(f"  总收益率        : {m['总收益率']:+.2%}")
    print(f"  (对比)买入持有  : {m['买入持有收益率']:+.2%}")
    print(f"  年化收益率      : {m['年化收益率']:+.2%}")
    print(f"  夏普比率        : {m['夏普比率']:.2f}   (>1 较好, >2 优秀)")
    print(f"  最大回撤        : {m['最大回撤']:.2%}   (越接近0越好)")
    print(f"  交易次数        : {m['交易次数']} 笔")
    print(f"  胜率            : {m['胜率']:.2%}")
    print(f"  最终资金        : {m['最终资金']:,.2f}  (本金 {config.INITIAL_CAPITAL:,})")
    print("=" * 44)


def plot_result(result: dict, save_path: str = None, title: str = ""):
    """画资金曲线 + 买卖点。"""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False

    df = result["df"]
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8),
                                   gridspec_kw={"height_ratios": [2, 1]})

    ax1.plot(df.index, df["equity"], label="策略 Strategy", linewidth=1.5)
    ax1.plot(df.index, df["buy_hold"], label="买入持有 Buy&Hold", linewidth=1.2, alpha=0.7)
    ax1.set_title(f"资金曲线对比 {title}")
    ax1.set_ylabel("资金")
    ax1.legend()
    ax1.grid(True, alpha=0.3)

    ax2.plot(df.index, df["close"], color="gray", linewidth=0.8, alpha=0.6, label="价格")
    pos_change = df["exec_pos"].diff()
    buys = df[pos_change > 0]
    sells = df[pos_change < 0]
    ax2.scatter(buys.index, buys["close"], marker="^", color="red", label="买入", s=40, zorder=5)
    ax2.scatter(sells.index, sells["close"], marker="v", color="green", label="卖出", s=40, zorder=5)
    ax2.set_title("价格与买卖点")
    ax2.legend()
    ax2.grid(True, alpha=0.3)

    plt.tight_layout()
    if save_path:
        plt.savefig(save_path, dpi=120)
        print(f"📊 图已保存:{save_path}")
    plt.close(fig)
