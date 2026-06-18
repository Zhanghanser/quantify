# -*- coding: utf-8 -*-
"""
短线/日内策略包(面向分钟级投机)。

这些策略是给"短线投机"准备的,周期建议用 1m/5m/15m。它们交易更频繁,
所以【手续费 + 滑点】对它们的影响比中长线大得多——务必结合"短线体检报告"看
每笔期望值和手续费占比,别被一条好看的资金曲线骗了。

⚠️ 诚实提醒:周期越短越接近噪音,简单短线规则在扣掉成本后大多是负期望。
   这几个策略是让你【亲手测、亲眼看】哪种短打在你的标的上真有微弱优势,
   而不是承诺它们能稳赚。和项目其它部分一样:只回测/给信号,绝不自动下单。

全部严格只用"当根及之前"的数据,且突破/通道类用 shift(1) 防未来函数。
"""

from src import indicators
from src.strategies.base import Strategy


class BollBounceStrategy(Strategy):
    """布林带反弹(逆势,适合震荡):价格跌破下轨抄底,回到中轨离场。"""
    name = "boll_bounce"
    display_name = "布林反弹"

    def generate(self, df):
        period = int(self.params.get("period", 20))
        k = float(self.params.get("k", 2.0))

        df = df.copy()
        ma = df["close"].rolling(period).mean()
        sd = df["close"].rolling(period).std(ddof=0)
        lower = ma - k * sd
        df["ma_slow"] = ma          # 借用图上"中轨"展示(回测引擎会画出来)

        position, holding = [], False
        for close, lo, mid in zip(df["close"], lower, ma):
            if lo != lo:            # NaN,指标还没算出来
                position.append(0)
                continue
            if not holding and close < lo:
                holding = True       # 跌破下轨,抄底
            elif holding and close >= mid:
                holding = False      # 回到中轨,离场
            position.append(1 if holding else 0)

        df["position"] = position
        return df


class RSIScalpStrategy(Strategy):
    """RSI(2) 快速反弹(Connors 短线经典):RSI(2) 极度超卖买入,回到中性快速离场。"""
    name = "rsi_scalp"
    display_name = "RSI快速反弹"

    def generate(self, df):
        period = int(self.params.get("period", 2))   # 短周期 RSI,反应极快
        buy = float(self.params.get("buy", 10))      # RSI 低于此值买入
        exit_level = float(self.params.get("exit_level", 60))  # 回升到此值离场

        df = df.copy()
        df["rsi"] = indicators.rsi(df["close"], period)

        position, holding = [], False
        for value in df["rsi"]:
            if value != value:
                position.append(0)
                continue
            if not holding and value < buy:
                holding = True
            elif holding and value > exit_level:
                holding = False
            position.append(1 if holding else 0)

        df["position"] = position
        return df


class MomoBreakoutStrategy(Strategy):
    """带量动量突破(顺势):创 N 根新高【且放量】才追,跌破 N 根新低离场。
    比普通通道突破多一道"成交量确认",过滤掉没人跟的假突破。"""
    name = "momo_breakout"
    display_name = "带量突破"

    def generate(self, df):
        lookback = int(self.params.get("lookback", 20))
        vol_mult = float(self.params.get("vol_mult", 1.5))   # 成交量需 > 均量的几倍

        df = df.copy()
        upper = df["high"].rolling(lookback).max().shift(1)   # shift(1) 防未来函数
        lower = df["low"].rolling(lookback).min().shift(1)
        vol_avg = df["volume"].rolling(lookback).mean().shift(1)
        df["upper"] = upper
        df["lower"] = lower

        position, holding = [], False
        for close, up, lo, vol, va in zip(df["close"], upper, lower, df["volume"], vol_avg):
            if up != up or va != va:
                position.append(0)
                continue
            if not holding and close > up and vol > va * vol_mult:
                holding = True       # 放量创新高才追
            elif holding and close < lo:
                holding = False
            position.append(1 if holding else 0)

        df["position"] = position
        return df


class BollRSIStrategy(Strategy):
    """BOLL 兼 RSI(双重确认的均值回归):
    价格跌破布林【下轨】、且 RSI 同时【超卖】,两个超卖信号一起成立才买入(比单用一个假信号少);
    价格回到布林【中轨】、或 RSI 回到中性,就离场。
    """
    name = "boll_rsi"
    display_name = "BOLL兼RSI"

    def generate(self, df):
        period = int(self.params.get("period", 20))     # 布林周期
        k = float(self.params.get("k", 2.0))            # 标准差倍数
        rsi_period = int(self.params.get("rsi_period", 14))
        oversold = float(self.params.get("oversold", 30))    # RSI 低于此算超卖
        exit_level = float(self.params.get("exit_level", 50))  # RSI 回到此值离场

        df = df.copy()
        ma = df["close"].rolling(period).mean()
        sd = df["close"].rolling(period).std(ddof=0)
        lower = ma - k * sd
        df["ma_slow"] = ma                              # 把布林中轨画到图上
        df["rsi"] = indicators.rsi(df["close"], rsi_period)

        position, holding = [], False
        for close, lo, mid, r in zip(df["close"], lower, ma, df["rsi"]):
            if lo != lo or r != r:                      # 指标还没算出来,空仓
                position.append(0)
                continue
            if not holding and close < lo and r < oversold:
                holding = True                          # 跌破下轨 + RSI 超卖 → 双重确认买入
            elif holding and (close >= mid or r > exit_level):
                holding = False                         # 回到中轨 或 RSI 回中性 → 离场
            position.append(1 if holding else 0)

        df["position"] = position
        return df


class VWAPRevertStrategy(Strategy):
    """VWAP 偏离回归(逆势,日内常用):价格跌到滚动 VWAP 下方一定幅度抄底,回到 VWAP 离场。"""
    name = "vwap_revert"
    display_name = "VWAP回归"

    def generate(self, df):
        window = int(self.params.get("window", 20))
        dev = float(self.params.get("dev", 1.0))   # 偏离百分比(跌破 VWAP 多少 % 才买)

        df = df.copy()
        typical = (df["high"] + df["low"] + df["close"]) / 3
        pv = (typical * df["volume"]).rolling(window).sum()
        vol = df["volume"].rolling(window).sum()
        vwap = pv / vol
        df["ma_slow"] = vwap        # 借"中轨"槽位把 VWAP 画到图上
        buy_line = vwap * (1 - dev / 100.0)

        position, holding = [], False
        for close, bl, vw in zip(df["close"], buy_line, vwap):
            if bl != bl:
                position.append(0)
                continue
            if not holding and close < bl:
                holding = True       # 跌到 VWAP 下方 dev% 抄底
            elif holding and close >= vw:
                holding = False      # 回到 VWAP 离场
            position.append(1 if holding else 0)

        df["position"] = position
        return df
