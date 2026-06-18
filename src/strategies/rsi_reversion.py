# -*- coding: utf-8 -*-
"""
策略二:RSI 均值回归(逆势类)。

逻辑:价格"跌过头"(RSI 超卖)时抄底做多,等反弹到中性区(RSI 回到 50)就卖出。
和双均线相反:双均线追涨杀跌(顺势),这个是低买高卖(逆势)。
适合震荡行情;遇到单边大跌时会"接飞刀",所以必须配止损(阶段4的风控)。
"""

from src import indicators
from src.strategies.base import Strategy


class RSIReversionStrategy(Strategy):
    name = "rsi_reversion"
    display_name = "RSI均值回归"

    def generate(self, df):
        period = self.params.get("period", 14)
        oversold = self.params.get("oversold", 30)    # 低于此值算"超卖",抄底
        exit_level = self.params.get("exit_level", 50)  # 反弹到此值就离场

        df = df.copy()
        df["rsi"] = indicators.rsi(df["close"], period)

        # 用"状态机"思路逐行决定仓位:
        #   一旦 RSI 跌破超卖线就买入并持有,直到 RSI 回升到离场线才卖出。
        position = []
        holding = False
        for value in df["rsi"]:
            if value != value:  # NaN(RSI还没算出来),空仓
                position.append(0)
                continue
            if not holding and value < oversold:
                holding = True            # 触发抄底
            elif holding and value > exit_level:
                holding = False           # 反弹离场
            position.append(1 if holding else 0)

        df["position"] = position
        return df
