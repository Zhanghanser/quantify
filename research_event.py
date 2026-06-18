# -*- coding: utf-8 -*-
"""
事件合约·完美量化研究脚本(可复现)。
口径全部写死在此,任何人重跑得到相同数字。
"""
import sys, math
if sys.platform == "win32":
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
import numpy as np
import pandas as pd
from src.data import get_data
from src import event_contract as ec

COINS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT", "DOGE/USDT"]
HORIZONS = [1, 3, 5, 10, 30]                       # 分钟
SIGNALS = ["momentum", "reversion", "strong_momentum", "ma_trend", "breakout"]
BET = 10.0                                          # 单注金额(元)
PAYOUTS = [1.80, 1.90, 1.95]                        # 评估的几档赔率
LIMIT = 1000

def norm_sf(z):                                     # P(Z > z),标准正态右尾
    return 0.5 * math.erfc(z / math.sqrt(2))

def wilson(p, n, z=1.96):                           # 胜率的 95% Wilson 置信区间
    if n == 0: return (float("nan"), float("nan"))
    d = 1 + z*z/n
    c = (p + z*z/(2*n)) / d
    h = z*math.sqrt(p*(1-p)/n + z*z/(4*n*n)) / d
    return (c-h, c+h)

# ---- 取数 + 数据完整性 ----
DATA = {}
print("=" * 78)
print("第一条 · 数据完整性检查")
print("=" * 78)
print(f"数据源: gate.io 现货(经 ccxt 拉取);周期: 1分钟;每币请求 {LIMIT} 根;复权: 币圈无除权问题")
for c in COINS:
    df = get_data("crypto", c, "1m", LIMIT)
    DATA[c] = df
    idx = df.index
    secs = pd.Series(idx).diff().dt.total_seconds().dropna()
    gaps = int((secs != 60).sum())                  # 非连续60秒的根数(缺K/合并)
    rets = (df["close"] / df["close"].shift(1) - 1).abs()
    anom = int((rets > 0.5).sum())                  # 单根>50%的异常
    zero = int((df[["open","high","low","close"]] <= 0).any(axis=1).sum())
    print(f"  {c:<10} 根数={len(df)} 区间={idx[0]}~{idx[-1]} "
          f"缺/跳K={gaps} 异常(>50%)={anom} 非正价={zero}")
print("  → 缺K数即 1m 时间戳间隔≠60s 的根数(gate 偶有跳K);异常/非正价为 0 即数据干净。")

# ---- 通用:对一段 closes 跑某信号,返回逐笔结果(含时间序)----
def bet_outcomes(closes, signal_name, horizon, lo=0, hi=None):
    fn = ec.SIGNALS[signal_name]
    hi = (len(closes) if hi is None else hi)
    out = []
    for t in range(lo, hi - horizon):
        pred = fn(closes, t)
        if pred is None: continue
        if closes[t + horizon] == closes[t]: continue      # 持平不计(口径:剔除平局)
        up = closes[t + horizon] > closes[t]
        out.append(1 if ((pred == "UP" and up) or (pred == "DOWN" and not up)) else 0)
    return out

def stats(out, payout):
    n = len(out); w = sum(out); wr = w / n if n else 0.0
    be = 1.0 / payout
    se = math.sqrt(be*(1-be)/n) if n else 0.0
    z = (wr - be)/se if se else 0.0
    p1 = norm_sf(z)                                          # 单边 p:真实=保本线时,看到≥此胜率的概率
    lo, hi = wilson(wr, n)
    ev = (wr*(payout-1) - (1-wr)) * BET                      # 每笔期望(元)
    # 最大连亏 + 押注资金最大回撤
    cap = 100.0; peak = cap; mdd = 0.0; cl = mc = 0
    for o in out:
        cap += BET*(payout-1) if o else -BET
        if o: cl = 0
        else: cl += 1; mc = max(mc, cl)
        peak = max(peak, cap); mdd = min(mdd, cap/peak - 1)
    return dict(n=n, w=w, wr=wr, be=be, z=z, p1=p1, lo=lo, hi=hi, ev=ev, mc=mc, mdd=mdd)

