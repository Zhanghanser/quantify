# -*- coding: utf-8 -*-
"""
专业K线交易终端(入口7,仿 Binance / OKX 盘面)。

运行方法:
    python run_web.py
然后浏览器打开  http://localhost:8000

架构(前后端分离,和真实交易所网站同构):
  - 后端:FastAPI,提供两类接口
      /api/klines    行情K线(走项目统一数据源,带缓存)
      /api/backtest  跑回测,返回买卖点/资金曲线/绩效指标
  - 前端:web/ 目录下的纯网页,图表用 TradingView 开源引擎
    lightweight-charts —— Binance、OKX 官网盘面用的就是 TradingView 技术。

⚠️ 和项目其它入口一样:只回测、只显示信号,绝不下单、不碰真钱。
"""

import sys
if sys.platform == "win32":
    # Windows 控制台默认 GBK,数据模块打印 emoji 会崩,统一切 UTF-8
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import math
import os
import time

import requests
import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import config
from src.data import get_data
from src.strategies import STRATEGIES, get_strategy
from src.backtest import run_backtest
from src.risk import RiskConfig
from src import indicators

app = FastAPI(title="quantify 交易终端")

WEB_DIR = os.path.join(config.RESOURCE_DIR, "web")   # 打包后 web/ 在解包资源目录里

# ============ 前端需要的元信息:市场 / 周期 / 策略参数定义 ============

MARKETS = {
    "crypto":  {"label": "币圈",
                "presets": ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT"],
                # 币圈 24 小时连续交易,周期最全
                "timeframes": ["1m", "3m", "5m", "15m", "30m", "1h", "4h", "1d", "1w", "1M"]},
    "astock":  {"label": "A股",
                "presets": ["000001", "600519", "300750"],
                # A股免费源只有日线稳定,周/月由日线合成;日内分钟暂不支持
                "timeframes": ["1d", "1w", "1M"]},
    "usstock": {"label": "美股",
                "presets": ["AAPL", "TSLA", "NVDA", "MSFT"],
                # 美股雅虎:日内仅近期有数据,日/周/月历史完整
                "timeframes": ["5m", "15m", "30m", "1h", "1d", "1w", "1M"]},
    "futures": {"label": "期货",
                # 主连(主力连续,代码+0):到期自动换月,适合连续回测
                "presets": ["RB0", "IF0", "SC0", "AU0", "AG0", "I0", "M0", "CU0"],
                "timeframes": ["5m", "15m", "30m", "1h", "1d", "1w", "1M"]},
}

# 每个策略暴露给界面的参数(范围 + 默认值),改这里界面会自动跟着变
STRATEGY_SCHEMAS = {
    "dual_ma": [
        {"key": "fast", "label": "快线周期", "value": 10, "min": 2, "max": 200},
        {"key": "slow", "label": "慢线周期", "value": 30, "min": 5, "max": 400},
    ],
    "rsi_reversion": [
        {"key": "period", "label": "RSI周期", "value": 14, "min": 2, "max": 50},
        {"key": "oversold", "label": "超卖线", "value": 30, "min": 5, "max": 49},
        {"key": "exit_level", "label": "离场线", "value": 50, "min": 35, "max": 90},
    ],
    "breakout": [
        {"key": "lookback", "label": "通道周期", "value": 20, "min": 5, "max": 200},
    ],
    "trend_filter": [
        {"key": "fast", "label": "快线周期", "value": 20, "min": 2, "max": 100},
        {"key": "slow", "label": "慢线周期", "value": 50, "min": 10, "max": 200},
        {"key": "trend", "label": "大趋势线", "value": 100, "min": 30, "max": 400},
    ],
    # 短线策略包(部分参数是小数,带 step)
    "boll_bounce": [
        {"key": "period", "label": "布林周期", "value": 20, "min": 5, "max": 100},
        {"key": "k", "label": "标准差倍数", "value": 2, "min": 1, "max": 4, "step": 0.1},
    ],
    "rsi_scalp": [
        {"key": "period", "label": "RSI周期", "value": 2, "min": 2, "max": 14},
        {"key": "buy", "label": "买入线", "value": 10, "min": 2, "max": 40},
        {"key": "exit_level", "label": "离场线", "value": 60, "min": 40, "max": 90},
    ],
    "momo_breakout": [
        {"key": "lookback", "label": "通道周期", "value": 20, "min": 5, "max": 100},
        {"key": "vol_mult", "label": "放量倍数", "value": 1.5, "min": 1, "max": 5, "step": 0.1},
    ],
    "vwap_revert": [
        {"key": "window", "label": "VWAP周期", "value": 20, "min": 5, "max": 100},
        {"key": "dev", "label": "偏离%", "value": 1.0, "min": 0.1, "max": 5, "step": 0.1},
    ],
    "boll_rsi": [
        {"key": "period", "label": "布林周期", "value": 20, "min": 5, "max": 100},
        {"key": "k", "label": "标准差倍数", "value": 2, "min": 1, "max": 4, "step": 0.1},
        {"key": "rsi_period", "label": "RSI周期", "value": 14, "min": 2, "max": 30},
        {"key": "oversold", "label": "超卖线", "value": 30, "min": 5, "max": 45},
        {"key": "exit_level", "label": "离场线", "value": 50, "min": 35, "max": 80},
    ],
    "regime_trend": [
        {"key": "adx_period", "label": "ADX周期", "value": 14, "min": 5, "max": 50},
        {"key": "adx_min", "label": "趋势阈值ADX", "value": 25, "min": 10, "max": 50},
        {"key": "trend_ma", "label": "大趋势线", "value": 100, "min": 20, "max": 400},
        {"key": "allow_short", "label": "可做空(1开0关)", "value": 1, "min": 0, "max": 1, "step": 1},
    ],
}

