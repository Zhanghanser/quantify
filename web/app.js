/* ============================================================
   量化终端前端逻辑(指标系统对标 Binance / OKX)
   图表引擎:TradingView lightweight-charts v4

   布局:主图(K线+MA/EMA/BOLL/VOL+买卖点)
        + 多个独立副图面板(MACD/RSI/KDJ,可同时开,各自带标题栏和✕)
        + 回测资金曲线
   全部图表:时间轴联动 + 十字光标联动 + 指标数值跟随光标显示
   指标参数:⚙️ 设置弹窗里全部可自定义,自动保存到浏览器
   ============================================================ */
"use strict";

const $ = id => document.getElementById(id);
const RED = "#f6465d", GREEN = "#2ebd85", GOLD = "#f0b90b", GRAY = "#848e9c";
const MA_COLORS = [GOLD, "#e056a0", "#8950fa", "#36c5f0"];
const EMA_COLORS = ["#74c0fc", "#7af0c3"];
const RSI_COLORS = [GOLD, "#e056a0", "#8950fa"];

const state = {
  market: "crypto", symbol: "BTC/USDT", timeframe: "1h", tfSel: "1h", limit: 1000,
  meta: null, candles: [], candleMap: new Map(),
  redUp: localStorage.getItem("redUp") !== "0",   // 默认中国习惯:红涨绿跌
  priceMode: localStorage.getItem("priceMode") || "Normal",  // 价格轴:线性/对数/百分比
  defaultBars: parseInt(localStorage.getItem("defaultBars")) || 160,  // K线默认显示根数(0=全部)
  bt: null,            // 最近一次回测结果
  stratOverlays: [],   // 回测画上去的策略线(系列对象)
  indLines: [],        // 主图指标线图例 [{label,color,map}]
  ovLines: [],         // 策略线图例 [{label,color,map}]
  nameCache: {},       // 标的代码 → 名字(贵州茅台 等)
};
// 请求序号令牌:防止快速切换标的时,先发后到的旧请求覆盖新结果
let klineSeq = 0, btSeq = 0, sigSeq = 0;
const upColor = () => state.redUp ? RED : GREEN;
const downColor = () => state.redUp ? GREEN : RED;
const lastTime = () => state.candles.length ? state.candles[state.candles.length - 1].time : null;

/* ---------------- 指标配置(可自定义,存浏览器) ---------------- */
const DEFAULT_CFG = {
  ma:  { on: true,  lines: [{ on: true, p: 7 }, { on: true, p: 25 }, { on: true, p: 99 }, { on: false, p: 200 }] },
  ema: { on: false, lines: [{ on: true, p: 12 }, { on: true, p: 26 }] },
  boll:{ on: false, p: 20, k: 2 },
  vol: { on: true },
  subs: {
    macd: { on: false, fast: 12, slow: 26, sig: 9 },
    rsi:  { on: true,  lines: [{ on: true, p: 6 }, { on: true, p: 12 }, { on: true, p: 24 }] },
    kdj:  { on: false, n: 9, kp: 3, dp: 3 },
  },
};
/* 把存档配置与默认配置递归合并:补齐新增字段、按默认长度对齐各 lines 数组,
   避免旧版存档缺字段导致设置弹窗 setPath 时报错卡死。 */
function mergeCfg(def, saved) {
  if (Array.isArray(def)) {
    return def.map((d, i) => mergeCfg(d, saved && saved[i]));
  }
  if (def && typeof def === "object") {
    const out = {};
    for (const k of Object.keys(def)) out[k] = mergeCfg(def[k], saved ? saved[k] : undefined);
    return out;
  }
  return saved === undefined ? def : saved;   // 叶子:有存档用存档,否则用默认
}
function loadCfg() {
  let saved = null;
  try { saved = JSON.parse(localStorage.getItem("indCfg_v2")); } catch (e) { }
  return mergeCfg(DEFAULT_CFG, saved);
}
let cfg = loadCfg();
function saveCfg() { localStorage.setItem("indCfg_v2", JSON.stringify(cfg)); }

