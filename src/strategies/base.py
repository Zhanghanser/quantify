# -*- coding: utf-8 -*-
"""
策略基类。

所有策略都继承这个基类,并实现 generate() 方法。
统一约定:generate() 输入行情表,输出一个新表,其中包含一列 'position':
    position = 1   → 做多(看涨,持有多头)
    position = 0   → 空仓(不持有)
    position = -1  → 做空(看跌,持有空头;币圈/外汇/美股可做空,A股一般不行)

这样回测引擎、对比工具、实时监控都能用同一套接口处理任何策略,
这就是"统一接口"的好处:加新策略只要写一个新子类,其它代码都不用改。
"""

import pandas as pd


class Strategy:
    # 策略英文名(用作字典 key 和文件名)
    name = "base"
    # 中文显示名
    display_name = "基类策略"

    def __init__(self, **params):
        # 策略参数(如均线周期),存成字典,方便参数优化时批量替换
        self.params = params

    def generate(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        子类必须实现:输入行情表,返回带 'position' 列的新表。
        """
        raise NotImplementedError("每个策略都要自己实现 generate() 方法")

    def __repr__(self):
        param_str = ", ".join(f"{k}={v}" for k, v in self.params.items())
        return f"{self.display_name}({param_str})"