# 策略生成的指标列 → 中文名(回测后画在主图上)
OVERLAY_COLUMNS = [("ma_fast", "策略快线"), ("ma_slow", "策略慢线"),
                   ("ma_trend", "大趋势线"), ("upper", "通道上轨"), ("lower", "通道下轨")]

# ============ 标的中文名(让用户看到"600519 贵州茅台"而不是干巴巴的代码)============

# 币圈常见币种 base → 中文/通俗名
CRYPTO_NAMES = {
    "BTC": "比特币", "ETH": "以太坊", "SOL": "Solana", "BNB": "币安币",
    "XRP": "瑞波币", "DOGE": "狗狗币", "ADA": "艾达币", "AVAX": "Avalanche",
    "LINK": "Chainlink", "TRX": "波场", "TON": "Toncoin", "DOT": "波卡",
    "MATIC": "Polygon", "LTC": "莱特币", "BCH": "比特现金", "SHIB": "柴犬币",
}
# 美股常见票 ticker → 中文名
US_NAMES = {
    "AAPL": "苹果", "TSLA": "特斯拉", "NVDA": "英伟达", "MSFT": "微软",
    "GOOGL": "谷歌", "AMZN": "亚马逊", "META": "Meta", "AMD": "AMD",
    "NFLX": "奈飞", "INTC": "英特尔", "KO": "可口可乐", "BABA": "阿里巴巴",
}
# 期货主连(代码+0)→ 中文名
FUTURES_NAMES = {
    "RB0": "螺纹钢主连", "I0": "铁矿石主连", "HC0": "热卷主连", "CU0": "沪铜主连", "AL0": "沪铝主连",
    "ZN0": "沪锌主连", "NI0": "沪镍主连", "AU0": "黄金主连", "AG0": "白银主连", "SC0": "原油主连",
    "FU0": "燃油主连", "BU0": "沥青主连", "RU0": "橡胶主连", "J0": "焦炭主连", "JM0": "焦煤主连",
    "M0": "豆粕主连", "Y0": "豆油主连", "P0": "棕榈油主连", "C0": "玉米主连", "CF0": "棉花主连",
    "SR0": "白糖主连", "TA0": "PTA主连", "MA0": "甲醇主连", "EG0": "乙二醇主连", "SA0": "纯碱主连",
    "FG0": "玻璃主连", "AP0": "苹果主连", "IF0": "沪深300主连", "IH0": "上证50主连",
    "IC0": "中证500主连", "IM0": "中证1000主连", "T0": "十年国债主连",
}
# A股名字按需向新浪实时行情查,查到的缓存起来(只缓存成功结果,失败不缓存以便下次重试)。
# 预设标的的名字直接内置,这样 /api/meta 首屏不会被新浪网络请求拖慢(只有用户手输的代码才联网查)。
_ASTOCK_NAME_CACHE = {"000001": "平安银行", "600519": "贵州茅台", "300750": "宁德时代"}
_ASTOCK_NAME_NEG = {}   # 查不到的代码 → 负缓存到期时间(短期内不再反复联网 6 秒)


def _astock_name(code: str) -> str:
    code = str(code).strip()
    if code in _ASTOCK_NAME_CACHE:
        return _ASTOCK_NAME_CACHE[code]
    if _ASTOCK_NAME_NEG.get(code, 0) > time.time():   # 负缓存未过期 → 直接返回代码,不联网
        return code
    try:
        from src.data.astock import AStockData
        sym = AStockData._sina_symbol(code)
        # 显式 proxies=None 直连(新浪是境内站,走 VPN 代理反而连不上),不再 monkey-patch 全局
        sess = requests.Session()
        sess.trust_env = False
        r = sess.get(f"https://hq.sinajs.cn/list={sym}",
                     headers={"Referer": "https://finance.sina.com.cn"},
                     timeout=6, proxies={"http": None, "https": None})
        r.encoding = "gbk"           # 新浪返回 GBK 编码
        name = r.text.split('"')[1].split(",")[0].strip()
        if name:
            _ASTOCK_NAME_CACHE[code] = name
            return name
    except Exception:
        pass
    _ASTOCK_NAME_NEG[code] = time.time() + 600   # 查失败:10 分钟内不再重试,避免每次请求都卡 6 秒
    return code   # 查不到就退回代码本身


