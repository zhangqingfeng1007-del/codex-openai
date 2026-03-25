"""产品评分引擎 — 7维度评分，输出 Top3 产品推荐

评分维度（满分100分，权重在 SCORING_WEIGHTS 中统一配置）：
  age_fit        20分  用户年龄在投保范围内=满分，范围外直接过滤
  budget_match   20分  实际保费/用户预算 比值决定得分
  coverage       15分  重疾病种数 + 轻/中症加分
  value_score    20分  实际保费 / 精算公允保费（调用 Java 精算服务）
  waiting_period 10分  等待期天数越短越高
  sale_status     8分  在售>停售预告>已停售
  preference      7分  用户指定>主流公司>其他

降级策略：
  精算服务不可用（SERVICE_UNAVAILABLE）→ value_score=0，20分权重转移至 coverage
  精算服务无配置（NOT_CONFIGURED）     → 同上，并在 pricing_status 字段标注
  精算服务计算失败（CALC_ERROR）        → 同上
  超出承保年龄                          → 直接过滤，不参与评分
"""

import os
import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

JAVA_SERVICE_URL = os.getenv("JAVA_SERVICE_URL", "http://actuarial:8080")

# ── 评分权重配置（后台调整此处即可，不需要改逻辑函数） ──────────────────────────
SCORING_WEIGHTS = {
    "age_fit":        20,   # 年龄适配（过滤维度，0或满分）
    "budget_match":   20,   # 预算匹配
    "coverage":       15,   # 保障完整性（精算不可用时最高扩展至35）
    "value_score":    20,   # 精算性价比
    "waiting_period": 10,   # 等待期
    "sale_status":     8,   # 在售状态
    "preference":      7,   # 公司偏好
}

# 精算服务错误码
PRICING_OK               = "OK"
PRICING_SERVICE_UNAVAIL  = "SERVICE_UNAVAILABLE"
PRICING_NOT_CONFIGURED   = "NOT_CONFIGURED"
PRICING_CALC_ERROR       = "CALC_ERROR"

MAJOR_COMPANIES = {
    "国寿", "平安", "太平洋", "新华", "泰康", "太平", "友邦",
    "人保", "中信保诚", "招商信诺", "阳光", "中国人寿", "中国平安",
    "中国太平", "中国太保",
}


