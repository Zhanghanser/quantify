# -*- coding: utf-8 -*-
"""
原生图形元件:蜡烛图 / 成交量 / 时间坐标轴。

全部用 pyqtgraph 的 QPainter 直接绘制,是真正的 Qt 矢量图形,
不含任何网页/HTML/JS。x 轴用"第几根K线"的整数序号(等距,
自动跳过周末与停盘空档,和交易所盘面一致),序号→日期由 TimeAxisItem 映射。
"""

import pyqtgraph as pg
from pyqtgraph.Qt import QtCore, QtGui

from desktop.theme import UP_COLOR, DOWN_COLOR


class CandlestickItem(pg.GraphicsObject):
    """一组蜡烛(开高低收),收>=开为阳线,收<开为阴线。"""

    def __init__(self):
        super().__init__()
        self.picture = QtGui.QPicture()
        self._o = self._h = self._l = self._c = []

    def set_data(self, opens, highs, lows, closes):
        self._o, self._h, self._l, self._c = opens, highs, lows, closes
        self._generate()
        self.informViewBoundsChanged()
        self.update()

    def _generate(self):
        self.picture = QtGui.QPicture()
        if len(self._o) == 0:
            return
        p = QtGui.QPainter(self.picture)
        up_pen = pg.mkPen(UP_COLOR, width=1)
        dn_pen = pg.mkPen(DOWN_COLOR, width=1)
        up_brush = pg.mkBrush(UP_COLOR)
        dn_brush = pg.mkBrush(DOWN_COLOR)
        w = 0.32  # 实体半宽
        for i in range(len(self._o)):
            o, h, l, c = self._o[i], self._h[i], self._l[i], self._c[i]
            up = c >= o
            p.setPen(up_pen if up else dn_pen)
            # 上下影线
            p.drawLine(QtCore.QPointF(i, l), QtCore.QPointF(i, h))
            # 实体
            top, bot = (c, o) if up else (o, c)
            if top == bot:
                # 一字线:画一条横线代替零高度矩形
                p.drawLine(QtCore.QPointF(i - w, o), QtCore.QPointF(i + w, o))
            else:
                p.setBrush(up_brush if up else dn_brush)
                p.drawRect(QtCore.QRectF(i - w, bot, w * 2, top - bot))
        p.end()

    def paint(self, painter, *args):
        painter.drawPicture(0, 0, self.picture)

    def boundingRect(self):
        return QtCore.QRectF(self.picture.boundingRect())


class VolumeItem(pg.GraphicsObject):
    """成交量柱,按当根涨跌着色。"""

    def __init__(self):
        super().__init__()
        self.picture = QtGui.QPicture()

    def set_data(self, opens, closes, volumes):
        self.picture = QtGui.QPicture()
        if len(volumes):
            p = QtGui.QPainter(self.picture)
            p.setPen(QtCore.Qt.NoPen)
            up_brush = pg.mkBrush(UP_COLOR)
            dn_brush = pg.mkBrush(DOWN_COLOR)
            w = 0.32
            for i in range(len(volumes)):
                p.setBrush(up_brush if closes[i] >= opens[i] else dn_brush)
                p.drawRect(QtCore.QRectF(i - w, 0, w * 2, volumes[i]))
            p.end()
        self.informViewBoundsChanged()
        self.update()

    def paint(self, painter, *args):
        painter.drawPicture(0, 0, self.picture)

    def boundingRect(self):
        return QtCore.QRectF(self.picture.boundingRect())


class TimeAxisItem(pg.AxisItem):
    """把 x 轴的整数序号翻译成日期标签(根据周期决定显示精度)。"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._labels = []   # 每根K线一个字符串

    def set_labels(self, labels):
        self._labels = list(labels)
        self.picture = None
        self.update()

    def tickStrings(self, values, scale, spacing):
        out = []
        n = len(self._labels)
        for v in values:
            i = int(round(v))
            out.append(self._labels[i] if 0 <= i < n else "")
        return out


def format_axis_labels(index, timeframe: str):
    """DatetimeIndex → 每根K线的轴标签字符串,按周期选择精度。"""
    if timeframe in ("1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h"):
        fmt = "%m-%d %H:%M"
    elif timeframe in ("1w", "1M"):
        fmt = "%Y-%m"
    else:
        fmt = "%Y-%m-%d"
    return [t.strftime(fmt) for t in index]