def _resolve_name(market: str, symbol: str) -> str:
    """把代码解析成"看得懂的名字",查不到就返回代码本身。"""
    if market == "astock":
        return _astock_name(symbol)
    if market == "crypto":
        return CRYPTO_NAMES.get(str(symbol).split("/")[0].upper(), str(symbol).split("/")[0].upper())
    if market == "usstock":
        t = str(symbol).upper()
        return US_NAMES.get(t, t)
    if market == "futures":
        s = str(symbol).strip().upper().replace(" ", "")
        if s and s[-1].isalpha():
            s += "0"          # 纯字母 → 主连
        return FUTURES_NAMES.get(s, s)
    return str(symbol)


def _ts(index_value) -> int:
    """pandas 时间索引 → unix 秒(lightweight-charts 的时间格式)。"""
    return int(index_value.timestamp())


def _points(index, values):
    """一列数值 → [{time, value}],自动跳过 NaN(JSON 不允许 NaN)。"""
    out = []
    for ts, v in zip(index, values):
        v = float(v)
        if math.isnan(v) or math.isinf(v):
            continue
        out.append({"time": _ts(ts), "value": v})
    return out


def _safe(v):
    """把 NaN/Inf 等非法 float 转成 None,确保 JSON 合法(否则前端 JSON.parse 直接崩)。"""
    if isinstance(v, bool):
        return v
    if isinstance(v, float):
        return v if math.isfinite(v) else None
    return v


# 各市场取数失败时给用户的人话提示(原始英文堆栈只进服务端日志,不糊用户脸上)
_FRIENDLY = {
    "crypto": "交易所连接失败,请稍后重试(币圈默认走 gate.io,通常可直连)。",
    "astock": "A股取数失败,请确认代码为6位数字(如 600519),且本机能联网。",
    "usstock": "雅虎财经连接失败,美股行情在国内通常需要科学上网。",
}


def _friendly_err(market: str, e: Exception) -> str:
    print(f"❌ [{market}] 取数失败:{e}")   # 详细错误进服务端日志
    return _FRIENDLY.get(market, f"取数失败:{e}")


def _validate(market: str, timeframe: str):
    if market not in MARKETS:
        raise HTTPException(status_code=400, detail=f"未知市场 {market}")
    if timeframe not in MARKETS[market]["timeframes"]:
        raise HTTPException(status_code=400,
                            detail=f"{MARKETS[market]['label']}暂不支持周期 {timeframe}")


# 各周期秒数(算平均持仓多少根用)
_TF_SEC = {"1m": 60, "3m": 180, "5m": 300, "15m": 900, "30m": 1800, "1h": 3600,
           "2h": 7200, "4h": 14400, "8h": 28800, "1d": 86400, "1w": 604800, "1M": 2592000}


def _trade_health(trades, days, timeframe, cost, size):
    """短线体检报告:把'这套短打到底是赚是在给交易所打工'量化出来。"""
    n = len(trades)
    if n == 0:
        return {"trades": 0}
    rets = [float(t["ret"]) for t in trades]
    wins = [r for r in rets if r > 0]
    losses = [r for r in rets if r < 0]
    gross_win, gross_loss = sum(wins), abs(sum(losses))
    mc = cur = 0
    for r in rets:                     # 最大连亏
        cur = cur + 1 if r < 0 else 0
        mc = max(mc, cur)
    psec = _TF_SEC.get(timeframe, 3600)
    holds = [(t["exit_time"] - t["entry_time"]).total_seconds() / psec
             for t in trades if t.get("entry_time") is not None and t.get("exit_time") is not None]
    return {
        "trades": n,
        "expectancy": _safe(round(sum(rets) / n, 6)),               # 每笔平均收益(已扣费)
        "win_rate": round(len(wins) / n, 4),
        "avg_win": _safe(round(gross_win / len(wins), 6)) if wins else 0.0,
        "avg_loss": _safe(round(sum(losses) / len(losses), 6)) if losses else 0.0,
        "profit_factor": (_safe(round(gross_win / gross_loss, 3)) if gross_loss > 0 else None),
        "trades_per_day": round(n / max(days, 1), 2),
        "avg_hold_bars": round(sum(holds) / len(holds), 1) if holds else 0.0,
        "max_consec_loss": mc,
        "fee_drag": round(n * 2 * cost * size, 4),                  # 手续费总拖累(占本金,近似)
    }


def _trade_markers(trades: list) -> list:
    """把逐笔交易拆成图上的开/平仓标记。
    开仓标记标方向(买/卖空),平仓标记带上这笔的盈亏%和平仓原因(对标交易所成交标注)。
    具体的颜色/箭头由前端按当前涨跌配色实时渲染,这里只给语义字段。"""
    markers = []
    for t in trades:
        d = int(t.get("dir", 1))
        if t.get("entry_time") is not None:
            markers.append({"time": _ts(t["entry_time"]), "kind": "entry", "dir": d})
        if t.get("exit_time") is not None:
            markers.append({"time": _ts(t["exit_time"]), "kind": "exit", "dir": d,
                            "ret": _safe(round(float(t["ret"]), 6)),
                            "reason": t.get("reason", "")})
    markers.sort(key=lambda m: m["time"])
    return markers