/* ---------------- 工具函数 ---------------- */
function fmtPrice(p) {
  if (p >= 1000) return p.toLocaleString("en-US", { maximumFractionDigits: 2 });
  if (p >= 10) return p.toFixed(2);
  if (p >= 0.1) return p.toFixed(4);
  return p.toPrecision(4);
}
function fmtVol(v) {
  if (v >= 1e9) return (v / 1e9).toFixed(2) + "B";
  if (v >= 1e6) return (v / 1e6).toFixed(2) + "M";
  if (v >= 1e3) return (v / 1e3).toFixed(2) + "K";
  return v.toFixed(2);
}
const DATE_ONLY_TF = new Set(["1d", "1w", "1M"]);   // 日/周/月只显示日期,不显示时分
function fmtTime(t) {
  const d = new Date(t * 1000);
  const p = n => String(n).padStart(2, "0");
  const base = `${d.getUTCFullYear()}-${p(d.getUTCMonth() + 1)}-${p(d.getUTCDate())}`;
  return DATE_ONLY_TF.has(state.timeframe) ? base : `${base} ${p(d.getUTCHours())}:${p(d.getUTCMinutes())}`;
}
function hexA(hex, a) {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${n >> 16}, ${(n >> 8) & 255}, ${n & 255}, ${a})`;
}
async function fetchJSON(url, opts) {
  const r = await fetch(url, opts);
  if (!r.ok) {
    let msg; try { msg = (await r.json()).detail; } catch (e) { msg = r.statusText; }
    throw new Error(msg);
  }
  return r.json();
}
let toastTimer = null;
function toast(msg) {
  const el = $("toast"); el.textContent = "❌ " + msg; el.classList.remove("hidden");
  clearTimeout(toastTimer); toastTimer = setTimeout(() => el.classList.add("hidden"), 6000);
}
function flash(msg) {   // 普通提示(无错误前缀)
  const el = $("toast"); el.textContent = msg; el.classList.remove("hidden");
  clearTimeout(toastTimer); toastTimer = setTimeout(() => el.classList.add("hidden"), 2800);
}

/* ---------------- 指标计算(纯前端,改参数零延迟) ---------------- */
function sma(src, p) {
  const out = new Array(src.length).fill(null); let s = 0;
  for (let i = 0; i < src.length; i++) {
    s += src[i]; if (i >= p) s -= src[i - p];
    if (i >= p - 1) out[i] = s / p;
  }
  return out;
}
function ema(src, p) {
  const out = new Array(src.length).fill(null);
  const k = 2 / (p + 1); let prev = null, s = 0;
  for (let i = 0; i < src.length; i++) {
    if (i < p - 1) { s += src[i]; continue; }
    if (i === p - 1) { s += src[i]; prev = s / p; }
    else prev = src[i] * k + prev * (1 - k);
    out[i] = prev;
  }
  return out;
}
function bollBands(src, p, mult) {
  const mid = sma(src, p);
  const up = new Array(src.length).fill(null), lo = new Array(src.length).fill(null);
  for (let i = p - 1; i < src.length; i++) {
    let v = 0;
    for (let j = i - p + 1; j <= i; j++) v += (src[j] - mid[i]) ** 2;
    const sd = Math.sqrt(v / p);
    up[i] = mid[i] + mult * sd; lo[i] = mid[i] - mult * sd;
  }
  return { mid, up, lo };
}
function rsiCalc(src, p) {
  const out = new Array(src.length).fill(null);
  let g = 0, l = 0;
  for (let i = 1; i < src.length; i++) {
    const d = src[i] - src[i - 1];
    const gain = Math.max(d, 0), loss = Math.max(-d, 0);
    if (i <= p) { g += gain; l += loss; if (i === p) { g /= p; l /= p; out[i] = 100 - 100 / (1 + (l === 0 ? 1e9 : g / l)); } }
    else {
      g = (g * (p - 1) + gain) / p; l = (l * (p - 1) + loss) / p;
      out[i] = 100 - 100 / (1 + (l === 0 ? 1e9 : g / l));
    }
  }
  return out;
}
function macdCalc(src, fast, slow, sig) {
  const ef = ema(src, fast), es = ema(src, slow);
  const dif = src.map((_, i) => (ef[i] != null && es[i] != null) ? ef[i] - es[i] : null);
  const start = dif.findIndex(v => v != null);
  const dea = new Array(src.length).fill(null);
  if (start >= 0) {
    const deaSub = ema(dif.slice(start), sig);
    for (let i = 0; i < deaSub.length; i++) dea[start + i] = deaSub[i];
  }
  const hist = dif.map((v, i) => (v != null && dea[i] != null) ? v - dea[i] : null);
  return { dif, dea, hist };
}
function kdjCalc(candles, n, kp, dp) {
  const K = [], D = [], J = []; let k = 50, d = 50;
  for (let i = 0; i < candles.length; i++) {
    if (i < n - 1) { K.push(null); D.push(null); J.push(null); continue; }
    let hh = -Infinity, ll = Infinity;
    for (let j = i - n + 1; j <= i; j++) { hh = Math.max(hh, candles[j].high); ll = Math.min(ll, candles[j].low); }
    const rsv = hh === ll ? 50 : (candles[i].close - ll) / (hh - ll) * 100;
    k = ((kp - 1) * k + rsv) / kp;
    d = ((dp - 1) * d + k) / dp;
    K.push(k); D.push(d); J.push(3 * k - 2 * d);
  }
  return { K, D, J };
}
/* 数组 → 数据点。pts 跳过 null;ptsW 用"空白点"占位,保证各图时间轴逐根对齐 */
function pts(times, arr) {
  const out = [];
  for (let i = 0; i < arr.length; i++) if (arr[i] != null) out.push({ time: times[i], value: arr[i] });
  return out;
}
function ptsW(times, arr) {
  return arr.map((v, i) => v == null ? { time: times[i] } : { time: times[i], value: v });
}
function toMap(points) { return new Map(points.filter(p => p.value != null).map(p => [p.time, p.value])); }

/* ---------------- 创建图表 ---------------- */
const CHART_OPTS = {
  autoSize: true,
  layout: { background: { type: "solid", color: "transparent" }, textColor: GRAY, fontSize: 11 },
  grid: { vertLines: { color: "#1c2127" }, horzLines: { color: "#1c2127" } },
  crosshair: { mode: LightweightCharts.CrosshairMode.Normal,
               vertLine: { labelBackgroundColor: "#2b3139" },
               horzLine: { labelBackgroundColor: "#2b3139" } },
  timeScale: { borderColor: "#2b3139", timeVisible: true, secondsVisible: false,
               rightOffset: 8 },   // 不锁左边界,允许自由往左拖看历史
  rightPriceScale: { borderColor: "#2b3139" },
};
const mainChart = LightweightCharts.createChart($("main-chart"), CHART_OPTS);
const eqChart = LightweightCharts.createChart($("equity-chart"), CHART_OPTS);

/* 主图系列(创建顺序 = 叠放顺序,K线最后创建保证在最上层) */
/* 持仓区间高亮:最先创建 = 最底层,半透明色块铺在K线背后,标出策略在场/空仓时段 */
const holdSeries = mainChart.addHistogramSeries({ priceScaleId: "hold", base: 0, lastValueVisible: false, priceLineVisible: false });
mainChart.priceScale("hold").applyOptions({ scaleMargins: { top: 0, bottom: 0 }, visible: false });

const volSeries = mainChart.addHistogramSeries({ priceScaleId: "vol", priceFormat: { type: "volume" }, lastValueVisible: false, priceLineVisible: false });
mainChart.priceScale("vol").applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });

const LINE_OPTS = { lineWidth: 1, lastValueVisible: false, priceLineVisible: false, crosshairMarkerVisible: false };
const bollUp = mainChart.addLineSeries({ ...LINE_OPTS, color: "#74c0fc" });
const bollMid = mainChart.addLineSeries({ ...LINE_OPTS, color: "#9aa4b2", lineStyle: 2 });
const bollLo = mainChart.addLineSeries({ ...LINE_OPTS, color: "#74c0fc" });
const maSeries = MA_COLORS.map(c => mainChart.addLineSeries({ ...LINE_OPTS, color: c }));
const emaSeries = EMA_COLORS.map(c => mainChart.addLineSeries({ ...LINE_OPTS, color: c, lineStyle: 0 }));

const areaSeries = mainChart.addAreaSeries({ visible: false, lineColor: GOLD, lineWidth: 2, topColor: hexA(GOLD, .25), bottomColor: hexA(GOLD, 0) });
const candleSeries = mainChart.addCandlestickSeries({});

/* 资金曲线图系列 */
const eqStrat = eqChart.addLineSeries({ color: GOLD, lineWidth: 2, lastValueVisible: false, priceLineVisible: false });
const eqBH = eqChart.addLineSeries({ color: GRAY, lineWidth: 1, lineStyle: 2, lastValueVisible: false, priceLineVisible: false });
const eqDD = eqChart.addHistogramSeries({ priceScaleId: "dd", color: hexA(RED, .4), lastValueVisible: false, priceLineVisible: false });
eqChart.priceScale("dd").applyOptions({ scaleMargins: { top: 0.78, bottom: 0 } });
eqChart.priceScale("right").applyOptions({ scaleMargins: { top: 0.08, bottom: 0.25 } });

/* ---------------- 副图面板管理(MACD/RSI/KDJ 可同时开) ---------------- */
let subPanes = {};   // kind -> {chart, el, head, series, lines, title}

/* ---------------- 图表联动:时间轴 + 十字光标 ---------------- */
let syncing = false;
let eqReady = false;
const anchors = new Map();   // chart -> {series, map} 十字光标定位锚点

function activeCharts() {
  const list = [mainChart, ...Object.values(subPanes).map(p => p.chart)];
  if (eqReady) list.push(eqChart);
  return list;
}
function wireRange(chart) {
  chart.timeScale().subscribeVisibleLogicalRangeChange(range => {
    if (syncing || !range) return;
    if (chart === eqChart && !eqReady) return;
    syncing = true;
    activeCharts().forEach(c => { if (c !== chart) c.timeScale().setVisibleLogicalRange(range); });
    syncing = false;
  });
}
let crossGuard = false;
function positionCross(chart, t) {
  const a = anchors.get(chart); if (!a) return;
  const v = t != null ? a.map.get(t) : undefined;
  if (v == null) chart.clearCrosshairPosition();
  else chart.setCrosshairPosition(v, t, a.series);
}
function wireCrosshair(chart) {
  chart.subscribeCrosshairMove(param => {
    if (crossGuard) return;
    crossGuard = true;
    const t = (param && param.time != null) ? param.time : null;
    updateReadouts(t);
    activeCharts().forEach(c => { if (c !== chart) positionCross(c, t); });
    crossGuard = false;
  });
}
wireRange(mainChart); wireRange(eqChart);
wireCrosshair(mainChart); wireCrosshair(eqChart);

/* 默认视野:显示最近 defaultBars 根(可在工具栏选,0=全部),往左拖可看历史 */
function applyDefaultRange() {
  const n = state.candles.length; if (!n) return;
  const bars = state.defaultBars || 160;
  if (bars <= 0 || bars >= n) { mainChart.timeScale().fitContent(); return; }  // 全部
  mainChart.timeScale().setVisibleLogicalRange({ from: n - bars, to: n + 8 });
}

/* 价格轴模式:线性 / 对数 / 百分比(只作用于主图右轴,成交量与副图各自独立) */
function applyPriceMode() {
  const mode = LightweightCharts.PriceScaleMode[state.priceMode] ?? 0;
  mainChart.priceScale("right").applyOptions({ mode });
  document.querySelectorAll("#price-mode .chip").forEach(b =>
    b.classList.toggle("active", b.dataset.mode === state.priceMode));
}

/* ---------------- 副图面板:创建 / 删除 / 填数据 ---------------- */
const PANE_TITLES = {
  macd: c => `MACD(${c.fast},${c.slow},${c.sig})`,
  rsi: c => `RSI(${c.lines.filter(l => l.on).map(l => l.p).join(",")})`,
  kdj: c => `KDJ(${c.n},${c.kp},${c.dp})`,
};

function createPane(kind) {
  const el = document.createElement("div");
  el.className = "sub-pane";
  el.innerHTML = `<div class="pane-head"></div><div class="pane-body"></div>`;
  $("sub-panes").appendChild(el);
  const head = el.querySelector(".pane-head");
  const chart = LightweightCharts.createChart(el.querySelector(".pane-body"), CHART_OPTS);
  // 点 ✕ 关闭面板(等同取消勾选)
  head.addEventListener("click", e => {
    if (e.target.classList.contains("pane-x")) { cfg.subs[kind].on = false; saveCfg(); applyAll(); }
  });
  const pane = { kind, chart, el, head, series: {}, lines: [] };

  if (kind === "macd") {
    pane.series.hist = chart.addHistogramSeries({ lastValueVisible: false, priceLineVisible: false });
    pane.series.dif = chart.addLineSeries({ ...LINE_OPTS, color: "#74c0fc" });
    pane.series.dea = chart.addLineSeries({ ...LINE_OPTS, color: GOLD });
  } else if (kind === "rsi") {
    pane.series.lines = RSI_COLORS.map(c => chart.addLineSeries({ ...LINE_OPTS, color: c, lineWidth: 1.5 }));
    [30, 50, 70].forEach(lv => pane.series.lines[0].createPriceLine({
      price: lv, color: "#3a4250", lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: "",
    }));
  } else if (kind === "kdj") {
    pane.series.k = chart.addLineSeries({ ...LINE_OPTS, color: GOLD, lineWidth: 1.5 });
    pane.series.d = chart.addLineSeries({ ...LINE_OPTS, color: "#74c0fc" });
    pane.series.j = chart.addLineSeries({ ...LINE_OPTS, color: "#e056a0" });
  }

  subPanes[kind] = pane;
  wireRange(chart); wireCrosshair(chart);
  updatePaneData(kind);
  const r = mainChart.timeScale().getVisibleLogicalRange();
  if (r) chart.timeScale().setVisibleLogicalRange(r);
}

function removePane(kind) {
  const pane = subPanes[kind]; if (!pane) return;
  anchors.delete(pane.chart);
  pane.chart.remove(); pane.el.remove();
  delete subPanes[kind];
}

function updatePaneData(kind) {
  const pane = subPanes[kind]; if (!pane || !state.candles.length) return;
  const c = state.candles, times = c.map(k => k.time), closes = c.map(k => k.close);
  const sc = cfg.subs[kind];
  pane.title = PANE_TITLES[kind](sc);
  pane.lines = [];

  if (kind === "macd") {
    const m = macdCalc(closes, sc.fast, sc.slow, sc.sig);
    pane.series.hist.setData(c.map((k, i) => m.hist[i] == null ? { time: k.time } : ({
      time: k.time, value: m.hist[i],
      color: hexA(m.hist[i] >= 0 ? upColor() : downColor(), .55),
    })));
    pane.series.dif.setData(ptsW(times, m.dif));
    pane.series.dea.setData(ptsW(times, m.dea));
    pane.lines = [
      { label: "DIF", color: "#74c0fc", map: toMap(ptsW(times, m.dif)) },
      { label: "DEA", color: GOLD, map: toMap(ptsW(times, m.dea)) },
      { label: "MACD", color: v => v >= 0 ? upColor() : downColor(), map: toMap(ptsW(times, m.hist)) },
    ];
    pane.anchor = { series: pane.series.dif, map: pane.lines[0].map };
  } else if (kind === "rsi") {
    sc.lines.forEach((l, i) => {
      const data = l.on ? ptsW(times, rsiCalc(closes, l.p)) : [];
      pane.series.lines[i].setData(data);
      if (l.on) pane.lines.push({ label: `RSI(${l.p})`, color: RSI_COLORS[i], map: toMap(data) });
    });
    const first = sc.lines.findIndex(l => l.on);
    pane.anchor = first >= 0 ? { series: pane.series.lines[first], map: pane.lines[0].map } : null;
  } else if (kind === "kdj") {
    const m = kdjCalc(c, sc.n, sc.kp, sc.dp);
    pane.series.k.setData(ptsW(times, m.K));
    pane.series.d.setData(ptsW(times, m.D));
    pane.series.j.setData(ptsW(times, m.J));
    pane.lines = [
      { label: "K", color: GOLD, map: toMap(ptsW(times, m.K)) },
      { label: "D", color: "#74c0fc", map: toMap(ptsW(times, m.D)) },
      { label: "J", color: "#e056a0", map: toMap(ptsW(times, m.J)) },
    ];
    pane.anchor = { series: pane.series.k, map: pane.lines[0].map };
  }

  if (pane.anchor) anchors.set(pane.chart, pane.anchor); else anchors.delete(pane.chart);
  updatePaneHead(kind, lastTime());
}

function updatePaneHead(kind, t) {
  const pane = subPanes[kind]; if (!pane) return;
  let html = `<b>${pane.title}</b>`;
  pane.lines.forEach(l => {
    const v = t != null ? l.map.get(t) : undefined;
    if (v != null) {
      const col = typeof l.color === "function" ? l.color(v) : l.color;
      html += ` <span style="color:${col}">${l.label}:${Math.abs(v) >= 1000 ? fmtPrice(v) : v.toFixed(2)}</span>`;
    }
  });
  html += `<button class="pane-x" title="关闭此指标">✕</button>`;
  pane.head.innerHTML = html;
}

/* 按配置增删副图面板 */
function syncPanes() {
  ["macd", "rsi", "kdj"].forEach(kind => {
    const want = cfg.subs[kind].on;
    if (want && !subPanes[kind]) createPane(kind);
    else if (!want && subPanes[kind]) removePane(kind);
  });
}

/* ---------------- 主图指标渲染 ---------------- */
function applyCandleColors() {
  const u = upColor(), d = downColor();
  candleSeries.applyOptions({
    upColor: u, downColor: d, borderUpColor: u, borderDownColor: d,
    wickUpColor: u, wickDownColor: d,
  });
  document.documentElement.style.setProperty("--up", u);
  document.documentElement.style.setProperty("--down", d);
  $("color-toggle").textContent = state.redUp ? "🎨 红涨绿跌" : "🎨 绿涨红跌";
}

function renderCandles() {
  const c = state.candles;
  const last = c[c.length - 1].close;
  const precision = last >= 10 ? 2 : last >= 0.1 ? 4 : 6;
  candleSeries.applyOptions({ priceFormat: { type: "price", precision, minMove: 1 / 10 ** precision } });
  candleSeries.setData(c);
  areaSeries.setData(c.map(k => ({ time: k.time, value: k.close })));
  candleSeries.setMarkers([]);
  anchors.set(mainChart, { series: candleSeries, map: new Map(c.map(k => [k.time, k.close])) });
}

function refreshIndicators() {
  const c = state.candles; if (!c.length) return;
  const times = c.map(k => k.time), closes = c.map(k => k.close);
  state.indLines = [];

  // MA × 4(每条独立开关 + 周期)。图例项带 del(点✕删)和 customize(点名字开设置)
  cfg.ma.lines.forEach((l, i) => {
    const show = cfg.ma.on && l.on && l.p >= 2;
    const data = show ? pts(times, sma(closes, l.p)) : [];
    maSeries[i].setData(data);
    if (show) state.indLines.push({ label: `MA(${l.p})`, color: MA_COLORS[i], map: toMap(data),
      del: () => { cfg.ma.lines[i].on = false; saveCfg(); applyAll(); }, customize: true });
  });

  // EMA × 2
  cfg.ema.lines.forEach((l, i) => {
    const show = cfg.ema.on && l.on && l.p >= 2;
    const data = show ? pts(times, ema(closes, l.p)) : [];
    emaSeries[i].setData(data);
    if (show) state.indLines.push({ label: `EMA(${l.p})`, color: EMA_COLORS[i], map: toMap(data),
      del: () => { cfg.ema.lines[i].on = false; saveCfg(); applyAll(); }, customize: true });
  });

  // BOLL(周期、倍数可自定义)。三条线合成一个图例项,一个✕删整组
  if (cfg.boll.on) {
    const b = bollBands(closes, Math.round(cfg.boll.p), cfg.boll.k);
    const dUp = pts(times, b.up), dMid = pts(times, b.mid), dLo = pts(times, b.lo);
    bollUp.setData(dUp); bollMid.setData(dMid); bollLo.setData(dLo);
    state.indLines.push({ label: `BOLL(${Math.round(cfg.boll.p)},${cfg.boll.k})`, color: "#9aa4b2", map: toMap(dMid),
      del: () => { cfg.boll.on = false; saveCfg(); applyAll(); }, customize: true });
  } else { bollUp.setData([]); bollMid.setData([]); bollLo.setData([]); }

  // 成交量(涨红跌绿,跟随颜色习惯)
  if (cfg.vol.on) {
    volSeries.setData(c.map(k => ({
      time: k.time, value: k.volume,
      color: hexA(k.close >= k.open ? upColor() : downColor(), .45),
    })));
    state.indLines.push({ label: "VOL", color: "#9aa4b2", map: null,
      del: () => { cfg.vol.on = false; saveCfg(); applyAll(); }, customize: false });
  } else volSeries.setData([]);

  // 各副图面板的数据
  Object.keys(subPanes).forEach(updatePaneData);

  updateReadouts(null);
  positionSyntheticBadge();   // 指标变化使图例高度变了,把模拟数据红标重新对齐到图例下方
}

/* ---------------- 数值跟随显示(主图图例 + 各副图标题栏) ---------------- */
function renderLegend(k) {
  if (!k) { $("legend-ohlc").innerHTML = ""; return; }
  const chg = (k.close / k.open - 1) * 100;
  const col = k.close >= k.open ? upColor() : downColor();
  const ampl = (k.high - k.low) / k.open * 100;
  $("legend-ohlc").innerHTML =
    `<b>${state.symbol}</b> · ${state.timeframe} &nbsp; ${fmtTime(k.time)}` +
    ` &nbsp;开 <b style="color:${col}">${fmtPrice(k.open)}</b>` +
    ` 高 <b style="color:${col}">${fmtPrice(k.high)}</b>` +
    ` 低 <b style="color:${col}">${fmtPrice(k.low)}</b>` +
    ` 收 <b style="color:${col}">${fmtPrice(k.close)}</b>` +
    ` &nbsp;涨跌 <b style="color:${col}">${chg >= 0 ? "+" : ""}${chg.toFixed(2)}%</b>` +
    ` 振幅 <b>${ampl.toFixed(2)}%</b>` +
    (cfg.vol.on ? ` 量 <b>${fmtVol(k.volume)}</b>` : "");
}

function updateLegendInd(t) {
  state.legendAll = [...state.indLines, ...state.ovLines];   // 供点击删除/设置时按下标取回
  const items = state.legendAll.map((l, i) => {
    const v = (t != null && l.map) ? l.map.get(t) : undefined;
    const val = v != null ? ":" + fmtPrice(v) : "";
    const x = l.del ? `<i class="leg-x" title="删除该指标">✕</i>` : "";
    const cls = "leg-pill" + (l.customize ? " can-cfg" : "") + (l.del ? "" : " ro");
    return `<span class="${cls}" data-li="${i}" style="color:${l.color}"` +
           `${l.customize ? ' title="点名字调参数,点✕删除"' : ""}>${l.label}${val}${x}</span>`;
  });
  $("legend-ind").innerHTML = items.join("");
  if (!$("legend-ind").__wired) {           // 事件委托只绑一次
    $("legend-ind").__wired = true;
    $("legend-ind").addEventListener("click", e => {
      const pill = e.target.closest(".leg-pill"); if (!pill) return;
      const item = (state.legendAll || [])[+pill.dataset.li]; if (!item) return;
      if (e.target.classList.contains("leg-x")) { if (item.del) item.del(); }
      else if (item.customize) openModal();
    });
  }
}

function updateReadouts(t) {
  rt.hovering = t != null;   // 悬停看历史时,暂停实时图例覆盖
  const tt = t != null ? t : lastTime();
  if (tt == null) return;
  renderLegend(state.candleMap.get(tt));
  updateLegendInd(tt);
  Object.keys(subPanes).forEach(kind => updatePaneHead(kind, tt));
}

/* 涨跌幅:币圈用真正的"24h涨跌"(找约24小时前那根做基准),A股/美股用"较上一根" */
function tickerChange(price) {
  const c = state.candles; if (c.length < 2) return { chg: 0, label: "涨跌" };
  if (state.market === "crypto") {
    const cutoff = c[c.length - 1].time - 86400;
    let base = c[0].close;   // 数据不足24h时退化为窗口最早一根
    for (let i = c.length - 1; i >= 0; i--) { if (c[i].time <= cutoff) { base = c[i].close; break; } }
    return { chg: base ? price / base - 1 : 0, label: "24h涨跌" };
  }
  return { chg: price / c[c.length - 2].close - 1, label: "较前根" };
}
/* 统一更新顶栏(价格/涨跌/区间高低/区间量),静态与实时态共用,口径一致 */
function applyTicker(price, lastHigh, lastLow, lastVol) {
  const { chg, label } = tickerChange(price);
  const col = chg >= 0 ? upColor() : downColor();
  const pe = $("t-price"); pe.textContent = fmtPrice(price); pe.style.color = col;
  const ce = $("t-chg"); ce.textContent = (chg >= 0 ? "+" : "") + (chg * 100).toFixed(2) + "%"; ce.style.color = col;
  if ($("t-chg-label")) $("t-chg-label").textContent = label;
  $("t-high").textContent = fmtPrice(Math.max(rt.rangeHiBase, lastHigh));
  $("t-low").textContent = fmtPrice(Math.min(rt.rangeLoBase, lastLow));
  $("t-vol").textContent = fmtVol(rt.volBase + lastVol);
}
function renderTicker() {
  const c = state.candles; if (!c.length) return;
  const last = c[c.length - 1];
  // 缓存"除最后一根外"的区间极值与累计量,实时态只需叠加当前根即可增量更新
  let hi = -Infinity, lo = Infinity, vol = 0;
  for (let i = 0; i < c.length - 1; i++) {
    if (c[i].high > hi) hi = c[i].high;
    if (c[i].low < lo) lo = c[i].low;
    vol += c[i].volume;
  }
  if (c.length === 1) { hi = last.high; lo = last.low; }
  rt.rangeHiBase = hi; rt.rangeLoBase = lo; rt.volBase = vol;
  applyTicker(last.close, last.high, last.low, last.volume);
}

/* ---------------- 回测 ---------------- */
function gatherParams() {
  const out = {};
  document.querySelectorAll("#param-box input").forEach(inp => {
    const mn = parseFloat(inp.min), mx = parseFloat(inp.max);
    let v = parseFloat(inp.value);                 // 支持小数(布林倍数/偏离% 等)
    if (!isFinite(v)) v = isFinite(mn) ? mn : 1;
    if (isFinite(mn)) v = Math.max(mn, v);
    if (isFinite(mx)) v = Math.min(mx, v);         // 钳到合法区间,杜绝空值/越界跑出垃圾结果
    inp.value = v;                                  // 回写让用户看到被修正的值
    out[inp.dataset.key] = v;
  });
  return out;
}

function renderMarkers() {
  if (!state.bt) { candleSeries.setMarkers([]); return; }
  const markers = state.bt.markers.map(m => {
    const long = m.dir > 0;
    if (m.kind === "entry") {
      return {
        time: m.time,
        position: long ? "belowBar" : "aboveBar",
        shape: long ? "arrowUp" : "arrowDown",
        color: long ? upColor() : downColor(),
        text: long ? "买" : "卖空",
      };
    }
    // 平仓:颜色按这笔盈亏(赚=涨色 亏=跌色),文字带盈亏% + 平仓原因
    const ret = m.ret == null ? 0 : m.ret;
    const pct = `${ret >= 0 ? "+" : ""}${(ret * 100).toFixed(1)}%`;
    return {
      time: m.time,
      position: long ? "aboveBar" : "belowBar",
      shape: long ? "arrowDown" : "arrowUp",
      color: ret >= 0 ? upColor() : downColor(),
      text: `平 ${pct} ${m.reason || ""}`.trim(),
    };
  });
  candleSeries.setMarkers(markers);
}

/* 持仓区间高亮:把每笔交易的 [开仓, 平仓] 区间内的K线背景染色(多/空两色) */
function renderHoldings() {
  if (!state.bt) { holdSeries.setData([]); return; }
  const ivs = (state.bt.trades || [])
    .filter(t => t.entry_ts != null && t.exit_ts != null)
    .map(t => [t.entry_ts, t.exit_ts, t.dir]);
  const data = state.candles.map(k => {
    const seg = ivs.find(iv => k.time >= iv[0] && k.time <= iv[1]);
    return seg
      ? { time: k.time, value: 1, color: hexA(seg[2] > 0 ? upColor() : downColor(), 0.08) }
      : { time: k.time };   // 空仓:留白
  });
  holdSeries.setData(data);
}

const OVERLAY_COLORS = ["#ff7aa2", "#ffd166", "#7af0c3", "#74c0fc", "#c792ea"];
function renderStrategyOverlays() {
  state.stratOverlays.forEach(s => mainChart.removeSeries(s));
  state.stratOverlays = []; state.ovLines = [];
  if (state.bt) {
    state.bt.overlays.forEach((o, i) => {
      const color = OVERLAY_COLORS[i % OVERLAY_COLORS.length];
      const s = mainChart.addLineSeries({ ...LINE_OPTS, color });
      s.setData(o.data);
      state.stratOverlays.push(s);
      state.ovLines.push({ label: `⚡${o.name}`, color, map: toMap(o.data) });
    });
  }
  updateReadouts(null);
}

const PCT = new Set(["总收益率", "买入持有收益率", "超额收益", "年化收益率", "最大回撤", "胜率"]);
const TOOLTIPS = {
  "总收益率": "整段回测的实际盈亏,最该看的数。",
  "买入持有收益率": "基准:全程满仓持有、不计手续费。策略含手续费且按你设的仓位(默认半仓),口径不完全可比,仅作参照。",
  "超额收益": "策略总收益 − 买入持有收益。为正才算跑赢『躺着不动』(注意上面口径差异)。",
  "年化收益率": "把这段盈亏复利外推到一年的理论值。样本越短越会被放大失真,请以『总收益率』为准。",
  "夏普比率": "风险调整后收益(假设无风险利率0)。>1 较好 >2 优秀;样本<90天受波动放大,仅供参考。",
  "最大回撤": "从资金最高点回撤的最大幅度,越接近 0 越稳。",
  "胜率": "盈利平仓笔数 ÷ 总平仓笔数;每次止损/止盈/信号反转/熔断都算一笔。",
  "交易次数": "回测期内的平仓次数。",
  "最终资金": "回测结束时的账户资金(本金按你设置的初始资金)。",
};
function renderMetrics() {
  if (!state.bt) return;
  const m = state.bt.metrics, box = $("metrics");
  box.innerHTML = "";
  // 顶部固定一行测试区间:让"年化-51%"在"仅41天"的语境下自洽,不再吓人
  if (m["测试起始"]) {
    const reliable = m["年化可靠"];
    box.insertAdjacentHTML("beforeend",
      `<div class="test-range${reliable ? "" : " warn"}">📅 测试区间 ${String(m["测试起始"]).slice(0, 10)} ~ ${String(m["测试结束"]).slice(0, 10)} · 共 ${m["测试天数"]} 天 / ${m["周期根数"]} 根${reliable ? "" : " · ⚠ 样本偏短,年化仅供参考"}</div>`);
  }
  const excess = (m["总收益率"] ?? 0) - (m["买入持有收益率"] ?? 0);
  const order = ["总收益率", "买入持有收益率", "超额收益", "年化收益率",
                 "夏普比率", "最大回撤", "胜率", "交易次数", "最终资金"];
  order.forEach(k => {
    let v, color = "var(--text)", dim = "";
    if (k === "超额收益") v = excess;
    else { if (!(k in m)) return; v = m[k]; }
    if (PCT.has(k)) {
      color = v > 0 ? upColor() : v < 0 ? downColor() : "var(--text)";
      const sign = (v > 0 && k !== "胜率") ? "+" : "";
      if (k === "胜率") color = "var(--text)";
      v = (v == null) ? "—" : sign + (v * 100).toFixed(1) + "%";
    } else if (k === "夏普比率") {
      color = (m[k] ?? 0) > 0 ? upColor() : downColor();
      v = (v == null) ? "—" : v.toFixed(2);
    } else if (k === "最终资金") v = Math.round(v).toLocaleString();
    if (k === "年化收益率" && m["年化可靠"] === false) dim = " mcard-dim";  // 短样本置灰降权
    const tip = TOOLTIPS[k] ? ` title="${TOOLTIPS[k]}"` : "";
    const sub = (k === "胜率" && m["盈利笔数"] != null)
      ? `<div class="sub">${m["盈利笔数"]}/${m["交易次数"]} 笔盈利</div>` : "";
    box.insertAdjacentHTML("beforeend",
      `<div class="mcard${dim}"${tip}><div class="k">${k}</div><div class="v" style="color:${color}">${v}</div>${sub}</div>`);
  });
}

/* 🩺 短线体检:把"这套短打是赚是给交易所打工"量化展示 + 一句话诊断 */
function renderHealth(h) {
  const box = $("health");
  if (!h || !h.trades) { box.classList.add("hidden"); box.innerHTML = ""; return; }
  box.classList.remove("hidden");
  const pct = v => (v == null ? "—" : (v >= 0 ? "+" : "") + (v * 100).toFixed(2) + "%");
  const exp = h.expectancy, pf = h.profit_factor;
  const good = exp > 0 && pf != null && pf > 1;
  const verdict = good
    ? "✅ 扣费后每笔为正期望 —— 这套短打在该区间有微弱优势(仍需样本外/walk-forward 验证)"
    : "❌ 扣费后每笔为负期望 —— 长期等于给交易所交手续费,别急着上实盘";
  const rows = [
    ["每笔期望(扣费)", pct(exp), exp > 0 ? upColor() : downColor()],
    ["盈亏比", pf == null ? "—" : pf.toFixed(2), (pf != null && pf >= 1) ? upColor() : downColor()],
    ["胜率", (h.win_rate * 100).toFixed(0) + "%", "var(--text)"],
    ["平均盈 / 亏", pct(h.avg_win) + " / " + pct(h.avg_loss), "var(--text)"],
    ["日均交易", h.trades_per_day + " 笔", "var(--text)"],
    ["平均持仓", h.avg_hold_bars + " 根", "var(--text)"],
    ["最大连亏", h.max_consec_loss + " 笔", "var(--text)"],
    ["手续费拖累", pct(-h.fee_drag), downColor()],
  ];
  box.innerHTML = `<div class="desk-h">🩺 短线体检 <span class="dim">(共 ${h.trades} 笔)</span></div>` +
    `<div class="health-verdict" style="color:${good ? upColor() : downColor()}">${verdict}</div>` +
    `<div class="health-grid">` + rows.map(([k, v, c]) =>
      `<div class="hrow"><span class="hk">${k}</span><span class="hv" style="color:${c}">${v}</span></div>`).join("") +
    `</div>`;
}

/* 🔬 稳健性检验:手续费敏感度 + 样本外(按需点击运行,较重)*/
async function runRobustness() {
  const btn = $("robust-btn");
  btn.disabled = true; btn.textContent = "🔬 检验中…";
  try {
    const d = await fetchJSON("/api/robustness", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        market: state.market, symbol: state.symbol, timeframe: state.timeframe, limit: state.limit,
        strategy: $("strategy").value, params: gatherParams(),
        risk: {
          stop_loss: (parseFloat($("r-sl").value) || 0) / 100,
          take_profit: (parseFloat($("r-tp").value) || 0) / 100,
          position_size: (parseFloat($("r-ps").value) || 50) / 100,
          max_drawdown_stop: (parseFloat($("r-dd").value) || 0) / 100,
        },
        capital: parseInt($("r-cap").value) || 10000,
      }),
    });
    renderRobust(d);
  } catch (e) { toast("稳健性检验失败:" + e.message); }
  btn.disabled = false; btn.textContent = "🔬 稳健性检验(手续费敏感度 + 样本外)";
}
function renderRobust(d) {
  const box = $("robust"); box.classList.remove("hidden");
  const pct = v => (v == null ? "—" : (v >= 0 ? "+" : "") + (v * 100).toFixed(1) + "%");
  // 手续费敏感度:逐档收益,标出当前档与"由正转负"的临界
  const feeRows = d.fee_curve.map(f => {
    const isCur = Math.abs(f.fee - d.current_fee) < 1e-9;
    const col = (f.ret || 0) >= 0 ? upColor() : downColor();
    return `<div class="hrow"><span class="hk">单边 ${(f.fee * 100).toFixed(2)}%${isCur ? " ←你现在" : ""}</span>` +
      `<span class="hv" style="color:${col}">${pct(f.ret)}</span></div>`;
  }).join("");
  const o = d.oos, f = o.first, s = o.second;
  const seg = (t, x) => x ? `<div class="hrow"><span class="hk">${t} ${x.start}~${x.end} · ${x.trades}笔</span><span class="hv" style="color:${(x.ret||0)>=0?upColor():downColor()}">${pct(x.ret)}</span></div>` : "";
  const vcol = o.verdict.startsWith("✅") ? upColor() : o.verdict.startsWith("❌") || o.verdict.startsWith("⚠") ? downColor() : "var(--sub)";
  box.innerHTML =
    `<div class="desk-h">💸 手续费敏感度 <span class="dim">(同一套信号,成本越高越亏)</span></div>` +
    `<div class="health-grid">${feeRows}</div>` +
    `<div class="desk-h" style="margin-top:8px">🔬 样本外检验 <span class="dim">(前后两段不同行情)</span></div>` +
    `<div class="health-verdict" style="color:${vcol}">${o.verdict}</div>` +
    `<div class="health-grid">${seg("前半段", f)}${seg("后半段", s)}</div>`;
}

function renderSignal() {
  if (!state.bt) return;
  const s = state.bt.signal, box = $("signal-box");
  const map = { 1: ["看多 / 持有", upColor()], 0: ["空仓观望", "var(--sub)"], "-1": ["看空", downColor()] };
  const [txt, col] = map[String(s.current)];
  const fresh = s.current !== s.prev ? `<div class="new-sig">📢 最新K线刚刚转向,新信号!</div>` : "";
  box.innerHTML = `<div class="dim">当前信号(${fmtTime(lastTime())} 收盘)</div>
    <div class="sig" style="color:${col}">${txt}</div>${fresh}`;
  box.classList.remove("hidden");
}

function renderTrades() {
  if (!state.bt) return;
  const t = state.bt.trades;
  $("trades-wrap").classList.remove("hidden");
  $("trade-count").textContent = `共 ${t.length} 笔 · ${state.bt.risk_desc} · 点某一行可跳到图上对应位置`;
  if (!t.length) { $("trades").innerHTML = `<div class="dim" style="padding:8px">这段数据没有产生交易。</div>`; return; }
  const fmtT = s => s ? s.slice(5, 16) : "—";   // 留 MM-DD HH:MM
  // 按【开仓时间倒序】展示:最新的一笔排在最上面(和交易所成交记录一致)。
  // # 仍保留这笔在回测里的真实先后序号(第几笔),方便和"最大连亏"等按时间顺序的统计对应。
  const ordered = t.map((x, i) => ({ x, seq: i + 1 }))
    .sort((a, b) => (b.x.entry_ts ?? 0) - (a.x.entry_ts ?? 0));
  const rows = ordered.map(({ x, seq }) => {
    const r = x.ret == null ? 0 : x.ret;
    const col = r >= 0 ? upColor() : downColor();
    return `<tr data-ts="${x.exit_ts ?? ""}">
      <td>${seq}</td>
      <td>${x.dir > 0 ? "多" : "空"}</td>
      <td class="num">${fmtT(x.entry_time)}</td>
      <td class="num">${fmtT(x.exit_time)}</td>
      <td class="num" style="color:${col}">${(r >= 0 ? "+" : "") + (r * 100).toFixed(2)}%</td>
      <td><span class="chip-tag">${x.reason}</span></td></tr>`;
  }).join("");
  $("trades").innerHTML = `<table><thead><tr><th>#</th><th>方向</th><th>开仓</th><th>平仓</th><th>单笔收益</th><th>平仓原因</th></tr></thead><tbody>${rows}</tbody></table>`;
  $("trades").querySelectorAll("tbody tr").forEach(tr => {
    tr.onclick = () => {
      const ts = parseInt(tr.dataset.ts);
      if (!ts) return;
      const idx = state.candles.findIndex(k => k.time >= ts);
      if (idx >= 0) mainChart.timeScale().setVisibleLogicalRange({ from: idx - 60, to: idx + 30 });
    };
  });
}

