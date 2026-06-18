# -*- coding: utf-8 -*-
"""
指标配置:默认值 / 颜色 / 持久化(存到 data 目录的 json,改完下次打开还在)。
默认值与网页版 web/app.js 的 DEFAULT_CFG 完全一致。
"""

import copy
import json
import os

import config

# 默认显示:MA(7/25/99) + 成交量 + RSI(6/12/24);其余默认关。
DEFAULT_CFG = {
    "ma":   {"on": True,  "lines": [{"on": True, "p": 7}, {"on": True, "p": 25},
                                    {"on": True, "p": 99}, {"on": False, "p": 200}]},
    "ema":  {"on": False, "lines": [{"on": True, "p": 12}, {"on": True, "p": 26}]},
    "boll": {"on": False, "p": 20, "k": 2.0},
    "vol":  {"on": True},
    "subs": {
        "macd": {"on": False, "fast": 12, "slow": 26, "sig": 9},
        "rsi":  {"on": True,  "lines": [{"on": True, "p": 6}, {"on": True, "p": 12},
                                        {"on": True, "p": 24}]},
        "kdj":  {"on": False, "n": 9, "kp": 3, "dp": 3},
    },
}

# 配色(对齐网页版指标弹窗的圆点色)
MA_COLORS = ["#f0b90b", "#e056a0", "#8950fa", "#36c5f0"]
EMA_COLORS = ["#74c0fc", "#7af0c3"]
RSI_COLORS = ["#f0b90b", "#e056a0", "#8950fa"]
BOLL_UP = "#74c0fc"
BOLL_MID = "#f0b90b"
BOLL_LO = "#74c0fc"
MACD_DIF = "#74c0fc"
MACD_DEA = "#f0b90b"
KDJ_K = "#f0b90b"
KDJ_D = "#74c0fc"
KDJ_J = "#e056a0"

_PATH = os.path.join(config.DATA_DIR, "indicator_cfg.json")


def _merge(base, saved):
    """把已保存的值深合并进默认配置(只覆盖存在的键,结构以默认为准)。"""
    if not isinstance(saved, dict):
        return base
    for k, v in saved.items():
        if k in base and isinstance(base[k], dict) and isinstance(v, dict):
            _merge(base[k], v)
        elif k in base and isinstance(base[k], list) and isinstance(v, list):
            for i, item in enumerate(v):
                if i < len(base[k]) and isinstance(base[k][i], dict) and isinstance(item, dict):
                    _merge(base[k][i], item)
        elif k in base:
            base[k] = v
    return base


def load_cfg():
    cfg = copy.deepcopy(DEFAULT_CFG)
    try:
        with open(_PATH, encoding="utf-8") as f:
            _merge(cfg, json.load(f))
    except Exception:
        pass
    return cfg


def save_cfg(cfg):
    try:
        os.makedirs(config.DATA_DIR, exist_ok=True)
        with open(_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def default_cfg():
    return copy.deepcopy(DEFAULT_CFG)