# ============================ 接口 ============================

@app.get("/api/meta")
def meta():
    strategies = [{"name": name, "label": cls.display_name,
                   "params": STRATEGY_SCHEMAS.get(name, [])}
                  for name, cls in STRATEGIES.items()]
    # 预设标的带上名字,前端下拉里就能看到"600519 贵州茅台"
    markets = {}
    for mk, info in MARKETS.items():
        markets[mk] = {**info,
                       "presets": [{"symbol": s, "name": _resolve_name(mk, s)}
                                   for s in info["presets"]]}
    return {"markets": markets, "strategies": strategies,
            "capital": config.INITIAL_CAPITAL,
            "risk": {"stop_loss": 10, "take_profit": 0,
                     "position_size": 50, "max_drawdown_stop": 25}}


@app.get("/api/klines")
def klines(market: str = "crypto", symbol: str = "BTC/USDT",
           timeframe: str = "1h", limit: int = Query(1000, ge=10, le=5000),
           refresh: bool = False):
    _validate(market, timeframe)
    try:
        df = get_data(market=market, symbol=symbol, timeframe=timeframe,
                      limit=limit, use_cache=not refresh)
    except Exception as e:
        raise HTTPException(status_code=502, detail=_friendly_err(market, e))
    synthetic = bool(df.attrs.get("synthetic", False))
    candles = [{"time": _ts(ts), "open": float(r["open"]), "high": float(r["high"]),
                "low": float(r["low"]), "close": float(r["close"]),
                "volume": float(r["volume"])}
               for ts, r in df.iterrows()]
    return {"symbol": symbol, "timeframe": timeframe, "candles": candles,
            "name": _resolve_name(market, symbol),
            "source": "synthetic" if synthetic else "real"}


class BacktestReq(BaseModel):
    market: str = "crypto"
    symbol: str = "BTC/USDT"
    timeframe: str = "1h"
    limit: int = 1000
    strategy: str = "trend_filter"
    params: dict = {}
    risk: dict = {}
    capital: int = 10000
    refresh: bool = False


@app.post("/api/backtest")
def backtest(req: BacktestReq):
    if req.strategy not in STRATEGIES:
        raise HTTPException(status_code=400, detail=f"未知策略 {req.strategy}")
    _validate(req.market, req.timeframe)
    try:
        df = get_data(market=req.market, symbol=req.symbol, timeframe=req.timeframe,
                      limit=max(10, min(5000, int(req.limit))), use_cache=not req.refresh)
    except Exception as e:
        raise HTTPException(status_code=502, detail=_friendly_err(req.market, e))
    synthetic = bool(df.attrs.get("synthetic", False))

    # 本金显式传给回测引擎(不再改全局 config.INITIAL_CAPITAL,避免并发请求相互覆盖)
    capital = max(100, int(req.capital))
    # 整数值转 int、小数值保留 float(短线策略有 k/倍数/偏离% 这类小数参数)
    def _num(v):
        f = float(v)
        return int(f) if f.is_integer() else f
    params = {k: _num(v) for k, v in req.params.items()}
    risk = RiskConfig(
        stop_loss=float(req.risk.get("stop_loss", 0.10)),
        take_profit=float(req.risk.get("take_profit", 0.0)),
        position_size=float(req.risk.get("position_size", 0.5)),
        max_drawdown_stop=float(req.risk.get("max_drawdown_stop", 0.25)))

    strat = get_strategy(req.strategy, **params)
    sdf = strat.generate(df)
    result = run_backtest(sdf, timeframe=req.timeframe, risk=risk,
                          initial_capital=capital)
    rdf = result["df"]

    # 买卖点:由逐笔交易成对生成(开仓+平仓),平仓标记带盈亏与原因
    markers = _trade_markers(result["trades"])

    # 策略自带的指标线(主图叠加)
    overlays = [{"name": label, "data": _points(rdf.index, rdf[col])}
                for col, label in OVERLAY_COLUMNS if col in rdf.columns]
    # RSI 这类 0-100 振荡指标放副图
    oscillator = (_points(rdf.index, rdf["rsi"]) if "rsi" in rdf.columns else None)

    equity = rdf["equity"]
    drawdown = equity / equity.cummax() - 1

    m = result["metrics"]
    metrics = {k: (_safe(round(v, 6)) if isinstance(v, float) else v)
               for k, v in m.items()}
    health = _trade_health(result["trades"], m.get("测试天数", 1), req.timeframe,
                           config.FEE_RATE + config.SLIPPAGE, risk.position_size)

    pos = sdf["position"]
    signal = {"current": int(pos.iloc[-1]),
              "prev": int(pos.iloc[-2]) if len(pos) > 1 else 0,
              "time": str(rdf.index[-1]), "close": float(rdf["close"].iloc[-1])}

    trades = [{"ret": _safe(round(float(t["ret"]), 6)), "reason": t.get("reason", ""),
               "dir": int(t.get("dir", 1)),
               "entry_time": str(t["entry_time"]) if t.get("entry_time") is not None else None,
               "exit_time": str(t["exit_time"]) if t.get("exit_time") is not None else None,
               "entry_ts": _ts(t["entry_time"]) if t.get("entry_time") is not None else None,
               "exit_ts": _ts(t["exit_time"]) if t.get("exit_time") is not None else None}
              for t in result["trades"]]

    return {"metrics": metrics, "markers": markers, "overlays": overlays,
            "oscillator": oscillator, "source": "synthetic" if synthetic else "real",
            "equity": _points(rdf.index, equity),
            "buy_hold": _points(rdf.index, rdf["buy_hold"]),
            "drawdown": _points(rdf.index, drawdown),
            "trades": trades, "health": health,
            "signal": signal, "risk_desc": risk.describe()}