function renderEquity() {
  if (!state.bt) return;
  const bt = state.bt;   // 闭包快照:两帧后若已切币/重跑,state.bt 可能被置空或替换
  $("equity-wrap").classList.remove("hidden");
  // 容器刚从隐藏变可见,等浏览器完成布局拿到真实宽度后再填数据,
  // 否则会以宽度0计算视野,联动时把主图带坏
  requestAnimationFrame(() => requestAnimationFrame(() => {
    if (state.bt !== bt) return;   // 已过期:放弃,避免崩溃或把旧标的曲线画到新图上
    eqStrat.setData(bt.equity);
    eqBH.setData(bt.buy_hold);
    eqDD.setData(bt.drawdown.map(p => ({ ...p, color: hexA(RED, .4) })));
    anchors.set(eqChart, { series: eqStrat, map: toMap(bt.equity) });
    eqReady = true;
    const r = mainChart.timeScale().getVisibleLogicalRange();
    if (r) eqChart.timeScale().setVisibleLogicalRange(r);
  }));
}

async function runBacktest() {
  const btn = $("run-bt");
  const my = ++btSeq;
  btn.disabled = true; btn.textContent = "⏳ 回测计算中…";
  try {
    const res = await fetchJSON("/api/backtest", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        market: state.market, symbol: state.symbol,
        timeframe: state.timeframe, limit: state.limit,
        strategy: $("strategy").value, params: gatherParams(),
        risk: {
          stop_loss: (parseFloat($("r-sl").value) || 0) / 100,
          take_profit: (parseFloat($("r-tp").value) || 0) / 100,
          position_size: (parseFloat($("r-ps").value) || 50) / 100,
          max_drawdown_stop: (parseFloat($("r-dd").value) || 0) / 100,
        },
        capital: parseInt($("r-cap").value) || 10000,
      }),
    });
    if (my !== btSeq) return;   // 期间又点了别的标的/策略,丢弃这次旧结果
    state.bt = res;
    renderMarkers(); renderHoldings(); renderStrategyOverlays(); renderMetrics();
    renderHealth(res.health); renderSignal(); renderTrades(); renderEquity();
    $("robust-btn").classList.remove("hidden");   // 回测完才允许点稳健性检验
    $("robust").classList.add("hidden");          // 旧结果先收起,点了重算
  } catch (e) { if (my === btSeq) toast("回测失败:" + e.message); }
  finally { if (my === btSeq) { btn.disabled = false; btn.textContent = "▶ 运行回测"; } }
}

