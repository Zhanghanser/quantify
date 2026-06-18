# -*- coding: utf-8 -*-
"""生成应用图标 icon.ico(深色盘面 + 红绿K线,贴合交易终端主题)。"""
from PIL import Image, ImageDraw

S = 256
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)

# 圆角深色底
bg = (14, 17, 22, 255)
d.rounded_rectangle([8, 8, S - 8, S - 8], radius=44, fill=bg, outline=(43, 49, 57, 255), width=3)

UP = (14, 203, 129)    # 涨-绿(Binance 绿)
DN = (246, 70, 93)     # 跌-红
GOLD = (240, 185, 11)

def candle(cx, body_top, body_bot, wick_top, wick_bot, color, bw=22):
    d.line([cx, wick_top, cx, wick_bot], fill=color, width=4)
    d.rounded_rectangle([cx - bw // 2, body_top, cx + bw // 2, body_bot], radius=4, fill=color)

# 三根K线:绿、红、绿(模拟一段行情)
candle(78,  96, 168,  70, 196, UP)
candle(128, 70, 132,  48, 176, DN)
candle(178, 110, 150,  86, 188, UP)

# 一条金色均线穿过
d.line([40, 150, 78, 120, 128, 138, 178, 104, 216, 120], fill=GOLD, width=5, joint="curve")

sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]
img.save("icon.ico", sizes=sizes)
print("icon.ico 生成完成")