# ---- 第三条:BTC 全信号×全时长明细(赔率1.90)----
print("\n" + "=" * 78)
print("第三条 · 胜率明细 — BTC/USDT,赔率1.90(保本胜率 1/1.90=52.63%),单注10元,平局剔除")
print("=" * 78)
print(f"{'信号':<14}{'时长':>4}{'胜/总':>11}{'胜率':>8}{'Wilson95%CI':>16}{'z':>7}{'单边p':>8}{'每笔期望':>9}{'最大连亏':>7}")
btc = DATA["BTC/USDT"]["close"].values
for s in SIGNALS:
    for h in HORIZONS:
        st = stats(bet_outcomes(btc, s, h), 1.90)
        ci = f"[{st['lo']*100:.1f},{st['hi']*100:.1f}]"
        print(f"{s:<14}{h:>3}m{st['w']:>6}/{st['n']:<4}{st['wr']*100:>7.2f}%{ci:>16}"
              f"{st['z']:>+7.2f}{st['p1']:>8.3f}{st['ev']:>+8.2f}元{st['mc']:>6}")

# ---- 第三条续:赔率敏感(同一胜率,换赔率看保本线)----
print("\n保本线随赔率(口径:保本胜率=1/赔率):")
for p in PAYOUTS:
    print(f"  赔率{p} → 保本胜率 {100/p:.2f}%")

# ---- 第五条:样本内→样本外 选择性偏差检验 ----
print("\n" + "=" * 78)
print("第五条 · 样本内选最优→样本外验证(量化'挑出来的赢家'有多少是过拟合)")
print("口径:每币用【前50%数据】选出胜率最高的(信号×时长),再到【后50%】实测该组合。赔率1.90")
print("=" * 78)
print(f"{'币种':<10}{'选中组合':<22}{'样本内胜率':>10}{'样本外胜率':>11}{'保本线':>8}{'样本外结论':>12}")
deg = []
for c in COINS:
    closes = DATA[c]["close"].values
    mid = len(closes) // 2
    best = None
    for s in SIGNALS:
        for h in HORIZONS:
            o_is = bet_outcomes(closes, s, h, 0, mid)
            if len(o_is) < 30: continue
            wr = sum(o_is)/len(o_is)
            if best is None or wr > best[0]:
                best = (wr, s, h, len(o_is))
    wr_is, s, h, n_is = best
    o_oos = bet_outcomes(closes, s, h, mid, len(closes))
    wr_oos = sum(o_oos)/len(o_oos) if o_oos else 0.0
    be = 1/1.90
    deg.append(wr_is - wr_oos)
    verdict = "仍>保本" if wr_oos > be else "跌破保本"
    print(f"{c:<10}{s+' '+str(h)+'m':<22}{wr_is*100:>9.2f}%{wr_oos*100:>10.2f}%{be*100:>7.2f}%{verdict:>12}")
print(f"  → 平均样本内→样本外胜率衰减 = {np.mean(deg)*100:+.2f} 个百分点(正=样本外变差=选择性偏差/过拟合的证据)")

# ---- 第五条续:多重检验 ----
N = len(COINS)*len(HORIZONS)*len(SIGNALS)
print("\n" + "=" * 78)
print("多重检验校正")
print("=" * 78)
print(f"  共检验组合数 N = {N}(6币×5时长×5信号)")
print(f"  α=0.05 单边下,纯靠运气的期望假阳性 = {0.05*N:.1f} 个")
alpha2 = 0.05 / N
a_lo, a_hi = 0.0, 6.0
for _ in range(60):
    m = (a_lo + a_hi) / 2
    if norm_sf(m) > alpha2: a_lo = m
    else: a_hi = m
print(f"  Bonferroni 校正后单组合阈值 alpha'=0.05/{N}={alpha2:.5f},需 z>{(a_lo+a_hi)/2:.2f} 才算真显著")

# 全样本所有组合里,统计显著(单边z>1.645)且样本外也>保本 的有几个(赔率1.90)
sig_total = sig_robust = 0
for c in COINS:
    closes = DATA[c]["close"].values; mid=len(closes)//2
    for s in SIGNALS:
        for h in HORIZONS:
            st = stats(bet_outcomes(closes, s, h), 1.90)
            if st["n"]>=30 and st["z"]>1.645:
                sig_total += 1
                o_oos = bet_outcomes(closes, s, h, mid, len(closes))
                wr_oos = sum(o_oos)/len(o_oos) if o_oos else 0
                if wr_oos > 1/1.90: sig_robust += 1
print(f"  全样本显著(z>1.645)组合 = {sig_total}/{N};其中样本外仍>保本 = {sig_robust}/{N}")
