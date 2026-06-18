# -*- coding: utf-8 -*-
"""
桌面版入口(纯原生窗口,零 HTML / 零浏览器)。

运行方式:
    python native_app.py            ← 源码运行(带控制台,方便看报错)
或双击    运行桌面版.bat              ← 无黑窗,像普通软件一样打开

打开后是一个真正的 Windows 程序窗口:左侧选市场/标的/策略/风控,
右侧看 K线盘面 + 买卖点 + 资金曲线 + 绩效指标。仍然只回测、不下单。
"""

import os
import sys

# 保证从任意目录双击/运行都能找到本项目的包
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from desktop.main_window import main

if __name__ == "__main__":
    main()