class RobustReq(BaseModel):
    market: str = "crypto"
    symbol: str = "BTC/USDT"
    timeframe: str = "1h"
    limit: int = 1000
    strategy: str = "trend_filter"
    params: dict = {}
    risk: dict = {}
    capital: int = 10000


@app.post("/api/robustness")
def robustness(req: RobustReq):
    """稳健性检验:① 手续费敏感度(看成本临界点)② 样本外(前后两段同规则对比,看是否过拟合/挑行情)。"""
    if req.strategy not in STRATEGIES:
        raise HTTPException(status_code=400, detail=f"未知策略 {req.strategy}")
    _validate(req.market, req.timeframe)
    try:
        df = get_data(market=req.market, symbol=req.symbol, timeframe=req.timeframe,
                      limit=max(120, min(5000, int(req.limit))))
    except Exception as e:
        raise HTTPException(status_code=502, detail=_friendly_err(req.market, e))

    def _num(v):
        f = float(v)
        return int(f) if f.is_integer() else f
    params = {k: _num(v) for k, v in req.params.items()}
    cap = max(100, int(req.capital))
    risk = RiskConfig(
        stop_loss=float(req.risk.get("stop_loss", 0.10)),
        take_profit=float(req.risk.get("take_profit", 0.0)),
        position_size=float(req.risk.get("position_size", 0.5)),
        max_drawdown_stop=float(req.risk.get("max_drawdown_stop", 0.25)))
    strat = get_strategy(req.strategy, **params)

    # ① 手续费敏感度:同一套信号,在不同单边成本下的总收益
    sdf = strat.generate(df)
    cur_cost = config.FEE_RATE + config.SLIPPAGE
    fee_levels = sorted({0.0, 0.0005, 0.001, 0.0015, 0.002, 0.003, round(cur_cost, 6)})
    fee_curve = [{"fee": fee,
                  "ret": _safe(round(run_backtest(sdf, req.timeframe, risk, cap, cost=fee)["metrics"]["总收益率"], 4))}
                 for fee in fee_levels]

    # ② 样本外:前后各半,各自独立重算策略再回测(同一规则两段不同行情,看一致性)
    half = len(df) // 2
    seg = []
    for part in (df.iloc[:half], df.iloc[half:]):
        if len(part) < 30:
            seg.append(None); continue
        r = run_backtest(strat.generate(part), req.timeframe, risk, cap)["metrics"]
        seg.append({"ret": _safe(round(r["总收益率"], 4)), "days": r.get("测试天数", 0),
                    "trades": r["交易次数"], "start": str(part.index[0])[:10], "end": str(part.index[-1])[:10]})

    r1, r2 = seg[0], seg[1]
    if r1 and r2:
        a, b = r1["ret"] or 0, r2["ret"] or 0
        if a > 0 and b > 0:
            oos_verdict = "✅ 前后两段都赚 —— 相对稳健(但仍非保证)"
        elif a <= 0 and b <= 0:
            oos_verdict = "❌ 前后两段都亏 —— 这套规则在该标的上不成立"
        else:
            oos_verdict = "⚠️ 一段赚一段亏 —— 很可能在挑行情/参数过拟合,样本外不可靠"
    else:
        oos_verdict = "数据太短,无法做样本外切分"

    return {"current_fee": round(cur_cost, 6), "fee_curve": fee_curve,
            "oos": {"first": r1, "second": r2, "verdict": oos_verdict}}


# ============================ 实时决策台 ============================
# 理念:系统实时捕捉信号 + 给出分析与"建议订单",但【绝不自动下单】;
#       下单和最终决定永远在用户手里。这是只读的决策支持,不是交易执行。

class SignalReq(BaseModel):
    market: str = "crypto"
    symbol: str = "BTC/USDT"
    timeframe: str = "1h"
    limit: int = 300
    risk: dict = {}
    capital: int = 10000
    refresh: bool = False


def _macd_hist(closes, fast=12, slow=26, sig=9):
    ef = closes.ewm(span=fast, adjust=False).mean()
    es = closes.ewm(span=slow, adjust=False).mean()
    dif = ef - es
    dea = dif.ewm(span=sig, adjust=False).mean()
    return float((dif - dea).iloc[-1])


