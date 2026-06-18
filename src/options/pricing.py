# -*- coding: utf-8 -*-
"""
国内大宗商品期权定价 · Black-76 · 纯 math 手写(不装 scipy/QuantLib,保护一键打包 exe)。

为什么用 Black-76 而不是 Black-Scholes:
  国内商品期权的【标的是期货合约】(不是现货)。Fischer Black(1976)把 BSM 里的现价 S
  换成期货价 F,并整体乘贴现因子 e^{-rT}。国内商品期权是【美式】(可提前行权),这里先用
  【欧式 Black-76 近似】——对看盘/教学足够;精确美式(CRR 二叉树)留作后续可选。
  所有结果都明确标注"近似",且只算给人看,绝不下单。

本模块对外:
  price(cp,F,K,T,r,sigma)        理论权利金
  greeks(cp,F,K,T,r,sigma)       delta/gamma/vega(每+1%)/theta(每日)/rho(每+1%)
  implied_vol(cp,price,F,K,T,r)  二分法反解隐含波动率(无解→None)
  enrich_chain(data,exchange)    给 quote_table 的期权链补 IV/希腊字母 + 标的F/到期T + PCR 情绪
"""

import math
from datetime import date, timedelta

# 无风险利率(年化):国内可近似 2%;只用于贴现/希腊字母,对结果影响很小。
R_DEFAULT = 0.02
_SQRT_2PI = math.sqrt(2.0 * math.pi)


# ----------------------------- 正态分布(math.erf,无需 scipy)-----------------------------
def _norm_cdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_pdf(x):
    return math.exp(-0.5 * x * x) / _SQRT_2PI


def _d1_d2(F, K, T, sigma):
    """退化情形(到期/零波动/非正价)返回 (None, None),由调用方兜底。"""
    if F <= 0 or K <= 0 or T <= 0 or sigma <= 0:
        return None, None
    vt = sigma * math.sqrt(T)
    d1 = (math.log(F / K) + 0.5 * sigma * sigma * T) / vt
    return d1, d1 - vt


# ----------------------------- 定价 / 希腊字母 -----------------------------
def price(cp, F, K, T, r, sigma):
    """Black-76 理论价。cp='C'(看涨)/'P'(看跌)。"""
    disc = math.exp(-r * T)
    d1, d2 = _d1_d2(F, K, T, sigma)
    if d1 is None:                       # 已到期/零波动 → 贴现内在价值
        intrinsic = max(F - K, 0.0) if cp == "C" else max(K - F, 0.0)
        return disc * intrinsic
    if cp == "C":
        return disc * (F * _norm_cdf(d1) - K * _norm_cdf(d2))
    return disc * (K * _norm_cdf(-d2) - F * _norm_cdf(-d1))


def greeks(cp, F, K, T, r, sigma):
    """返回 dict。口径按看盘习惯:
       delta 对期货价 F 的一阶;gamma 二阶;
       vega  = 波动率每 +1%(0.01)的权利金变化;
       theta = 每过 1 个日历日的权利金变化(年化 theta / 365,通常为负);
       rho   = 利率每 +1%(0.01)的权利金变化。
    """
    out = {"delta": None, "gamma": None, "vega": None, "theta": None, "rho": None}
    d1, d2 = _d1_d2(F, K, T, sigma)
    if d1 is None:
        return out
    disc = math.exp(-r * T)
    sqrtT = math.sqrt(T)
    pdf = _norm_pdf(d1)
    px = price(cp, F, K, T, r, sigma)
    out["delta"] = disc * _norm_cdf(d1) if cp == "C" else -disc * _norm_cdf(-d1)
    out["gamma"] = disc * pdf / (F * sigma * sqrtT)
    out["vega"] = disc * F * pdf * sqrtT * 0.01           # 每 +1% 波动率
    theta_year = r * px - disc * F * pdf * sigma / (2.0 * sqrtT)
    out["theta"] = theta_year / 365.0                     # 每个日历日
    out["rho"] = -T * px * 0.01                           # 每 +1% 利率
    return out


def implied_vol(cp, market_price, F, K, T, r, lo=1e-4, hi=5.0, tol=1e-6, max_iter=100):
    """二分法反解隐含波动率(价格对 sigma 单调递增,稳健)。
       报价低于贴现内在价值 / 区间内无根(波动率>500%等极端)→ None。"""
    if market_price is None or market_price <= 0 or F <= 0 or K <= 0 or T <= 0:
        return None
    disc = math.exp(-r * T)
    intrinsic = disc * (max(F - K, 0.0) if cp == "C" else max(K - F, 0.0))
    if market_price < intrinsic - 1e-9:
        return None
    f_lo = price(cp, F, K, T, r, lo) - market_price
    f_hi = price(cp, F, K, T, r, hi) - market_price
    if (f_lo < 0) == (f_hi < 0):         # 同号 → 无根
        return None
    for _ in range(max_iter):
        mid = 0.5 * (lo + hi)
        fm = price(cp, F, K, T, r, mid) - market_price
        if abs(fm) < tol:
            return mid
        if (f_lo < 0) == (fm < 0):
            lo, f_lo = mid, fm
        else:
            hi = mid
    return 0.5 * (lo + hi)


