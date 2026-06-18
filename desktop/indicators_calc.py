# -*- coding: utf-8 -*-
"""
技术指标计算(逐根对齐网页版 web/app.js 的口径,保证线一模一样)。

输入 numpy 数组,输出 numpy 数组(用 np.nan 占位前导无效值)。
口径要点:
  EMA   种子 = 前 p 根的简单均值,之后 prev*(1-k)+x*k, k=2/(p+1)
  BOLL  标准差用【总体】口径(除以 p,即 ddof=0),和 TradingView/币安一致
  MACD  hist = dif - dea(不 ×2);dea 是对 dif 有效段再取 EMA
  RSI   Wilder 平滑(和 src.indicators.rsi 同源)
  KDJ   k=((kp-1)*k+rsv)/kp 递推,初值 50;j=3k-2d
"""

import numpy as np


def sma(src, p):
    src = np.asarray(src, dtype=float)
    n = len(src)
    out = np.full(n, np.nan)
    if p <= 0 or n < p:
        return out
    csum = np.cumsum(src)
    out[p - 1] = csum[p - 1] / p
    if n > p:
        out[p:] = (csum[p:] - csum[:-p]) / p
    return out


def ema(src, p):
    src = np.asarray(src, dtype=float)
    n = len(src)
    out = np.full(n, np.nan)
    if p <= 0 or n < p:
        return out
    k = 2.0 / (p + 1)
    prev = float(np.mean(src[:p]))   # 种子=前 p 根 SMA,落在 i=p-1
    out[p - 1] = prev
    for i in range(p, n):
        prev = src[i] * k + prev * (1 - k)
        out[i] = prev
    return out


def boll(src, p, mult):
    src = np.asarray(src, dtype=float)
    n = len(src)
    mid = sma(src, p)
    up = np.full(n, np.nan)
    lo = np.full(n, np.nan)
    for i in range(p - 1, n):
        seg = src[i - p + 1:i + 1]
        sd = float(np.sqrt(np.mean((seg - mid[i]) ** 2)))   # 总体标准差
        up[i] = mid[i] + mult * sd
        lo[i] = mid[i] - mult * sd
    return mid, up, lo


def rsi(src, p):
    src = np.asarray(src, dtype=float)
    n = len(src)
    out = np.full(n, np.nan)
    if n <= p or p <= 0:
        return out
    g = l = 0.0
    for i in range(1, n):
        d = src[i] - src[i - 1]
        gain = d if d > 0 else 0.0
        loss = -d if d < 0 else 0.0
        if i <= p:
            g += gain
            l += loss
            if i == p:
                g /= p
                l /= p
                rs = 1e9 if l == 0 else g / l
                out[i] = 100 - 100 / (1 + rs)
        else:
            g = (g * (p - 1) + gain) / p
            l = (l * (p - 1) + loss) / p
            rs = 1e9 if l == 0 else g / l
            out[i] = 100 - 100 / (1 + rs)
    return out


def macd(src, fast, slow, sig):
    src = np.asarray(src, dtype=float)
    n = len(src)
    ef, es = ema(src, fast), ema(src, slow)
    dif = np.full(n, np.nan)
    m = ~np.isnan(ef) & ~np.isnan(es)
    dif[m] = ef[m] - es[m]
    dea = np.full(n, np.nan)
    valid = np.flatnonzero(~np.isnan(dif))
    if valid.size:
        start = valid[0]
        dea[start:] = ema(dif[start:], sig)
    hist = np.full(n, np.nan)
    m2 = ~np.isnan(dif) & ~np.isnan(dea)
    hist[m2] = dif[m2] - dea[m2]
    return dif, dea, hist


def kdj(high, low, close, n, kp, dp):
    high = np.asarray(high, dtype=float)
    low = np.asarray(low, dtype=float)
    close = np.asarray(close, dtype=float)
    L = len(close)
    K = np.full(L, np.nan)
    D = np.full(L, np.nan)
    J = np.full(L, np.nan)
    k = d = 50.0
    for i in range(L):
        if i < n - 1:
            continue
        hh = float(np.max(high[i - n + 1:i + 1]))
        ll = float(np.min(low[i - n + 1:i + 1]))
        rsv = 50.0 if hh == ll else (close[i] - ll) / (hh - ll) * 100
        k = ((kp - 1) * k + rsv) / kp
        d = ((dp - 1) * d + k) / dp
        K[i] = k
        D[i] = d
        J[i] = 3 * k - 2 * d
    return K, D, J
