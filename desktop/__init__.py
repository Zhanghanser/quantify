# -*- coding: utf-8 -*-
"""
原生桌面版界面(纯 PySide6 + pyqtgraph,零 HTML / 零浏览器)。

和网页版(run_web.py)完全等价地复用同一套后端:
  src.data.get_data / src.strategies / src.backtest.run_backtest / src.risk
区别只在于:这里是一个真正的 Windows 程序窗口,不再开浏览器、没有网址栏。

入口:项目根目录的 native_app.py  →  desktop.main_window.main()
仍然只回测 / 只显示信号,绝不下单、不碰真钱。
"""
