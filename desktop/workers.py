# -*- coding: utf-8 -*-
"""
后台任务线程:取数和回测都在子线程跑,避免界面卡死(转圈)。

复用的全是项目既有后端,和网页版同一套引擎:
    src.data.get_data / src.strategies / src.backtest.run_backtest / src.risk
"""

import numpy as np
from pyqtgraph.Qt import QtCore

import config
from src.data import get_data
from src.strategies import get_strategy
from src.backtest import run_backtest
from src.risk import RiskConfig

# 复用网页版里已经定义好的"市场/周期/策略参数/叠加线/标的中文名",零重复。
from run_web import MARKETS, STRATEGY_SCHEMAS, OVERLAY_COLUMNS, _resolve_name


def _candles(df):
    """DataFrame → 给图形元件用的几条 numpy 数组。"""
    return {
        "index": df.index,
        "opens": df["open"].to_numpy(dtype=float),
        "highs": df["high"].to_numpy(dtype=float),
        "lows": df["low"].to_numpy(dtype=float),
        "closes": df["close"].to_numpy(dtype=float),
        "volumes": df["volume"].to_numpy(dtype=float),
    }


def _execute(job: dict) -> dict:
    """在子线程里真正干活。返回一个可直接喂给界面的结果字典。"""
    market = job["market"]
    symbol = job["symbol"]
    timeframe = job["timeframe"]
    limit = int(job.get("limit", 1000))
    refresh = bool(job.get("refresh", False))

    df = get_data(market=market, symbol=symbol, timeframe=timeframe,
                  limit=limit, use_cache=not refresh)
    synthetic = bool(df.attrs.get("synthetic", False))
    name = _resolve_name(market, symbol)

    base = {
        "mode": job["mode"], "market": market, "symbol": symbol,
        "timeframe": timeframe, "name": name,
        "source": "synthetic" if synthetic else "real",
        **_candles(df),
    }

    if job["mode"] == "klines":
        return base

    # ---- 回测 ----
    strat = get_strategy(job["strategy"], **job.get("params", {}))
    sdf = strat.generate(df)
    r = job.get("risk", {})
    risk = RiskConfig(
        stop_loss=float(r.get("stop_loss", 0.10)),
        take_profit=float(r.get("take_profit", 0.0)),
        position_size=float(r.get("position_size", 0.5)),
        max_drawdown_stop=float(r.get("max_drawdown_stop", 0.25)),
    )
    capital = max(100, int(job.get("capital", config.INITIAL_CAPITAL)))
    result = run_backtest(sdf, timeframe=timeframe, risk=risk, initial_capital=capital)
    rdf = result["df"]

    # K线可能在 run_backtest 内部对齐过(一般同长),统一以 rdf 为准重取蜡烛
    base.update(_candles(rdf))

    # 时间 → 第几根K线 的映射(给买卖点定位)
    pos_of = {ts: i for i, ts in enumerate(rdf.index)}

    markers = []
    trades = []
    for t in result["trades"]:
        ei = pos_of.get(t.get("entry_time"))
        xi = pos_of.get(t.get("exit_time"))
        d = int(t.get("dir", 1))
        ret = float(t["ret"])
        if ei is not None:
            markers.append({"idx": ei, "price": float(t["entry_price"]),
                            "kind": "entry", "dir": d})
        if xi is not None:
            markers.append({"idx": xi, "price": float(t["exit_price"]),
                            "kind": "exit", "dir": d, "ret": ret,
                            "reason": t.get("reason", "")})
        trades.append({
            "entry_idx": ei, "exit_idx": xi, "dir": d,
            "entry_price": float(t["entry_price"]),
            "exit_price": float(t["exit_price"]), "ret": ret,
            "reason": t.get("reason", ""),
            "entry_time": str(t.get("entry_time")) if t.get("entry_time") is not None else "",
            "exit_time": str(t.get("exit_time")) if t.get("exit_time") is not None else "",
        })

    overlays = [(label, rdf[col].to_numpy(dtype=float))
                for col, label in OVERLAY_COLUMNS if col in rdf.columns]
    oscillator = ("RSI", rdf["rsi"].to_numpy(dtype=float)) if "rsi" in rdf.columns else None

    equity = rdf["equity"].to_numpy(dtype=float)
    cummax = np.maximum.accumulate(equity)
    drawdown = equity / cummax - 1.0

    base.update({
        "metrics": result["metrics"],
        "overlays": overlays,
        "oscillator": oscillator,
        "markers": markers,
        "trades": trades,
        "equity": equity,
        "buy_hold": rdf["buy_hold"].to_numpy(dtype=float),
        "drawdown": drawdown,
        "risk_desc": risk.describe(),
        "capital": capital,
    })
    return base


class Job(QtCore.QThread):
    """跑一个任务:成功发 done(dict),失败发 failed(str)。"""

    done = QtCore.Signal(dict)
    failed = QtCore.Signal(str)

    def __init__(self, job: dict, parent=None):
        super().__init__(parent)
        self._job = job

    def run(self):
        try:
            self.done.emit(_execute(self._job))
        except Exception as e:  # 联网失败/未知代码等,转成人话给界面弹窗
            import traceback
            traceback.print_exc()
            self.failed.emit(_friendly(self._job.get("market", ""), e))


_FRIENDLY = {
    "crypto": "交易所连接失败,请稍后重试(币圈默认走 gate.io,通常可直连)。",
    "astock": "A股取数失败,请确认代码为6位数字(如 600519),且本机能联网。",
    "usstock": "雅虎财经连接失败,美股行情在国内通常需要科学上网。",
    "futures": "期货取数失败(新浪境内源),请确认代码并稍后重试。",
}


def _friendly(market: str, e: Exception) -> str:
    return _FRIENDLY.get(market, f"出错了:{e}")