/* ---------------- 实时决策台(只给信号与建议,绝不自动下单)---------------- */
const live = { timer: null, on: false, lastKey: null, scanAlerted: {} };

function switchPanelTab(tab) {
  document.querySelectorAll(".ptab").forEach(b => b.classList.toggle("active", b.dataset.tab === tab));
  $("tab-bt").classList.toggle("hidden", tab !== "bt");
  $("tab-live").classList.toggle("hidden", tab !== "live");
  if (tab === "live") pollAll();   // 打开决策台立刻拉一次快照(不必先点开始监控)
  wlSync();                        // 离开决策台停掉自选实时价,进入则订阅
}

/* 一轮完整刷新:当前标的详情 + 自选扫描 + 事件合约方向 */
function pollAll() { pollSignal(); pollScan(); pollEvent(); }

function liveBody() {
  return JSON.stringify({
    market: state.market, symbol: state.symbol, timeframe: state.timeframe,
    risk: {
      stop_loss: (parseFloat($("r-sl").value) || 5) / 100,
      position_size: (parseFloat($("r-ps").value) || 50) / 100,
    },
    capital: parseInt($("r-cap").value) || 10000,
  });
}

async function pollSignal() {
  const my = ++sigSeq;
  try {
    const s = await fetchJSON("/api/signal", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: liveBody(),
    });
    if (my !== sigSeq) return;   // 有更新的轮询发出了,丢弃这次旧响应(防乱序覆盖)
    if (s.symbol !== state.symbol || s.timeframe !== state.timeframe) return;  // 期间已切标的/周期,丢弃旧响应
    renderDesk(s);
    const key = `${s.symbol}|${s.timeframe}|${s.time}`;
    if (s.new_signal && key !== live.lastKey) alertNewSignal(s);   // 同一根K线只提醒一次
    live.lastKey = key;
  } catch (e) { $("live-updated").textContent = "取信号失败:" + e.message; }
}

function startLive() {
  live.on = true;
  $("live-toggle").textContent = "⏸ 停止信号提醒";
  $("live-toggle").classList.add("live-on");
  pollAll();
  const sec = parseInt($("live-interval").value) || 30;
  live.timer = setInterval(pollAll, sec * 1000);
}
function stopLive() {
  live.on = false; clearInterval(live.timer); live.timer = null;
  $("live-toggle").textContent = "▶ 开始信号提醒";
  $("live-toggle").classList.remove("live-on");
}

function renderDesk(s) {
  const dirCls = s.direction > 0 ? "rec-long" : s.direction < 0 ? "rec-short" : "rec-flat";
  const arrow = s.direction > 0 ? "↑ 做多" : s.direction < 0 ? "↓ 做空" : "— 观望";
  const card = $("rec-card");
  card.className = "rec-card " + dirCls;
  card.innerHTML = `<div class="rec-dir">${arrow}</div>
    <div class="rec-sub">${s.agree}/${s.total} 策略一致 · 一致度 ${(s.conviction * 100).toFixed(0)}% · 现价 ${fmtPrice(s.price)}</div>`;
  $("live-updated").textContent = `${s.name || s.symbol} · ${s.timeframe} · 数据截至 ${s.time}`;

  $("consensus").innerHTML = s.strategies.map(st => {
    const cls = st.stance > 0 ? "up" : st.stance < 0 ? "down" : "flat";
    const txt = st.stance > 0 ? "做多" : st.stance < 0 ? "做空" : "空仓";
    return `<div class="cons-row"><span>${st.label}</span><span class="cons-tag ${cls}">${txt}${st.flipped ? " 🔔" : ""}</span></div>`;
  }).join("") + (s.basis ? `<div class="dim" style="font-size:10.5px;margin-top:5px">ⓘ ${s.basis}</div>` : "");

  $("reads").innerHTML = s.reads.map(r => {
    const c = r.dir > 0 ? "var(--up)" : r.dir < 0 ? "var(--down)" : "var(--text)";
    return `<div class="read-row"><span class="read-k">${r.k}</span><span class="read-v" style="color:${c}">${r.v}</span></div>`;
  }).join("");

  if (!s.ticket) {
    $("ticket").innerHTML = `<div class="dim" style="padding:8px 2px">策略分歧、方向不明 → 建议<b>观望</b>,不急于进场(空仓也是一种决策)。</div>`;
  } else {
    const t = s.ticket;
    $("ticket").innerHTML = `
      <div class="tk-dir ${t.dir > 0 ? "up" : "down"}">${t.direction}</div>
      <div class="tk-grid">
        <div><span>参考入场</span><b>${fmtPrice(t.entry)}</b></div>
        <div><span>止损 -${(t.stop_pct * 100).toFixed(1)}%</span><b class="down">${fmtPrice(t.stop)}</b></div>
        <div><span>止盈(盈亏比2:1)</span><b class="up">${fmtPrice(t.target)}</b></div>
        <div><span>建议仓位</span><b>${(t.position_pct * 100).toFixed(0)}% · ${t.position_value.toLocaleString()}</b></div>
        <div><span>约合数量</span><b>${t.qty}</b></div>
        <div><span>触发止损约亏</span><b class="down">${t.risk_amount.toLocaleString()}</b></div>
      </div>
      <button id="copy-ticket" class="ghost small" style="margin-top:8px;width:100%">📋 复制订单要点</button>`;
    $("copy-ticket").onclick = () => {
      const txt = `${s.symbol} ${t.direction}｜入场 ${fmtPrice(t.entry)}｜止损 ${fmtPrice(t.stop)}｜止盈 ${fmtPrice(t.target)}｜仓位 ${t.position_value}（约 ${t.qty}）`;
      if (navigator.clipboard) navigator.clipboard.writeText(txt);
      flash("✅ 订单要点已复制,去交易所自己手动下单");
    };
  }
}