# ----------------------------- 合约 → 到期日(近似)-----------------------------
def parse_contract(contract):
    """合约月份代码 → (交割年, 交割月)。
       'm2609'→(2026,9)(大商所4位:2位年+2位月);'SR609'→(2026,9)(郑商所3位:1位年+2位月)。
       失败 → (None, None)。"""
    digits = "".join(ch for ch in str(contract) if ch.isdigit())
    today = date.today()
    if len(digits) >= 4:
        year, mm = 2000 + int(digits[-4:-2]), int(digits[-2:])
    elif len(digits) == 3:
        y1, mm = int(digits[0]), int(digits[1:])
        year = (today.year // 10) * 10 + y1          # 按当前十年补全
        if year < today.year - 1:                    # 跨十年进位(如 '9'→次个十年)
            year += 10
    else:
        return None, None
    if not (1 <= mm <= 12):
        return None, None
    return year, mm


def _nth_business_day(year, month, n):
    """某年月的第 n 个工作日(忽略法定节假日,做近似)。"""
    d = date(year, month, 1)
    cnt = 0
    while True:
        if d.weekday() < 5:
            cnt += 1
            if cnt == n:
                return d
        d += timedelta(days=1)


def _nth_last_business_day(year, month, n):
    """某年月的倒数第 n 个工作日(忽略法定节假日,做近似)。"""
    d = (date(year, 12, 31) if month == 12
         else date(year, month + 1, 1) - timedelta(days=1))
    cnt = 0
    while True:
        if d.weekday() < 5:
            cnt += 1
            if cnt == n:
                return d
        d -= timedelta(days=1)


def expiry_date(contract, exchange):
    """近似到期日:国内商品期权一般在【标的期货交割月的前一个月】到期。
       大商所/郑商所/广期所偏月初(用第5个交易日近似),上期所/能源中心偏月末
       (用倒数第5个交易日近似)。仅近似——精确到期需逐所规则+节假日表。"""
    year, mm = parse_contract(contract)
    if year is None:
        return None
    ey, em = (year - 1, 12) if mm == 1 else (year, mm - 1)
    if (exchange or "").lower() in ("shfe", "ine"):
        return _nth_last_business_day(ey, em, 5)
    return _nth_business_day(ey, em, 5)


def year_fraction(expiry, today=None):
    """到期剩余年化时间 T;已到期/无效 → None。"""
    if expiry is None:
        return None
    today = today or date.today()
    days = (expiry - today).days
    return days / 365.0 if days > 0 else None


# ----------------------------- 给期权链补 IV / 希腊字母 -----------------------------
def _mid(side):
    """该侧用于反解 IV 的价格:优先买卖中价(更稳),否则最新价;无效 → None。"""
    bid, ask, last = side.get("bid"), side.get("ask"), side.get("last")
    if bid and ask and bid > 0 and ask > 0:
        return 0.5 * (bid + ask)
    return last if (last and last > 0) else None


def forward_from_parity(rows, T, r):
    """用看跌-看涨平价从期权报价反推标的期货价 F(取多行中位数,抗个别异常报价)。
       平价:C - P = e^{-rT}(F - K) ⇒ F = K + (C-P)·e^{rT}。"""
    if not T or T <= 0:
        return None
    grow = math.exp(r * T)
    fs = []
    for row in rows:
        K = row.get("strike")
        c, p = _mid(row["call"]), _mid(row["put"])
        if K and c is not None and p is not None:
            fs.append(K + (c - p) * grow)
    if not fs:
        return None
    fs.sort()
    n = len(fs)
    return fs[n // 2] if n % 2 else 0.5 * (fs[n // 2 - 1] + fs[n // 2])


def enrich_chain(data, exchange, r=R_DEFAULT, today=None):
    """原地给 quote_table(...) 的结果补:
         每格 side 增加 iv/delta/gamma/theta/vega;
         data['analytics'] = {forward, expiry, T_days, r, atm_iv, atm_call_iv,
                              atm_put_iv, pcr_oi, approx}
       依赖:从合约月推近似到期 T、从平价反推标的 F;任一缺失则对应字段为 None。"""
    rows = data.get("rows", [])
    exp = expiry_date(data.get("contract"), exchange)
    T = year_fraction(exp, today)
    F = forward_from_parity(rows, T, r)

    sum_call_oi = sum_put_oi = 0.0
    atm_call_iv = atm_put_iv = None
    best_gap = None

    for row in rows:
        K = row.get("strike")
        for side_key, cp in (("call", "C"), ("put", "P")):
            s = row[side_key]
            sum_call_oi += (s.get("oi") or 0) if side_key == "call" else 0
            sum_put_oi += (s.get("oi") or 0) if side_key == "put" else 0
            iv, g = None, {"delta": None, "gamma": None, "theta": None, "vega": None}
            mp = _mid(s)
            if F and T and K and mp:
                iv = implied_vol(cp, mp, F, K, T, r)
                if iv:
                    gk = greeks(cp, F, K, T, r, iv)
                    g = {k: gk[k] for k in ("delta", "gamma", "theta", "vega")}
            s["iv"] = iv
            s.update(g)
        if F and K is not None and (best_gap is None or abs(K - F) < best_gap):
            best_gap = abs(K - F)
            atm_call_iv = row["call"].get("iv")
            atm_put_iv = row["put"].get("iv")

    ivs = [v for v in (atm_call_iv, atm_put_iv) if v]
    data["analytics"] = {
        "forward": F,
        "expiry": exp.isoformat() if exp else None,
        "T_days": round(T * 365) if T else None,
        "r": r,
        "atm_iv": (sum(ivs) / len(ivs)) if ivs else None,
        "atm_call_iv": atm_call_iv,
        "atm_put_iv": atm_put_iv,
        "pcr_oi": (sum_put_oi / sum_call_oi) if sum_call_oi else None,
        "approx": True,
    }
    return data
