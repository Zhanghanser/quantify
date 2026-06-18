# -*- coding: utf-8 -*-
"""
主窗口:左侧控制面板 + 右侧盘面/资金曲线/成交明细 + 绩效指标卡。

纯 PySide6 原生窗口,双击启动就是独立程序,不开浏览器、无网址栏。
所有计算复用项目既有后端(和网页版同引擎),只回测、不下单。
"""

import os
import sys

import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets
import pyqtgraph as pg

import config
from src.strategies import STRATEGIES
from run_web import MARKETS, STRATEGY_SCHEMAS

from desktop import theme
from desktop.chart_view import PriceChart, EquityChart
from desktop.workers import Job

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 绩效指标卡:键 → (标题, 类型)。类型决定怎么格式化与上色。
METRIC_CARDS = [
    ("总收益率", "总收益率", "pct_signed"),
    ("年化收益率", "年化收益率", "pct_signed"),
    ("夏普比率", "夏普比率", "num"),
    ("最大回撤", "最大回撤", "pct_dd"),
    ("胜率", "胜率", "pct_plain"),
    ("交易次数", "交易次数", "int"),
    ("最终资金", "最终资金", "money"),
]


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("量化终端 · 桌面版（只回测 / 只显示信号，不下单）")
        self.resize(1320, 820)
        self.setMinimumSize(1100, 700)
        ico = os.path.join(ROOT, "icon.ico")
        if os.path.exists(ico):
            self.setWindowIcon(QtGui.QIcon(ico))

        self._job = None
        self._param_widgets = {}

        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        root = QtWidgets.QHBoxLayout(central)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)
        root.addWidget(self._build_controls(), 0)
        root.addWidget(self._build_right(), 1)

        self.status = self.statusBar()
        self.status.showMessage("就绪。选择市场/标的/策略后点「运行回测」。")

        self._on_market_changed()
        self._on_strategy_changed()
        QtCore.QTimer.singleShot(300, self.run_backtest)  # 启动后自动跑一次默认配置

    # ------------------------------------------------------------------ 控制面板
    def _build_controls(self):
        panel = QtWidgets.QFrame()
        panel.setObjectName("Panel")
        panel.setFixedWidth(330)
        outer = QtWidgets.QVBoxLayout(panel)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        outer.addWidget(scroll)
        inner = QtWidgets.QWidget()
        scroll.setWidget(inner)
        form = QtWidgets.QVBoxLayout(inner)
        form.setContentsMargins(14, 14, 14, 14)
        form.setSpacing(10)

        title = QtWidgets.QLabel("量化终端")
        title.setStyleSheet(f"font-size:18px;font-weight:bold;color:{theme.ACCENT};")
        form.addWidget(title)
        sub = QtWidgets.QLabel("纯原生窗口 · 复用回测引擎")
        sub.setObjectName("FieldLabel")
        form.addWidget(sub)

        form.addWidget(self._section("行情"))
        self.cb_market = QtWidgets.QComboBox()
        for mk, info in MARKETS.items():
            self.cb_market.addItem(info["label"], mk)
        form.addLayout(self._field("市场", self.cb_market))

        self.cb_symbol = QtWidgets.QComboBox()
        self.cb_symbol.setEditable(True)
        self.cb_symbol.setInsertPolicy(QtWidgets.QComboBox.NoInsert)
        form.addLayout(self._field("标的（可手输代码）", self.cb_symbol))

        self.cb_tf = QtWidgets.QComboBox()
        form.addLayout(self._field("周期", self.cb_tf))

        self.sp_limit = QtWidgets.QSpinBox()
        self.sp_limit.setRange(100, 5000)
        self.sp_limit.setSingleStep(100)
        self.sp_limit.setValue(config.LIMIT)
        form.addLayout(self._field("K线根数", self.sp_limit))

        form.addWidget(self._section("策略"))
        self.cb_strategy = QtWidgets.QComboBox()
        for name, cls in STRATEGIES.items():
            self.cb_strategy.addItem(cls.display_name, name)
        idx = self.cb_strategy.findData(config.STRATEGY)
        if idx >= 0:
            self.cb_strategy.setCurrentIndex(idx)
        form.addLayout(self._field("策略", self.cb_strategy))

        self.param_box = QtWidgets.QVBoxLayout()
        self.param_box.setSpacing(8)
        form.addLayout(self.param_box)

        form.addWidget(self._section("资金与风控"))
        self.sp_capital = QtWidgets.QSpinBox()
        self.sp_capital.setRange(100, 100_000_000)
        self.sp_capital.setSingleStep(1000)
        self.sp_capital.setValue(config.INITIAL_CAPITAL)
        self.sp_capital.setGroupSeparatorShown(True)
        form.addLayout(self._field("本金", self.sp_capital))

        self.sp_stop = self._pct_spin(10)
        form.addLayout(self._field("止损 %（0=关）", self.sp_stop))
        self.sp_take = self._pct_spin(0, top=300)
        form.addLayout(self._field("止盈 %（0=关）", self.sp_take))
        self.sp_pos = self._pct_spin(50, bottom=1)
        form.addLayout(self._field("仓位 %", self.sp_pos))
        self.sp_dd = self._pct_spin(25)
        form.addLayout(self._field("回撤熔断 %（0=关）", self.sp_dd))

        form.addSpacing(6)
        self.btn_run = QtWidgets.QPushButton("运行回测")
        self.btn_run.setObjectName("Primary")
        self.btn_run.clicked.connect(self.run_backtest)
        form.addWidget(self.btn_run)

        row = QtWidgets.QHBoxLayout()
        self.btn_klines = QtWidgets.QPushButton("只看K线")
        self.btn_klines.clicked.connect(self.load_klines)
        self.btn_refresh = QtWidgets.QPushButton("刷新数据")
        self.btn_refresh.clicked.connect(lambda: self.run_backtest(refresh=True))
        row.addWidget(self.btn_klines)
        row.addWidget(self.btn_refresh)
        form.addLayout(row)

        self.risk_lbl = QtWidgets.QLabel("")
        self.risk_lbl.setObjectName("FieldLabel")
        self.risk_lbl.setWordWrap(True)
        form.addWidget(self.risk_lbl)

        form.addStretch(1)
        note = QtWidgets.QLabel("⚠ 仅回测/显示信号，绝不下单、不碰真钱。")
        note.setObjectName("FieldLabel")
        note.setWordWrap(True)
        form.addWidget(note)

        self.cb_market.currentIndexChanged.connect(self._on_market_changed)
        self.cb_strategy.currentIndexChanged.connect(self._on_strategy_changed)
        return panel

    def _build_right(self):
        right = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(right)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)

        # 模拟数据警示横幅
        self.banner = QtWidgets.QLabel("")
        self.banner.setStyleSheet(
            f"background:{theme.NEG};color:#fff;padding:6px 10px;border-radius:6px;font-weight:bold;")
        self.banner.hide()
        v.addWidget(self.banner)

        # 行情 Ticker 条(对标交易所:最新价 + 涨跌 + 区间统计)
        v.addWidget(self._build_ticker())

        # 指标卡
        v.addWidget(self._build_metric_bar())

        # 图表标签页
        self.tabs = QtWidgets.QTabWidget()
        self.price_chart = PriceChart()
        self.equity_chart = EquityChart()
        self.trades_table = self._build_trades_table()
        self.tabs.addTab(self.price_chart, "盘面 K线")
        self.tabs.addTab(self.equity_chart, "资金曲线")
        self.tabs.addTab(self.trades_table, "成交明细")
        v.addWidget(self.tabs, 1)
        return right

    def _build_metric_bar(self):
        frame = QtWidgets.QFrame()
        frame.setObjectName("Panel")
        grid = QtWidgets.QHBoxLayout(frame)
        grid.setContentsMargins(8, 8, 8, 8)
        self.metric_labels = {}
        for i, (title, key, kind) in enumerate(METRIC_CARDS):
            if i:
                grid.addWidget(self._vsep(34))
            cell = QtWidgets.QVBoxLayout()
            cell.setSpacing(3)
            t = QtWidgets.QLabel(title)
            t.setObjectName("FieldLabel")
            t.setAlignment(QtCore.Qt.AlignCenter)
            val = QtWidgets.QLabel("—")
            val.setAlignment(QtCore.Qt.AlignCenter)
            val.setFont(self._mono(17, bold=True))
            cell.addWidget(t)
            cell.addWidget(val)
            grid.addLayout(cell, 1)
            self.metric_labels[key] = (val, kind)
        return frame

    # ------------------------------------------------------------------ 行情条
    def _build_ticker(self):
        f = QtWidgets.QFrame()
        f.setObjectName("Ticker")
        f.setFixedHeight(74)
        lay = QtWidgets.QHBoxLayout(f)
        lay.setContentsMargins(16, 8, 16, 8)
        lay.setSpacing(16)

        # 左:标的名 + 周期徽章 + 数据源
        left = QtWidgets.QVBoxLayout()
        left.setSpacing(3)
        self.tk_symbol = QtWidgets.QLabel("—")
        self.tk_symbol.setStyleSheet(f"font-size:16px;font-weight:bold;color:{theme.TEXT};")
        meta = QtWidgets.QHBoxLayout()
        meta.setSpacing(6)
        self.tk_tf = QtWidgets.QLabel("")
        self.tk_tf.setObjectName("TfBadge")
        self.tk_src = QtWidgets.QLabel("")
        self.tk_src.setStyleSheet(f"color:{theme.MUTED};font-size:11px;")
        meta.addWidget(self.tk_tf)
        meta.addWidget(self.tk_src)
        meta.addStretch(1)
        left.addWidget(self.tk_symbol)
        left.addLayout(meta)
        lay.addLayout(left)

        lay.addWidget(self._vsep(46))

        # 中:最新价 + 涨跌徽章
        self.tk_last = QtWidgets.QLabel("—")
        self.tk_last.setFont(self._mono(26, bold=True))
        self.tk_last.setStyleSheet(f"color:{theme.TEXT};")
        lay.addWidget(self.tk_last)
        self.tk_chg = QtWidgets.QLabel("")
        self.tk_chg.setStyleSheet(f"color:{theme.MUTED};")
        lay.addWidget(self.tk_chg)

        lay.addStretch(1)

        # 右:区间统计(基于当前加载的K线区间,非自然24h)
        self.tk_high = self._ticker_stat(lay, "区间高")
        self.tk_low = self._ticker_stat(lay, "区间低")
        self.tk_amp = self._ticker_stat(lay, "振幅")
        self.tk_vol = self._ticker_stat(lay, "成交量")
        return f

    def _ticker_stat(self, lay, title):
        col = QtWidgets.QVBoxLayout()
        col.setSpacing(3)
        t = QtWidgets.QLabel(title)
        t.setStyleSheet(f"color:{theme.MUTED};font-size:11px;")
        val = QtWidgets.QLabel("—")
        val.setFont(self._mono(13, bold=True))
        val.setStyleSheet(f"color:{theme.TEXT};")
        col.addWidget(t)
        col.addWidget(val)
        wrap = QtWidgets.QWidget()
        wrap.setLayout(col)
        wrap.setMinimumWidth(80)
        lay.addWidget(wrap)
        return val

    def _vsep(self, h=40):
        line = QtWidgets.QFrame()
        line.setFixedSize(1, h)
        line.setStyleSheet(f"background:{theme.BORDER};")
        return line

    def _mono(self, px, bold=False):
        font = QtGui.QFont("Consolas")
        font.setStyleHint(QtGui.QFont.Monospace)
        font.setPixelSize(px)
        font.setBold(bold)
        return font

    @staticmethod
    def _fmt_price(x):
        ax = abs(x)
        if ax >= 1000:
            return f"{x:,.2f}"
        if ax >= 1:
            return f"{x:,.4f}"
        return f"{x:.6g}"

    @staticmethod
    def _fmt_vol(x):
        if x >= 1e8:
            return f"{x/1e8:.2f} 亿"
        if x >= 1e4:
            return f"{x/1e4:.2f} 万"
        return f"{x:,.0f}"

    def _update_ticker(self, res, tf, src):
        o = np.asarray(res["opens"], dtype=float)
        h = np.asarray(res["highs"], dtype=float)
        low = np.asarray(res["lows"], dtype=float)
        c = np.asarray(res["closes"], dtype=float)
        vol_arr = np.asarray(res["volumes"], dtype=float)
        if c.size == 0:
            return
        last = float(c[-1])
        first = float(o[0])
        chg = last - first
        pct = (last / first - 1.0) if first else 0.0
        hi = float(h.max())
        lo = float(low.min())
        amp = (hi - lo) / first if first else 0.0
        vol = float(vol_arr.sum())
        color = theme.UP_COLOR if pct >= 0 else theme.DOWN_COLOR
        soft = theme.UP_SOFT if pct >= 0 else theme.DOWN_SOFT

        self.tk_symbol.setText(f"{res['name']}　{res['symbol']}")
        self.tk_tf.setText(tf)
        self.tk_src.setText(src)
        self.tk_src.setStyleSheet(
            f"color:{theme.POS if '实时' in src else theme.ACCENT};font-size:11px;")
        self.tk_last.setText(self._fmt_price(last))
        self.tk_last.setStyleSheet(f"color:{color};")
        self.tk_chg.setText(f"{chg:+.4g}　{pct*100:+.2f}%")
        self.tk_chg.setStyleSheet(
            f"color:{color};background:{soft};border-radius:6px;padding:4px 10px;font-weight:bold;")
        self.tk_high.setText(self._fmt_price(hi))
        self.tk_low.setText(self._fmt_price(lo))
        self.tk_amp.setText(f"{amp*100:.2f}%")
        self.tk_vol.setText(self._fmt_vol(vol))

    def _build_trades_table(self):
        t = QtWidgets.QTableWidget(0, 7)
        t.setHorizontalHeaderLabels(["方向", "开仓时间", "开仓价", "平仓时间", "平仓价", "收益%", "原因"])
        t.verticalHeader().setVisible(False)
        t.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        t.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        hh = t.horizontalHeader()
        hh.setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        return t

    # ------------------------------------------------------------------ 小工具
    def _section(self, text):
        lbl = QtWidgets.QLabel(text)
        lbl.setObjectName("SectionTitle")
        lbl.setContentsMargins(0, 8, 0, 0)
        return lbl

    def _field(self, label, widget):
        box = QtWidgets.QVBoxLayout()
        box.setSpacing(3)
        lbl = QtWidgets.QLabel(label)
        lbl.setObjectName("FieldLabel")
        box.addWidget(lbl)
        box.addWidget(widget)
        return box

    def _pct_spin(self, value, bottom=0, top=90):
        sp = QtWidgets.QSpinBox()
        sp.setRange(bottom, top)
        sp.setValue(value)
        sp.setSuffix(" %")
        return sp

    # ------------------------------------------------------------------ 联动
    def _on_market_changed(self):
        mk = self.cb_market.currentData()
        info = MARKETS[mk]
        self.cb_symbol.blockSignals(True)
        self.cb_symbol.clear()
        self.cb_symbol.addItems(info["presets"])
        self.cb_symbol.setCurrentText(info["presets"][0])
        self.cb_symbol.blockSignals(False)
        cur_tf = self.cb_tf.currentText()
        self.cb_tf.blockSignals(True)
        self.cb_tf.clear()
        self.cb_tf.addItems(info["timeframes"])
        if cur_tf in info["timeframes"]:
            self.cb_tf.setCurrentText(cur_tf)
        elif "1d" in info["timeframes"]:
            self.cb_tf.setCurrentText("1d")
        self.cb_tf.blockSignals(False)

    def _on_strategy_changed(self):
        # 清空旧参数控件
        while self.param_box.count():
            item = self.param_box.takeAt(0)
            w = item.layout()
            if w:
                self._clear_layout(w)
        self._param_widgets = {}
        name = self.cb_strategy.currentData()
        for p in STRATEGY_SCHEMAS.get(name, []):
            step = p.get("step", 1)
            sp = QtWidgets.QDoubleSpinBox()
            sp.setRange(float(p["min"]), float(p["max"]))
            sp.setSingleStep(float(step))
            sp.setDecimals(0 if float(step).is_integer() else 1)
            sp.setValue(float(p["value"]))
            self.param_box.addLayout(self._field(p["label"], sp))
            self._param_widgets[p["key"]] = sp

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
            elif item.layout():
                self._clear_layout(item.layout())

    # ------------------------------------------------------------------ 跑任务
    def _collect_job(self, mode, refresh=False):
        params = {k: w.value() for k, w in self._param_widgets.items()}
        # 整数参数还原为 int(避免 10.0 这种)
        params = {k: (int(v) if float(v).is_integer() else v) for k, v in params.items()}
        return {
            "mode": mode,
            "market": self.cb_market.currentData(),
            "symbol": self.cb_symbol.currentText().strip(),
            "timeframe": self.cb_tf.currentText(),
            "limit": self.sp_limit.value(),
            "refresh": refresh,
            "strategy": self.cb_strategy.currentData(),
            "params": params,
            "capital": self.sp_capital.value(),
            "risk": {
                "stop_loss": self.sp_stop.value() / 100.0,
                "take_profit": self.sp_take.value() / 100.0,
                "position_size": self.sp_pos.value() / 100.0,
                "max_drawdown_stop": self.sp_dd.value() / 100.0,
            },
        }

    def load_klines(self):
        self._start(self._collect_job("klines"))

    def run_backtest(self, refresh=False):
        self._start(self._collect_job("backtest", refresh=refresh))

    def _start(self, job):
        if self._job is not None and self._job.isRunning():
            return
        self._set_busy(True)
        sym = job["symbol"]
        self.status.showMessage(f"正在取数并计算：{sym} · {job['timeframe']} …")
        self._job = Job(job)
        self._job.done.connect(self._on_done)
        self._job.failed.connect(self._on_failed)
        self._job.finished.connect(lambda: self._set_busy(False))
        self._job.start()

    def _set_busy(self, busy):
        for b in (self.btn_run, self.btn_klines, self.btn_refresh):
            b.setEnabled(not busy)
        self.btn_run.setText("运行中…" if busy else "运行回测")

    # ------------------------------------------------------------------ 渲染结果
    def _on_failed(self, msg):
        self.status.showMessage("失败:" + msg)
        QtWidgets.QMessageBox.warning(self, "取数/回测失败", msg)

    def _on_done(self, res):
        tf = res["timeframe"]
        self.price_chart.set_klines(res, tf)
        src = "🎲 模拟数据" if res["source"] == "synthetic" else "● 实时"
        self._update_ticker(res, tf, src)
        if res["source"] == "synthetic":
            self.banner.setText("⚠ 当前为【模拟离线数据】(随机假数据),仅供熟悉流程,绝不能用于真实判断!")
            self.banner.show()
        else:
            self.banner.hide()

        if res["mode"] == "klines":
            self.status.showMessage(f"已加载K线:{res['symbol']} · {tf} · {src} · 共 {len(res['closes'])} 根")
            return

        self.price_chart.set_overlays(res["overlays"])
        self.price_chart.set_oscillator(res["oscillator"])
        self.price_chart.set_markers(res["markers"])
        self.equity_chart.set_data(res["equity"], res["buy_hold"], res["drawdown"],
                                   res["index"], tf)
        self._fill_metrics(res["metrics"])
        self._fill_trades(res["trades"])
        self.risk_lbl.setText("风控:" + res["risk_desc"])
        m = res["metrics"]
        self.status.showMessage(
            f"完成:{res['symbol']} · {tf} · {src} · "
            f"交易 {m['交易次数']} 笔 · 总收益 {m['总收益率']*100:+.2f}% · "
            f"测试 {m.get('测试天数','?')} 天" +
            ("（年化样本偏短,仅参考）" if not m.get("年化可靠", True) else ""))

    def _fill_metrics(self, m):
        for key, (label, kind) in self.metric_labels.items():
            v = m.get(key)
            text, color = self._fmt_metric(v, kind)
            label.setText(text)
            label.setStyleSheet(f"font-size:17px;font-weight:bold;color:{color};")

    def _fmt_metric(self, v, kind):
        if v is None:
            return "—", theme.TEXT
        if kind == "pct_signed":
            return f"{v*100:+.2f}%", theme.fmt_color(v)
        if kind == "pct_dd":
            return f"{v*100:.2f}%", theme.NEG if v < 0 else theme.TEXT
        if kind == "pct_plain":
            return f"{v*100:.1f}%", theme.TEXT
        if kind == "num":
            return f"{v:.2f}", theme.fmt_color(v)
        if kind == "int":
            return f"{int(v)}", theme.TEXT
        if kind == "money":
            return f"{v:,.0f}", theme.TEXT
        return str(v), theme.TEXT

    def _fill_trades(self, trades):
        t = self.trades_table
        t.setRowCount(len(trades))
        for i, tr in enumerate(trades):
            dir_txt = "做多" if tr["dir"] == 1 else "做空"
            ret = tr["ret"] * 100
            cells = [
                dir_txt, tr["entry_time"][:16], f"{tr['entry_price']:.4g}",
                tr["exit_time"][:16], f"{tr['exit_price']:.4g}",
                f"{ret:+.2f}%", tr["reason"],
            ]
            for c, val in enumerate(cells):
                item = QtWidgets.QTableWidgetItem(val)
                if c == 0:
                    item.setForeground(QtGui.QColor(theme.UP_COLOR if tr["dir"] == 1 else theme.DOWN_COLOR))
                if c == 5:
                    item.setForeground(QtGui.QColor(theme.fmt_color(tr["ret"])))
                t.setItem(i, c, item)


def main():
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass
    os.makedirs(config.DATA_DIR, exist_ok=True)

    pg.setConfigOptions(antialias=True, background=theme.BG, foreground=theme.TEXT)
    QtWidgets.QApplication.setHighDpiScaleFactorRoundingPolicy(
        QtCore.Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QtWidgets.QApplication(sys.argv)
    app.setStyleSheet(theme.QSS)
    app.setFont(QtGui.QFont("Microsoft YaHei UI", 10))

    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