function alertNewSignal(s) {
  const flips = s.flips.map(f =>
    `${f.label} ${f.from > 0 ? "多" : f.from < 0 ? "空" : "空仓"}→${f.to > 0 ? "做多" : f.to < 0 ? "做空" : "空仓"}`).join("; ");
  const box = $("new-sig-alert");
  box.textContent = `📢 新信号!${flips}`;
  box.classList.remove("hidden", "flash"); void box.offsetWidth; box.classList.add("flash");
  beep();
  try {
    if (window.Notification && Notification.permission === "granted")
      new Notification(`📢 ${s.name || s.symbol} 新信号`, { body: `${flips} · 建议${s.recommendation}` });
  } catch (e) { }
}
function beep() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const o = ctx.createOscillator(), g = ctx.createGain();
    o.connect(g); g.connect(ctx.destination);
    o.type = "sine"; o.frequency.value = 880;
    g.gain.setValueAtTime(0.0001, ctx.currentTime);
    g.gain.exponentialRampToValueAtTime(0.25, ctx.currentTime + 0.01);
    g.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.35);
    o.start(); o.stop(ctx.currentTime + 0.35);
  } catch (e) { }
}

/* ===== 多标的自选监控 ===== */
function loadWatchlist(market) {
  try { const w = JSON.parse(localStorage.getItem("wl_" + market)); if (Array.isArray(w)) return w; } catch (e) { }
  const presets = (state.meta && state.meta.markets[market] && state.meta.markets[market].presets) || [];
  return presets.map(p => p.symbol || p);
}
function saveWatchlist(market, list) { localStorage.setItem("wl_" + market, JSON.stringify(list)); }
function curWatchlist() { return loadWatchlist(state.market); }

async function pollScan() {
  const symbols = curWatchlist();
  const mk = state.market, tf = state.timeframe;   // 快照:期间切了市场/周期就丢弃这次扫描结果
  if (!symbols.length) { $("watchlist").innerHTML = `<div class="dim" style="padding:6px 2px">还没有自选,在上面输入代码加入。</div>`; $("wl-count").textContent = ""; return; }
  try {
    const d = await fetchJSON("/api/scan", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ market: mk, symbols, timeframe: tf }),
    });
    if (mk !== state.market || tf !== state.timeframe) return;   // 已切市场/周期,旧扫描结果作废
    renderWatchlist(d.results);
    d.results.forEach(r => {   // 任意自选标的出新信号 → 提醒(同一根K线只提醒一次)
      if (!(r.new_signal && r.time)) return;
      const fresh = live.scanAlerted[r.symbol] !== r.time;
      live.scanAlerted[r.symbol] = r.time;          // 无论是否报警都记键,避免切焦点后漏报/补报
      if (r.symbol === state.symbol) return;        // 当前标的由 pollSignal 详细报警,这里不重复响
      if (fresh) alertWatch(r);                     // 本根第一次见到才报
    });
  } catch (e) { $("watchlist").innerHTML = `<div class="dim" style="padding:6px 2px">扫描失败:${e.message}</div>`; }
}

/* 增量更新自选表:复用已有行节点、只改名字/信号格,绝不碰价格/异动格,
   这样 WS 实时价不会每 30 秒被整表重建抹掉再盖回(消除闪烁、不打断颜色过渡)。*/
function renderWatchlist(results) {
  const container = $("watchlist");
  $("wl-count").textContent = results.length ? `(${results.length})` : "";
  if (!results.length) {
    container.innerHTML = `<div class="dim" style="padding:6px 2px">还没有自选,在上面输入代码加入。</div>`;
    wlSync(); return;
  }
  const existing = new Map();
  container.querySelectorAll(".wl-row").forEach(row => existing.set(row.dataset.sym, row));
  results.forEach(r => {
    let row = existing.get(r.symbol);
    existing.delete(r.symbol);
    if (!row) {
      row = document.createElement("div");
      row.className = "wl-row"; row.dataset.sym = r.symbol;
      row.innerHTML = `<span class="wl-sym"><span class="wl-name"></span><span class="wl-flag"></span><span class="wl-spike"></span></span>` +
        `<span class="wl-price"></span><span class="wl-sig"></span><button class="wl-x" title="移除">×</button>`;
    }
    const nm = (r.name && r.name !== r.symbol) ? r.name : r.symbol;
    row.querySelector(".wl-name").textContent = nm;
    row.querySelector(".wl-flag").textContent = r.new_signal ? " 🔔" : "";
    const sig = row.querySelector(".wl-sig");
    if (r.error) { sig.textContent = "取数失败"; sig.className = "wl-sig flat"; }
    else {
      const cls = r.direction > 0 ? "up" : r.direction < 0 ? "down" : "flat";
      const txt = r.direction > 0 ? "做多" : r.direction < 0 ? "做空" : "观望";
      sig.textContent = `${txt} ${r.agree}/${r.total}`; sig.className = "wl-sig " + cls;
    }
    row.classList.toggle("active", r.symbol === state.symbol);
    const priceCell = row.querySelector(".wl-price");
    if (!priceCell.textContent && r.price != null) priceCell.textContent = fmtPrice(r.price);  // 仅新行填扫描价
    container.appendChild(row);   // 复用并按结果顺序重排(已存在节点被移动,价格/异动保留)
  });
  existing.forEach(row => row.remove());   // 移除已不在自选里的行
  wlSync();    // 自选变了就重订阅实时价
  wlFlush();   // 把已有实时价立刻盖回
}
function markWatchActive() {
  document.querySelectorAll("#watchlist .wl-row").forEach(r =>
    r.classList.toggle("active", r.dataset.sym === state.symbol));
}
function addWatch(raw) {
  const norm = normalizeSymbol(state.market, raw);
  if (!norm) { toast("格式不对,如 DOGE/USDT"); return; }
  const list = curWatchlist();
  if (!list.includes(norm)) { list.push(norm); saveWatchlist(state.market, list); }
  $("wl-input").value = "";
  pollScan();
}
function removeWatch(sym) {
  saveWatchlist(state.market, curWatchlist().filter(s => s !== sym));
  pollScan();
}
async function focusSymbol(sym) {
  if (sym === state.symbol) return;
  state.symbol = sym; $("symbol").value = sym;
  markWatchActive();
  await loadKlines(); runBacktest();
  pollSignal(); pollEvent();
}
function alertWatch(r) {
  const dir = r.direction > 0 ? "做多" : r.direction < 0 ? "做空" : "观望";
  const box = $("new-sig-alert");
  box.textContent = `📢 ${r.name || r.symbol} 出现新信号:${dir}(${r.agree}/${r.total} 策略一致)`;
  box.classList.remove("hidden", "flash"); void box.offsetWidth; box.classList.add("flash");
  beep();
  try {
    if (window.Notification && Notification.permission === "granted")
      new Notification(`📢 ${r.name || r.symbol} 新信号`, { body: `建议${dir}` });
  } catch (e) { }
}

/* ===== 事件合约·超短实时方向(仅币圈,负期望赌博,只给方向+把真实胜率摆出来)===== */
async function pollEvent(refresh) {
  if (state.market !== "crypto") { $("event-sec").classList.add("hidden"); return; }
  $("event-sec").classList.remove("hidden");
  const pe = $("event-payout");
  const payout = Math.max(1.1, Math.min(3, parseFloat(pe && pe.value) || 1.8));
  try {
    const d = await fetchJSON("/api/event", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ market: "crypto", symbol: state.symbol, payout, horizons: [1, 3, 5], refresh: !!refresh }),
    });
    if (d.symbol !== state.symbol || state.market !== "crypto") return;   // 期间已切标的/市场,丢弃
    renderEvent(d);
  } catch (e) { $("event-rows").innerHTML = `<div class="dim" style="padding:4px 2px">${e.message}</div>`; }
}
function renderEvent(d) {
  // 用实测数据算一句最扎心的总结:本币所有信号每笔期望的范围(几乎全负)
  const evs = d.rows.map(r => r.ev_pct).filter(v => v != null);
  const worst = evs.length ? Math.min(...evs) * 100 : 0;
  const best = evs.length ? Math.max(...evs) * 100 : 0;
  const sigCount = d.rows.filter(r => r.significant).length;
  const be = $("event-be"); if (be) be.innerHTML = `保本胜率 <b>${(d.breakeven * 100).toFixed(1)}%</b>`;
  $("event-warn").innerHTML =
    `本质二元期权·赌博。赔率 ${d.payout} → <b>保本胜率 ${(d.breakeven * 100).toFixed(1)}%</b>。` +
    `实测本币各信号每笔期望约 <b class="down">${best.toFixed(1)}% ~ ${worst.toFixed(1)}%</b>` +
    `(下注10元≈每笔亏 ${(-worst / 10).toFixed(2)}~${(-best / 10).toFixed(2)} 元)。` +
    (sigCount ? `有 <b>${sigCount}</b> 个信号统计显著跑赢(⚠ 60+组合里凑巧显著也属正常,务必小资金样本外再验证)。`
              : `<b>无一信号能统计显著跑赢保本线 → 长期必亏</b>。`) +
    `只给方向,绝不替你下注。`;
  const byH = {};
  d.rows.forEach(r => { (byH[r.horizon] = byH[r.horizon] || []).push(r); });
  $("event-rows").innerHTML = Object.keys(byH).map(h => {
    // 每个时长内按"每笔期望"从高到低排,最有边际的排最上面,方便做决策
    const list = byH[h].slice().sort((a, b) => (b.ev_pct ?? -9) - (a.ev_pct ?? -9));
    const rows = list.map((r, i) => {
      const dir = r.direction === "UP" ? "押涨" : r.direction === "DOWN" ? "押跌" : "不押";
      const dcls = r.direction === "UP" ? "up" : r.direction === "DOWN" ? "down" : "flat";
      const good = !!r.significant;                 // 只有【统计显著】才给绿,杜绝"56%在120笔"的假希望
      const wcls = good ? "up" : "down";
      const ev = (r.ev_pct == null ? 0 : r.ev_pct * 100);
      const evs = (ev >= 0 ? "+" : "") + ev.toFixed(1) + "%";
      const star = (good && i === 0) ? "★ " : "";   // 该时长里最好且显著 → 标星
      return `<div class="ev-row"><span class="ev-lbl">${star}${r.signal_label}</span>
        <span class="ev-dir ${dcls}">${dir}</span>
        <span class="ev-wr ${wcls}">胜${(r.win_rate * 100).toFixed(1)}% · 期望${evs}</span></div>
        <div class="ev-verdict ${good ? "ok" : ""}">${r.verdict} <span class="dim">(${r.bets}笔)</span></div>`;
    }).join("");
    return `<div class="ev-group"><div class="ev-h">${h} 分钟合约</div>${rows}</div>`;
  }).join("");
}

/* ===== 实时行情 WebSocket(直连 gate 推送,毫秒级更新 + 收盘倒计时)===== */
const GATE_WS = "wss://api.gateio.ws/ws/v4/";
// 我们的周期 → gate 原生支持推送的K线周期(派生的 3m/1月 没有,靠成交价更新最后一根)
const GATE_CANDLE_TF = { "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m", "1h": "1h", "4h": "4h", "1d": "1d", "1w": "7d" };
const TF_SECONDS_FE = { "1m": 60, "3m": 180, "5m": 300, "15m": 900, "30m": 1800, "1h": 3600, "2h": 7200, "4h": 14400, "8h": 28800, "1d": 86400, "1w": 604800 };
const COUNTDOWN_TF = new Set(["1m", "3m", "5m", "15m", "30m", "1h", "4h", "1d"]);

