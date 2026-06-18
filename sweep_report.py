# -*- coding: utf-8 -*-
"""
全策略·完美量化扫描(可复现)。
口径写死:现货收盘价;单边成本0.0015(0.1%手续费+0.05%滑点);止损10%、满仓、无止盈/熔断;
信号 t-1 决策、t 执行(无前视);夏普 rf=0(年化);样本外=时间后30%。
"""
import sys, math
if sys.platform == "win32":
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
import numpy as np
import pandas as pd
from src.data import get_data
from src.strategies import STRATEGIES, get_strategy
from src.backtest import run_backtest
from src.risk import RiskConfig

SYMBOLS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT"]
TFS = ["15m", "1h", "4h", "1d"]
LIMIT = 1000
COST = 0.0015
RISK = RiskConfig(stop_loss=0.10, take_profit=0.0, position_size=1.0, max_drawdown_stop=0.0)
OOS_FRAC = 0.30                      # 末尾30%作时间样本外

def norm_sf(z): return 0.5 * math.erfc(z / math.sqrt(2))

# ---------- 取数 + 完整性 ----------
DATA = {}
print("=" * 88)
print("数据完整性(数据源 gate.io 现货·ccxt·每集请求1000根)")
print("=" * 88)
for s in SYMBOLS:
    for tf in TFS:
        try:
            df = get_data("crypto", s, tf, LIMIT)
            DATA[(s, tf)] = df
        except Exception as e:
            print(f"  {s} {tf} 取数失败: {e}")
for (s, tf), df in DATA.items():
    idx = df.index
    span_days = (idx[-1] - idx[0]).total_seconds() / 86400
    rets = (df["close"] / df["close"].shift(1) - 1).abs()
    anom = int((rets > 0.5).sum())
    print(f"  {s:<10}{tf:>4}  根数={len(df):>4}  跨度={span_days:>6.1f}天  异常(>50%)={anom}  {idx[0].date()}~{idx[-1].date()}")

# ---------- 单次回测 → 指标(含时间样本内/外切分)----------
def metrics_one(name, s, tf):
    df = DATA[(s, tf)]
    sig = get_strategy(name).generate(df)
    res = run_backtest(sig, timeframe=tf, risk=RISK, initial_capital=10000, cost=COST)
    m, trades = res["metrics"], res["trades"]
    eq = res["df"]["equity"].values
    n = len(eq)
    cut = int(n * (1 - OOS_FRAC))
    is_net = eq[cut - 1] / eq[0] - 1 if cut > 1 else 0.0
    oos_net = eq[-1] / eq[cut - 1] - 1 if cut >= 1 and eq[cut - 1] > 0 else 0.0
    cut_time = df.index[cut]
    tr_rets = [t["ret"] for t in trades]
    oos_tr = [t["ret"] for t in trades if t["entry_time"] is not None and t["entry_time"] >= cut_time]
    return dict(net=m["总收益率"], bh=m["买入持有收益率"], sharpe=m["夏普比率"],
                mdd=m["最大回撤"], trades=m["交易次数"], wr=m["胜率"],
                rets=tr_rets, is_net=is_net, oos_net=oos_net, oos_rets=oos_tr)

# ---------- 跑全矩阵 ----------
rows = {}
for name in STRATEGIES:
    rows[name] = [metrics_one(name, s, tf) for (s, tf) in DATA]

print("\n" + "=" * 88)
print("全策略汇总(5币×4周期=20数据集;net=均净收益;每笔期望=池化所有交易的均值,t检验 vs 0)")
print("口径:成本0.0015单边·止损10%·满仓·夏普rf=0年化·样本外=时间末30%")
print("=" * 88)
print(f"{'策略':<12}{'均净':>7}{'中位':>7}{'超额BH':>8}{'胜BH':>6}{'均笔':>6}{'胜率':>6}{'每笔期望%':>10}{'t值':>6}{'p':>7}{'正期望集':>8}")
print("-" * 88)
agg = []
for name in STRATEGIES:
    rs = rows[name]
    nets = [r["net"] for r in rs]
    excess = [r["net"] - r["bh"] for r in rs]
    beat = sum(1 for r in rs if r["net"] > r["bh"])
    pooled = [x for r in rs for x in r["rets"]]
    pos_sets = sum(1 for r in rs if (np.mean(r["rets"]) if r["rets"] else -1) > 0)
    if len(pooled) > 1 and np.std(pooled) > 0:
        t = np.mean(pooled) / (np.std(pooled, ddof=1) / math.sqrt(len(pooled)))
        p = norm_sf(t)
    else:
        t = p = float("nan")
    exp = np.mean(pooled) * 100 if pooled else 0.0
    disp = STRATEGIES[name].display_name
    agg.append((disp, name, float(np.mean(nets)), float(np.median(nets)), float(np.mean(excess)),
                beat, float(np.mean([r["trades"] for r in rs])), float(np.mean([r["wr"] for r in rs])),
                exp, t, p, pos_sets, len(pooled)))
