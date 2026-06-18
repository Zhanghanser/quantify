# -*- coding: utf-8 -*-
"""
桌面启动器(打包成 exe 的入口)。

双击 exe 后:
  1. 在本机启动 FastAPI 交易终端(端口 8000 被占用就自动顺延到 8001、8002…)
  2. 自动用默认浏览器打开页面
  3. 这个黑色控制台窗口保持开着 = 程序在运行;关掉窗口 = 停止程序

和源码运行完全等价,只是多了"自动开浏览器 + 找空闲端口 + 友好提示"。
仍然只回测/只显示信号,绝不下单、不碰真钱。
"""

import sys
import os
import time
import socket
import threading
import webbrowser

# Windows 控制台默认 GBK,打印中文/emoji 会报错,统一切 UTF-8
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import uvicorn

import config
# 确保可写的缓存目录存在(打包后它在 exe 旁边)
os.makedirs(config.DATA_DIR, exist_ok=True)

# 复用 run_web.py 里已经搭好的 FastAPI app(导入时不会启动服务器,因为它在 __main__ 里才 run)
from run_web import app

HOST = "127.0.0.1"


def _find_free_port(start=8000, tries=20):
    """从 start 开始找一个没被占用的端口,避免本机已有程序占着 8000 时直接崩。"""
    for p in range(start, start + tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind((HOST, p))
                return p
            except OSError:
                continue
    return start  # 实在都占用了就用默认的,让 uvicorn 自己报错


def _open_browser_when_ready(url, timeout=40):
    """轮询服务器,起来了再开浏览器,避免开太早打开一个还连不上的页面。"""
    import urllib.request
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=1)
            break
        except Exception:
            time.sleep(0.4)
    try:
        webbrowser.open(url)
    except Exception:
        pass


def main():
    port = _find_free_port(8000)
    url = f"http://{HOST}:{port}/"

    print("=" * 56)
    print("   量化终端 · quantify   （只回测 / 只显示信号，不下单）")
    print("   作者：张佳泽（软件工程师）   © 2026  保留所有权利")
    print("=" * 56)
    print(f"   正在启动... 浏览器会自动打开：{url}")
    print("   如果没自动打开，手动复制上面这个地址到浏览器即可。")
    print("   ⚠ 关闭这个黑色窗口 = 停止程序。")
    print("=" * 56)

    threading.Thread(target=_open_browser_when_ready, args=(url,), daemon=True).start()

    try:
        uvicorn.run(app, host=HOST, port=port, log_level="warning")
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"\n启动失败：{e}")
        input("按回车键退出...")


if __name__ == "__main__":
    main()