const rt = { ws: null, sym: null, tf: null, gateSym: null, liveBar: null, liveVol: null,
             lastPrice: null, raf: null, reconnectTimer: null, rolloverTimer: null,
             hovering: false, newBar: false, resync: false, rollover: false, refreshSeq: 0,
             rangeHiBase: null, rangeLoBase: null, volBase: 0 };

function gateSymbol(sym) { return sym.replace("/", "_").toUpperCase(); }
function setLiveDot(on) { $("live-dot").classList.toggle("on", on); }

/* 某派生周期的"当前根"是否已到期(该换根了)。1月按自然月、其余按定长秒 */
function tfExpired(tf, lastOpenSec) {
  const now = Date.now() / 1000;
  if (tf === "1M") {
    const d = new Date(lastOpenSec * 1000);
    const nextMonth = Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 1) / 1000;
    return now >= nextMonth;
  }
  const p = TF_SECONDS_FE[tf];
  return p ? now >= lastOpenSec + p : false;
}

function rtStop() {
  if (rt.ws) { try { rt.ws.onclose = null; rt.ws.close(); } catch (e) { } rt.ws = null; }
  clearTimeout(rt.reconnectTimer); rt.reconnectTimer = null;
  clearTimeout(rt.rolloverTimer); rt.rolloverTimer = null; rt.rollover = false;
  if (rt.raf) { cancelAnimationFrame(rt.raf); rt.raf = null; }
  setLiveDot(false);
}

/* 启动/切换实时订阅(仅币圈;标的/周期没变且连接仍 OPEN 才复用)*/
function rtStart() {
  if (state.market !== "crypto") { rtStop(); rt.sym = null; setLiveDot(false); return; }
  if (rt.ws && rt.ws.readyState === WebSocket.OPEN
      && rt.sym === state.symbol && rt.tf === state.timeframe) return;
  rtStop();
  rt.sym = state.symbol; rt.tf = state.timeframe; rt.gateSym = gateSymbol(state.symbol);
  rt.liveBar = rt.liveVol = rt.lastPrice = null;
  connectWS();
}

function connectWS() {
  let ws;
  try { ws = new WebSocket(GATE_WS); } catch (e) { scheduleReconnect(); return; }
  rt.ws = ws;
  const myWs = ws;   // 身份令牌:只有"当前这条"socket 的回调才生效,旧 socket 一律忽略
  ws.onopen = () => {
    if (rt.ws !== myWs) return;
    setLiveDot(true);
    const t = Math.floor(Date.now() / 1000);
    ws.send(JSON.stringify({ time: t, channel: "spot.trades", event: "subscribe", payload: [rt.gateSym] }));
    const gtf = GATE_CANDLE_TF[rt.tf];
    if (gtf) ws.send(JSON.stringify({ time: t, channel: "spot.candlesticks", event: "subscribe", payload: [gtf, rt.gateSym] }));
  };
  ws.onmessage = e => {
    if (rt.ws !== myWs) return;
    let j; try { j = JSON.parse(e.data); } catch (x) { return; }
    if (j.event !== "update" || !j.result) return;
    if (rt.sym !== state.symbol || rt.tf !== state.timeframe) return;   // 已切换,丢弃旧推送
    if (j.channel === "spot.candlesticks") onCandle(j.result);
    else if (j.channel === "spot.trades") onTrade(j.result);
  };
  ws.onclose = () => {
    if (rt.ws !== myWs) return;   // 不是当前 socket(已被新连接取代)→ 不重连
    setLiveDot(false);
    if (rt.sym === state.symbol && state.market === "crypto") scheduleReconnect();
  };
  ws.onerror = () => { try { ws.close(); } catch (e) { } };
}
function scheduleReconnect() {
  clearTimeout(rt.reconnectTimer);
  rt.reconnectTimer = setTimeout(() => { if (state.market === "crypto" && rt.sym) connectWS(); }, 2000);
}

function onTrade(r) {
  const tr = Array.isArray(r) ? r[r.length - 1] : r;
  const price = parseFloat(tr.price);
  if (!isFinite(price)) return;
  rt.lastPrice = price;
  if (!GATE_CANDLE_TF[rt.tf]) {           // 派生周期(3m/1月):用成交价更新最后一根
    const c = state.candles; if (!c.length) { scheduleFlush(); return; }
    const last = c[c.length - 1];
    if (tfExpired(rt.tf, last.time)) { scheduleFlush(); return; }   // 本根已收盘,等换根,不再改写
    const bar = (rt.liveBar && rt.liveBar.time === last.time) ? rt.liveBar : { ...last };
    bar.close = price; bar.high = Math.max(bar.high, price); bar.low = Math.min(bar.low, price);
    bar.volume = (bar.volume || 0) + (parseFloat(tr.amount) || 0);   // 成交量实时累加
    rt.liveBar = bar;
    rt.liveVol = { time: bar.time, value: bar.volume };
  }
  scheduleFlush();
}
function onCandle(r) {
  const t = parseInt(r.t);
  const c = state.candles, lastT = c.length ? c[c.length - 1].time : 0;
  // gate 的 v 是【计价币成交额 USDT】,a 才是【基础币成交量 BTC】。
  // 历史K线(ccxt)用的是基础币量,这里必须取 a 对齐,否则两者量纲差一个币价(~6万倍),
  // 实时柱会把整个成交量刻度撑爆,历史柱被压成 0 像素看不见(就是之前 VOL 显示异常的原因)。
  const baseVol = r.a != null ? +r.a : (+r.c ? +r.v / +r.c : +r.v);
  const full = { time: t, open: +r.o, high: +r.h, low: +r.l, close: +r.c, volume: baseVol };
  if (lastT && t > lastT) {                // 新K线形成 → 追加,标记需要重算指标
    state.candles.push(full); state.candleMap.set(t, full);
    if (state.candles.length > state.limit + 80) {   // 裁掉最老一根 → 需整图重对齐(见 flushLive)
      const drop = state.candles.shift(); state.candleMap.delete(drop.time); rt.resync = true;
    }
    rt.newBar = true;
  } else if (t === lastT) {                 // 当前根更新 → 原地改
    Object.assign(c[c.length - 1], full); state.candleMap.set(t, full);
  } else { return; }                        // 过期推送
  rt.liveBar = { time: t, open: +r.o, high: +r.h, low: +r.l, close: +r.c };
  rt.liveVol = { time: t, value: baseVol };
  rt.lastPrice = +r.c;
  scheduleFlush();
}

/* 用 requestAnimationFrame 节流(~60fps),即使每秒上百笔成交也不卡 */
function scheduleFlush() {
  if (rt.raf) return;
  rt.raf = requestAnimationFrame(flushLive);
}
/* 整图与 state.candles 强制对齐(裁剪/换根后用):重设数据 + 重建 anchors + 保留回测标记 */
function resyncChart() {
  const range = mainChart.timeScale().getVisibleLogicalRange();
  renderCandles(); refreshIndicators();
  renderMarkers(); renderHoldings(); renderStrategyOverlays();
  if (range) mainChart.timeScale().setVisibleLogicalRange(range);
}
function flushLive() {
  rt.raf = null;
  if (rt.sym !== state.symbol || rt.tf !== state.timeframe) return;
  if (rt.lastPrice != null) updateTickerLive(rt.lastPrice);
  if (rt.resync) {                 // 删头那一帧:全量重对齐(避免图表与 state.candles 发散)
    rt.resync = false; rt.newBar = false;
    resyncChart();
  } else {
    const bar = rt.liveBar;
    if (bar) {
      const lastT = state.candles.length ? state.candles[state.candles.length - 1].time : 0;
      if (bar.time >= lastT) {
        try {
          candleSeries.update(bar);
          areaSeries.update({ time: bar.time, value: bar.close });
          if (rt.liveVol && cfg.vol.on)
            volSeries.update({ time: rt.liveVol.time, value: rt.liveVol.value,
              color: hexA(bar.close >= bar.open ? upColor() : downColor(), .45) });
        } catch (e) { }
      }
    }
    if (rt.newBar) { rt.newBar = false; refreshIndicators(); }   // 新K线收盘后重算指标
  }
  if (!rt.hovering && rt.liveBar)   // 不在悬停看历史时,图例显示实时 OHLC
    renderLegend({ ...rt.liveBar, volume: rt.liveVol ? rt.liveVol.value : 0 });
  positionCountdown();   // 价格实时变,倒计时跟着最新价标签上下移
}

function updateTickerLive(price) {
  if (state.candles.length < 1 || rt.rangeHiBase == null) return;
  const bar = rt.liveBar;
  // 区间高低/量随实时价一起更新(不再冻结在上次重载时刻)
  applyTicker(price, bar ? bar.high : price, bar ? bar.low : price,
              rt.liveVol ? rt.liveVol.value : (bar ? bar.volume || 0 : 0));
}

/* ===== K线收盘倒计时 + 派生周期换根触发 ===== */
function fmtCountdown(sec) {
  sec = Math.max(0, Math.floor(sec));
  const h = Math.floor(sec / 3600), m = Math.floor(sec % 3600 / 60), s = sec % 60;
  const p = n => String(n).padStart(2, "0");
  return h > 0 ? `${h}:${p(m)}:${p(s)}` : `${p(m)}:${p(s)}`;
}
/* 派生周期(无WS自动换根:3m/1月)到点时触发静默换根。独立于倒计时显示,故 1月也覆盖 */
function checkRollover() {
  if (state.market !== "crypto") return;
  const tf = state.timeframe;
  if (GATE_CANDLE_TF[tf]) return;                 // 原生周期靠 WS 自动换根
  const c = state.candles; if (!c.length) return;
  if (tfExpired(tf, c[c.length - 1].time)) maybeRollover();
}
function updateCountdown() {
  checkRollover();                                // 换根触发(覆盖 1月,与显示解耦)
  const el = $("countdown");
  const c = state.candles;
  if (state.market !== "crypto" || !c.length || !COUNTDOWN_TF.has(state.timeframe)) {
    el.classList.add("hidden"); return;
  }
  const period = TF_SECONDS_FE[state.timeframe];
  const remain = c[c.length - 1].time + period - Date.now() / 1000;
  el.classList.remove("hidden");
  el.textContent = remain <= 0 ? "00:00" : fmtCountdown(remain);   // 只显示倒计时时间
  positionCountdown();
}
/* 让倒计时贴在右侧价格轴、紧跟最新价标签下方(随价格上下移动)*/
function positionCountdown() {
  const el = $("countdown");
  if (el.classList.contains("hidden")) return;
  const c = state.candles; if (!c.length) return;
  const price = (rt.liveBar && rt.liveBar.time === c[c.length - 1].time)
    ? rt.liveBar.close : c[c.length - 1].close;
  let y = null;
  try { y = candleSeries.priceToCoordinate(price); } catch (e) { }
  if (y == null) return;
  let w = 60;
  try { w = Math.round(mainChart.priceScale("right").width()); } catch (e) { }
  const h = $("main-chart").clientHeight || 400;
  el.style.width = w + "px";                                    // 与价格标签等宽
  el.style.top = Math.max(2, Math.min(h - 18, y + 8)) + "px";   // 紧贴价签下方,夹在可视高度内
}
function maybeRollover() {
  if (rt.rollover) return;
  rt.rollover = true;
  rt.rolloverTimer = setTimeout(async () => {
    rt.rolloverTimer = null;
    await silentRefreshKlines();
    rt.rollover = false;
  }, 1500);
}
/* 静默刷新K线:换根/补指标,保持视野、保留回测买卖点/持仓/策略线 */
async function silentRefreshKlines() {
  const myKline = klineSeq;          // 期间若有更新的 loadKlines 就让位
  const my = ++rt.refreshSeq;
  try {
    const data = await fetchJSON(`/api/klines?market=${state.market}` +
      `&symbol=${encodeURIComponent(state.symbol)}&timeframe=${state.timeframe}&limit=${state.limit}&refresh=true`);
    if (klineSeq !== myKline || my !== rt.refreshSeq
        || rt.sym !== state.symbol || rt.tf !== state.timeframe) return;
    const range = mainChart.timeScale().getVisibleLogicalRange();
    state.candles = data.candles;
    state.candleMap = new Map(data.candles.map(k => [k.time, k]));
    renderCandles(); refreshIndicators(); renderTicker();
    renderMarkers(); renderHoldings(); renderStrategyOverlays();   // 别把回测结果抹掉
    if (range) mainChart.timeScale().setVisibleLogicalRange(range);
    rt.liveBar = null; rt.liveVol = null;
  } catch (e) { }
}

/* ===== 自选监控实时价(gate spot.tickers 推送整篮子,毫秒级)+ 异动提醒 ===== */
const wlrt = { ws: null, symbols: [], reconnectTimer: null, price: {}, prev: {}, raf: null,
               hist: {}, lastAlert: {}, spike: {} };
const SPIKE_WINDOW = 60;   // 异动观察窗口:近 60 秒
const SPIKE_COOLDOWN = 120; // 同一个币两次异动提醒至少间隔 2 分钟,避免刷屏

