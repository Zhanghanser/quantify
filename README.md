<div align="center">

# 📈 量化终端 · quantify

**一套代码,三个市场。** 仿币安 / OKX 的专业 K 线交易终端 + 多策略回测引擎 + 实时信号决策台
—— 纯 Python,免费开箱,**断网也能用**。

*A Binance-style trading terminal for crypto / A-shares / US stocks — multi-strategy backtesting,
real-time signals & an honest decision desk. Pure Python, free, offline-capable.*

![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![Charts](https://img.shields.io/badge/Charts-TradingView%20lightweight--charts-2962FF)
![GitHub stars](https://img.shields.io/github/stars/Zhanghanser/quantify?style=flat&logo=github)
![Last commit](https://img.shields.io/github/last-commit/Zhanghanser/quantify)
![Platform](https://img.shields.io/badge/platform-Web%20%7C%20Windows-lightgrey)
![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)

</div>

![专业 K 线交易终端](docs/screenshots/terminal.png)

> ⚠️ **重要**:本项目只做**回测和信号显示**,**绝不自动下单、不碰你的钱**,不构成任何投资建议。
> 回测赚钱 ≠ 实盘赚钱。真金白银前还有很长的路(见文末路线图)。

---

## ✨ 亮点速览

- 🖥️ **专业 K 线终端**:TradingView 同款图表引擎(lightweight-charts),仿币安深色盘面 ——
  滚轮缩放 / 拖拽 / 十字光标、线性·对数·百分比价格轴、红涨绿跌一键互换。
- ⚡ **毫秒级实时行情**(币圈):直连 gate WebSocket,价格与最后一根 K 线实时跳动,带**收盘倒计时**。
- 📊 **交易所级指标系统**:主图 MA×4 / EMA×2 / BOLL / 成交量,副图 MACD / RSI×3 / KDJ 可**同时多开**,
  参数全自定义、十字光标跨图联动、数值跟随。
- 📡 **实时决策台**:多策略**共识方向** + 人话**盘面解读** + 一张算好止损止盈仓位的**建议订单** ——
  出新信号弹窗+响铃+通知,但**永远只给建议、绝不替你下单**。
- 🧠 **9 个可插拔策略**:双均线 / 通道突破 / RSI 均值回归 / 趋势过滤 + 5 个短线策略(布林反弹 / RSI 快速反弹 / 带量突破 / VWAP 回归 / BOLL+RSI 双确认)。
- 🩺 **短线体检 + 🔬 稳健性检验**:每笔期望、盈亏比、**手续费拖累**、样本外对比 —— 一眼看穿"这套短打是真有优势还是在给交易所打工"。
- 🌍 **三市场统一接口**:币圈(ccxt)/ A 股(新浪)/ 美股(雅虎),换市场只改一行配置。
- 🔒 **诚实**:连不上网用模拟数据会**打红标**;绩效指标样本太短自动置灰;事件合约直接把"负期望、长期必亏"摆给你看。

![实时决策台](docs/screenshots/decision-desk.png)

---

## 🚀 快速开始

```powershell
pip install -r requirements.txt
python run_web.py          # 然后浏览器打开 http://localhost:8000
```

停止:终端按 `Ctrl+C`。换市场 / 标的 / 策略,只改 [`config.py`](config.py) 一处即可。

<details>
<summary>🇬🇧 <b>English summary</b> (click to expand)</summary>

**quantify** is a pure-Python quant toolkit with a professional, Binance/OKX-style trading terminal.
One codebase covers **crypto, A-shares and US stocks**.

- **Pro charting terminal** powered by TradingView's `lightweight-charts`: MA/EMA/BOLL/Volume on the main
  pane, MACD/RSI/KDJ sub-panes, fully configurable, synced crosshair, log/linear/percent price axis.
- **Millisecond real-time** crypto quotes via a direct gate WebSocket, with a candle-close countdown.
- **Real-time decision desk**: multi-strategy consensus, plain-language market read, and a ready-to-use
  order ticket (entry / stop / take-profit / position size). **It only signals — it never places orders.**
- **9 pluggable strategies** (trend & mean-reversion, incl. 5 scalping strategies) + an event-driven
  backtest engine with shorting, stops and drawdown circuit-breaker.
- **Honesty by design**: synthetic-data fallback is flagged in red, annualized metrics are dimmed on short
  samples, and the binary-options module shows you the real (losing) edge instead of hiding it.

```bash
pip install -r requirements.txt
python run_web.py     # open http://localhost:8000
```
</details>

---

## 一、安装(只做一次)

```powershell
cd D:\桌面\quantify
pip install -r requirements.txt
```

## 一点五、专业K线交易终端(推荐)🌟

```powershell
python run_web.py
```

然后浏览器打开 **http://localhost:8000**。停止:在终端按 `Ctrl+C`。

仿 Binance / OKX 盘面,图表用 **TradingView 同款引擎**(lightweight-charts,已下载到本地,断网也能开):
- **K线**:滚轮缩放、拖拽平移、十字光标跟随;**双击复位**;价格轴 **线性/对数/百分比** 一键切换
- **⚡ 实时行情(币圈)**:直连 gate WebSocket 推送,**价格/最后一根K线毫秒级跳动**(每秒数十笔成交实时更新),顶部绿点=实时在线;右上角 **K线收盘倒计时**(如"收盘 00:54"),和交易所一致
- **主图指标**:MA×4 每条独立开关+周期可改(默认币安同款 7/25/99)、EMA×2、BOLL(周期/倍数可调)、成交量
- **副图指标**:MACD / RSI(最多3条)/ KDJ,**可同时开多个面板**,每个面板有自己的数值栏和 ✕ 关闭按钮
- **⚙️ 指标设置弹窗**:所有指标参数自定义,修改即时生效、自动保存(下次打开还在)
- **数值跟随光标**:十字光标挪到哪根K线,主图图例和每个副图都显示那一刻的指标数值(交易所同款)
- **🎨 红涨绿跌 ⇄ 绿涨红跌** 一键切换(全部图表、指标、涨跌幅跟着翻)
- **回测联动**:买▲卖▼箭头打在K线上(平仓标记带**单笔盈亏%+原因**),**持仓时段背景着色**,策略线(⚡前缀)叠加,
  资金曲线+回撤,逐笔交易表(开/平时间、方向、盈亏;**点某行跳到图上对应位置**);所有图表时间轴+十字光标全联动
- **绩效指标更诚实**:顶部标注**测试区间天数**,**样本太短时年化自动置灰降权**+鼠标悬停解释每个指标口径,新增**超额收益**(策略−买入持有)
- **数据可信**:缓存按周期判新鲜度自动更新、⟳ 刷新强制拉最新;连不上网时用**模拟数据并打红标**(绝不把假行情当真盘)
- 顶部行情条:最新价/涨跌幅/区间高低/成交量;支持切换 币圈/A股/美股、自定义标的(输 btcusdt 自动补成 BTC/USDT)、K线 500~3000 根
- **标的自动显示名字**:输入代码即在顶栏显示中文名(600519→贵州茅台、002594→比亚迪、AAPL→苹果、BTC→比特币),下拉预设也带名字;A股名字实时查新浪、币圈/美股用内置名表
- **A股真实行情**:走新浪数据源、绕过本机 VPN 代理直连,600519/000001/300750 等都是当日真实数据(不再是假数据)
- **📡 实时决策台**(右侧面板切到"实时决策"):**实时捕捉信号 + 给建议,但绝不自动下单**
  - 一键"开始实时监控":按当前标的/周期每 15秒~3分 持续刷新,**出新信号时弹提醒 + 响铃 + 浏览器通知**
  - 给出**多策略共识**(几个策略看多/看空/空仓)+ **盘面解读**(趋势/动能/波动/位置,都是人话)
  - 给一张**建议订单**:方向、参考入场、止损、止盈(2:1 盈亏比)、建议仓位与金额、约合数量、触发止损约亏多少,可一键复制
  - **多标的自选监控**:一次盯一篮子币(可自由增删、点击切换),**谁出新信号就提醒谁**;每行直显方向+几个策略一致
  - 输代码自动补全(`dogeusdt`→`DOGE/USDT`)、显示中文名、记住你的自选列表
  - **整篮子价格毫秒级实时跳动**(直连 gate ticker 推送,涨绿跌红);只在决策台开着时连,省资源
  - **⚡ 异动提醒**:某个币近 1 分钟涨/跌幅超过你设的阈值(默认 1%)就单独提醒——弹横幅+响铃+行内⚡标记,帮你在一堆币里第一时间抓到动起来的那个(每币 2 分钟冷却,不刷屏)
- **⚡ 事件合约·超短方向**(仅币圈):给出 1/3/5 分钟合约该押涨/押跌,**但把每个信号的真实历史胜率摆出来**
  - 实测各信号胜率都在 ~50%,**全低于保本胜率 55.6%(赔率1.8)= 负期望长期必亏**,只给方向、绝不替你下注
- 🛑 **下单与最终决定永远在你手里**——系统只负责发现机会和算清楚风险,你照着自己去交易所手动下

## 一点六、分析仪表盘(多策略对比/多标的验证)

```powershell
streamlit run app.py
```

浏览器打开 **http://localhost:8501**。四个标签页:策略回测 / 多策略对比 / 多标的验证(阶段6)/ 实时信号。
适合做研究分析;看盘和调参用上面的交易终端更顺手。

## 二、命令行入口脚本(理解原理用)

| 命令 | 作用 | 对应阶段 |
|------|------|---------|
| `python run_demo.py` | 单策略回测 + 资金曲线图 | 阶段1 |
| `python run_compare.py` | 所有策略并排对比 | 阶段2 |
| `python run_optimize.py` | 参数优化 + **过拟合演示**(必看) | 阶段2 |
| `python run_live.py once` | 实时信号监控(只读不下单) | 阶段3 |
| `python run_validate.py` | **多标的诚实验证**(固定参数跑5个币 + 等权组合) | 阶段6 |
| `python run_event.py` | 事件合约回测(真实胜率/盈亏) | 事件合约 |
| `python run_event.py live` | 事件合约实时信号 + 风险提醒(不下单) | 事件合约 |

先按顺序把这几个都跑一遍,你就理解了量化的核心流程。

## 三、怎么换市场 / 标的 / 策略

打开 [`config.py`](config.py),改这几个值,然后重跑任意入口:

```python
MARKET   = "crypto"     # crypto=币圈 / astock=A股 / usstock=美股
SYMBOL   = "BTC/USDT"   # 币圈用 BTC/USDT;A股用 000001;美股用 AAPL
TIMEFRAME= "1h"         # 15m/1h/4h/1d ...
STRATEGY = "dual_ma"    # dual_ma / rsi_reversion / breakout
```

> 国内网络:币圈走 gate.io,美股走雅虎(可能需科学上网),A股走新浪(绕代理直连)。
> 连不上时会自动用**模拟数据**兜底,先让你跑通流程(假数据,别当真)。

## 四、九个策略

| 策略 | 类型 | 思路 |
|------|------|------|
| `dual_ma` 双均线 | 趋势跟随 | 快线上穿慢线做多,下穿空仓。适合趋势行情 |
| `breakout` 通道突破 | 趋势跟随 | 创 N 日新高做多,跌破 N 日新低离场(海龟法核心) |
| `rsi_reversion` RSI均值回归 | 逆势 | RSI 超卖抄底,反弹到中性离场。适合震荡行情 |
| `trend_filter` 趋势过滤 | 趋势跟随(稳健) | 双均线 + 长期均线大趋势过滤,只做多、逆风空仓。目标是降回撤"活得久" |
| `boll_bounce` 布林反弹 | 短线·逆势 | 跌破下轨抄底,回中轨离场。适合震荡(建议 5m/15m) |
| `rsi_scalp` RSI快速反弹 | 短线·逆势 | RSI(2) 极度超卖买入、快速离场(Connors 经典 scalp) |
| `momo_breakout` 带量突破 | 短线·顺势 | 创新高【且放量】才追,过滤假突破 |
| `vwap_revert` VWAP回归 | 短线·逆势 | 跌到滚动 VWAP 下方一定幅度抄底,回 VWAP 离场 |
| `boll_rsi` BOLL兼RSI | 短线·逆势(双确认) | 跌破布林下轨**且**RSI超卖才买、回中轨**或**RSI回中性离场;两个信号一起才出手、假信号更少 |

> ⚡ **短线投机工具**(顶栏"⚡短线模式"一键进入 5分钟+决策台+15秒刷新):
> - **🩺 短线体检**:回测后看每笔期望值、盈亏比、日均交易、平均持仓、最大连亏、**手续费拖累**,一句话诊断这套短打是真有优势还是在给交易所打工。
> - **🔬 稳健性检验**:**手续费敏感度**(看你的策略在多少成本下由盈转亏)+ **样本外检验**(前后两段不同行情对比,识别过拟合)。
> - ⚠️ 真相:多数简单短线规则**有微弱毛利、但被手续费吃光**(实测某策略零成本 +1.5%、扣 0.15% 费就 -3.4%)。短线能不能做,自己用这两个工具测,别信"稳赚"。

## 五、看懂回测报告

| 指标 | 含义 | 怎么看 |
|------|------|--------|
| 总收益率 | 整段时间赚/亏多少 | 要和"买入持有"对比,跑赢才算有效 |
| 夏普比率 | 性价比(收益/风险) | >1 较好,>2 优秀,<0 是亏的 |
| 最大回撤 | 最坏时从高点跌多少 | 越接近 0 越好 |
| 胜率 | 赚钱交易占比 | 50%+ 较好,但不是越高越好 |

> 💡 你会发现**大部分策略都跑输买入持有或者亏钱**——这很正常,也是量化最难的地方。
> 本项目的价值是让你**理解流程、学会正确评估**,而不是直接给你一个印钞机。

---

## 五点五、事件合约(二元期权)模块 —— 必读

事件合约 = 押价格 N 分钟后涨/跌,猜对按赔率返还,猜错本金归零,**本质是二元期权(赌博)**。

- `python run_event.py`:用真实分钟K线回测各时长/各信号的**真实胜率与盈亏**。
- `python run_event.py live`:实时给出当前方向信号 + **风险提醒**(显示保本胜率、本信号历史胜率等)。

⚠️ **这个模块不下单,只给信号和提醒**,下注由你自己手动操作并负责。
⚠️ **数学事实**:赔率 < 2 时是负期望游戏。保本胜率 = 1/赔率(赔率1.8 → 需 55.6%)。
   实测:动量/反转/任意信号在 3~60 分钟所有窗口的真实胜率都在 50% 上下,**全部低于保本线、长期必亏**。
   时长越短越接近抛硬币。想清楚再碰。

> 关于自动下单:事件合约这类产品基本没有公开下单 API,本项目**不提供自动下注**——
> 不会去编造无法验证的接口代码(那种 bug 会直接让你亏钱)。正确做法是看信号自己手动下。

## 六、项目结构

```
quantify/
├── run_web.py           🌟 专业K线交易终端后端(python run_web.py → localhost:8000)
├── web/                 终端前端(TradingView 图表引擎 + 仿币安界面)
├── app.py               分析仪表盘(streamlit run app.py → localhost:8501)
├── config.py            所有配置(最常改这个)
├── run_demo.py          入口1:单策略回测
├── run_compare.py       入口2:多策略对比
├── run_optimize.py      入口3:参数优化 + 过拟合演示
├── run_live.py          入口4:实时信号监控(只读)
├── run_validate.py      入口5:多标的诚实验证(固定参数+等权组合)
├── run_event.py         事件合约回测/实时信号(不下单)
├── data/                行情数据缓存(自动生成)
└── src/
    ├── data/            统一数据源接口(阶段5)
    │   ├── base.py        DataSource 基类 + 缓存 + 模拟兜底
    │   ├── crypto.py      币圈(ccxt)
    │   ├── astock.py      A股(新浪)
    │   └── usstock.py     美股(yfinance)
    ├── strategies/      策略包(阶段2)— 9 个策略,继承 Strategy 基类
    ├── indicators.py    技术指标(均线/RSI/ATR)
    ├── risk.py          风控:止损/止盈/仓位/回撤熔断(阶段4)
    ├── backtest.py      事件驱动回测引擎(支持做空+风控)
    └── event_contract.py  事件合约(二元期权)回测与信号
```

**加新东西很简单**(这就是统一接口的好处):
- 加策略:在 `src/strategies/` 写个新类,继承 `Strategy`,登记到 `__init__.py`
- 加市场:在 `src/data/` 写个新类,继承 `DataSource`,登记到 `__init__.py`

---

## 七、成长路线图(各阶段已实现 ✅)

- **阶段1** ✅ 跑通单策略回测,理解每个环节
- **阶段2** ✅ 多策略对比 + 参数优化 + **防过拟合**(train/test 检验)
- **阶段3** ✅ 实时信号监控(只读)。接测试网自动下单的方法见 `run_live.py` 文末
- **阶段4** ✅ 风控:止损/止盈/仓位管理/回撤熔断
- **阶段5** ✅ 统一数据接口,已支持币圈/A股/美股(外汇待接 MT5/OANDA)
- **阶段6** ✅ 多标的诚实验证:固定参数(不优化)在 BTC/ETH/SOL/BNB/XRP 日线上同跑,
  并演示等权组合分散。实测结论:`trend_filter` 约 2.7 年平均 +13%,远跑输买入持有(+137%),
  但单币平均回撤 -21% → 组合 -16%,分散确实降风险。**策略没有"普遍优势",这就是诚实验证的意义。**

### 接下来真正要做的(从"能跑"到"能用"):
1. **数据要更长更干净**:现在只取 1000 根,实盘研究要几年的数据、处理缺失和异常。
2. **更严谨的验证**:多标的组合测试 ✅(`run_validate.py`),滚动 walk-forward 还没做。
3. **接交易所测试网**:用假钱长期跑自动交易,验证工程稳定性(断线/重试/对账)。
4. **A股特殊规则**:T+1、涨跌停、不能裸卖空,回测要专门处理。
5. **极小资金实盘**:一切验证通过后,用能亏得起的小钱试水。

> 🛑 **铁律**:数据 → 回测 → 样本外检验 → 测试网 → 极小资金实盘,绝不跳步。
> 任何"稳赚不赔/包教包会躺赚"都是骗局。量化是概率游戏,不是确定性印钞。

---

## 授权 / License

本项目采用 **[MIT License](LICENSE)** 开源 —— 你可以自由使用、修改、分发(商用亦可),只需保留版权与许可声明。
版权所有 © 2026 张佳泽 / [@Zhanghanser](https://github.com/Zhanghanser)。

> 如果这个项目对你有帮助,**点个 ⭐ Star 是对作者最大的鼓励!**
