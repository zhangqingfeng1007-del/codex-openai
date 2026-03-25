"""需求分析报告存取服务 — 读写 insurance_need_reports 表"""

import os
import json
import logging
from datetime import date
from typing import Optional

logger = logging.getLogger(__name__)


def _get_aix_conn_params() -> dict:
    return {
        "host":     os.getenv("MYSQL_HOST", "localhost"),
        "port":     int(os.getenv("MYSQL_PORT", "3306")),
        "user":     os.getenv("MYSQL_USER", "aix"),
        "password": os.getenv("MYSQL_PASSWORD", "aix_secret"),
        "db":       os.getenv("MYSQL_DATABASE", "aix_engine"),
        "charset":  "utf8mb4",
        "autocommit": True,
        "connect_timeout": 5,
    }


def _calc_age(birth_date: Optional[str]) -> Optional[int]:
    """从 YYYY-MM 格式出生年月推算当前年龄"""
    if not birth_date:
        return None
    try:
        year, month = int(birth_date[:4]), int(birth_date[5:7])
        today = date.today()
        age = today.year - year - (1 if (today.month, today.day) < (month, 1) else 0)
        return age
    except Exception:
        return None


async def save_needs_report(profile_id: str, report: dict) -> str:
    """
    保存需求分析报告到数据库，返回新记录的 id。
    report 为 generate_needs_report 工具参数 dict。
    """
    import aiomysql

    birth_date = report.get("birth_date")
    age = report.get("age") or _calc_age(birth_date)

    params = _get_aix_conn_params()
    try:
        conn = await aiomysql.connect(**params)
    except Exception as e:
        logger.warning(f"save_needs_report: 无法连接数据库: {e}")
        return "anonymous"

    try:
        async with conn.cursor() as cur:
            await cur.execute("""
                INSERT INTO insurance_need_reports
                  (profile_id, birth_date, age, gender, annual_income, budget_annual,
                   family_structure, health_status, existing_coverage,
                   primary_concern, preferred_company, report_json)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (
                profile_id,
                birth_date,
                age,
                report.get("gender"),
                report.get("annual_income"),
                report.get("budget_annual"),
                report.get("family_structure"),
                report.get("health_status"),
                report.get("existing_coverage"),
                report.get("primary_concern"),
                report.get("preferred_company"),
                json.dumps(report, ensure_ascii=False),
            ))
            await cur.execute("SELECT LAST_INSERT_ID()")  # UUID 需单独查
            # 由于主键是 UUID()，用 lastrowid 无法获取，改为查最新记录
            await cur.execute(
                "SELECT id FROM insurance_need_reports WHERE profile_id=%s ORDER BY created_at DESC LIMIT 1",
                (profile_id,)
            )
            row = await cur.fetchone()
            return row[0] if row else "unknown"
    except Exception as e:
        logger.warning(f"save_needs_report: 写入失败: {e}")
        return "anonymous"
    finally:
        conn.close()


async def update_report_recommendations(report_id: str, top3: list[dict]) -> None:
    """将 Top3 评分结果回写到报告记录"""
    if report_id in ("anonymous", "unknown"):
        return
    import aiomysql

    params = _get_aix_conn_params()
    try:
        conn = await aiomysql.connect(**params)
    except Exception as e:
        logger.warning(f"update_report_recommendations: 无法连接数据库: {e}")
        return

    try:
        async with conn.cursor() as cur:
            await cur.execute(
                "UPDATE insurance_need_reports SET recommended_products=%s WHERE id=%s",
                (json.dumps(top3, ensure_ascii=False), report_id)
            )
    except Exception as e:
        logger.warning(f"update_report_recommendations: 更新失败: {e}")
    finally:
        conn.close()


async def load_latest_report(profile_id: str) -> Optional[dict]:
    """读取指定客户的最新需求报告，不存在时返回 None"""
    import aiomysql

    params = _get_aix_conn_params()
    try:
        conn = await aiomysql.connect(**params)
    except Exception as e:
        logger.warning(f"load_latest_report: 无法连接数据库: {e}")
        return None

    try:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT * FROM insurance_need_reports WHERE profile_id=%s ORDER BY created_at DESC LIMIT 1",
                (profile_id,)
            )
            return await cur.fetchone()
    except Exception as e:
        logger.warning(f"load_latest_report: 查询失败: {e}")
        return None
    finally:
        conn.close()


def _normalize_family_structure(raw: Optional[str]) -> str:
    """
    将 AI 生成的自然语言家庭结构归一到标准分类，再套预算公式。
    不依赖原始字符串直接匹配，避免措辞差异导致分支跳错。
    """
    s = (raw or "").lower()
    has_child = any(k in s for k in ("孩", "子女", "child", "kids", "宝宝", "儿子", "女儿"))
    is_married = any(k in s for k in ("婚", "married", "配偶", "老公", "老婆", "丈夫", "妻子"))
    is_single = any(k in s for k in ("单身", "single", "未婚", "离婚", "丧偶"))

    if has_child:
        return "married_with_child"
    if is_married:
        return "married_no_child"
    if is_single:
        return "single"
    return "other"


def _calc_budget_estimated(annual_income: int, annual_expense: int,
                            normalized_fs: str) -> int:
    """
    预算测算公式（参考2018年精算验证版，已适配当前一期需求分析链路）。

    触发时机：budget_mode == "estimated" 且 annual_income 已知。
    normalized_fs 必须先经过 _normalize_family_structure() 归一化。

    单身：          max(年收入×15%, (年收入-年支出)×40%)
    已婚无孩：      max(年收入×7.5%, (年收入-年支出)×20%)
    已婚有孩/其他：  max(年收入×5%,  (年收入-年支出)×17%)
    """
    surplus = max(annual_income - annual_expense, 0)
    if normalized_fs == "single":
        return max(int(annual_income * 0.15), int(surplus * 0.40))
    if normalized_fs == "married_no_child":
        return max(int(annual_income * 0.075), int(surplus * 0.20))
    # married_with_child / other
    return max(int(annual_income * 0.05), int(surplus * 0.17))


def _calc_recommended_sum_assured(annual_income: int,
                                   family_annual_income: Optional[int]) -> int:
    """
    推荐保额公式：min(500万, max(年收入×10, 家庭年收入×5))
    family_annual_income 须在 generate_needs_report schema 中正式定义；
    未传入时退化为 年收入×10，下限50万。
    """
    base = annual_income * 10
    if family_annual_income and family_annual_income > annual_income:
        base = max(base, family_annual_income * 5)
    return max(min(base, 5_000_000), 500_000)


def build_report_summary(report: dict) -> dict:
    """构建前端展示用的摘要（供 SSE needs_report 事件使用）"""
    age = report.get("age")
    birth_date = report.get("birth_date")
    if not age and birth_date:
        age = _calc_age(birth_date)

    budget_mode = report.get("budget_mode")
    budget = report.get("budget_annual")
    annual_income = report.get("annual_income")
    annual_expense = report.get("annual_expense") or 0
    family_structure = report.get("family_structure")

    # 预算处理：user_stated 不覆盖，estimated 或无预算时后台测算
    if budget_mode == "user_stated":
        pass  # 保留用户原始预算，不做任何覆盖
    elif annual_income:
        normalized_fs = _normalize_family_structure(family_structure)
        budget = _calc_budget_estimated(annual_income, annual_expense, normalized_fs)
        budget_mode = "estimated"

    # 推荐保额（独立字段，不受预算模式影响）
    recommended_sum_assured: Optional[int] = None
    if annual_income:
        family_income = report.get("family_annual_income")  # schema 中已正式定义
        recommended_sum_assured = _calc_recommended_sum_assured(annual_income, family_income)

    summary: dict = {
        "age":              age,
        "gender":           "男" if report.get("gender") == "male" else "女",
        "primary_concern":  report.get("primary_concern", "重大疾病"),
        "family_structure": family_structure,
        "health_status":    report.get("health_status"),
        "budget_annual":    budget,
        "budget_mode":      budget_mode,
    }

    if recommended_sum_assured is not None:
        summary["recommended_sum_assured"] = recommended_sum_assured

    # 仅 estimated 模式才填区间字段
    if budget_mode == "estimated":
        if report.get("budget_annual_estimated_min"):
            summary["budget_annual_estimated_min"] = report["budget_annual_estimated_min"]
        if report.get("budget_annual_estimated_max"):
            summary["budget_annual_estimated_max"] = report["budget_annual_estimated_max"]
        if report.get("budget_annual_recommended"):
            summary["budget_annual_recommended"] = report["budget_annual_recommended"]

    return summary
