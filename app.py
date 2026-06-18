# -*- coding: utf-8 -*-
"""
可视化操作台(入口6,Web 仪表盘)。

运行方法(在项目目录下执行,浏览器会自动打开):
    streamlit run app.py

这是整个项目的"驾驶舱",把之前所有命令行入口图形化:
  📊 策略回测   = run_demo     (K线+买卖点+资金曲线+回撤,全部可缩放拖动)
  ⚖️ 多策略对比 = run_compare
  🌍 多标的验证 = run_validate
  📡 实时信号   = run_live     (只读不下单)

左侧边栏改任何参数,页面会自动重新计算 —— 不用改代码、不用敲命令。
"""

import sys
if sys.platform == "win32":
    # Windows 控制台默认 GBK,打印 emoji 会报错,统一切到 UTF-8
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import config
from src.data import get_data
from src.strategies import STRATEGIES, get_strategy
from src.backtest import run_backtest, PERIODS_PER_YEAR
from src.risk import RiskConfig

# ============================================================
# 页面基础设置 + 一点自定义样式(让界面更像专业终端)
# ============================================================
st.set_page_config(page_title="量化操作台 · quantify", page_icon="📈",
                   layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
/* 顶部留白收紧 */
.block-container { padding-top: 1.2rem; padding-bottom: 2rem; }
/* 指标卡片:加边框和圆角,像交易终端 */
div[data-testid="stMetric"] {
    background: linear-gradient(145deg, #161b26 0%, #1c2230 100%);
    border: 1px solid #2a3142;
    border-radius: 12px;
    padding: 12px 16px;
}
div[data-testid="stMetricLabel"] { color: #9aa4b2; }
/* 标签页字体加大 */
button[data-baseweb="tab"] { font-size: 1.05rem; }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div style="background: linear-gradient(90deg,#1a2235 0%,#10141f 100%);
            border:1px solid #2a3142;border-radius:14px;
            padding:18px 26px;margin-bottom:14px;">
  <span style="font-size:1.7rem;font-weight:700;color:#f0b90b;">📈 量化操作台</span>
  <span style="color:#9aa4b2;margin-left:14px;">
    数据 → 策略 → 回测 → 风控 → 信号,全流程可视化 · 只回测不下单,不动你的钱
  </span>
</div>
""", unsafe_allow_html=True)

# 中国习惯配色:红涨绿跌
C_UP, C_DOWN = "#f6465d", "#2ebd85"
C_GOLD, C_GRAY = "#f0b90b", "#8a8f98"

# ============================================================
# 侧边栏:所有可调参数
# ============================================================
st.sidebar.title("⚙️ 控制台")

MARKET_NAMES = {"crypto": "₿ 币圈", "astock": "🇨🇳 A股", "usstock": "🇺🇸 美股"}
market = st.sidebar.selectbox("市场", list(MARKET_NAMES),
                              format_func=lambda m: MARKET_NAMES[m])

# 各市场常用标的(也可以选"自定义"手动输入)
PRESETS = {
    "crypto":  ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT"],
    "astock":  ["000001", "600519", "300750"],
    "usstock": ["AAPL", "TSLA", "NVDA", "MSFT"],
}
sym_choice = st.sidebar.selectbox("标的", PRESETS[market] + ["自定义…"])
symbol = (st.sidebar.text_input("输入标的代码", value=PRESETS[market][0])
          if sym_choice == "自定义…" else sym_choice)

TF_OPTIONS = {"crypto": ["15m", "1h", "4h", "1d"],
              "astock": ["1d"], "usstock": ["1d", "1h"]}
timeframe = st.sidebar.selectbox("K线周期", TF_OPTIONS[market],
                                 index=1 if market == "crypto" else 0)
limit = st.sidebar.slider("K线数量(数据长度)", 300, 3000, 1000, step=100)

st.sidebar.divider()
strat_name = st.sidebar.selectbox(
    "策略", list(STRATEGIES),
    format_func=lambda n: f"{STRATEGIES[n].display_name} ({n})", index=3)

# 各策略的参数控件(滑块改完即时生效)
params = {}
if strat_name == "dual_ma":
    params["fast"] = st.sidebar.slider("快线周期", 3, 60, 10)
    params["slow"] = st.sidebar.slider("慢线周期", 10, 200, 30)
elif strat_name == "rsi_reversion":
    params["period"] = st.sidebar.slider("RSI 周期", 5, 30, 14)
    params["oversold"] = st.sidebar.slider("超卖线(低于此抄底)", 10, 45, 30)
    params["exit_level"] = st.sidebar.slider("离场线(回升到此卖出)", 40, 80, 50)
elif strat_name == "breakout":
    params["lookback"] = st.sidebar.slider("通道回看周期", 5, 100, 20)
elif strat_name == "trend_filter":
    params["fast"] = st.sidebar.slider("快线周期", 3, 60, 20)
    params["slow"] = st.sidebar.slider("慢线周期", 10, 120, 50)
    params["trend"] = st.sidebar.slider("大趋势均线周期", 50, 300, 100)

st.sidebar.divider()
with st.sidebar.expander("🛡️ 风控设置(阶段4)", expanded=True):
    capital = st.number_input("初始资金 (USDT)", 1000, 10_000_000,
                              config.INITIAL_CAPITAL, step=1000)
    stop_loss = st.slider("止损 %(0=关闭)", 0, 30, 10) / 100
    take_profit = st.slider("止盈 %(0=关闭)", 0, 100, 0) / 100
    position_size = st.slider("每笔仓位 %", 10, 100, 50) / 100
    mdd_stop = st.slider("回撤熔断 %(0=关闭)", 0, 50, 25) / 100

risk = RiskConfig(stop_loss=stop_loss, take_profit=take_profit,
                  position_size=position_size, max_drawdown_stop=mdd_stop)
config.INITIAL_CAPITAL = int(capital)   # 本金对全局生效

st.sidebar.caption("国内网络:币圈走 gate.io 可直连;A股/美股连不上时会用模拟数据兜底(图上会很假,别当真)。")


# ============================================================
# 数据加载(带10分钟缓存,改参数不会反复下载)
# ============================================================
@st.cache_data(ttl=600, show_spinner="📡 正在获取行情数据…")
def load_data(market, symbol, timeframe, limit):
    return get_data(market=market, symbol=symbol,
                    timeframe=timeframe, limit=limit)


def find_trades_points(df):
    """从逐K线持仓里找出买卖点(持仓增加=买入,减少=卖出)。"""
    chg = df["exec_pos"].diff()
    return df[chg > 0], df[chg < 0]


def drawdown_series(equity):
    return equity / equity.cummax() - 1


try:
    raw = load_data(market, symbol, timeframe, limit)
except Exception as e:
    st.error(f"取数失败:{e}")
    st.stop()

# ============================================================
# 四个标签页
# ============================================================
tab1, tab2, tab3, tab4 = st.tabs(
    ["📊 策略回测", "⚖️ 多策略对比", "🌍 多标的验证", "📡 实时信号"])

# ------------------------------------------------------------
# 标签1:单策略回测(主页面)
# ------------------------------------------------------------
with tab1:
    strat = get_strategy(strat_name, **params)
    sdf = strat.generate(raw)
    result = run_backtest(sdf, timeframe=timeframe, risk=risk)
    df, m = result["df"], result["metrics"]

    # ----- 指标卡片 -----
    cols = st.columns(7)
    diff = m["总收益率"] - m["买入持有收益率"]
    cols[0].metric("总收益率", f"{m['总收益率']:+.1%}",
                   f"{diff:+.1%} vs 买入持有",
                   delta_color="normal" if diff >= 0 else "inverse")
    cols[1].metric("买入持有", f"{m['买入持有收益率']:+.1%}")
    cols[2].metric("年化收益", f"{m['年化收益率']:+.1%}")
    cols[3].metric("夏普比率", f"{m['夏普比率']:.2f}",
                   ">1 较好 >2 优秀", delta_color="off")
    cols[4].metric("最大回撤", f"{m['最大回撤']:.1%}")
    cols[5].metric("交易次数", f"{m['交易次数']} 笔")
    cols[6].metric("胜率", f"{m['胜率']:.0%}")

    # ----- 主图:K线 + 指标 + 买卖点 / 资金曲线 / 回撤 / 副图 -----
    has_rsi = "rsi" in df.columns
    sub_title = "RSI 指标" if has_rsi else "成交量"
    fig = make_subplots(
        rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.03,
        row_heights=[0.45, 0.22, 0.16, 0.17],
        subplot_titles=(f"{symbol} · {timeframe} K线与买卖点",
                        "资金曲线(策略 vs 买入持有)", "回撤", sub_title))

    fig.add_trace(go.Candlestick(
        x=df.index, open=df["open"], high=df["high"],
        low=df["low"], close=df["close"], name="K线",
        increasing_line_color=C_UP, increasing_fillcolor=C_UP,
        decreasing_line_color=C_DOWN, decreasing_fillcolor=C_DOWN), row=1, col=1)

    # 策略自带的指标线,有什么画什么
    OVERLAYS = [("ma_fast", "快线", "#5ab0ff"), ("ma_slow", "慢线", "#f0b90b"),
                ("ma_trend", "大趋势线", "#c792ea"),
                ("upper", "通道上轨", "#5ab0ff"), ("lower", "通道下轨", "#c792ea")]
    for col_name, label, color in OVERLAYS:
        if col_name in df.columns:
            fig.add_trace(go.Scatter(x=df.index, y=df[col_name], name=label,
                                     line=dict(width=1.2, color=color)),
                          row=1, col=1)

    buys, sells = find_trades_points(df)
    fig.add_trace(go.Scatter(x=buys.index, y=buys["close"], mode="markers",
                             name="买入", marker=dict(symbol="triangle-up",
                             size=11, color=C_UP, line=dict(width=1, color="white"))),
                  row=1, col=1)
    fig.add_trace(go.Scatter(x=sells.index, y=sells["close"], mode="markers",
                             name="卖出", marker=dict(symbol="triangle-down",
                             size=11, color=C_DOWN, line=dict(width=1, color="white"))),
                  row=1, col=1)

    fig.add_trace(go.Scatter(x=df.index, y=df["equity"], name="策略资金",
                             line=dict(width=2, color=C_GOLD)), row=2, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df["buy_hold"], name="买入持有",
                             line=dict(width=1.3, color=C_GRAY, dash="dash")),
                  row=2, col=1)

    dd = drawdown_series(df["equity"])
    fig.add_trace(go.Scatter(x=df.index, y=dd, name="回撤", fill="tozeroy",
                             line=dict(width=1, color=C_UP),
                             fillcolor="rgba(246,70,93,0.25)"), row=3, col=1)

    if has_rsi:
        fig.add_trace(go.Scatter(x=df.index, y=df["rsi"], name="RSI",
                                 line=dict(width=1.2, color="#5ab0ff")), row=4, col=1)
        fig.add_hline(y=params.get("oversold", 30), line_dash="dot",
                      line_color=C_DOWN, row=4, col=1)
        fig.add_hline(y=params.get("exit_level", 50), line_dash="dot",
                      line_color=C_GRAY, row=4, col=1)
    elif "volume" in df.columns:
        vol_color = np.where(df["close"] >= df["open"], C_UP, C_DOWN)
        fig.add_trace(go.Bar(x=df.index, y=df["volume"], name="成交量",
                             marker_color=vol_color), row=4, col=1)

    fig.update_layout(template="plotly_dark", height=950,
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#10141f",
                      hovermode="x unified",
                      legend=dict(orientation="h", y=1.04, x=0),
                      margin=dict(l=10, r=10, t=60, b=10))
    fig.update_xaxes(rangeslider_visible=False)
    fig.update_yaxes(tickformat=".0%", row=3, col=1)
    st.plotly_chart(fig, use_container_width=True)
    st.caption("💡 图表可以鼠标框选放大、双击还原、滚轮缩放;图例点一下可以隐藏/显示对应线条。")

    # ----- 逐笔交易明细 -----
    with st.expander(f"📋 逐笔交易明细(共 {len(result['trades'])} 笔)"):
        if result["trades"]:
            tdf = pd.DataFrame(result["trades"])
            tdf.index = range(1, len(tdf) + 1)
            tdf["收益率"] = tdf["ret"].map(lambda r: f"{r:+.2%}")
            reason_stat = tdf["reason"].value_counts().to_dict()
            st.write("平仓原因统计:", reason_stat)
            st.dataframe(tdf[["收益率", "reason"]].rename(columns={"reason": "平仓原因"}),
                         use_container_width=True, height=240)
        else:
            st.info("这段数据里没有产生交易(信号太少或都被风控挡住)。")
        st.download_button("⬇️ 导出回测明细 CSV",
                           df.to_csv().encode("utf-8-sig"),
                           file_name=f"backtest_{strat_name}.csv")

# ------------------------------------------------------------
# 标签2:多策略对比
# ------------------------------------------------------------
with tab2:
    st.markdown(f"同一段 **{symbol} · {timeframe}** 数据,4 个策略(默认参数)+ 当前风控一起跑:")
    rows, curves = [], {}
    for name, cls in STRATEGIES.items():
        r = run_backtest(cls().generate(raw), timeframe=timeframe, risk=risk)
        mm = r["metrics"]
        rows.append({"策略": cls.display_name, "总收益率": mm["总收益率"],
                     "年化": mm["年化收益率"], "夏普": mm["夏普比率"],
                     "最大回撤": mm["最大回撤"], "交易数": mm["交易次数"],
                     "胜率": mm["胜率"]})
        curves[cls.display_name] = r["df"]["equity"]

    cmp_df = pd.DataFrame(rows).set_index("策略")
    bh = m["买入持有收益率"]

    c1, c2 = st.columns([3, 2])
    with c1:
        figc = go.Figure()
        for label, eq in curves.items():
            figc.add_trace(go.Scatter(x=eq.index, y=eq, name=label, line=dict(width=1.8)))
        figc.add_trace(go.Scatter(x=df.index, y=df["buy_hold"], name="买入持有(基准)",
                                  line=dict(width=1.3, color=C_GRAY, dash="dash")))
        figc.update_layout(template="plotly_dark", height=420, title="资金曲线对比",
                           paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#10141f",
                           legend=dict(orientation="h", y=1.12, x=0),
                           margin=dict(l=10, r=10, t=70, b=10))
        st.plotly_chart(figc, use_container_width=True)
    with c2:
        figb = go.Figure(go.Bar(
            x=cmp_df["总收益率"], y=cmp_df.index, orientation="h",
            marker_color=[C_UP if v >= 0 else C_DOWN for v in cmp_df["总收益率"]],
            text=[f"{v:+.1%}" for v in cmp_df["总收益率"]], textposition="outside"))
        figb.add_vline(x=bh, line_dash="dash", line_color=C_GRAY,
                       annotation_text=f"买入持有 {bh:+.1%}")
        figb.update_layout(template="plotly_dark", height=420, title="总收益率对比",
                           paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#10141f",
                           xaxis_tickformat=".0%", margin=dict(l=10, r=40, t=70, b=10))
        st.plotly_chart(figb, use_container_width=True)

    st.dataframe(cmp_df.style.format({"总收益率": "{:+.1%}", "年化": "{:+.1%}",
                                      "夏普": "{:.2f}", "最大回撤": "{:.1%}",
                                      "胜率": "{:.0%}"}),
                 use_container_width=True)
    st.caption("💡 趋势类(双均线/突破/趋势过滤)和逆势类(RSI)在同一行情里表现常常相反——没有万能策略。")

# ------------------------------------------------------------
# 标签3:多标的诚实验证(阶段6)
# ------------------------------------------------------------
with tab3:
    st.markdown("""**固定参数、绝不回头调**(杜绝过拟合),用同一套策略跑多个币的日线,
看它是不是"普遍"有效,顺便验证"等权组合能降回撤"。""")
    v_assets = st.multiselect("参与验证的标的(日线)",
                              PRESETS["crypto"], default=PRESETS["crypto"])
    V_PARAMS = {"fast": 20, "slow": 50, "trend": 100}
    V_RISK = RiskConfig(stop_loss=0.10, take_profit=0.0,
                        position_size=0.5, max_drawdown_stop=0.25)
    st.caption(f"固定配置:trend_filter {V_PARAMS} · {V_RISK.describe()}")

    if v_assets:
        vstrat = get_strategy("trend_filter", **V_PARAMS)
        vrows, rets = [], {}
        for a in v_assets:
            try:
                vdf = load_data("crypto", a, "1d", 1000)
            except Exception as e:
                st.warning(f"{a} 跳过:{e}")
                continue
            vr = run_backtest(vstrat.generate(vdf), timeframe="1d", risk=V_RISK)
            vm = vr["metrics"]
            vrows.append({"标的": a, "策略收益": vm["总收益率"],
                          "买入持有": vm["买入持有收益率"], "夏普": vm["夏普比率"],
                          "最大回撤": vm["最大回撤"], "交易数": vm["交易次数"],
                          "胜率": vm["胜率"]})
            rets[a] = vr["df"]["equity"].pct_change()

        if vrows:
            vt = pd.DataFrame(vrows).set_index("标的")
            port = pd.DataFrame(rets).mean(axis=1)
            port_eq = (1 + port.fillna(0)).cumprod() * config.INITIAL_CAPITAL
            port_dd = drawdown_series(port_eq).min()
            ppy = PERIODS_PER_YEAR["1d"]
            port_sharpe = (port.mean() / port.std() * np.sqrt(ppy)
                           if port.std() > 0 else 0.0)

            k1, k2, k3, k4 = st.columns(4)
            k1.metric("组合总收益", f"{port_eq.iloc[-1]/config.INITIAL_CAPITAL-1:+.1%}")
            k2.metric("组合夏普", f"{port_sharpe:.2f}")
            k3.metric("组合最大回撤", f"{port_dd:.1%}",
                      f"单币平均 {vt['最大回撤'].mean():.1%}", delta_color="off")
            k4.metric("正收益标的", f"{(vt['策略收益']>0).sum()} / {len(vt)}")

            figp = go.Figure()
            for a, r in rets.items():
                eq = (1 + r.fillna(0)).cumprod() * config.INITIAL_CAPITAL
                figp.add_trace(go.Scatter(x=eq.index, y=eq, name=a,
                                          line=dict(width=1), opacity=0.45))
            figp.add_trace(go.Scatter(x=port_eq.index, y=port_eq, name="等权组合",
                                      line=dict(width=3, color=C_GOLD)))
            figp.update_layout(template="plotly_dark", height=420,
                               title="各标的策略资金曲线 vs 等权组合(金色粗线)",
                               paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#10141f",
                               legend=dict(orientation="h", y=1.12, x=0),
                               margin=dict(l=10, r=10, t=70, b=10))
            st.plotly_chart(figp, use_container_width=True)

            st.dataframe(vt.style.format({"策略收益": "{:+.1%}", "买入持有": "{:+.1%}",
                                          "夏普": "{:.2f}", "最大回撤": "{:.1%}",
                                          "胜率": "{:.0%}"}),
                         use_container_width=True)
            st.info("📊 诚实解读:只有在【大多数】标的上同时有正收益/正夏普,策略才算有普遍性;"
                    "只有 1-2 个好 = 很可能是运气。组合回撤通常小于单币平均——分散是少有的免费午餐。"
                    "固定参数 + 多标的 + 保守风控,目标是活得久,不是暴富。")

# ------------------------------------------------------------
# 标签4:实时信号(只读,不下单)
# ------------------------------------------------------------
with tab4:
    st.markdown(f"**{symbol} · {timeframe}** 最新一根K线收盘后,各策略给出的方向判断:")
    if st.button("🔄 拉取最新行情并刷新信号"):
        load_data.clear()           # 清掉缓存,强制重新下载
        st.rerun()

    last_time = raw.index[-1]
    last_close = raw["close"].iloc[-1]
    st.caption(f"数据截至:{last_time} · 最新收盘价:{last_close:,.2f}")

    sig_cols = st.columns(len(STRATEGIES))
    for i, (name, cls) in enumerate(STRATEGIES.items()):
        s = cls().generate(raw)
        cur = int(s["position"].iloc[-1])
        prev = int(s["position"].iloc[-2]) if len(s) > 1 else 0
        label = {1: "🔴 看多/持有", 0: "⚪ 空仓观望", -1: "🟢 看空"}[cur]
        change = {(0, 1): "📢 新买入信号!", (1, 0): "📢 新卖出信号!"}.get((prev, cur), "")
        sig_cols[i].metric(cls.display_name, label, change or "信号无变化",
                           delta_color="off")

    st.warning("⚠️ 信号 ≠ 赚钱保证。本程序**只显示信号,绝不自动下单**。"
               "回测好看 ≠ 实盘赚钱,任何真金白银操作前请先走完:样本外检验 → 测试网 → 极小资金试水。")
