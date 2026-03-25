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


def build_report_summary(report: dict) -> dict:
    """构建前端展示用的摘要（供 SSE needs_report 事件使用）"""
    age = report.get("age")
    birth_date = report.get("birth_date")
    if not age and birth_date:
        age = _calc_age(birth_date)

    budget_mode = report.get("budget_mode")
    budget = report.get("budget_annual")
    annual_income = report.get("annual_income")

    # 兼容旧逻辑：如果AI未填budget_mode但给了annual_income，推算预算
    if not budget and annual_income and not budget_mode:
        budget = int(annual_income * 0.07)
        budget_mode = "estimated"

    summary: dict = {
        "age":              age,
        "gender":           "男" if report.get("gender") == "male" else "女",
        "primary_concern":  report.get("primary_concern", "重大疾病"),
        "family_structure": report.get("family_structure"),
        "health_status":    report.get("health_status"),
        "budget_annual":    budget,
        "budget_mode":      budget_mode,
    }

    # 仅 estimated 模式才填区间字段
    if budget_mode == "estimated":
        if report.get("budget_annual_estimated_min"):
            summary["budget_annual_estimated_min"] = report["budget_annual_estimated_min"]
        if report.get("budget_annual_estimated_max"):
            summary["budget_annual_estimated_max"] = report["budget_annual_estimated_max"]
        if report.get("budget_annual_recommended"):
            summary["budget_annual_recommended"] = report["budget_annual_recommended"]

    return summary
