# -*- coding: utf-8 -*-
"""
改造策略检验:vol_trend(波动率门控趋势) vs 区间过滤趋势(regime_trend,基准)。
口径:gate现货·成本0.0015单边·满仓·5币×4周期=20数据集·样本外=时间末30%。
基准 regime_trend 用固定止损10%(与扫描报告一致);新策略 vol_trend 用自带ATR追踪(引擎止损关)。
"""
import sys, math
if sys.platform == "win32":
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
import numpy as np
from src.data import get_data
from src.strategies import get_strategy
from src.backtest import run_backtest
from src.risk import RiskConfig, NO_RISK

SYMBOLS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT"]
TFS = ["15m", "1h", "4h", "1d"]
LIMIT = 1000
COST = 0.0015
BASE_RISK = RiskConfig(stop_loss=0.10, take_profit=0.0, position_size=1.0, max_drawdown_stop=0.0)

_cache = {}
def load(s, tf):
    if (s, tf) not in _cache:
        _cache[(s, tf)] = get_data("crypto", s, tf, LIMIT)
    return _cache[(s, tf)]

def bt(stratname, s, tf, risk, cost=COST, **params):
    df = load(s, tf)
    sig = get_strategy(stratname, **params).generate(df)
    res = run_backtest(sig, timeframe=tf, risk=risk, initial_capital=10000, cost=cost)
    m, trades = res["metrics"], res["trades"]
    eq = res["df"]["equity"].values
    n = len(eq); cut = int(n * 0.7)
    oos_net = eq[-1] / eq[cut - 1] - 1 if eq[cut - 1] > 0 else 0.0
    return dict(net=m["总收益率"], bh=m["买入持有收益率"], sharpe=m["夏普比率"],
                mdd=m["最大回撤"], rets=[t["ret"] for t in trades],
                oos_net=oos_net, gate_skipped=sig.attrs.get("gate_skipped", 0))

def sixpack(allrows):
    nets = [r["net"] for r in allrows]
    pooled = [x for r in allrows for x in r["rets"]]
    n = len(pooled)
    w = [x for x in pooled if x > 0]; lo = [abs(x) for x in pooled if x <= 0]
    wr = len(w) / n if n else 0.0
    pnl = (np.mean(w) / np.mean(lo)) if w and lo else float("inf")
    be = 1 / (1 + pnl) if pnl != float("inf") else 0.0
    exp = np.mean(pooled) * 100 if n else 0.0
    t = (np.mean(pooled) / (np.std(pooled, ddof=1) / math.sqrt(n))) if n > 1 and np.std(pooled) > 0 else 0.0
    return dict(wr=wr, pnl=pnl, be=be, exp=exp, t=t, n=n,
                med_net=float(np.median(nets)), mean_net=float(np.mean(nets)),
                beat=sum(1 for r in allrows if r["net"] > r["bh"]),
                sharpe=float(np.mean([r["sharpe"] for r in allrows])),
                worst_mdd=float(np.min([r["mdd"] for r in allrows])),
                oos_mean=float(np.mean([r["oos_net"] for r in allrows])),
                oos_pos=sum(1 for r in allrows if r["oos_net"] > 0))

# ---------- 基准 vs 改造 ----------
base_rows = [bt("regime_trend", s, tf, BASE_RISK) for s in SYMBOLS for tf in TFS]
new_rows = [bt("vol_trend", s, tf, NO_RISK) for s in SYMBOLS for tf in TFS]
B, Nw = sixpack(base_rows), sixpack(new_rows)

def line(label, b, n, pct=True, dec=1):
    f = (lambda x: f"{x*100:+.{dec}f}%") if pct else (lambda x: f"{x:.{dec}f}")
    return f"{label:<10}{f(b):>10} → {f(n):>10}   变化 {f(n-b) if pct else f'{n-b:+.{dec}f}'}"