function sameSet(a, b) { return a.length === b.length && a.every(x => b.includes(x)); }

function spikeThreshold() {
  const v = parseFloat(($("spike-thresh") || {}).value);
  return isFinite(v) && v > 0 ? v / 100 : 0;   // 返回小数,0=关闭
}

/* 近 SPIKE_WINDOW 秒内涨跌幅超过阈值 → 异动提醒(每币冷却) */
function detectSpike(sym, p) {
  const thresh = spikeThreshold();
  if (!thresh) return;
  const now = Date.now() / 1000;
  const buf = wlrt.hist[sym] || (wlrt.hist[sym] = []);
  buf.push({ t: now, p });
  while (buf.length && now - buf[0].t > SPIKE_WINDOW) buf.shift();
  if (buf.length < 2) return;
  const base = buf[0].p;
  const chg = base ? p / base - 1 : 0;
  if (Math.abs(chg) >= thresh && now - (wlrt.lastAlert[sym] || 0) >= SPIKE_COOLDOWN) {
    wlrt.lastAlert[sym] = now;
    wlrt.spike[sym] = { chg, until: now + 12 };   // 行上⚡标记保持 12 秒
    alertSpike(sym, chg);
  }
}
function alertSpike(sym, chg) {
  const nm = state.nameCache[sym] || sym;
  const dir = chg >= 0 ? "拉升" : "跳水";
  const pct = (chg >= 0 ? "+" : "") + (chg * 100).toFixed(1) + "%";
  const box = $("new-sig-alert");
  box.textContent = `⚡ 异动!${nm} 近${SPIKE_WINDOW}秒${dir} ${pct}`;
  box.classList.remove("hidden", "flash"); void box.offsetWidth; box.classList.add("flash");
  beep();
  try {
    if (window.Notification && Notification.permission === "granted")
      new Notification(`⚡ ${nm} 异动`, { body: `近${SPIKE_WINDOW}秒${dir} ${pct}` });
  } catch (e) { }
}

/* 按"当前是否在决策台 + 币圈 + 自选列表"决定订阅,变了才重连 */
function wlSync() {
  const liveVisible = !$("tab-live").classList.contains("hidden");
  if (state.market !== "crypto" || !liveVisible) { wlStop(); return; }
  const want = curWatchlist().map(gateSymbol);
  if (wlrt.ws && wlrt.ws.readyState === WebSocket.OPEN && sameSet(wlrt.symbols, want)) return;
  wlStop();
  wlrt.symbols = want;
  if (want.length) wlConnect();
}
function wlStop() {
  if (wlrt.ws) { try { wlrt.ws.onclose = null; wlrt.ws.close(); } catch (e) { } wlrt.ws = null; }
  clearTimeout(wlrt.reconnectTimer); wlrt.reconnectTimer = null;
  if (wlrt.raf) { cancelAnimationFrame(wlrt.raf); wlrt.raf = null; }
}
function wlConnect() {
  let ws; try { ws = new WebSocket(GATE_WS); } catch (e) { wlReconnect(); return; }
  wlrt.ws = ws; const myWs = ws;
  ws.onopen = () => { if (wlrt.ws !== myWs) return;
    ws.send(JSON.stringify({ time: Math.floor(Date.now() / 1000), channel: "spot.tickers", event: "subscribe", payload: wlrt.symbols })); };
  ws.onmessage = e => {
    if (wlrt.ws !== myWs) return;
    let j; try { j = JSON.parse(e.data); } catch (x) { return; }
    if (j.event !== "update" || j.channel !== "spot.tickers" || !j.result) return;
    onTicker(j.result);
  };
  ws.onclose = () => { if (wlrt.ws !== myWs) return; wlReconnect(); };
  ws.onerror = () => { try { ws.close(); } catch (e) { } };
}
function wlReconnect() {
  clearTimeout(wlrt.reconnectTimer);
  wlrt.reconnectTimer = setTimeout(() => {
    if (state.market === "crypto" && !$("tab-live").classList.contains("hidden")) wlConnect();
  }, 2500);
}
function onTicker(r) {
  const tk = Array.isArray(r) ? r[0] : r;
  if (!tk || !tk.currency_pair) return;
  const sym = tk.currency_pair.replace("_", "/");
  const p = parseFloat(tk.last);
  if (!isFinite(p)) return;
  wlrt.price[sym] = p;
  detectSpike(sym, p);
  if (!wlrt.raf) wlrt.raf = requestAnimationFrame(wlFlush);
}
/* 把最新实时价刷进自选表对应行(rAF 节流,涨绿跌红),并维护异动⚡标记 */
function wlFlush() {
  wlrt.raf = null;
  const now = Date.now() / 1000;
  document.querySelectorAll("#watchlist .wl-row").forEach(row => {
    const sym = row.dataset.sym;
    const cell = row.querySelector(".wl-price");
    const p = wlrt.price[sym];
    if (cell && p != null) {
      const txt = fmtPrice(p);
      if (cell.textContent !== txt) {
        const prev = wlrt.prev[sym];
        if (prev != null) cell.style.color = p >= prev ? upColor() : downColor();
        cell.textContent = txt;
      }
      wlrt.prev[sym] = p;
    }
    const badge = row.querySelector(".wl-spike");
    if (badge) {
      const sp = wlrt.spike[sym];
      if (sp && now < sp.until) {
        badge.textContent = `⚡${sp.chg >= 0 ? "+" : ""}${(sp.chg * 100).toFixed(1)}%`;
        badge.className = "wl-spike " + (sp.chg >= 0 ? "up" : "down");
        row.classList.add("spiking");
      } else if (badge.textContent) {
        badge.textContent = ""; badge.className = "wl-spike"; row.classList.remove("spiking");
      }
    }
  });
}

/* ---------------- 数据加载 ---------------- */
function positionSyntheticBadge() {   // 把"模拟数据"红标放到图例下方,避免与指标图例压字
  const b = $("synthetic-badge");
  if (b.classList.contains("hidden")) return;
  const lg = $("legend");
  b.style.top = (lg.offsetTop + lg.offsetHeight + 4) + "px";
}
function setSynthetic(on) {
  $("synthetic-badge").classList.toggle("hidden", !on);
  if (on) positionSyntheticBadge();
}

async function loadKlines(refresh = false) {
  const my = ++klineSeq;
  $("loading").classList.remove("hidden");
  try {
    const data = await fetchJSON(`/api/klines?market=${state.market}` +
      `&symbol=${encodeURIComponent(state.symbol)}&timeframe=${state.timeframe}` +
      `&limit=${state.limit}${refresh ? "&refresh=true" : ""}`);
    if (my !== klineSeq) return;   // 先发后到的旧请求,丢弃
    state.candles = data.candles;
    state.candleMap = new Map(data.candles.map(k => [k.time, k]));
    if (data.name) state.nameCache[state.symbol] = data.name;   // 记下名字
    renderSymbolName();
    state.bt = null;
    eqReady = false;            // 资金曲线图先退出联动,等新回测数据就位再加入
    anchors.delete(eqChart);
    $("equity-wrap").classList.add("hidden");
    $("trades-wrap").classList.add("hidden");
    $("health").classList.add("hidden");
    $("robust-btn").classList.add("hidden");
    $("robust").classList.add("hidden");
    setSynthetic(data.source === "synthetic");   // 假数据时显示醒目红标
    renderCandles(); refreshIndicators(); renderTicker();
    renderMarkers(); renderHoldings(); renderStrategyOverlays();   // 清掉上一个标的的回测残留
    applyDefaultRange();        // 最后统一设置视野,覆盖中途任何自动重置
    rtStart();                  // 订阅实时推送(仅币圈,标的/周期没变则复用)
  } catch (e) { if (my === klineSeq) toast(e.message); }
  finally { if (my === klineSeq) $("loading").classList.add("hidden"); }
}

/* ---------------- 工具栏:指标开关 chips ---------------- */
const CHIPS_MAIN = [["MA", "ma"], ["EMA", "ema"], ["BOLL", "boll"], ["VOL", "vol"]];
const CHIPS_SUB = [["MACD", "macd"], ["RSI", "rsi"], ["KDJ", "kdj"]];
function renderChips() {
  $("chips-main").innerHTML = CHIPS_MAIN.map(([l, k]) =>
    `<button class="chip ${cfg[k].on ? "active" : ""}" data-k="${k}">${l}</button>`).join("");
  $("chips-sub").innerHTML = CHIPS_SUB.map(([l, k]) =>
    `<button class="chip ${cfg.subs[k].on ? "active" : ""}" data-k="${k}">${l}</button>`).join("");
  $("chips-main").querySelectorAll(".chip").forEach(b => b.onclick = () => {
    cfg[b.dataset.k].on = !cfg[b.dataset.k].on; saveCfg(); applyAll();
  });
  $("chips-sub").querySelectorAll(".chip").forEach(b => b.onclick = () => {
    cfg.subs[b.dataset.k].on = !cfg.subs[b.dataset.k].on; saveCfg(); applyAll();
  });
}

/* 配置变化后的统一刷新入口 */
function applyAll() {
  renderChips();
  syncPanes();
  refreshIndicators();
}

/* ---------------- 指标设置弹窗 ---------------- */
function getPath(o, p) { return p.split(".").reduce((a, k) => (a == null ? a : a[k]), o); }
function setPath(o, p, v) {
  const ks = p.split("."); const last = ks.pop();
  ks.reduce((a, k) => a[k], o)[last] = v;
}
function openModal() {
  document.querySelectorAll("#ind-modal [data-path]").forEach(inp => {
    const v = getPath(cfg, inp.dataset.path);
    if (inp.type === "checkbox") inp.checked = !!v; else inp.value = v;
  });
  $("ind-modal").classList.remove("hidden");
}
function wireModal() {
  $("ind-settings").onclick = openModal;
  $("modal-close").onclick = () => $("ind-modal").classList.add("hidden");
  $("ind-modal").addEventListener("click", e => {     // 点弹窗外面也关闭
    if (e.target.id === "ind-modal") $("ind-modal").classList.add("hidden");
  });
  document.querySelectorAll("#ind-modal [data-path]").forEach(inp => {
    inp.onchange = () => {
      const v = inp.type === "checkbox" ? inp.checked : (parseFloat(inp.value) || 0);
      setPath(cfg, inp.dataset.path, v);
      saveCfg(); applyAll();
    };
  });
  $("cfg-reset").onclick = () => {
    cfg = structuredClone(DEFAULT_CFG);
    saveCfg(); openModal(); applyAll();
  };
}

/* ---------------- 周期选择 ---------------- */
const TF_LABELS = {
  "1m": "1分", "3m": "3分", "5m": "5分", "15m": "15分", "30m": "30分",
  "1h": "1时", "2h": "2时", "4h": "4时", "8h": "8时",
  "1d": "日", "1w": "周", "1M": "月",
};

function applyChartType() {
  const line = $("chart-type").checked;
  candleSeries.applyOptions({ visible: !line });
  areaSeries.applyOptions({ visible: line });
}

// 每个市场默认直接显示的"常用"周期(其余的收进"更多▾"下拉,对标 Binance/OKX)
const TF_QUICK = {
  crypto: ["分时", "15m", "1h", "4h", "1d"],
  astock: ["1d", "1w", "1M"],
  usstock: ["1h", "1d", "1w", "1M"],
  futures: ["5m", "30m", "1h", "1d"],
};
// 下拉菜单里的分组
const TF_MENU_GROUPS = [
  ["分钟", ["分时", "1m", "3m", "5m", "15m", "30m"]],
  ["小时", ["1h", "2h", "4h", "8h"]],
  ["日/周/月", ["1d", "1w", "1M"]],
];

// 用户自定义"固定在快捷栏的周期"(每个市场各记一份,存浏览器);没自定义就用上面的默认
function getQuick(market) {
  try { const s = JSON.parse(localStorage.getItem("tfQuick_" + market)); if (Array.isArray(s) && s.length) return s; } catch (e) { }
  return TF_QUICK[market] || [];
}
function toggleQuick(market, v) {
  const list = getQuick(market).slice();
  const i = list.indexOf(v);
  if (i >= 0) { if (list.length > 1) list.splice(i, 1); }   // 至少保留一个,避免清空
  else {
    list.push(v);
    const order = allTfValues();                            // 按周期从小到大排,保持顺序自然
    list.sort((a, b) => order.indexOf(a) - order.indexOf(b));
  }
  localStorage.setItem("tfQuick_" + market, JSON.stringify(list));
}

const tfLabel = v => (v === "分时" ? "分时" : (TF_LABELS[v] || v));
function allTfValues() {
  const tfs = state.meta.markets[state.market].timeframes;
  return (state.market === "crypto" ? ["分时"] : []).concat(tfs);
}
function closeTfMenu() {
  const m = document.querySelector("#tf-group .tf-menu");
  if (m) m.classList.add("hidden");
}

