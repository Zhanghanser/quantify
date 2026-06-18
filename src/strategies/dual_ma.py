# -*- coding: utf-8 -*-
"""
策略一:双均线交叉(趋势跟随类)。

逻辑:快线上穿慢线 → 做多;快线下穿慢线 → 空仓。
适合有明显趋势的行情,震荡行情里容易反复被"打脸"(频繁交易亏手续费)。
"""

import config
from src import indicators
from src.strategies.base import Strategy


class DualMAStrategy(Strategy):
    name = "dual_ma"
    display_name = "双均线交叉"

    def generate(self, df):
        fast = self.params.get("fast", config.FAST_MA)
        slow = self.params.get("slow", config.SLOW_MA)

        df = df.copy()
        df["ma_fast"] = indicators.moving_average(df["close"], fast)
        df["ma_slow"] = indicators.moving_average(df["close"], slow)

        # 快线在慢线上方 → 持多(1),否则空仓(0)
        df["position"] = 0
        df.loc[df["ma_fast"] > df["ma_slow"], "position"] = 1
        # 均线还没算出来的阶段,空仓观望
        df.loc[df["ma_slow"].isna(), "position"] = 0
        return df