print("=" * 60)
print("  改造策略检验: 波动率门控趋势(vol_trend) vs 区间过滤趋势(基准)")
print("=" * 60)
print("\n--- 改造参数 ---")
print("fast_ema=20 slow_ema=100 volatility_gate=0.35 atr_multiplier=2.5 trend_strength_min=0.02 cooling=3")
print("\n--- 改造前 vs 改造后(池化20数据集) ---")
print(f"胜率:     {B['wr']*100:.1f}% → {Nw['wr']*100:.1f}%   变化 {(Nw['wr']-B['wr'])*100:+.1f}pp")
print(f"盈亏比:   {B['pnl']:.2f} → {Nw['pnl']:.2f}   变化 {Nw['pnl']-B['pnl']:+.2f}")
print(f"保本胜率: {B['be']*100:.1f}% → {Nw['be']*100:.1f}%")
print(f"每笔期望: {B['exp']:+.3f}% → {Nw['exp']:+.3f}%   变化 {Nw['exp']-B['exp']:+.3f}pp  (新t={Nw['t']:+.2f})")
print(f"中位净收益:{B['med_net']*100:+.1f}% → {Nw['med_net']*100:+.1f}%")
print(f"最差回撤: {B['worst_mdd']*100:+.1f}% → {Nw['worst_mdd']*100:+.1f}%   变化 {(Nw['worst_mdd']-B['worst_mdd'])*100:+.1f}pp")
print(f"跑赢B&H:  {B['beat']}/20 → {Nw['beat']}/20   变化 {Nw['beat']-B['beat']:+d}")
print(f"夏普(均): {B['sharpe']:+.2f} → {Nw['sharpe']:+.2f}   变化 {Nw['sharpe']-B['sharpe']:+.2f}")
print(f"总笔数:   {B['n']} → {Nw['n']}")

print("\n--- 样本外(时间末30%) ---")
print(f"基准: 均净{B['oos_mean']*100:+.1f}%  正集{B['oos_pos']}/20")
print(f"改造: 均净{Nw['oos_mean']*100:+.1f}%  正集{Nw['oos_pos']}/20")

# ---------- 淘汰交易分析:门控开 vs 关 ----------
nogate_rows = [bt("vol_trend", s, tf, NO_RISK, volatility_gate=0.0) for s in SYMBOLS for tf in TFS]
G = sixpack(nogate_rows)
skipped = sum(r["gate_skipped"] for r in new_rows)
extra_trades = G["n"] - Nw["n"]
print("\n--- 淘汰交易分析(波动率门控 开0.35 vs 关) ---")
print(f"门控挡下的'本可开仓'根数(20集合计): {skipped}")
print(f"关掉门控后的总笔数 {G['n']}  vs 开门控 {Nw['n']}  → 门控少做 {extra_trades} 笔")
print(f"关门控胜率{G['wr']*100:.1f}% 每笔期望{G['exp']:+.3f}%  vs 开门控胜率{Nw['wr']*100:.1f}% 每笔期望{Nw['exp']:+.3f}%")
print(f"关门控中位净{G['med_net']*100:+.1f}% 跑赢B&H{G['beat']}/20  vs 开门控中位净{Nw['med_net']*100:+.1f}% 跑赢B&H{Nw['beat']}/20")

# ---------- 参数敏感性:volatility_gate ----------
print("\n--- 参数敏感性: volatility_gate 0.15→0.55 ---")
print(f"{'gate':>6}{'胜率':>7}{'盈亏比':>7}{'每笔期望%':>10}{'中位净':>8}{'跑赢B&H':>8}")
for g in [0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55]:
    rr = [bt("vol_trend", s, tf, NO_RISK, volatility_gate=g) for s in SYMBOLS for tf in TFS]
    S = sixpack(rr)
    print(f"{g:>6.2f}{S['wr']*100:>6.1f}%{S['pnl']:>7.2f}{S['exp']:>+9.3f}{S['med_net']*100:>+7.1f}%{S['beat']:>5}/20")

# ---------- 成本压力 ----------
print("\n--- 成本压力: 单边成本 0.001→0.004 ---")
print(f"{'cost':>7}{'胜率':>7}{'每笔期望%':>10}{'中位净':>8}{'跑赢B&H':>8}")
for cst in [0.001, 0.0015, 0.002, 0.003, 0.004]:
    rr = [bt("vol_trend", s, tf, NO_RISK, cost=cst) for s in SYMBOLS for tf in TFS]
    S = sixpack(rr)
    print(f"{cst:>7.4f}{S['wr']*100:>6.1f}%{S['exp']:>+9.3f}{S['med_net']*100:>+7.1f}%{S['beat']:>5}/20")

# ---------- 各周期(改造后)----------
print("\n--- 改造后各周期(5币中位净收益) ---")
for tf in TFS:
    rr = [bt("vol_trend", s, tf, NO_RISK) for s in SYMBOLS]
    print(f"  {tf:>4}: 中位净{np.median([r['net'] for r in rr])*100:+.1f}%  跑赢B&H{sum(1 for r in rr if r['net']>r['bh'])}/5")