def _strategy_consensus(df):
    """跑所有策略,汇总当前多空立场、是否刚翻转、共识方向与一致度。
    被 /api/signal(单标的详情)和 /api/scan(多标的扫描)共用。"""
    # 丢掉【未收盘】的最后一根:实时行情里它随价格抖动,立场会在一根K线内反复翻转(repaint)。
    # 用已收盘的根判立场/翻转,与回测引擎"上一根收盘决策"口径一致,信号才稳定。
    if len(df) > 2:
        df = df.iloc[:-1]
    strat_rows, longs, shorts, flips = [], 0, 0, []
    for name, cls in STRATEGIES.items():
        try:
            pos = cls().generate(df)["position"]
        except Exception:
            continue
        cur = int(pos.iloc[-1])
        prev = int(pos.iloc[-2]) if len(pos) > 1 else 0
        flipped = cur != prev
        if cur > 0:
            longs += 1
        elif cur < 0:
            shorts += 1
        if flipped:
            flips.append({"label": cls.display_name, "from": prev, "to": cur})
        strat_rows.append({"name": name, "label": cls.display_name,
                           "stance": cur, "flipped": flipped})
    total = max(1, len(strat_rows))
    if longs > shorts and longs >= 2:
        cons_dir, cons_n = 1, longs
    elif shorts > longs and shorts >= 2:
        cons_dir, cons_n = -1, shorts
    else:
        cons_dir, cons_n = 0, max(longs, shorts)
    return {"strategies": strat_rows, "longs": longs, "shorts": shorts, "flips": flips,
            "total": total, "direction": cons_dir, "agree": cons_n,
            "conviction": cons_n / total}


@app.post("/api/signal")
def signal(req: SignalReq):
    _validate(req.market, req.timeframe)
    try:
        df = get_data(market=req.market, symbol=req.symbol, timeframe=req.timeframe,
                      limit=max(120, int(req.limit)), use_cache=not req.refresh)
    except Exception as e:
        raise HTTPException(status_code=502, detail=_friendly_err(req.market, e))

    closes = df["close"]
    price = float(closes.iloc[-1])
    last_time = str(df.index[-1])

    # ---- 各策略当前立场 + 是否刚刚翻转(实时信号捕捉)----
    c = _strategy_consensus(df)
    strat_rows, longs, shorts, flips = c["strategies"], c["longs"], c["shorts"], c["flips"]
    total, cons_dir, cons_n, conviction = c["total"], c["direction"], c["agree"], c["conviction"]

    # ---- 盘面解读(给人话)----
    ma7 = float(indicators.moving_average(closes, 7).iloc[-1])
    ma25 = float(indicators.moving_average(closes, 25).iloc[-1])
    ma99 = float(indicators.moving_average(closes, 99).iloc[-1]) if len(closes) >= 99 else float("nan")
    rsi14 = float(indicators.rsi(closes, 14).iloc[-1])
    atr14 = float(indicators.atr(df, 14).iloc[-1])
    atr_pct = atr14 / price if price else 0.0
    macd_h = _macd_hist(closes)

    if ma7 > ma25 and (math.isnan(ma99) or ma25 > ma99):
        trend_txt, trend_dir = "多头排列(短中长均线向上)", 1
    elif ma7 < ma25 and (math.isnan(ma99) or ma25 < ma99):
        trend_txt, trend_dir = "空头排列(短中长均线向下)", -1
    else:
        trend_txt, trend_dir = "均线纠缠,趋势不明", 0

    if rsi14 >= 70:
        rsi_txt = f"RSI {rsi14:.0f} 超买,追高需谨慎"
    elif rsi14 <= 30:
        rsi_txt = f"RSI {rsi14:.0f} 超卖,可能超跌反弹"
    else:
        rsi_txt = f"RSI {rsi14:.0f} 中性"

    win = df.tail(20)
    hi20, lo20 = float(win["high"].max()), float(win["low"].min())
    pos_pct = (price - lo20) / (hi20 - lo20) if hi20 > lo20 else 0.5

    reads = [
        {"k": "趋势", "v": trend_txt, "dir": trend_dir},
        {"k": "动能", "v": f"{rsi_txt};MACD柱{'翻红走强' if macd_h > 0 else '翻绿走弱'}",
         "dir": 1 if macd_h > 0 else -1},
        {"k": "波动", "v": f"ATR≈{atr_pct*100:.1f}%/根 —— {'高波动,止损要放宽' if atr_pct > 0.02 else '波动适中'}",
         "dir": 0},
        {"k": "位置", "v": f"处于近20根区间 {pos_pct*100:.0f}% 位置（0=最低 100=最高）",
         "dir": 0},
    ]

    # ---- 建议订单(纯建议,用户手动下单)----
    risk = RiskConfig(
        stop_loss=float(req.risk.get("stop_loss", 0.05)) or 0.05,
        take_profit=float(req.risk.get("take_profit", 0.0)),
        position_size=float(req.risk.get("position_size", 0.5)),
        max_drawdown_stop=float(req.risk.get("max_drawdown_stop", 0.25)))
    capital = max(100, int(req.capital))
    ticket = None
    if cons_dir != 0:
        sl = risk.stop_loss
        long = cons_dir > 0
        stop = price * (1 - sl) if long else price * (1 + sl)
        target = price * (1 + 2 * sl) if long else price * (1 - 2 * sl)   # 2:1 盈亏比
        pos_value = capital * risk.position_size
        qty = pos_value / price if price else 0.0
        ticket = {
            "direction": "做多 / 买入" if long else "做空 / 卖出",
            "dir": cons_dir,
            "entry": _safe(round(price, 6)),
            "stop": _safe(round(stop, 6)),
            "target": _safe(round(target, 6)),
            "stop_pct": round(sl, 4),
            "position_pct": round(risk.position_size, 4),
            "position_value": _safe(round(pos_value, 2)),
            "qty": _safe(round(qty, 6)),
            "risk_amount": _safe(round(pos_value * sl, 2)),   # 触发止损约亏多少
            "reward_risk": 2.0,
        }

    rec_map = {1: "做多", -1: "做空", 0: "观望"}
    return {
        "symbol": req.symbol, "name": _resolve_name(req.market, req.symbol),
        "timeframe": req.timeframe, "time": last_time, "price": _safe(round(price, 6)),
        "recommendation": rec_map[cons_dir], "direction": cons_dir,
        "conviction": round(conviction, 2), "agree": cons_n, "total": total,
        "longs": longs, "shorts": shorts,
        "strategies": strat_rows, "flips": flips, "new_signal": bool(flips),
        "reads": reads, "ticket": ticket,
        # 口径说明:共识用各策略【默认参数】算,和回测面板里你调的参数是两回事,可能给出不同结论
        "basis": "共识基于各策略默认参数(非回测面板自定义参数);盘面解读为固定 MA7/25/99、RSI14",
        "source": "real",
    }