function renderTfGroup() {
  const tfs = state.meta.markets[state.market].timeframes;
  const allowFenshi = state.market === "crypto";   // 分时(1分线)只对币圈提供
  // 校正当前选择,保证对当前市场有效
  if (state.tfSel === "分时" && !allowFenshi) state.tfSel = null;
  if (state.tfSel !== "分时" && !tfs.includes(state.timeframe)) state.tfSel = null;
  if (!state.tfSel) {
    state.timeframe = tfs.includes("1h") ? "1h" : (tfs.includes("1d") ? "1d" : tfs[0]);
    state.tfSel = state.timeframe;
  }

  const all = allTfValues();
  const quick = getQuick(state.market).filter(v => all.includes(v));
  const inQuick = quick.includes(state.tfSel);

  // 常用周期按钮(用户可在"更多"里用★自定义固定哪些)
  let html = quick.map(v =>
    `<button class="tf-btn ${v === state.tfSel ? "active" : ""}" data-tf="${v}">${tfLabel(v)}</button>`).join("");

  // "更多▾":列出全部周期,每个带★可固定/取消固定到上方快捷栏;点周期名=切换
  const groups = TF_MENU_GROUPS
    .map(([name, vals]) => [name, vals.filter(v => all.includes(v))])
    .filter(([, vals]) => vals.length);
  const menu = `<div class="tf-menu-tip">点 ★ 把周期固定/取消固定到上方快捷栏</div>` +
    groups.map(([name, vals]) =>
      `<div class="tf-menu-h">${name}</div><div class="tf-menu-row">` +
      vals.map(v => {
        const pinned = quick.includes(v);
        return `<span class="tf-menu-item ${v === state.tfSel ? "active" : ""}" data-tf="${v}">` +
          `<i class="tf-pin ${pinned ? "on" : ""}" data-pin="${v}" title="${pinned ? "取消固定" : "固定到快捷栏"}">★</i>` +
          `<span class="tf-name">${tfLabel(v)}</span></span>`;
      }).join("") +
      `</div>`).join("");
  html += `<div class="tf-more">
    <button class="tf-btn tf-more-btn ${inQuick ? "" : "active"}">${inQuick ? "更多" : tfLabel(state.tfSel)}<span class="caret">▾</span></button>
    <div class="tf-menu hidden">${menu}</div>
  </div>`;
  $("tf-group").innerHTML = html;

  $("tf-group").querySelectorAll(".tf-btn[data-tf]").forEach(b =>
    b.onclick = () => { closeTfMenu(); selectTimeframe(b.dataset.tf); });
  const moreBtn = $("tf-group").querySelector(".tf-more-btn");
  if (moreBtn) {
    const menu = $("tf-group").querySelector(".tf-menu");
    moreBtn.onclick = e => { e.stopPropagation(); menu.classList.toggle("hidden"); };
    // 点★:固定/取消固定到快捷栏(不切换周期)
    menu.querySelectorAll(".tf-pin").forEach(pin =>
      pin.onclick = e => { e.stopPropagation(); toggleQuick(state.market, pin.dataset.pin); renderTfGroup(); });
    // 点周期名:切换周期
    menu.querySelectorAll(".tf-menu-item[data-tf]").forEach(it =>
      it.onclick = () => { menu.classList.add("hidden"); selectTimeframe(it.dataset.tf); });
  }
}

async function selectTimeframe(val) {
  const wasFenshi = state.tfSel === "分时";
  state.tfSel = val;
  if (val === "分时") {
    state.timeframe = "1m";              // 分时 = 1分钟 + 折线视图
    $("chart-type").checked = true;
  } else {
    state.timeframe = val;
    if (wasFenshi) $("chart-type").checked = false;   // 从分时切回普通K线
  }
  applyChartType();
  renderTfGroup();
  await loadKlines(); runBacktest();
  if (!$("tab-live").classList.contains("hidden")) pollScan();   // 决策台开着 → 自选表立即按新周期重扫
}

function renderSymbolList() {
  const presets = state.meta.markets[state.market].presets;
  // datalist 选项带上名字:下拉里直接看到"600519 贵州茅台"
  $("symbol-list").innerHTML = presets.map(p =>
    `<option value="${p.symbol}">${p.name && p.name !== p.symbol ? p.name : ""}</option>`).join("");
  // 顺手把预设的名字记进缓存,切换时即时显示、不用等接口
  presets.forEach(p => { if (p.name) state.nameCache[p.symbol] = p.name; });
}

/* 顶部行情条显示标的名字(如"贵州茅台");没有名字就留空 */
function renderSymbolName() {
  const nm = state.nameCache[state.symbol];
  $("sym-name").textContent = (nm && nm !== state.symbol) ? nm : "";
}

/* 标的代码归一化:币圈按 App 习惯输入 btcusdt 自动补成 BTC/USDT;认不出返回 null */
const QUOTES = ["USDT", "USDC", "FDUSD", "TUSD", "BTC", "ETH", "BNB", "DAI"];
function normalizeSymbol(market, raw) {
  let v = (raw || "").trim();
  if (!v) return null;
  if (market === "crypto") {
    v = v.toUpperCase().replace(/\s/g, "");
    if (!v.includes("/")) {
      const q = QUOTES.find(q => v.endsWith(q) && v.length > q.length);
      if (!q) return null;
      v = v.slice(0, -q.length) + "/" + q;
    }
    return v;
  }
  return market === "usstock" ? v.toUpperCase() : v;
}

function renderParamBox() {
  const sc = state.meta.strategies.find(s => s.name === $("strategy").value);
  $("param-box").innerHTML = sc.params.map(p =>
    `<label class="field"><span>${p.label}</span>
     <input type="number" data-key="${p.key}" value="${p.value}" min="${p.min}" max="${p.max}" step="${p.step || 1}"></label>`).join("");
}

/* 拖动调整K线图高度(记住你设的高度)*/
function initChartResizer() {
  const resizer = $("chart-resizer"), chartEl = $("main-chart");
  const saved = parseInt(localStorage.getItem("chartH"));
  if (saved >= 200) chartEl.style.height = saved + "px";
  let startY = 0, startH = 0, dragging = false;
  const onMove = e => {
    if (!dragging) return;
    const h = Math.max(200, Math.min(window.innerHeight - 120, startH + (e.clientY - startY)));
    chartEl.style.height = h + "px";
  };
  const onUp = () => {
    if (!dragging) return;
    dragging = false; resizer.classList.remove("dragging");
    document.body.style.userSelect = "";
    localStorage.setItem("chartH", parseInt(chartEl.style.height));
    document.removeEventListener("mousemove", onMove);
    document.removeEventListener("mouseup", onUp);
  };
  resizer.addEventListener("mousedown", e => {
    dragging = true; startY = e.clientY; startH = chartEl.clientHeight;
    resizer.classList.add("dragging");
    document.body.style.userSelect = "none";
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
    e.preventDefault();
  });
}

async function init() {
  applyCandleColors();
  renderChips();
  wireModal();
  initChartResizer();
  try { state.meta = await fetchJSON("/api/meta"); }
  catch (e) { toast("无法连接后端:" + e.message); return; }

  $("market").innerHTML = Object.entries(state.meta.markets)
    .map(([k, v]) => `<option value="${k}">${v.label}</option>`).join("");
  $("market").onchange = async () => {
    state.market = $("market").value;
    state.symbol = state.meta.markets[state.market].presets[0].symbol;
    $("symbol").value = state.symbol;
    renderSymbolList(); renderSymbolName(); renderTfGroup();
    await loadKlines(); runBacktest();
    if (!$("tab-live").classList.contains("hidden")) pollScan();   // 决策台开着 → 刷新自选(含重订阅实时价)
    else wlSync();
  };

  $("symbol").value = state.symbol;
  renderSymbolList();
  $("symbol").onchange = async () => {
    const norm = normalizeSymbol(state.market, $("symbol").value);
    if (norm === null) {   // 认不出格式:提示并还原,不发无效请求
      toast("标的格式应为 BASE/QUOTE,如 BTC/USDT");
      $("symbol").value = state.symbol; return;
    }
    $("symbol").value = norm;
    if (norm === state.symbol) return;
    state.symbol = norm;
    await loadKlines(); runBacktest();
  };

  renderTfGroup();

  $("limit").onchange = async () => { state.limit = parseInt($("limit").value); await loadKlines(); runBacktest(); };
  // K线默认显示根数:选了立刻应用 + 记住
  const db = $("default-bars");
  if (db) {
    db.value = String(state.defaultBars);
    db.onchange = () => {
      state.defaultBars = parseInt(db.value);
      localStorage.setItem("defaultBars", db.value);
      applyDefaultRange();
    };
  }

  $("chart-type").onchange = () => {
    // 手动勾"折线"时,若当前是"分时"快捷态,取消其高亮(回到普通周期选择)
    if (!$("chart-type").checked && state.tfSel === "分时") {
      state.tfSel = state.timeframe; renderTfGroup();
    }
    applyChartType();
  };

  // 涨跌配色切换(红涨绿跌 ⇄ 绿涨红跌),全部图表跟着翻
  $("color-toggle").onclick = () => {
    state.redUp = !state.redUp;
    localStorage.setItem("redUp", state.redUp ? "1" : "0");
    applyCandleColors(); refreshIndicators(); renderTicker();
    renderMarkers(); renderHoldings(); renderMetrics(); renderSignal(); renderTrades();
  };

  // ⚡ 短线模式:一键配置 5分钟 + 决策台 + 15秒快速刷新信号
  $("scalp-mode").onclick = async () => {
    if (state.market === "crypto") await selectTimeframe("5m");   // 仅币圈有分钟实时
    switchPanelTab("live");
    $("live-interval").value = "15";
    stopLive(); startLive();
    flash("⚡ 短线模式:5分钟 · 决策台 · 每15秒刷新信号(仍只提醒、不下单)");
  };

  // ⟳ 刷新:跳过缓存拉最新行情,再重跑回测
  $("refresh-btn").onclick = async () => {
    const b = $("refresh-btn"); b.disabled = true; b.textContent = "⟳ 刷新中…";
    await loadKlines(true); runBacktest();
    b.disabled = false; b.textContent = "⟳ 刷新";
  };

  // 价格轴 线性/对数/百分比
  applyPriceMode();
  document.querySelectorAll("#price-mode .chip").forEach(b => b.onclick = () => {
    state.priceMode = b.dataset.mode;
    localStorage.setItem("priceMode", state.priceMode);
    applyPriceMode();
  });

  // 双击图表复位到默认视野(交易所同款)
  $("main-chart").addEventListener("dblclick", applyDefaultRange);
  $("sub-panes").addEventListener("dblclick", applyDefaultRange);

  // 点页面其它地方关闭"更多周期"下拉
  document.addEventListener("click", closeTfMenu);

  // 右侧面板:回测 / 实时决策 切换
  document.querySelectorAll(".ptab").forEach(b => b.onclick = () => switchPanelTab(b.dataset.tab));
  $("live-toggle").onclick = () => {
    if (live.on) { stopLive(); return; }
    try { if (window.Notification && Notification.permission === "default") Notification.requestPermission(); } catch (e) { }
    startLive();
  };
  $("live-interval").onchange = () => { if (live.on) { stopLive(); startLive(); } };
  $("wl-add-btn").onclick = () => addWatch($("wl-input").value);
  $("wl-input").onkeydown = e => { if (e.key === "Enter") addWatch($("wl-input").value); };
  $("event-refresh").onclick = () => pollEvent(true);
  const pe = $("event-payout");
  if (pe) { let t; pe.oninput = () => { clearTimeout(t); t = setTimeout(() => pollEvent(false), 350); }; }
  // 自选表点击用事件委托(行增量更新后不必每行重绑):点 × 移除,点行切焦点
  $("watchlist").onclick = e => {
    const row = e.target.closest(".wl-row"); if (!row) return;
    if (e.target.closest(".wl-x")) removeWatch(row.dataset.sym);
    else focusSymbol(row.dataset.sym);
  };

  const savedThresh = localStorage.getItem("spikeThresh");
  if (savedThresh) $("spike-thresh").value = savedThresh;
  $("spike-thresh").onchange = () => localStorage.setItem("spikeThresh", $("spike-thresh").value);

  setInterval(updateCountdown, 250);   // K线收盘倒计时(每 250ms 刷新显示)

  // 策略面板
  $("strategy").innerHTML = state.meta.strategies
    .map(s => `<option value="${s.name}">${s.label}</option>`).join("");
  $("strategy").value = "trend_filter";
  renderParamBox();
  $("strategy").onchange = () => { renderParamBox(); runBacktest(); };
  $("run-bt").onclick = runBacktest;
  $("robust-btn").onclick = runRobustness;

  $("r-cap").value = state.meta.capital;
  const r = state.meta.risk;
  $("r-sl").value = r.stop_loss; $("r-tp").value = r.take_profit;
  $("r-ps").value = r.position_size; $("r-dd").value = r.max_drawdown_stop;

  await loadKlines();
  syncPanes();        // 按配置打开副图面板
  refreshIndicators();
  runBacktest();      // 打开页面自动跑一次,立刻能看到买卖点
}

init();
