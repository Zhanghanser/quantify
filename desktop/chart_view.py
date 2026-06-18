# -*- coding: utf-8 -*-
"""
盘面图与资金曲线图(纯 pyqtgraph 控件)。

PriceChart:主图蜡烛 + 叠加均线 + 买卖点 + 成交量 + 可选RSI副图 + 十字光标。
EquityChart:策略资金曲线 vs 买入持有 + 回撤填充。
"""

import numpy as np
import pyqtgraph as pg
from pyqtgraph.Qt import QtCore

from desktop import theme
from desktop.charts import CandlestickItem, VolumeItem, TimeAxisItem, format_axis_labels


class PriceChart(pg.GraphicsLayoutWidget):
    def __init__(self):
        super().__init__()
        self.setBackground(theme.BG)
        self._n = 0
        self._data = None  # 当前蜡烛数据,供光标读数

        # ---- 主图(蜡烛 + 均线 + 买卖点)----
        self.p_price = self.addPlot(row=0, col=0)
        self.p_price.showGrid(x=True, y=True, alpha=0.15)
        self.p_price.getAxis("left").setWidth(64)
        self.p_price.getAxis("bottom").setStyle(showValues=False)
        self.p_price.setMouseEnabled(y=False)
        self.legend = self.p_price.addLegend(offset=(60, 8), labelTextColor=theme.MUTED)

        self.candles = CandlestickItem()
        self.p_price.addItem(self.candles)
        self.overlay_items = []
        self.entry_long = self._scatter("t1", "#26c6da")
        self.entry_short = self._scatter("t", theme.ACCENT)
        self.exit_win = self._scatter("o", theme.POS)
        self.exit_loss = self._scatter("o", theme.NEG)
        for s in (self.entry_long, self.entry_short, self.exit_win, self.exit_loss):
            self.p_price.addItem(s)

        # ---- 成交量副图 ----
        self.taxis = TimeAxisItem(orientation="bottom")
        self.p_vol = self.addPlot(row=1, col=0, axisItems={"bottom": self.taxis})
        self.p_vol.setXLink(self.p_price)
        self.p_vol.showGrid(x=False, y=True, alpha=0.12)
        self.p_vol.getAxis("left").setWidth(64)
        self.p_vol.setMouseEnabled(y=False)
        self.volume = VolumeItem()
        self.p_vol.addItem(self.volume)

        # ---- RSI 副图(按需显示)----
        self.taxis2 = TimeAxisItem(orientation="bottom")
        self.p_rsi = self.addPlot(row=2, col=0, axisItems={"bottom": self.taxis2})
        self.p_rsi.setXLink(self.p_price)
        self.p_rsi.getAxis("left").setWidth(64)
        self.p_rsi.setMouseEnabled(y=False)
        self.p_rsi.setYRange(0, 100)
        self.rsi_line = self.p_rsi.plot([], [], pen=pg.mkPen("#b47cff", width=1.2))
        for lv in (30, 70):
            self.p_rsi.addLine(y=lv, pen=pg.mkPen(theme.BORDER, style=QtCore.Qt.DashLine))
        self.p_rsi.hide()

        self.ci.layout.setRowStretchFactor(0, 6)
        self.ci.layout.setRowStretchFactor(1, 2)
        self.ci.layout.setRowStretchFactor(2, 2)

        # ---- 十字光标 ----
        self.vline = pg.InfiniteLine(angle=90, pen=pg.mkPen(theme.MUTED, style=QtCore.Qt.DashLine))
        self.hline = pg.InfiniteLine(angle=0, pen=pg.mkPen(theme.MUTED, style=QtCore.Qt.DashLine))
        self.p_price.addItem(self.vline, ignoreBounds=True)
        self.p_price.addItem(self.hline, ignoreBounds=True)
        self.info = pg.TextItem(anchor=(0, 0), color=theme.TEXT, fill=pg.mkBrush(theme.PANEL2))
        self.info.setZValue(100)
        self.p_price.addItem(self.info, ignoreBounds=True)
        self._proxy = pg.SignalProxy(self.scene().sigMouseMoved, rateLimit=60, slot=self._on_move)

    def _scatter(self, symbol, color):
        return pg.ScatterPlotItem(symbol=symbol, size=12, brush=pg.mkBrush(color),
                                  pen=pg.mkPen("#000", width=0.5))

    # ---------- 数据装载 ----------
    def set_klines(self, data, timeframe):
        self._data = data
        o, h, l, c, v = (data["opens"], data["highs"], data["lows"],
                         data["closes"], data["volumes"])
        self._n = len(c)
        self.candles.set_data(o, h, l, c)
        self.volume.set_data(o, c, v)
        labels = format_axis_labels(data["index"], timeframe)
        self.taxis.set_labels(labels)
        self.taxis2.set_labels(labels)
        self.clear_overlays()
        self.clear_markers()
        self.set_oscillator(None)
        if self._n:
            self.p_price.setXRange(max(0, self._n - 180), self._n, padding=0.02)
            self._autorange_price(max(0, self._n - 180), self._n)

    def clear_overlays(self):
        for it in self.overlay_items:
            self.p_price.removeItem(it)
        self.overlay_items = []
        self.legend.clear()  # 否则每次回测均线名会在图例里越堆越多

    def set_overlays(self, overlays):
        self.clear_overlays()
        x = np.arange(self._n)
        for i, (label, y) in enumerate(overlays):
            color = theme.OVERLAY_COLORS[i % len(theme.OVERLAY_COLORS)]
            item = self.p_price.plot(x, y, pen=pg.mkPen(color, width=1.4),
                                     connect="finite", name=label)
            self.overlay_items.append(item)

    def set_oscillator(self, osc):
        if osc is None:
            self.rsi_line.setData([], [])
            self.p_rsi.hide()
            return
        _, y = osc
        self.rsi_line.setData(np.arange(self._n), y, connect="finite")
        self.p_rsi.show()

    def clear_markers(self):
        for s in (self.entry_long, self.entry_short, self.exit_win, self.exit_loss):
            s.setData([], [])

    def set_markers(self, markers):
        el, es, ew, elo = [], [], [], []
        for m in markers:
            x, y = m["idx"], m["price"]
            if m["kind"] == "entry":
                (el if m["dir"] == 1 else es).append((x, y))
            else:
                (ew if m.get("ret", 0) > 0 else elo).append((x, y))
        self.entry_long.setData([p[0] for p in el], [p[1] for p in el])
        self.entry_short.setData([p[0] for p in es], [p[1] for p in es])
        self.exit_win.setData([p[0] for p in ew], [p[1] for p in ew])
        self.exit_loss.setData([p[0] for p in elo], [p[1] for p in elo])

    # ---------- 视图辅助 ----------
    def _autorange_price(self, lo, hi):
        d = self._data
        if not d or hi <= lo:
            return
        lo, hi = max(0, lo), min(self._n, hi)
        if hi <= lo:
            return
        ylo = float(np.min(d["lows"][lo:hi]))
        yhi = float(np.max(d["highs"][lo:hi]))
        pad = (yhi - ylo) * 0.06 or 1.0
        self.p_price.setYRange(ylo - pad, yhi + pad, padding=0)

    def _on_move(self, evt):
        pos = evt[0]
        if not self.p_price.sceneBoundingRect().contains(pos) or not self._data:
            return
        mp = self.p_price.vb.mapSceneToView(pos)
        i = int(round(mp.x()))
        self.vline.setPos(mp.x())
        self.hline.setPos(mp.y())
        if 0 <= i < self._n:
            d = self._data
            o, h, l, c = d["opens"][i], d["highs"][i], d["lows"][i], d["closes"][i]
            chg = (c / o - 1) * 100 if o else 0
            color = theme.UP_COLOR if c >= o else theme.DOWN_COLOR
            label = d["index"][i].strftime("%Y-%m-%d %H:%M")
            self.info.setHtml(
                f'<div style="font-size:11px;color:{theme.MUTED}">{label}</div>'
                f'<div style="color:{color};font-size:12px">'
                f'开 {o:.4g}　高 {h:.4g}　低 {l:.4g}　收 {c:.4g}　'
                f'<b>{chg:+.2f}%</b></div>')
            vr = self.p_price.vb.viewRange()
            self.info.setPos(vr[0][0], vr[1][1])


