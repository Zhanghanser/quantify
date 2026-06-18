# -*- coding: utf-8 -*-
"""
策略三:唐奇安通道突破(趋势跟随类,经典"海龟交易法"核心)。

逻辑:价格创出最近 N 根K线的新高 → 突破,做多;
      价格跌破最近 N 根K线的新低 → 趋势反转,空仓。
适合抓大趋势的启动,假突破多的震荡市里表现差。
"""

import pandas as pd
from src.strategies.base import Strategy


class BreakoutStrategy(Strategy):
    name = "breakout"
    display_name = "通道突破"

    def generate(self, df):
        lookback = self.params.get("lookback", 20)

        df = df.copy()
        # 最近 lookback 根K线的最高价/最低价(不含当前这根,所以 shift(1))
        df["upper"] = df["high"].rolling(lookback).max().shift(1)
        df["lower"] = df["low"].rolling(lookback).min().shift(1)

        # 状态机:突破上轨进场做多,跌破下轨离场
        position = []
        holding = False
        for close, upper, lower in zip(df["close"], df["upper"], df["lower"]):
            if pd.isna(upper) or pd.isna(lower):
                position.append(0)
                continue
            if not holding and close > upper:
                holding = True
            elif holding and close < lower:
                holding = False
            position.append(1 if holding else 0)

        df["position"] = position
        return df
