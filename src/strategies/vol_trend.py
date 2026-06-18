# -*- coding: utf-8 -*-
"""
策略:趋势过滤 + 波动率门控合成系统(vol_trend)。

这是对"区间过滤趋势"(可多空趋势跟随)的改造,针对三个失血点:
  1) 低波动震荡期频繁开仓 → 用【波动率门控】只在 ATR 百分位够高时才出手。
  2) 做空遇逼空回撤失控   → 用【逼空熔断】单根暴涨>阈值无条件平空 + 冷却。
  3) 固定止损太钝         → 用【ATR 吊灯追踪止损】让盈利单跑得更远(抬高盈亏比)。

实现说明(对齐本框架,不依赖 TA-Lib):
  - EMA 用 pandas ewm;ATR 用 indicators.atr;ATR 百分位用 rolling(window).rank(pct=True)。
  - 追踪止损/逼空熔断是【路径依赖】的逐根状态机,本框架的引擎只有固定%止损,
    所以这些出场逻辑全部写在【信号层】(generate 里逐根算 position),引擎只照单执行。
  - 严格无未来函数:第 t 根只用 closes/highs/lows[..t];出场在第 t 根收盘"决定",
    由引擎 signals[t-1] 在第 t+1 根执行(天然 1 根延迟,偏保守)。
仍然只回测/只给信号,绝不自动下单。
"""

import numpy as np
from src import indicators
from src.strategies.base import Strategy


class VolGatedTrendStrategy(Strategy):
    name = "vol_trend"
    display_name = "波动率门控趋势"

    def generate(self, df):
        p = self.params
        fast_ema = int(p.get("fast_ema", 20))
        slow_ema = int(p.get("slow_ema", 100))
        vol_gate = float(p.get("volatility_gate", 0.35))
        ts_min = float(p.get("trend_strength_min", 0.02))    # 均线最小发散度(%)
        k_atr = float(p.get("atr_multiplier", 2.5))
        cooling = int(p.get("cooling_period", 3))
        allow_short = bool(int(p.get("allow_short", 1)))
        atr_period = int(p.get("atr_period", 14))
        vol_window = int(p.get("vol_window", 20))
        band = float(p.get("band", 0.02))                    # 慢线上下 2% 缓冲带
        squeeze_thr = float(p.get("squeeze_thr", 0.08))      # 单根涨幅>8% 视为逼空

        df = df.copy()
        close = df["close"]
        ema_fast = close.ewm(span=fast_ema, adjust=False).mean()
        ema_slow = close.ewm(span=slow_ema, adjust=False).mean()
        atr = indicators.atr(df, atr_period)
        atr_pct = atr / close * 100.0
        atr_rank = atr_pct.rolling(vol_window).rank(pct=True)
        trend_strength = (ema_fast - ema_slow) / close * 100.0
        df["ma_trend"] = ema_slow            # 画到图上
        df["atr_rank"] = atr_rank

        c = close.values
        h = df["high"].values
        l = df["low"].values
        ef = ema_fast.values
        es = ema_slow.values
        a = atr.values
        ar = atr_rank.values
        ts = trend_strength.values
        n = len(df)

        position = np.zeros(n, dtype=int)
        holding = 0
        extreme = 0.0          # 持多记最高价 / 持空记最低价
        cooldown = 0
        # 统计:被波动率门控挡下的"本可开仓"的根数
        gate_skipped = 0

        for t in range(n):
            # 指标未就绪 → 空仓
            if not (np.isfinite(es[t]) and np.isfinite(a[t]) and np.isfinite(ar[t])):
                position[t] = 0
                continue

            ct, ht, lt, pc = c[t], h[t], l[t], c[t - 1] if t > 0 else c[t]

            # 期望方向(三层门控的方向+强度部分,先不含波动率)
            up = (ct > es[t] * (1 + band)) and (ef[t] > es[t]) and (ts[t] > ts_min)
            dn = (ct < es[t] * (1 - band)) and (ef[t] < es[t]) and (ts[t] < -ts_min)
            ddir = 1 if up else (-1 if (dn and allow_short) else 0)
            vok = ar[t] > vol_gate

            # 1) 管理现有持仓:追踪止损 / 逼空熔断
            if holding == 1:
                extreme = max(extreme, ht)
                trail = extreme - k_atr * a[t]
                if lt <= trail:
                    holding = 0                       # 多头吊灯追踪止损
            elif holding == -1:
                extreme = min(extreme, lt)
                trail = extreme + k_atr * a[t]
                if pc > 0 and (ht / pc - 1.0) > squeeze_thr:
                    holding = 0
                    cooldown = cooling                # 逼空熔断 → 平空 + 冷却
                elif ht >= trail:
                    holding = 0                       # 空头吊灯追踪止损

            # 2) 趋势消失/反转 → 平掉现有仓
            if holding != 0 and ddir != holding:
                holding = 0

            # 3) 冷却期:不开新仓
            if cooldown > 0:
                cooldown -= 1
                position[t] = holding
                continue

            # 4) 开新仓:仅在空仓 + 波动率达标 + 有明确趋势时
            if holding == 0 and ddir != 0:
                if vok:
                    holding = ddir
                    extreme = ht if ddir == 1 else lt
                else:
                    gate_skipped += 1                 # 被波动率门控挡下

            position[t] = holding

        df["position"] = position
        # 供分析脚本读取的统计(挂在 df.attrs,不影响回测)
        df.attrs["gate_skipped"] = int(gate_skipped)
        return df
