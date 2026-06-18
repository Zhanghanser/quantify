/* ============================================================
 * 国内大宗商品期权 · 期权链视图(自包含模块,不依赖 app.js 内部状态)
 * 数据接口:/api/options/products | /contracts | /chain | /klines
 * 只读展示真实行情,绝不下单。
 * ============================================================ */
(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  // 跟随项目默认习惯:红涨绿跌(--up 红 / --down 绿)
  const UP = "#f6465d", DOWN = "#2ebd85", GOLD = "#f0b90b", GRAY = "#848e9c";
  const RED = "#f6465d";

  let inited = false;
  let groups = [];                 // [{exchange: label, products:[{name,product,exchange}]}]
  let curProduct = null, curContract = null;
  let chart = null, candleSeries = null, curCode = null;
  let curChainData = null;         // 最近一次期权链(含每格 iv/希腊字母),供点击查希腊字母

  /* ---------- 工具 ---------- */
  async function jget(url) {
    const r = await fetch(url);
    if (!r.ok) {
      let msg = "HTTP " + r.status;
      try { msg = (await r.json()).detail || msg; } catch (e) {}
      throw new Error(msg);
    }
    return r.json();
  }
  function status(t, isErr) {
    const el = $("opt-status");
    if (!el) return;
    el.textContent = t || "";
    el.style.color = isErr ? RED : GRAY;
  }
  const numf = (v, d = 2) => (v == null || isNaN(v)) ? "—" : Number(v).toFixed(d);
  const intf = (v) => (v == null || isNaN(v)) ? "—" : Math.round(v).toLocaleString();
  // IV 显示成百分比(0.138 → 13.8%)
  const ivf = (v) => (v == null || isNaN(v)) ? "—" : (Number(v) * 100).toFixed(1) + "%";
  // 希腊字母数值(自定义小数位)
  const gf = (v, d = 3) => (v == null || isNaN(v)) ? "—" : Number(v).toFixed(d);
  function chgCell(v) {
    if (v == null || isNaN(v)) return `<span class="dim">—</span>`;
    const c = v > 0 ? UP : (v < 0 ? DOWN : GRAY);
    const s = v > 0 ? "+" : "";
    return `<span style="color:${c}">${s}${Number(v).toFixed(2)}%</span>`;
  }

  /* ---------- 显示 / 隐藏整页 ---------- */
  async function show() {
    $("options-view").classList.remove("hidden");
    document.body.style.overflow = "hidden";
    if (!inited) {
      inited = true;
      try { await loadProducts(); } catch (e) { status("加载品种失败:" + e.message, true); }
    } else if (chart) {
      chart.timeScale().fitContent();
    }
  }
  function hide() {
    $("options-view").classList.add("hidden");
    document.body.style.overflow = "";
  }

  /* ---------- 品种 / 合约 级联 ---------- */
  async function loadProducts() {
    status("加载品种…");
    const d = await jget("/api/options/products");
    groups = d.groups || [];
    const exSel = $("opt-exchange");
    exSel.innerHTML = groups.map((g, i) => `<option value="${i}">${g.exchange}</option>`).join("");
    fillProducts(0);
    status(`新浪免费数据共 ${d.count} 个品种`);
  }
  function fillProducts(exIdx) {
    const g = groups[exIdx];
    const pSel = $("opt-product");
    pSel.innerHTML = (g.products || []).map(p => `<option value="${p.name}">${p.name}</option>`).join("");
    if (g.products && g.products.length) loadContracts(g.products[0].name);
  }
  async function loadContracts(product) {
    curProduct = product;
    status("加载合约月份…");
    $("opt-chain-body").innerHTML = "";
    const d = await jget("/api/options/contracts?product=" + encodeURIComponent(product));
    const cSel = $("opt-contract");
    const months = d.contracts || [];
    cSel.innerHTML = months.map(m => `<option value="${m}">${m}</option>`).join("");
    if (months.length) loadChain(product, months[0]);
    else { status("该品种暂无在交易合约", true); }
  }
  async function loadChain(product, contract) {
    curProduct = product; curContract = contract;
    status("加载期权链…");
    const body = $("opt-chain-body");
    body.innerHTML = `<tr><td colspan="13" class="opt-loading">加载中…</td></tr>`;
    try {
      const d = await jget(`/api/options/chain?product=${encodeURIComponent(product)}&contract=${encodeURIComponent(contract)}`);
      curChainData = d;
      renderChain(d);
      renderAnalytics(d);
      status(`${product} ${contract} · ${d.rows.length} 个行权价 · ATM≈${numf(d.atm_strike, 0)}`);
    } catch (e) {
      body.innerHTML = `<tr><td colspan="13" class="opt-loading" style="color:${RED}">加载失败:${e.message}</td></tr>`;
      status("加载期权链失败:" + e.message, true);
    }
  }

  /* ---------- 顶部:波动率 / 情绪汇总条 ---------- */
  function renderAnalytics(d) {
    const el = $("opt-analytics");
    if (!el) return;
    const a = d.analytics || {};
    if (a.error) { el.innerHTML = `<span class="opt-an-err">⚠️ ${a.error}</span>`; return; }
    const pcr = a.pcr_oi;
    // PCR(看跌/看涨持仓比):>1 看跌持仓更重(情绪偏空/避险),<1 偏多
    const pcrTag = (pcr == null) ? "" :
      (pcr > 1 ? `<span style="color:${DOWN}">偏空</span>`
               : `<span style="color:${UP}">偏多</span>`);
    const cell = (label, val, extra) =>
      `<div class="opt-an-cell"><span class="opt-an-k">${label}</span>` +
      `<span class="opt-an-v">${val}${extra ? " " + extra : ""}</span></div>`;
    el.innerHTML =
      cell("标的期货 F(估)", numf(a.forward, 0)) +
      cell("到期", `${a.expiry || "—"}`, a.T_days != null ? `· 剩${a.T_days}天` : "") +
      cell("平值 IV", ivf(a.atm_iv)) +
      cell("PCR(持仓)", numf(pcr, 3), pcrTag) +
      `<div class="opt-an-cell opt-an-note">IV/希腊字母为 Black-76 估算</div>`;
  }

  /* ---------- 渲染 T 型期权链 ---------- */
  function renderChain(d) {
    const atm = d.atm_strike;
    const body = $("opt-chain-body");
    body.innerHTML = (d.rows || []).map(r => {
      const c = r.call, p = r.put;
      const isATM = (atm != null && r.strike === atm);
      const ccode = c.code || "", pcode = p.code || "";
      // 看涨侧整体可点(看它K线);看跌侧同理
      const callAttr = ccode ? `data-code="${ccode}" class="opt-clk"` : "";
      const putAttr = pcode ? `data-code="${pcode}" class="opt-clk"` : "";
      return `<tr class="${isATM ? "opt-atm" : ""}">
        <td ${callAttr}>${intf(c.oi)}</td>
        <td ${callAttr}>${numf(c.bid)}</td>
        <td ${callAttr} class="opt-last call">${numf(c.last)}</td>
        <td ${callAttr}>${numf(c.ask)}</td>
        <td ${callAttr}>${chgCell(c.chg)}</td>
        <td ${callAttr} class="opt-iv">${ivf(c.iv)}</td>
        <td class="opt-strike-col">${numf(r.strike, 0)}</td>
        <td ${putAttr} class="opt-iv">${ivf(p.iv)}</td>
        <td ${putAttr}>${chgCell(p.chg)}</td>
        <td ${putAttr}>${numf(p.bid)}</td>
        <td ${putAttr} class="opt-last put">${numf(p.last)}</td>
        <td ${putAttr}>${numf(p.ask)}</td>
        <td ${putAttr}>${intf(p.oi)}</td>
      </tr>`;
    }).join("");
    // 滚动到 ATM 附近
    const atmRow = body.querySelector(".opt-atm");
    if (atmRow) atmRow.scrollIntoView({ block: "center" });
  }

  /* ---------- 单合约历史K线 ---------- */
  function ensureChart() {
    if (chart) return;
    chart = LightweightCharts.createChart($("opt-kline"), {
      autoSize: true,
      layout: { background: { type: "solid", color: "transparent" }, textColor: GRAY, fontSize: 11 },
      grid: { vertLines: { color: "#1c2127" }, horzLines: { color: "#1c2127" } },
      crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
      timeScale: { borderColor: "#2b3139", timeVisible: false, rightOffset: 4 },
      rightPriceScale: { borderColor: "#2b3139" },
    });
    candleSeries = chart.addCandlestickSeries({
      upColor: UP, downColor: DOWN, borderUpColor: UP, borderDownColor: DOWN,
      wickUpColor: UP, wickDownColor: DOWN,
    });
  }
  async function loadKline(code) {
    if (!code || code === curCode) return;
    curCode = code;
    const side = code.includes("C") && code.lastIndexOf("C") > code.search(/\d/) ? "看涨 CALL" : "看跌 PUT";
    $("opt-kline-title").textContent = `📈 ${code}  历史日K`;
    $("opt-kline-meta").textContent = "加载中…";
    ensureChart();
    try {
      const d = await jget(`/api/options/klines?code=${encodeURIComponent(code)}&limit=250`);
      candleSeries.setData(d.candles);
      chart.timeScale().fitContent();
      const n = d.candles.length;
      const last = n ? d.candles[n - 1].close : null;
      $("opt-kline-meta").textContent = `${code} · ${n} 根日线 · 最新权利金 ${numf(last)}`;
    } catch (e) {
      $("opt-kline-meta").textContent = "加载失败:" + e.message;
    }
  }

  /* ---------- 点合约 → 显示该合约希腊字母 ---------- */
  function renderGreeks(code) {
    const box = $("opt-greeks");
    if (!box) return;
    if (!curChainData || !code) { box.innerHTML = ""; return; }
    let f = null;
    for (const r of (curChainData.rows || [])) {
      if (r.call && r.call.code === code) { f = { s: r.call, strike: r.strike, cp: "看涨 CALL", cls: "call" }; break; }
      if (r.put && r.put.code === code) { f = { s: r.put, strike: r.strike, cp: "看跌 PUT", cls: "put" }; break; }
    }
    if (!f) { box.innerHTML = ""; return; }
    const s = f.s;
    const item = (k, v, tip) =>
      `<div class="opt-gk" title="${tip || ""}"><span class="opt-gk-k">${k}</span><span class="opt-gk-v">${v}</span></div>`;
    box.innerHTML =
      `<div class="opt-gk-head"><b class="${f.cls}">${f.cp}</b> · 行权价 ${numf(f.strike, 0)}</div>` +
      `<div class="opt-gk-grid">` +
      item("IV", ivf(s.iv), "隐含波动率(由市价用 Black-76 反解)") +
      item("Delta", gf(s.delta, 3), "标的期货每涨 1 元,权利金大约变化(元)") +
      item("Gamma", gf(s.gamma, 4), "标的每涨 1 元,Delta 的变化") +
      item("Theta", gf(s.theta, 3), "每过 1 天,权利金的时间损耗(通常为负)") +
      item("Vega", gf(s.vega, 3), "波动率每 +1%,权利金大约变化(元)") +
      `</div>`;
  }

  /* ---------- 事件绑定 ---------- */
  function bind() {
    const openBtn = $("opt-open");
    if (openBtn) openBtn.addEventListener("click", show);
    $("opt-close").addEventListener("click", hide);
    $("opt-refresh").addEventListener("click", () => {
      if (curProduct && curContract) loadChain(curProduct, curContract);
    });
    $("opt-exchange").addEventListener("change", (e) => fillProducts(Number(e.target.value)));
    $("opt-product").addEventListener("change", (e) => loadContracts(e.target.value));
    $("opt-contract").addEventListener("change", (e) => {
      if (curProduct) loadChain(curProduct, e.target.value);
    });
    // 期权链点击 → 看该合约K线(事件委托)
    $("opt-chain-body").addEventListener("click", (e) => {
      const td = e.target.closest("td.opt-clk, td [data-code]") || e.target.closest("td");
      if (!td) return;
      const code = td.getAttribute("data-code");
      if (code) { renderGreeks(code); loadKline(code); }
    });
    // Esc 关闭
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && !$("options-view").classList.contains("hidden")) hide();
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bind);
  } else {
    bind();
  }
})();