class EquityChart(pg.GraphicsLayoutWidget):
    def __init__(self):
        super().__init__()
        self.setBackground(theme.BG)
        self.taxis = TimeAxisItem(orientation="bottom")
        self.p_eq = self.addPlot(row=0, col=0)
        self.p_eq.showGrid(x=True, y=True, alpha=0.15)
        self.p_eq.getAxis("left").setWidth(72)
        self.p_eq.getAxis("bottom").setStyle(showValues=False)
        self.leg = self.p_eq.addLegend(offset=(70, 8), labelTextColor=theme.MUTED)
        self.eq_line = self.p_eq.plot([], [], pen=pg.mkPen(theme.EQUITY, width=1.8), name="策略")
        self.bh_line = self.p_eq.plot([], [], pen=pg.mkPen(theme.BUYHOLD, width=1.4), name="买入持有")

        self.p_dd = self.addPlot(row=1, col=0, axisItems={"bottom": self.taxis})
        self.p_dd.setXLink(self.p_eq)
        self.p_dd.showGrid(x=False, y=True, alpha=0.12)
        self.p_dd.getAxis("left").setWidth(72)
        self.dd_line = self.p_dd.plot([], [], pen=pg.mkPen(theme.DRAWDOWN, width=1.2),
                                      fillLevel=0, brush=pg.mkBrush(246, 70, 93, 60))
        self.ci.layout.setRowStretchFactor(0, 3)
        self.ci.layout.setRowStretchFactor(1, 1)

    def set_data(self, equity, buy_hold, drawdown, index, timeframe):
        x = np.arange(len(equity))
        self.eq_line.setData(x, equity)
        self.bh_line.setData(x, buy_hold)
        self.dd_line.setData(x, drawdown * 100)  # 显示成百分比
        self.taxis.set_labels(format_axis_labels(index, timeframe))
        self.p_eq.enableAutoRange()
        self.p_dd.enableAutoRange()

    def clear(self):
        self.eq_line.setData([], [])
        self.bh_line.setData([], [])
        self.dd_line.setData([], [])
