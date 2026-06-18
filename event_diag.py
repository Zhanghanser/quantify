# -*- coding: utf-8 -*-
"""事件合约诚实诊断:多币×多时长×多信号,看有没有任何组合【显著且稳定】跑赢保本线。"""
import sys
if sys.platform == "win32":
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
from src.data import get_data
from src import event_contract as ec

COINS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT", "DOGE/USDT"]
HORIZONS = [1, 3, 5, 10, 30]
SIGNALS = ["momentum", "reversion"]
PAYOUT = 1.8

print(f"赔率={PAYOUT} → 保本胜率={1/PAYOUT:.1%}  (1m数据·每币1000根)")
data = {}
for c in COINS:
    try:
        data[c] = get_data("crypto", c, "1m", 1000)
    except Exception as e:
        print(f"  {c} 数据失败: {e}")

total = sig_count = stable_sig = above_naive = 0
best = []
for c, df in data.items():
    for h in HORIZONS:
        for s in SIGNALS:
            cfg = ec.EventConfig(horizon_minutes=h, payout=PAYOUT)
            bt = ec.backtest(df, cfg, s)
            total += 1
            if bt["win_rate"] > bt["breakeven"]:
                above_naive += 1
            if bt["significant"]:
                sig_count += 1
                if "稳定" in bt["verdict"]:
                    stable_sig += 1
                    best.append((c, h, s, bt["win_rate"], bt["z_score"], bt["verdict"]))

print(f"\n共测 {total} 个(币×时长×信号)组合,赔率 {PAYOUT}:")
print(f"  胜率>保本线(天真口径)        : {above_naive}/{total}  ({above_naive/total:.0%})")
print(f"  其中【统计显著】跑赢保本       : {sig_count}/{total}  ({sig_count/total:.0%})")
print(f"  其中【显著且前后半段都稳】     : {stable_sig}/{total}  ({stable_sig/total:.0%})")
if best:
    print("\n  显著且稳定的组合(即便如此也仍属高风险):")
    for c, h, s, wr, z, v in best:
        print(f"    {c:<10} {h:>2}分 {s:<10} 胜率{wr:.1%} z={z:.2f}  {v}")
else:
    print("\n  → 没有任何组合【显著且稳定】跑赢保本线。这与二元期权的数学一致:")
    print("    赔率<2 时房子有结构性优势,短线方向预测的真实胜率压不过保本线。")

# 示例:BTC 各时长两种信号的明细 + 每笔期望(钱)
print("\n示例明细 BTC/USDT(下注10元):")
df = data.get("BTC/USDT")
if df is not None:
    for h in HORIZONS:
        for s in SIGNALS:
            bt = ec.backtest(df, ec.EventConfig(horizon_minutes=h, payout=PAYOUT, bet_size=10), s)
            print(f"  {h:>2}分 {s:<10} 胜率{bt['win_rate']:.1%} 保本{bt['breakeven']:.1%} "
                  f"z={bt['z_score']:+.2f} 每笔期望{bt['ev_per_bet']:+.2f}元/{bt['bets']}笔 → {bt['verdict']}")
