# -*- coding: utf-8 -*-
"""
策略四:趋势过滤(稳健版,风险优先)。

这是在"双均线"基础上加了一道**大趋势过滤**的稳健改进:
  - 只做多,不做空(更安全,避免做空被逼空的无限风险)
  - 只有在【价格站上长期均线】(说明大趋势向上)时,才允许按双均线做多
  - 大趋势向下时一律空仓,绝不逆着大势抄底

核心思想:不预测、不抄底,只在顺风时上车、逆风时下车。
配合阶段4的止损 + 回撤熔断 + 半仓,目标是"活得久",而不是"赚得猛"。

⚠️ 仍然不保证盈利。它的价值是【降低回撤、减少在熊市里乱交易】,属于风险优先取向。
"""

import config
from src import indicators
from src.strategies.base import Strategy


class TrendFilterStrategy(Strategy):
    name = "trend_filter"
    display_name = "趋势过滤"

    def generate(self, df):
        fast = self.params.get("fast", 20)
        slow = self.params.get("slow", 50)
        trend = self.params.get("trend", 100)   # 长期均线:判断大趋势方向

        df = df.copy()
        df["ma_fast"] = indicators.moving_average(df["close"], fast)
        df["ma_slow"] = indicators.moving_average(df["close"], slow)
        df["ma_trend"] = indicators.moving_average(df["close"], trend)

        # 同时满足两个条件才做多:
        #   1) 快线 > 慢线(短期向上)
        #   2) 收盘价 > 长期均线(大趋势向上)—— 这是"过滤器"
        long_ok = (df["ma_fast"] > df["ma_slow"]) & (df["close"] > df["ma_trend"])
        df["position"] = 0
        df.loc[long_ok, "position"] = 1

        # 长期均线还没算出来的阶段,空仓
        df.loc[df["ma_trend"].isna(), "position"] = 0
        return df