# ============================ 多标的自选监控(扫描)============================

class ScanReq(BaseModel):
    market: str = "crypto"
    symbols: list = []
    timeframe: str = "1h"
    refresh: bool = False


@app.post("/api/scan")
def scan(req: ScanReq):
    _validate(req.market, req.timeframe)
    out = []
    rec_map = {1: "做多", -1: "做空", 0: "观望"}
    for sym in req.symbols[:30]:        # 上限保护
        try:
            df = get_data(market=req.market, symbol=sym, timeframe=req.timeframe,
                          limit=160, use_cache=not req.refresh)
            c = _strategy_consensus(df)
            out.append({
                "symbol": sym, "name": _resolve_name(req.market, sym),
                "price": _safe(round(float(df["close"].iloc[-1]), 6)),
                "time": str(df.index[-1]),
                "direction": c["direction"], "recommendation": rec_map[c["direction"]],
                "agree": c["agree"], "total": c["total"],
                "conviction": round(c["conviction"], 2),
                "new_signal": bool(c["flips"]),
                "flips": c["flips"],
            })
        except Exception as e:
            out.append({"symbol": sym, "name": sym, "error": str(e)[:60]})
    return {"results": out}


# ============================ 事件合约·超短实时方向 ============================
# ⚠️ 二元期权,本质赌博、负期望。这里只给方向 + 把残酷的真实胜率/保本线摆出来,绝不下注。

from src import event_contract as ec

# 事件合约要评测的信号集 + 中文标签(strong_momentum/breakout 会"空手不押",是高确认型)
EVENT_SIGNALS = ["momentum", "reversion", "strong_momentum", "ma_trend", "breakout"]
EVENT_SIGNAL_LABELS = {
    "momentum": "动量(追涨杀跌)",
    "reversion": "反转(赌回调)",
    "strong_momentum": "强动量(够猛才押)",
    "ma_trend": "均线方向",
    "breakout": "突破(创新高/低才押)",
}


class EventReq(BaseModel):
    market: str = "crypto"
    symbol: str = "BTC/USDT"
    payout: float = 1.8
    horizons: list = [1, 3, 5]
    refresh: bool = False


