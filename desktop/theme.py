# -*- coding: utf-8 -*-
"""
深色主题(对标币安 / OKX 盘面的配色与排版)。集中放颜色和样式表,改这一处全局变样。
"""

# ---- 涨跌配色 ----------------------------------------------------------
# 国际所(币安/OKX)默认:绿涨红跌。若你更习惯 A 股的"红涨绿跌",把这里改成 False。
UP_IS_GREEN = True

_GREEN = "#0ecb81"   # 币安绿
_RED = "#f6465d"     # 币安红

UP_COLOR = _GREEN if UP_IS_GREEN else _RED      # 阳线(收>开)
DOWN_COLOR = _RED if UP_IS_GREEN else _GREEN    # 阴线(收<开)

# ---- 基础色板 ----------------------------------------------------------
BG = "#0b0e11"          # 最底色(窗口)
PANEL = "#161a1e"       # 面板背景
PANEL2 = "#1e2329"      # 次级面板/输入框
HOVER = "#2a313b"       # 悬停高亮(按钮/行)
BORDER = "#2b3139"      # 描边
BORDER_SOFT = "#20262d" # 更细的内部分隔线
TEXT = "#eaecef"        # 主文字
MUTED = "#848e9c"       # 次要文字
FAINT = "#5e6673"       # 最弱文字(单位/角标)
ACCENT = "#f0b90b"      # 币安金(主按钮/高亮)
GRID = "#222831"        # 网格线

# 涨跌徽章的半透明浅底(行情条的涨跌 badge)
UP_SOFT = "rgba(14, 203, 129, 0.14)"
DOWN_SOFT = "rgba(246, 70, 93, 0.14)"

# 资金曲线 / 指标线配色
EQUITY = "#f0b90b"      # 策略资金曲线(金)
BUYHOLD = "#5b9cf6"     # 买入持有基准(蓝)
DRAWDOWN = "#f6465d"    # 回撤填充(红)
OVERLAY_COLORS = ["#f0b90b", "#5b9cf6", "#b47cff", "#26c6da", "#ff9f43"]  # 叠加均线轮换色

# 正/负数值上色(指标卡)
POS = _GREEN
NEG = _RED


def fmt_color(value) -> str:
    """正数绿(或按习惯)、负数红,用于指标卡文字。"""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return TEXT
    if v > 0:
        return POS
    if v < 0:
        return NEG
    return TEXT


# ---- 全局样式表(Qt QSS)-----------------------------------------------
QSS = f"""
* {{
    font-family: "Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI", sans-serif;
    font-size: 13px;
    color: {TEXT};
}}
QMainWindow, QWidget {{ background: {BG}; }}

QFrame#Panel {{
    background: {PANEL};
    border: 1px solid {BORDER};
    border-radius: 8px;
}}
QFrame#Ticker {{
    background: {PANEL};
    border: 1px solid {BORDER};
    border-radius: 8px;
}}

QLabel#SectionTitle {{
    color: {TEXT};
    font-size: 12px;
    font-weight: bold;
    padding-bottom: 4px;
    border-bottom: 1px solid {BORDER_SOFT};
}}
QLabel#FieldLabel {{ color: {MUTED}; font-size: 12px; }}
QLabel#TfBadge {{
    background: {PANEL2};
    color: {MUTED};
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 1px 8px;
    font-size: 11px;
    font-weight: bold;
}}

QComboBox, QLineEdit, QSpinBox, QDoubleSpinBox {{
    background: {PANEL2};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 5px 8px;
    min-height: 20px;
    selection-background-color: {ACCENT};
    selection-color: #16181c;
}}
QComboBox:hover, QLineEdit:hover, QSpinBox:hover, QDoubleSpinBox:hover {{ border: 1px solid {MUTED}; }}
QComboBox:focus, QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {{ border: 1px solid {ACCENT}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{
    background: {PANEL2};
    border: 1px solid {BORDER};
    border-radius: 6px;
    selection-background-color: {ACCENT};
    selection-color: #16181c;
    outline: none;
    padding: 2px;
}}
QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{ width: 16px; background: {BORDER}; }}
QSpinBox::up-button:hover, QSpinBox::down-button:hover,
QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover {{ background: {HOVER}; }}

QPushButton {{
    background: {PANEL2};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 8px 14px;
    color: {TEXT};
}}
QPushButton:hover {{ background: {HOVER}; border: 1px solid {MUTED}; }}
QPushButton:pressed {{ background: {PANEL}; }}
QPushButton:disabled {{ color: {MUTED}; background: {PANEL}; border: 1px solid {BORDER_SOFT}; }}

QPushButton#Primary {{
    background: {ACCENT};
    color: #16181c;
    font-weight: bold;
    border: none;
}}
QPushButton#Primary:hover {{ background: #f8c52a; }}
QPushButton#Primary:pressed {{ background: #d9a400; }}
QPushButton#Primary:disabled {{ background: {BORDER}; color: {MUTED}; }}

QTabWidget::pane {{ border: none; border-top: 1px solid {BORDER_SOFT}; top: -1px; }}
QTabBar {{ background: transparent; }}
QTabBar::tab {{
    background: transparent;
    color: {MUTED};
    padding: 8px 20px;
    border: none;
    border-bottom: 2px solid transparent;
    margin-right: 4px;
    font-size: 13px;
}}
QTabBar::tab:hover {{ color: {TEXT}; }}
QTabBar::tab:selected {{ color: {TEXT}; border-bottom: 2px solid {ACCENT}; font-weight: bold; }}

QTableWidget {{
    background: {PANEL};
    border: 1px solid {BORDER};
    border-radius: 8px;
    gridline-color: {BORDER_SOFT};
    selection-background-color: {HOVER};
    selection-color: {TEXT};
}}
QTableWidget::item {{ padding: 2px 4px; }}
QHeaderView::section {{
    background: {PANEL2};
    color: {MUTED};
    border: none;
    border-bottom: 1px solid {BORDER};
    padding: 7px 6px;
    font-weight: 600;
}}
QTableCornerButton::section {{ background: {PANEL2}; border: none; }}

QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 5px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {MUTED}; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 0; }}
QScrollBar::handle:horizontal {{ background: {BORDER}; border-radius: 5px; min-width: 30px; }}
QScrollBar::handle:horizontal:hover {{ background: {MUTED}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QStatusBar {{ background: {PANEL}; color: {MUTED}; border-top: 1px solid {BORDER}; }}
QStatusBar::item {{ border: none; }}

QToolTip {{ background: {PANEL2}; color: {TEXT}; border: 1px solid {ACCENT}; padding: 4px 6px; }}
"""
