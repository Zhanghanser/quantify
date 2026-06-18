# -*- coding: utf-8 -*-
"""
风控模块(阶段4)。

风控是量化能不能活下来的关键。再好的策略,没有风控也可能被一次极端行情打爆。
本模块定义风控参数,回测引擎会按这些规则强制止损/止盈/控制仓位。

三个核心工具:
  1) 止损(stop loss):亏到一定比例就认输离场,防止小亏拖成大亏。
  2) 止盈(take profit):赚到一定比例就落袋,防止利润回吐(可选)。
  3) 仓位管理(position sizing):每笔只投入部分资金,而不是全押。
  4) 总回撤熔断:整体亏损超过阈值就停止交易,保护本金。
"""

from dataclasses import dataclass


@dataclass
class RiskConfig:
    # 止损比例:持仓亏损达到这个比例就强制平仓。0.05 = 亏 5% 就止损。设 0 表示不启用。
    stop_loss: float = 0.05

    # 止盈比例:持仓盈利达到这个比例就平仓落袋。0.10 = 赚 10% 就止盈。设 0 表示不启用。
    take_profit: float = 0.0

    # 仓位比例:每笔交易投入多少比例的资金。1.0 = 满仓;0.5 = 半仓(更稳但收益也减半)。
    position_size: float = 1.0

    # 总回撤熔断:从资金最高点回撤超过这个比例,就停止后续所有交易。0 表示不启用。
    max_drawdown_stop: float = 0.0

    def describe(self) -> str:
        parts = []
        parts.append(f"止损 {self.stop_loss:.0%}" if self.stop_loss > 0 else "止损 关")
        parts.append(f"止盈 {self.take_profit:.0%}" if self.take_profit > 0 else "止盈 关")
        parts.append(f"仓位 {self.position_size:.0%}")
        parts.append(f"回撤熔断 {self.max_drawdown_stop:.0%}"
                     if self.max_drawdown_stop > 0 else "回撤熔断 关")
        return " | ".join(parts)


# 默认风控配置(不带风控,用于和"加了风控"做对比)
NO_RISK = RiskConfig(stop_loss=0.0, take_profit=0.0,
                     position_size=1.0, max_drawdown_stop=0.0)