async def get_fair_premium(product_id: str, age: int, gender: str) -> tuple[float, str]:
    """
    调用 Java 精算服务获取 50万保额基准公允年保费。

    返回 (fair_premium, error_code)：
      (保费值, PRICING_OK)               — 成功
      (0.0, PRICING_NOT_CONFIGURED)      — 产品未配置精算参数（404）
      (0.0, PRICING_CALC_ERROR)          — 服务返回计算错误（5xx）
      (0.0, PRICING_SERVICE_UNAVAIL)     — 服务不可达/超时

    调用方应根据 error_code 决定是否降级，不得在无配置时编造保费。
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(
                f"{JAVA_SERVICE_URL}/api/v1/actuarial/fair-price",
                params={"productId": product_id, "age": age, "gender": gender},
            )
            if r.status_code == 200:
                data = r.json()
                return (float(data.get("fairPremium") or 0), PRICING_OK)
            elif r.status_code == 404:
                logger.info("精算配置不存在 product_id=%s", product_id)
                return (0.0, PRICING_NOT_CONFIGURED)
            else:
                logger.warning("精算服务返回异常 product_id=%s status=%d", product_id, r.status_code)
                return (0.0, PRICING_CALC_ERROR)
    except Exception as e:
        logger.debug("精算服务不可达 product_id=%s: %s", product_id, e)
        return (0.0, PRICING_SERVICE_UNAVAIL)


def _score_age(age: int, min_age: int, max_age: int) -> float:
    """年龄是否在投保范围内；范围外返回0（直接过滤）"""
    return float(SCORING_WEIGHTS["age_fit"]) if min_age <= age <= max_age else 0.0


def _score_budget(annual_premium: float, budget: float) -> float:
    """预算匹配（SCORING_WEIGHTS["budget_match"] 分）"""
    w = SCORING_WEIGHTS["budget_match"]
    if budget <= 0 or annual_premium <= 0:
        return round(w * 0.5, 1)   # 无保费数据给中间分
    ratio = annual_premium / budget
    if ratio <= 0.2:
        return round(w * 0.6, 1)   # 太便宜，保额可能不足
    elif ratio <= 0.8:
        return float(w)             # 最佳区间
    elif ratio <= 1.0:
        return round(w * 0.7, 1)
    elif ratio <= 1.2:
        return round(w * 0.3, 1)
    else:
        return 0.0                  # 超出预算


def _score_coverage(disease_counts: dict, has_minor_ci: bool, has_moderate_ci: bool) -> float:
    """保障完整性（SCORING_WEIGHTS["coverage"] 分，精算不可用时最高扩展至35）"""
    w = SCORING_WEIGHTS["coverage"]
    major = disease_counts.get("重大疾病", 0) or disease_counts.get("重疾", 0)
    score = min(major / 120 * (w - 2), float(w - 2))
    if has_minor_ci:
        score += 1.0
    if has_moderate_ci:
        score += 1.0
    return round(score, 1)


def _score_value(
    annual_premium: float,
    fair_premium: float,
    error_code: str,
) -> tuple[float, Optional[float], str]:
    """
    性价比（SCORING_WEIGHTS["value_score"] 分）。

    返回 (score, value_ratio, pricing_status)。
    fair_premium 为 0 或 error_code != OK 时：score=0, value_ratio=None，
    需由调用方将权重转移至 coverage。
    """
    if error_code != PRICING_OK or fair_premium <= 0 or annual_premium <= 0:
        return (0.0, None, error_code)
    ratio = annual_premium / fair_premium
    w = SCORING_WEIGHTS["value_score"]
    if ratio <= 0.90:
        score = float(w)
    elif ratio <= 1.00:
        score = round(w - (ratio - 0.90) / 0.10 * (w * 0.4), 1)
    elif ratio <= 1.20:
        score = round(max(0.0, w * 0.6 - (ratio - 1.00) / 0.20 * (w * 0.6)), 1)
    else:
        score = 0.0
    return (score, round(ratio, 3), PRICING_OK)


def _score_waiting(waiting_days: int) -> float:
    """等待期（SCORING_WEIGHTS["waiting_period"] 分）"""
    w = SCORING_WEIGHTS["waiting_period"]
    if waiting_days <= 90:
        return float(w)
    elif waiting_days <= 180:
        return round(w * 0.6, 1)
    else:
        return round(w * 0.2, 1)


def _score_status(sale_status: str) -> float:
    """在售状态（SCORING_WEIGHTS["sale_status"] 分）"""
    w = SCORING_WEIGHTS["sale_status"]
    return {"Y": float(w), "P": round(w * 0.6, 1), "N": 0.0}.get(sale_status, 0.0)


def _score_preference(company_name: str, preferred_company: str) -> float:
    """公司偏好（SCORING_WEIGHTS["preference"] 分）"""
    w = SCORING_WEIGHTS["preference"]
    if preferred_company and preferred_company in company_name:
        return float(w)
    for major in MAJOR_COMPANIES:
        if major in company_name:
            return round(w * 6 / 7, 1)
    return round(w * 5 / 7, 1)


async def score_products(products: list[dict], needs: dict) -> list[dict]:
    """
    对产品列表打分，返回按总分降序的 Top3。

    products: fetch_products_for_scoring() 的返回值
    needs:    generate_needs_report 工具参数，含 age, gender, budget_annual,
              annual_income, preferred_company 等字段

    每条结果包含：
      total_score       总分（100分制）
      score_breakdown   各维度得分明细
      value_ratio       实际保费/公允保费（pricing_status=OK 时有效）
      pricing_status    精算服务状态码（OK/NOT_CONFIGURED/SERVICE_UNAVAILABLE/CALC_ERROR）
      fair_premium      精算公允保费（0 = 不可用）
    """
    age = int(needs.get("age") or 35)
    gender = needs.get("gender") or "male"
    annual_income = int(needs.get("annual_income") or 0)
    budget = int(needs.get("budget_annual") or 0) or (annual_income * 7 // 100) or 8000
    preferred_company = needs.get("preferred_company") or ""

    scored = []
    for p in products:
        pid = p["product_id"]
        min_age = p.get("min_age", 0)
        max_age = p.get("max_age", 999)
        annual_premium = p.get("annual_premium", 0.0)

        breakdown: dict[str, float] = {}

        # 1. 年龄适配（过滤维度：不在投保范围直接跳过，不进入结果）
        breakdown["age_fit"] = _score_age(age, min_age, max_age)
        if breakdown["age_fit"] == 0:
            logger.debug("产品 %s 年龄 %d 超出投保范围 [%d,%d]，跳过", pid, age, min_age, max_age)
            continue

        # 2. 预算匹配
        breakdown["budget_match"] = _score_budget(annual_premium, budget)

        # 3. 保障完整性（初始值，可能被精算降级加成）
        breakdown["coverage"] = _score_coverage(
            p.get("disease_counts", {}),
            p.get("has_minor_ci", False),
            p.get("has_moderate_ci", False),
        )

        # 4. 性价比（精算） — 异步调用 Java 精算服务，显式处理错误状态
        fair_premium, pricing_error = await get_fair_premium(pid, age, gender)
        value_score, value_ratio, pricing_status = _score_value(annual_premium, fair_premium, pricing_error)
        breakdown["value_score"] = value_score

        if pricing_status != PRICING_OK:
            # 精算不可用：将 value_score 权重（20分）转移至 coverage，不得编造保费
            max_coverage = SCORING_WEIGHTS["coverage"] + SCORING_WEIGHTS["value_score"]
            breakdown["coverage"] = min(breakdown["coverage"] + SCORING_WEIGHTS["value_score"], float(max_coverage))
            logger.info("产品 %s 精算不可用（%s），权重转移至 coverage", pid, pricing_status)

        # 5. 等待期
        breakdown["waiting_period"] = _score_waiting(p.get("waiting_period", 180))

        # 6. 在售状态
        breakdown["sale_status"] = _score_status(p.get("sale_status", "N"))

        # 7. 公司偏好
        breakdown["preference"] = _score_preference(p.get("company_name", ""), preferred_company)

        # value_ratio 不计入总分，单独存储
        total = sum(v for k, v in breakdown.items())
        scored.append({
            **p,
            "total_score":     round(total, 1),
            "score_breakdown": breakdown,
            "value_ratio":     value_ratio,       # None = 精算不可用
            "pricing_status":  pricing_status,    # 供前端展示说明
            "fair_premium":    fair_premium,
        })

    return sorted(scored, key=lambda x: x["total_score"], reverse=True)[:3]
