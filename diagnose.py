# -*- coding: utf-8 -*-
"""策略诊断:多币种×多周期,扣成本后实测每个策略到底有没有边际。"""
import sys
if sys.platform == "win32":
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
import numpy as np
import config
from src.data import get_data
from src.strategies import STRATEGIES, get_strategy
from src.backtest import run_backtest
from src.risk import RiskConfig

SYMBOLS = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]
TFS = ["15m", "1h", "4h"]
LIMIT = 1000
COST = config.FEE_RATE + config.SLIPPAGE          # 单边成本(手续费+滑点)
RISK = RiskConfig(stop_loss=0.10, take_profit=0.0, position_size=1.0, max_drawdown_stop=0.0)

print(f"加载数据... 成本(单边)={COST:.4f}  止损=10%  本金=10000")
data = {}
for s in SYMBOLS:
    for tf in TFS:
        try:
            data[(s, tf)] = get_data("crypto", s, tf, LIMIT)
        except Exception as e:
            print(f"  数据获取失败 {s} {tf}: {e}")
print(f"已加载 {len(data)} 个数据集\n")

rows = []
for name in STRATEGIES:
    nets, sharpes, trds, wins, expects = [], [], [], [], []
    beat_bh = 0
    cnt = 0
    for (s, tf), df in data.items():
        try:
            sig = get_strategy(name).generate(df)
            res = run_backtest(sig, timeframe=tf, risk=RISK, initial_capital=10000, cost=COST)
            m = res["metrics"]
            t = res["trades"]
            exp = float(np.mean([x["ret"] for x in t])) if t else 0.0
            nets.append(m["总收益率"]); sharpes.append(m["夏普比率"])
            trds.append(m["交易次数"]); wins.append(m["胜率"]); expects.append(exp)
            if m["总收益率"] > m["买入持有收益率"]:
                beat_bh += 1
            cnt += 1
        except Exception as e:
            print(f"  回测失败 {name} {s} {tf}: {e}")
    if cnt:
        disp = STRATEGIES[name].display_name
        rows.append((disp, name, float(np.mean(nets)), float(np.median(nets)),
                     float(np.mean(sharpes)), float(np.mean(trds)),
                     float(np.mean(wins)), float(np.mean(expects)) * 100, beat_bh, cnt))

rows.sort(key=lambda r: -r[2])
print(f"{'策略':<12}{'均净收益':>10}{'中位收益':>10}{'夏普':>7}{'均笔数':>7}{'胜率':>7}{'每笔期望%':>11}{'胜过持有':>9}")
print("-" * 80)
for r in rows:
    print(f"{r[0]:<12}{r[2]:>+9.1%}{r[3]:>+9.1%}{r[4]:>7.2f}{r[5]:>7.0f}{r[6]:>7.0%}{r[7]:>+10.3f}{r[8]:>5}/{r[9]}")
print("-" * 80)
print("【每笔期望%】= 平均每笔交易扣完成本的净收益。<0 = 这个策略在这批行情里是负期望(越交易越亏)。")
