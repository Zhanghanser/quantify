# -*- coding: utf-8 -*-
"""
全局配置文件。
所有可调参数都集中放在这里,改这一个文件就能调整整个程序的行为。
新手只需要改这里的几个值,就能换币种、换周期、调策略。
"""

# ========== 数据相关 ==========

# 市场:决定用哪个数据源。可选:
#   "crypto"  币圈(默认)   "astock" A股   "usstock" 美股
# 换市场记得同时把下面的 SYMBOL 改成对应格式。
MARKET = "crypto"

# 交易标的(代码)。不同市场格式不同:
#   币圈:  "BTC/USDT"、"ETH/USDT"
#   A股:   "000001"(平安银行)、"600519"(贵州茅台)  ← 6位数字
#   美股:  "AAPL"、"TSLA"、"NVDA"
SYMBOL = "BTC/USDT"

# K线周期(每根蜡烛代表多长时间):
#   "1m"=1分钟  "5m"=5分钟  "15m"=15分钟  "1h"=1小时  "4h"=4小时  "1d"=1天
# 短线一般用 15m / 1h。新手建议先用 1h(数据量适中,信号不会太频繁)。
TIMEFRAME = "4h"

# 下载多少根K线(历史数据长度)。1000 根 1小时线 ≈ 41 天。
LIMIT = 1000

# 优先尝试的交易所列表(按顺序尝试,某个连不上就自动换下一个)。
# 国内网络环境下,gate(gate.io)实测可直连,binance/okx/kucoin 多被墙、连不上会白等几十秒,
# 所以把 gate 放最前面,冷启动拉新周期时不用先卡在那几个连不上的交易所上。
EXCHANGES = ["gate", "mexc", "bybit", "binance", "okx", "kucoin"]

# 当所有交易所都连不上时,是否用"模拟生成的离线数据"兜底,
# 好处:没有梯子也能先把整套流程跑通、看到结果。
# 注意:模拟数据是随机生成的假数据,只能用来熟悉流程,绝不能用于真实策略判断!
ALLOW_SYNTHETIC_FALLBACK = True


# ========== 策略选择与参数 ==========

# 用哪个策略。可选:"dual_ma"(双均线)、"rsi_reversion"(RSI均值回归)、"breakout"(突破)
STRATEGY = "trend_filter"

# --- 双均线策略参数 ---
# 快线周期:短期均线,反应灵敏。
FAST_MA = 10
# 慢线周期:长期均线,反应迟钝、更平滑。
SLOW_MA = 30
# 策略逻辑:快线上穿慢线 → 买入;快线下穿慢线 → 卖出/空仓。


# ========== 回测交易成本 ==========

# 手续费率(单边)。币安现货约 0.1% = 0.001。
FEE_RATE = 0.001
# 滑点(实际成交价和理想价的偏差),按比例估算。短线务必考虑。
SLIPPAGE = 0.0005

# 初始资金(回测假设的本金,单位 USDT)。
INITIAL_CAPITAL = 10000


# ========== 路径 ==========
import os
import sys

# 兼容 PyInstaller 打包:打包成 exe 后,程序代码/网页被解包到临时目录(_MEIPASS),
# 而缓存这类需要"写得进、留得住"的文件必须放在可写位置,不能放进只读的解包目录。
# 所以这里把【只读资源目录 RESOURCE_DIR】(web 网页)和【可写数据目录 DATA_DIR】(data 缓存)分开。


def _is_writable(d):
    """探测目录可写性:决定缓存放 exe 旁边还是退回用户目录。"""
    try:
        os.makedirs(d, exist_ok=True)
        probe = os.path.join(d, ".write_test")
        with open(probe, "w") as f:
            f.write("ok")
        os.remove(probe)
        return True
    except Exception:
        return False


if getattr(sys, "frozen", False):
    # 已打包运行:
    EXE_DIR = os.path.dirname(sys.executable)              # exe 所在目录
    BASE_DIR = EXE_DIR
    RESOURCE_DIR = getattr(sys, "_MEIPASS", EXE_DIR)       # 打包进去的 web/ 在这里(只读)
    # 缓存目录:优先写 exe 旁边(免安装绿色版自包含);若装到了 Program Files 等只读位置写不进,
    # 自动退回用户目录 %LOCALAPPDATA%\quantify-terminal\data,保证装到哪都能跑、不会因写不进而崩。
    _beside_exe = os.path.join(EXE_DIR, "data")
    if _is_writable(_beside_exe):
        DATA_DIR = _beside_exe
    else:
        DATA_DIR = os.path.join(
            os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"),
            "quantify-terminal", "data",
        )
else:
    # 源码方式运行:就是这个文件所在的目录
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    RESOURCE_DIR = BASE_DIR
    DATA_DIR = os.path.join(BASE_DIR, "data")