@app.post("/api/event")
def event(req: EventReq):
    if req.market != "crypto":
        raise HTTPException(status_code=400, detail="事件合约只接币圈分钟数据,A股/美股暂不支持")
    try:
        df = get_data(market="crypto", symbol=req.symbol, timeframe="1m",
                      limit=1000, use_cache=not req.refresh)
    except Exception as e:
        raise HTTPException(status_code=502, detail=_friendly_err("crypto", e))

    breakeven = 1.0 / req.payout
    rows = []
    for h in req.horizons[:6]:
        cfg = ec.EventConfig(horizon_minutes=int(h), payout=float(req.payout))
        for sig in EVENT_SIGNALS:
            bt = ec.backtest(df, cfg, sig)
            ls = ec.live_signal(df, cfg, sig, bt["win_rate"])
            rows.append({
                "horizon": int(h), "signal": sig,
                "signal_label": EVENT_SIGNAL_LABELS.get(sig, sig),
                "direction": ls["prediction"],   # "UP"/"DOWN"/None
                "win_rate": round(bt["win_rate"], 4),
                "bets": bt["bets"],
                "above_breakeven": bt["win_rate"] > breakeven,
                # ↓ 诚实统计:不光看"胜率>保本",还看是否【统计显著 + 前后半段稳定】
                "ev_pct": round(bt["ev_pct"], 4),       # 每笔期望(占下注额比例,几乎总是负)
                "z": round(bt["z_score"], 2),           # 跑赢保本线的显著性 z 值
                "significant": bt["significant"],
                "verdict": bt["verdict"],               # 一句人话结论
            })
    return {"symbol": req.symbol, "name": _resolve_name("crypto", req.symbol),
            "price": round(float(df["close"].iloc[-1]), 6),
            "time": str(df.index[-1]),
            "payout": req.payout, "breakeven": round(breakeven, 4),
            "rows": rows}


# ============================ 国内大宗商品期权 ============================
# 只读:展示真实期权链(T型报价)+ 单合约K线。数据来自新浪免费接口(境内直连绕代理)。
# ⚠️ 同样【绝不下单】。本阶段只摆真实行情;隐含波动率/希腊字母为后续阶段(需本地自算)。

from src.data import options as opt
from src.options import pricing as optprice


@app.get("/api/options/products")
def options_products():
    """新浪当前实际供应的商品期权品种,按交易所分组(供前端下拉)。"""
    try:
        ps = opt.list_products()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"取期权品种列表失败:{e}")
    groups = {}
    for p in ps:
        groups.setdefault(p["exchange_label"], []).append(
            {"name": p["name"], "product": p["product"], "exchange": p["exchange"]})
    return {"count": len(ps),
            "groups": [{"exchange": k, "products": v} for k, v in groups.items()]}


@app.get("/api/options/contracts")
def options_contracts(product: str = Query(..., description="品种中文名,如 豆粕期权")):
    """某品种当前在交易的到期月列表,如 ['m2609','m2701',...]。"""
    try:
        months = opt.list_contracts(product)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"取 {product} 合约月份失败:{e}")
    return {"product": product, "contracts": months}


@app.get("/api/options/chain")
def options_chain(product: str = Query(..., description="品种中文名,如 豆粕期权"),
                  contract: str = Query(..., description="到期月,如 m2609")):
    """T型期权链快照:看涨 | 行权价 | 看跌(买卖价量/最新价/持仓/涨跌)。"""
    try:
        data = opt.quote_table(product, contract)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"取 {product} {contract} 期权链失败:{e}")
    # 阶段2:本地 Black-76 反解 IV + 希腊字母,并推标的 F / 到期 T / PCR 情绪(全部近似,只读)
    try:
        optprice.enrich_chain(data, data.get("exchange"))
    except Exception as e:
        data["analytics"] = {"error": f"IV/希腊字母计算失败:{e}", "approx": True}
    # 标出平值(ATM):优先用反推的标的价 F 找最近行权价;F 缺失时退回 |call-put| 最小那行
    F = (data.get("analytics") or {}).get("forward")
    atm_strike = None
    if F:
        cand = [r for r in data["rows"] if r["strike"] is not None]
        if cand:
            atm_strike = min(cand, key=lambda r: abs(r["strike"] - F))["strike"]
    if atm_strike is None:
        best = None
        for r in data["rows"]:
            cl, pl = r["call"]["last"], r["put"]["last"]
            if cl is not None and pl is not None:
                diff = abs(cl - pl)
                if best is None or diff < best:
                    best, atm_strike = diff, r["strike"]
    data["atm_strike"] = atm_strike
    return data


@app.get("/api/options/klines")
def options_klines(code: str = Query(..., description="单个期权合约代码,如 m2609C3000"),
                   limit: int = Query(250, ge=10, le=2000), refresh: bool = False):
    """单个期权合约的历史日K(标准 OHLCV)。"""
    try:
        df = get_data(market="options", symbol=code, timeframe="1d",
                      limit=limit, use_cache=not refresh)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"取期权合约 {code} K线失败:{e}")
    candles = [{"time": _ts(ts), "open": float(r["open"]), "high": float(r["high"]),
                "low": float(r["low"]), "close": float(r["close"]),
                "volume": float(r["volume"])}
               for ts, r in df.iterrows()]
    return {"code": code, "candles": candles}


# ============================ 静态页面 ============================

@app.middleware("http")
async def no_cache_static(request, call_next):
    """前端文件每次都向服务器确认是否有更新(304 很便宜),
    避免浏览器用缓存的旧 JS/CSS 导致改了代码页面却没变。"""
    resp = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith("/static"):
        resp.headers["Cache-Control"] = "no-cache"
    return resp


app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


@app.get("/")
def index():
    return FileResponse(os.path.join(WEB_DIR, "index.html"))


if __name__ == "__main__":
    print("🚀 交易终端启动:http://localhost:8000  (Ctrl+C 停止)")
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")
