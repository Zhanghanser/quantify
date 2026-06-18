# -*- coding: utf-8 -*-
"""对 regime_trend(区间过滤趋势)做稳健性压力测试,输出各维度数字 + JSON 汇总。
目的:判断它的边际是【真实可重复】还是【这段下跌行情的运气/过拟合】。"""
import sys, json
if sys.platform == "win32":
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
import numpy as np
import config
from src.data import get_data
from src.strategies import get_strategy
from src.backtest import run_backtest
from src.risk import RiskConfig

LIMIT = 1000
RISK = RiskConfig(stop_loss=0.10, take_profit=0.0, position_size=1.0, max_drawdown_stop=0.0)
BASE_COST = config.FEE_RATE + config.SLIPPAGE
IN_SYM = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]
OOS_SYM = ["BNB/USDT", "XRP/USDT", "DOGE/USDT", "ADA/USDT", "LTC/USDT"]
TFS = ["15m", "1h", "4h"]

_cache = {}
def load(sym, tf):
    if (sym, tf) not in _cache:
        _cache[(sym, tf)] = get_data("crypto", sym, tf, LIMIT)
    return _cache[(sym, tf)]

def run(sym, tf, cost=BASE_COST, params=None):
    df = load(sym, tf)
    sig = get_strategy("regime_trend", **(params or {})).generate(df)
    res = run_backtest(sig, timeframe=tf, risk=RISK, initial_capital=10000, cost=cost)
    t = res["trades"]
    exp = float(np.mean([x["ret"] for x in t])) if t else 0.0
    return res["metrics"]["总收益率"], exp, res["metrics"]["交易次数"]

def agg(syms, tfs, cost=BASE_COST, params=None):
    nets, exps, pos = [], [], 0
    for s in syms:
        for tf in tfs:
            try:
                net, exp, _ = run(s, tf, cost, params)
                nets.append(net); exps.append(exp)
                if net > 0: pos += 1
            except Exception as e:
                print(f"  跳过 {s} {tf}: {e}")
    n = len(nets) or 1
    return dict(mean_net=float(np.mean(nets)), median_net=float(np.median(nets)),
                mean_exp=float(np.mean(exps)), pct_pos=pos / n, n=len(nets))

summary = {}

print("=" * 72)
print("A. 样本内逐数据集净收益(看是不是只靠 1~2 个数据集撑起来的)")
print("=" * 72)
per = {}
for s in IN_SYM:
    line = f"  {s:<10}"
    for tf in TFS:
        net, exp, nt = run(s, tf)
        per[f"{s} {tf}"] = round(net, 4)
        line += f"  {tf}={net:+6.1%}({nt})"
    print(line)
vals = list(per.values())
summary["in_sample"] = dict(per=per, pct_positive=sum(v > 0 for v in vals) / len(vals),
                            best=max(vals), worst=min(vals))
print(f"  → 正收益占比 {summary['in_sample']['pct_positive']:.0%}  最好 {max(vals):+.1%}  最差 {min(vals):+.1%}")

print("\n" + "=" * 72)
print("B. 成本敏感度(成本翻倍/翻3倍还正吗?短线最怕这个)")
print("=" * 72)
summary["cost"] = {}
for mult in [1, 2, 3]:
    a = agg(IN_SYM, TFS, cost=BASE_COST * mult)
    summary["cost"][f"x{mult}"] = a
    print(f"  成本x{mult}({BASE_COST*mult:.4f}): 均净{a['mean_net']:+.1%} 中位{a['median_net']:+.1%} 期望{a['mean_exp']:+.3f}% 正占比{a['pct_pos']:.0%}")

print("\n" + "=" * 72)
print("C. 参数敏感度(是稳健高原 还是 只有一个幸运尖峰)")
print("=" * 72)
summary["param_grid"] = {}
pos_cells = 0; total_cells = 0
for adx_min in [20, 25, 30]:
    line = f"  adx_min={adx_min}"
    for trend_ma in [50, 100, 150]:
        a = agg(IN_SYM, TFS, params=dict(adx_min=adx_min, trend_ma=trend_ma))
        summary["param_grid"][f"adx{adx_min}_ma{trend_ma}"] = round(a["mean_net"], 4)
        line += f"  ma{trend_ma}={a['mean_net']:+5.1%}"
        total_cells += 1; pos_cells += a["mean_net"] > 0
    print(line)
summary["param_pct_positive"] = pos_cells / total_cells
print(f"  → 9 个参数组合里 {pos_cells}/{total_cells} 为正({pos_cells/total_cells:.0%})")

print("\n" + "=" * 72)
print("D. 样本外币种(没参与调参的币:BNB/XRP/DOGE/ADA/LTC)")
print("=" * 72)
oos = agg(OOS_SYM, TFS)
summary["oos"] = oos
print(f"  均净{oos['mean_net']:+.1%} 中位{oos['median_net']:+.1%} 期望{oos['mean_exp']:+.3f}% 正占比{oos['pct_pos']:.0%} (n={oos['n']})")

print("\n" + "=" * 72)
print("E. 做空贡献(allow_short=1 对比 0:边际有多少来自做空?)")
print("=" * 72)
both = agg(IN_SYM + OOS_SYM, TFS, params=dict(allow_short=1))
longonly = agg(IN_SYM + OOS_SYM, TFS, params=dict(allow_short=0))
summary["short_on"] = both; summary["long_only"] = longonly
print(f"  可多可空: 均净{both['mean_net']:+.1%} 期望{both['mean_exp']:+.3f}% 正占比{both['pct_pos']:.0%}")
print(f"  只做多  : 均净{longonly['mean_net']:+.1%} 期望{longonly['mean_exp']:+.3f}% 正占比{longonly['pct_pos']:.0%}")

print("\n" + "=" * 72)
print("JSON_SUMMARY_START")
print(json.dumps(summary, ensure_ascii=False))
print("JSON_SUMMARY_END")
