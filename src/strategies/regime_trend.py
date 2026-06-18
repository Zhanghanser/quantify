# -*- coding: utf-8 -*-
"""
策略:区间过滤趋势(ADX/DMI,可多可空)。

这是针对"为什么各种策略在下跌/震荡里都在亏"的两个根因做的改进:
  根因1:以前所有策略都【只能做多】,行情一路跌就只能挨着,赚不到下跌的钱。
  根因2:以前不分行情好坏一直在交易,没方向的震荡市里被【手续费+滑点】反复磨。

对策(都靠 ADX/DMI 这套"趋势强度+方向"指标):
  - ADX 衡量趋势强不强:ADX 低(<阈值)= 没方向的震荡 → 直接空仓,不出手;
  - +DI/-DI 衡量方向:上升趋势(且站上大均线)做多,下降趋势(且跌破大均线)做空;
  - allow_short=0 时退化为"只做多 + 震荡空仓",适合不能做空的市场(如 A 股)。

严格三重确认(ADX 够强 + DI 方向 + 价格在大均线正确一侧),所以交易不频繁——
这正是目的:宁可少做、只做趋势明确的单,把被成本磨损的烂单滤掉。
仍然只回测/只给信号,绝不自动下单。
"""

from src import indicators
from src.strategies.base import Strategy


class RegimeTrendStrategy(Strategy):
    name = "regime_trend"
    display_name = "区间过滤趋势"

    def generate(self, df):
        adx_period = int(self.params.get("adx_period", 14))
        adx_min = float(self.params.get("adx_min", 25))     # ADX 低于此=震荡,空仓
        trend_ma = int(self.params.get("trend_ma", 100))    # 大趋势均线,再加一道方向确认
        allow_short = bool(int(self.params.get("allow_short", 1)))

        df = df.copy()
        adx_line, pdi, mdi = indicators.adx(df, adx_period)
        ma = indicators.moving_average(df["close"], trend_ma)
        df["adx"] = adx_line
        df["ma_trend"] = ma          # 借"中轨/趋势线"槽位画到图上

        position = []
        for c, a, p, m, mt in zip(df["close"], adx_line, pdi, mdi, ma):
            if a != a or mt != mt:           # 指标还没算出来 → 空仓
                position.append(0)
                continue
            if a < adx_min:                  # 趋势太弱(震荡市)→ 空仓,躲开成本磨损
                position.append(0)
                continue
            long_ok = (p > m) and (c > mt)   # 多头占优 且 站上大均线
            short_ok = (p < m) and (c < mt)  # 空头占优 且 跌破大均线
            if long_ok:
                position.append(1)
            elif short_ok:
                position.append(-1 if allow_short else 0)
            else:
                position.append(0)
        df["position"] = position
        return df
