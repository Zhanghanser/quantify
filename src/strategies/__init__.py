# -*- coding: utf-8 -*-
"""
策略注册表。

把所有策略集中登记在 STRATEGIES 字典里,这样别处可以用名字取策略,
方便"对比工具"和"参数优化"批量遍历所有策略。
新增策略:写好类后,在下面 import 并加进字典即可。
"""

from src.strategies.base import Strategy
from src.strategies.dual_ma import DualMAStrategy
from src.strategies.rsi_reversion import RSIReversionStrategy
from src.strategies.breakout import BreakoutStrategy
from src.strategies.trend_filter import TrendFilterStrategy
from src.strategies.scalping import (
    BollBounceStrategy, RSIScalpStrategy, MomoBreakoutStrategy, VWAPRevertStrategy,
    BollRSIStrategy,
)
from src.strategies.regime_trend import RegimeTrendStrategy
from src.strategies.vol_trend import VolGatedTrendStrategy

# 名字 → 策略类
STRATEGIES = {
    DualMAStrategy.name: DualMAStrategy,
    RSIReversionStrategy.name: RSIReversionStrategy,
    BreakoutStrategy.name: BreakoutStrategy,
    TrendFilterStrategy.name: TrendFilterStrategy,
    # 短线/日内策略包
    BollBounceStrategy.name: BollBounceStrategy,
    RSIScalpStrategy.name: RSIScalpStrategy,
    MomoBreakoutStrategy.name: MomoBreakoutStrategy,
    VWAPRevertStrategy.name: VWAPRevertStrategy,
    BollRSIStrategy.name: BollRSIStrategy,
    # 趋势/区间过滤(可多可空)
    RegimeTrendStrategy.name: RegimeTrendStrategy,
    VolGatedTrendStrategy.name: VolGatedTrendStrategy,
}


def get_strategy(name: str, **params) -> Strategy:
    """按名字创建一个策略实例,可传入参数覆盖默认值。"""
    if name not in STRATEGIES:
        raise ValueError(f"未知策略 '{name}',可选:{list(STRATEGIES.keys())}")
    return STRATEGIES[name](**params)
