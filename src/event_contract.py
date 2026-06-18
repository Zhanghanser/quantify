# -*- coding: utf-8 -*-
"""
事件合约(二元期权)信号引擎 + 回测 + 风险提醒。

事件合约 = 押 BTC 等价格在 N 分钟后涨/跌,猜对按赔率返还,猜错本金归零。
本模块用【真实历史/实时价格】做两件事:
  1) 回测:把一个押注逻辑跑几千次,算出真实胜率、盈亏、最大连亏、回撤。
  2) 实时信号 + 风险提醒:实时算当前该押涨还是跌,并把风险数据摆在你面前。

⚠️ 本模块【不下单】。它只产生信号和提醒,真正下注由你自己在平台手动操作。
⚠️ 数学事实:赔率 < 2 时,这是负期望游戏。保本胜率 = 1 / 赔率(见下)。
"""

from dataclasses import dataclass
import numpy as np
import pandas as pd


@dataclass
class EventConfig:
    horizon_minutes: int = 5      # 合约时长:3 / 5 / 10 / 30 / 60 分钟
    payout: float = 1.8           # 平台赔率:猜对返还 本金×payout(净赚 payout-1),猜错亏光
    bet_size: float = 10.0        # 每次下注金额
    initial_capital: float = 1000.0
    # ---- 风险提醒 / 限制 ----
    max_daily_loss: float = 100.0     # 当日累计亏损达到此值 → 提示停手(模拟里也强制停)
    max_consecutive_losses: int = 5   # 连亏达到此次数 → 提示停手

    @property
    def breakeven_winrate(self) -> float:
        """保本所需胜率 = 1 / 赔率。低于它,长期必亏。"""
        return 1.0 / self.payout


# ---------------- 押注方向信号 ----------------
# 信号函数:看历史到第 t 根为止的信息,返回 "UP" / "DOWN" / None(不押)。
# 注意:严格只用第 t 根及之前的数据,绝不偷看未来。

def signal_momentum(closes, t, lookback=5):
    """动量:最近 lookback 根涨了就押涨,跌了就押跌(追涨杀跌)。"""
    if t < lookback:
        return None
    return "UP" if closes[t] > closes[t - lookback] else "DOWN"


def signal_reversion(closes, t, lookback=5):
    """反转:最近涨多了押跌,跌多了押涨(赌回调)。"""
    if t < lookback:
        return None
    return "DOWN" if closes[t] > closes[t - lookback] else "UP"


def signal_always_up(closes, t):
    """基准对照:永远押涨。用来证明『有方向信号也赢不了赔率』。"""
    return "UP"


def signal_strong_momentum(closes, t, lookback=5, thr=0.002):
    """强动量(高确认):只在最近 lookback 根涨跌幅【够猛】(超过 thr)时才押,否则【不押】。
    核心思想:躲开没方向的小波动(那些最容易被赔率吃掉),只在动量明显时出手。"""
    if t < lookback:
        return None
    chg = closes[t] / closes[t - lookback] - 1
    if abs(chg) < thr:
        return None                      # 动量不够,空手——少押就是少交学费
    return "UP" if chg > 0 else "DOWN"


def signal_ma_trend(closes, t, window=20):
    """均线方向:收盘价在近 window 根均线上方押涨,下方押跌(顺短期趋势)。"""
    if t < window:
        return None
    ma = closes[t - window + 1:t + 1].mean()
    return "UP" if closes[t] > ma else "DOWN"


def signal_breakout(closes, t, lookback=20):
    """突破(高确认):创近 lookback 根新高押涨、新低押跌,区间内【不押】。"""
    if t < lookback:
        return None
    window = closes[t - lookback:t]      # 不含当前根
    if closes[t] >= window.max():
        return "UP"
    if closes[t] <= window.min():
        return "DOWN"
    return None


SIGNALS = {
    "momentum": signal_momentum,
    "reversion": signal_reversion,
    "strong_momentum": signal_strong_momentum,
    "ma_trend": signal_ma_trend,
    "breakout": signal_breakout,
    "always_up": signal_always_up,
}


# ---------------- 回测模拟 ----------------

