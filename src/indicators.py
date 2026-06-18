# -*- coding: utf-8 -*-
"""
技术指标计算。

技术指标就是把价格/成交量做各种数学加工,帮助我们判断趋势和买卖时机。
这里全部用 pandas 自己算,不依赖 ta-lib(ta-lib 在 Windows 上对新手安装很麻烦)。
"""

import pandas as pd


def moving_average(series: pd.Series, window: int) -> pd.Series:
    """
    简单移动平均线(MA / SMA)。
    就是最近 window 根K线收盘价的平均值,用来平滑价格、看趋势方向。
    例如 window=10 就是"10周期均线"。
    """
    return series.rolling(window=window).mean()


def rsi(series: pd.Series, window: int = 14) -> pd.Series:
    """
    相对强弱指标(RSI),取值 0~100。
    > 70 通常认为"超买"(可能要回落),< 30 认为"超卖"(可能要反弹)。
    是短线均值回归策略的常用指标。
    """
    delta = series.diff()                      # 相邻K线的涨跌幅
    gain = delta.clip(lower=0)                 # 只保留上涨部分
    loss = -delta.clip(upper=0)               # 只保留下跌部分(转正)
    # 用 Wilder 平滑(alpha=1/window),这是 RSI 的行业标准口径,
    # 与前端图表/Binance/TradingView 一致;之前用 rolling().mean()(简单平均)会和图上的线对不上。
    avg_gain = gain.ewm(alpha=1 / window, min_periods=window, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / window, min_periods=window, adjust=False).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def atr(df: pd.DataFrame, window: int = 14) -> pd.Series:
    """
    平均真实波幅(ATR),衡量价格波动大小,常用来设置止损距离。
    需要 high / low / close 三列。
    """
    high_low = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift()).abs()
    low_close = (df["low"] - df["close"].shift()).abs()
    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return true_range.rolling(window=window).mean()


def _true_range(df: pd.DataFrame) -> pd.Series:
    """真实波幅 TR(ATR/ADX 的公共部分)。"""
    high_low = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift()).abs()
    low_close = (df["low"] - df["close"].shift()).abs()
    return pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)


def adx(df: pd.DataFrame, window: int = 14):
    """
    平均趋向指数 ADX + 方向指标 +DI / -DI(Wilder 经典口径)。

    用途:衡量"有没有趋势 + 趋势朝哪边",是区分【趋势市】和【震荡市】的标准工具。
      - ADX 高(>25)= 趋势强;ADX 低(<20)= 没方向的震荡(短线最容易在这里被成本磨死)。
      - +DI > -DI = 多头占优;-DI > +DI = 空头占优。
    返回:(adx, plus_di, minus_di) 三条 Series。需要 high/low/close 三列。
    """
    up_move = df["high"].diff()
    down_move = -df["low"].diff()
    # 只有"涨幅 > 跌幅且为正"才算 +DM;反之才算 -DM(互斥)
    plus_dm = ((up_move > down_move) & (up_move > 0)) * up_move.clip(lower=0)
    minus_dm = ((down_move > up_move) & (down_move > 0)) * down_move.clip(lower=0)

    tr = _true_range(df)
    a = 1.0 / window
    atr_w = tr.ewm(alpha=a, min_periods=window, adjust=False).mean()
    plus_di = 100 * plus_dm.ewm(alpha=a, min_periods=window, adjust=False).mean() / atr_w
    minus_di = 100 * minus_dm.ewm(alpha=a, min_periods=window, adjust=False).mean() / atr_w

    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, float("nan"))
    adx_line = dx.ewm(alpha=a, min_periods=window, adjust=False).mean()
    return adx_line, plus_di, minus_di