agg.sort(key=lambda a: -a[3])   # 按中位净收益排
for a in agg:
    print(f"{a[0]:<12}{a[2]:>+6.1%}{a[3]:>+7.1%}{a[4]:>+8.1%}{a[5]:>4}/20{a[6]:>6.0f}{a[7]:>6.0%}"
          f"{a[8]:>+9.3f}{a[9]:>+6.2f}{a[10]:>7.3f}{a[11]:>5}/20")

print("\n" + "=" * 88)
print("六件套(池化全部交易;胜率带95%区间;保本胜率=1/(1+盈亏比);成本已扣)")
print("=" * 88)
print(f"{'策略':<12}{'胜率(±CI)':>14}{'保本胜率':>9}{'盈亏比':>7}{'每笔期望%':>10}{'夏普(均)':>9}{'最差回撤':>9}{'总笔数':>7}{'跑赢B&H':>8}")
print("-" * 88)
six = []
for name in STRATEGIES:
    rs = rows[name]
    pooled = [x for r in rs for x in r["rets"]]
    n = len(pooled)
    wins_r = [x for x in pooled if x > 0]
    loss_r = [x for x in pooled if x <= 0]
    wr = len(wins_r) / n if n else 0.0
    ci = 1.96 * math.sqrt(wr * (1 - wr) / n) if n else 0.0
    avg_w = float(np.mean(wins_r)) if wins_r else 0.0
    avg_l = abs(float(np.mean(loss_r))) if loss_r else 0.0
    pnl = avg_w / avg_l if avg_l > 0 else float("inf")
    be_wr = 1 / (1 + pnl) if pnl != float("inf") else 0.0
    exp = float(np.mean(pooled)) * 100 if n else 0.0
    sharpe = float(np.mean([r["sharpe"] for r in rs]))
    worst_dd = float(np.min([r["mdd"] for r in rs]))
    beat = sum(1 for r in rs if r["net"] > r["bh"])
    six.append((STRATEGIES[name].display_name, wr, ci, be_wr, pnl, exp, sharpe, worst_dd, n, beat))
six.sort(key=lambda a: -a[5])
for a in six:
    pnl_s = "inf" if a[4] == float("inf") else f"{a[4]:.2f}"
    print(f"{a[0]:<12}{a[1]*100:>6.1f}±{a[2]*100:>4.1f}%{a[3]*100:>8.1f}%{pnl_s:>7}{a[5]:>+9.3f}"
          f"{a[6]:>+9.2f}{a[7]:>+9.1%}{a[8]:>7}{a[9]:>5}/20")

print("\n" + "=" * 88)
print("时间样本内→样本外(每集前70%=样本内净收益,末30%=样本外净收益;看稳定性)")
print("=" * 88)
print(f"{'策略':<12}{'样本内均净':>11}{'样本外均净':>11}{'样本外正集':>10}{'样本外每笔期望%':>15}")
print("-" * 88)
oos_rank = []
for name in STRATEGIES:
    rs = rows[name]
    is_mean = float(np.mean([r["is_net"] for r in rs]))
    oos_mean = float(np.mean([r["oos_net"] for r in rs]))
    oos_pos = sum(1 for r in rs if r["oos_net"] > 0)
    oos_pooled = [x for r in rs for x in r["oos_rets"]]
    oos_exp = np.mean(oos_pooled) * 100 if oos_pooled else 0.0
    oos_rank.append((STRATEGIES[name].display_name, is_mean, oos_mean, oos_pos, oos_exp))
oos_rank.sort(key=lambda a: -a[2])
for a in oos_rank:
    print(f"{a[0]:<12}{a[1]:>+10.1%}{a[2]:>+11.1%}{a[3]:>7}/20{a[4]:>+14.3f}")

print("\n" + "=" * 88)
print("各周期最佳(按该周期5币的中位净收益)")
print("=" * 88)
for tf in TFS:
    best = None
    for name in STRATEGIES:
        nets = [metrics_one(name, s, tf)["net"] for s in SYMBOLS if (s, tf) in DATA]
        med = float(np.median(nets))
        if best is None or med > best[1]:
            best = (STRATEGIES[name].display_name, med, nets)
    print(f"  {tf:>4}: {best[0]:<12} 中位净收益 {best[1]:+.1%}  (5币: {[f'{x:+.0%}' for x in best[2]]})")

N = len(STRATEGIES) * len(DATA)
print("\n多重检验:共 {} 个(策略×数据集)回测;若按每笔期望t>1.645当显著,α=0.05期望假阳性≈{:.1f}个".format(N, 0.05*len(STRATEGIES)))