def backtest(df: pd.DataFrame, cfg: EventConfig, signal_name="momentum") -> dict:
    """
    用真实分钟K线模拟反复押注,返回真实统计。
    假设传入的 df 是【1分钟】K线,horizon_minutes 即跨多少根。

    为了让胜率统计【可信】:这里对每一根可下注的K线都结算一次(不做提前停手),
    这样样本量最大、噪音最小——胜率才有统计意义。
    (当日止损/连亏停手属于"实时风险提醒"功能,不参与历史胜率的测量。)
    """
    closes = df["close"].values
    horizon = cfg.horizon_minutes
    signal_fn = SIGNALS[signal_name]
    n = len(closes)

    capital = cfg.initial_capital
    peak = capital
    equity_curve = [capital]

    wins = losses = bets = 0
    consec_losses = max_consec = 0
    max_dd = 0.0
    outcomes = []   # 每笔结果(1赢/0输),按时间顺序——用来做"前后半段稳定性"检验

    for t in range(n - horizon):
        pred = signal_fn(closes, t)
        if pred is None:
            equity_curve.append(capital)
            continue

        # 持平(N 分钟后价格完全不变)方向不明,不计入胜率统计——
        # 否则押"跌"会在持平根上被白算成赢,系统性虚高反转/看跌方向的胜率。
        if closes[t + horizon] == closes[t]:
            equity_curve.append(capital)
            continue

        # 结算:N 分钟后价格是否更高
        actual_up = closes[t + horizon] > closes[t]
        win = (pred == "UP" and actual_up) or (pred == "DOWN" and not actual_up)

        bets += 1
        outcomes.append(1 if win else 0)
        if win:
            pnl = cfg.bet_size * (cfg.payout - 1)
            wins += 1
            consec_losses = 0
        else:
            pnl = -cfg.bet_size
            losses += 1
            consec_losses += 1
            max_consec = max(max_consec, consec_losses)

        capital += pnl
        peak = max(peak, capital)
        max_dd = min(max_dd, capital / peak - 1)
        equity_curve.append(capital)

    win_rate = wins / bets if bets else 0.0
    be = cfg.breakeven_winrate
    ev_pct = win_rate * (cfg.payout - 1) - (1 - win_rate)   # 每笔期望(占下注额比例)
    ev_per_bet = ev_pct * cfg.bet_size

    # 显著性:胜率是否【统计上真的】高过保本线,而不是样本少时的运气。
    # 一边 z 检验:z=(p̂-p0)/sqrt(p0(1-p0)/N)。z>1.645 ≈ 95% 置信度才算"显著跑赢"。
    if bets > 0:
        se = (be * (1 - be) / bets) ** 0.5
        z_score = (win_rate - be) / se if se > 0 else 0.0
    else:
        z_score = 0.0

    # 前后半段稳定性:把所有下注按时间一切两半,看胜率是不是稳的(还是只在某半段虚高)。
    if bets >= 2:
        half = bets // 2
        wr_first = float(np.mean(outcomes[:half])) if half else 0.0
        wr_second = float(np.mean(outcomes[half:]))
    else:
        wr_first = wr_second = win_rate

    return {
        "signal": signal_name,
        "horizon": horizon,
        "bets": bets,
        "win_rate": win_rate,
        "breakeven": be,
        "ev_per_bet": ev_per_bet,
        "ev_pct": ev_pct,
        "z_score": z_score,
        "significant": bool(bets >= 30 and z_score > 1.645),   # 显著且样本够才算数
        "wr_first": wr_first,
        "wr_second": wr_second,
        "verdict": _verdict(win_rate, be, bets, z_score, wr_first, wr_second),
        "total_pnl": capital - cfg.initial_capital,
        "final_capital": capital,
        "max_consecutive_losses": max_consec,
        "max_drawdown": max_dd,
        "equity_curve": equity_curve,
    }


def _verdict(wr, be, bets, z, wr_first, wr_second) -> str:
    """把胜率/显著性/稳定性翻译成一句人话结论,避免被'56%在120笔'这种噪音骗了。"""
    if bets < 30:
        return "样本太少·不可信"
    if wr <= be:
        return "低于保本线·长期必亏"
    # 高于保本线,但要看显著 + 稳定
    if z <= 1.645:
        return "略高于保本·不显著(基本是噪音)"
    both_halves_ok = (wr_first > be) and (wr_second > be)
    if not both_halves_ok:
        return "显著但前后半段不稳·疑似过拟合"
    return "显著且稳定跑赢保本(仍属高风险,警惕未来失效)"


# ---------------- 实时信号 + 风险提醒 ----------------

def live_signal(df: pd.DataFrame, cfg: EventConfig, signal_name="momentum",
                hist_win_rate: float = None) -> dict:
    """
    根据最新数据算出当前该押的方向,并附上风险数据。
    hist_win_rate:这个信号的历史真实胜率(从 backtest 拿),用于风险提醒。
    """
    closes = df["close"].values
    t = len(closes) - 1
    pred = SIGNALS[signal_name](closes, t)
    return {
        "time": df.index[-1],
        "price": closes[t],
        "prediction": pred,
        "breakeven": cfg.breakeven_winrate,
        "hist_win_rate": hist_win_rate,
    }


def format_risk_reminder(cfg: EventConfig, hist_win_rate: float = None) -> str:
    """生成风险提醒文本块。"""
    lines = [
        "─" * 48,
        "⚠️ 下注前风险提醒(请认真看完再决定):",
        f"   平台赔率        : {cfg.payout} 倍",
        f"   保本所需胜率    : {cfg.breakeven_winrate:.1%}  ← 长期低于它必亏",
    ]
    if hist_win_rate is not None:
        gap = hist_win_rate - cfg.breakeven_winrate
        verdict = "✅ 高于保本线" if gap > 0 else "❌ 低于保本线,长期会亏"
        lines.append(f"   本信号历史胜率  : {hist_win_rate:.1%}   {verdict}")
    lines += [
        f"   单笔下注        : {cfg.bet_size}",
        f"   当日止损上限    : {cfg.max_daily_loss}（到了就停手)",
        f"   连亏停手        : {cfg.max_consecutive_losses} 次",
        "   👉 程序只给信号,下注与否、下多少,由你自己手动决定并负责。",
        "─" * 48,
    ]
    return "\n".join(lines)
