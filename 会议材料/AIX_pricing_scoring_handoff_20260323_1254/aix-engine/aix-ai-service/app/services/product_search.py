"""重疾险产品数据查询服务 — 从 my_ensure 数据库读取产品信息"""

import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# 模块级缓存，避免每次请求都查数据库
_products_cache: Optional[str] = None
_cache_fail_count: int = 0
_CACHE_FAIL_LIMIT = 3  # 连续失败 3 次后才锁定空缓存，防止单次瞬断锁死


async def fetch_products_text() -> str:
    """
    从 my_ensure 数据库查询重疾险产品信息，格式化为结构化文本。
    结果缓存在模块级变量中。如果数据库连接失败，返回空字符串。
    """
    global _products_cache, _cache_fail_count
    if _products_cache is not None:
        return _products_cache

    try:
        import aiomysql
    except ImportError:
        logger.warning("aiomysql 未安装，跳过产品数据库查询")
        _products_cache = ""
        return ""

    host = os.getenv("MYSQL_HOST", "localhost")
    port = int(os.getenv("MYSQL_PORT", "3306"))
    user = os.getenv("MYSQL_USER", "aix")
    password = os.getenv("MYSQL_PASSWORD", "aix_secret")
    db = os.getenv("PRODUCT_DB_DATABASE", "my_ensure")

    try:
        conn = await aiomysql.connect(
            host=host, port=port, user=user, password=password, db=db,
            charset="utf8mb4", autocommit=True, connect_timeout=5,
        )
    except Exception as e:
        _cache_fail_count += 1
        logger.warning(f"无法连接 my_ensure 数据库（第{_cache_fail_count}次）: {e}")
        if _cache_fail_count >= _CACHE_FAIL_LIMIT:
            _products_cache = ""  # 连续失败才锁定
        return ""

    try:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            # 1. 查询产品基本信息 + 关键条款字段（用条件聚合横向展开）
            # 注意：cmb_product.product_id 是 utf8mb4_general_ci，
            #       cmb_product_coverage.product_id 是 utf8mb4_unicode_ci，
            #       JOIN 时需加 COLLATE 避免排序规则冲突。
            await cur.execute("""
                SELECT
                    p.product_id,
                    p.product_name,
                    p.company_name,
                    p.sale_status,
                    p.long_short_term,
                    p.tag,
                    MAX(CASE WHEN c.coverage_name = '投保年龄'   THEN pc.standard_content END) AS age_range,
                    MAX(CASE WHEN c.coverage_name = '保险期间'   THEN pc.standard_content END) AS insurance_period,
                    MAX(CASE WHEN c.coverage_name = '交费期间'   THEN pc.standard_content END) AS payment_period,
                    MAX(CASE WHEN c.coverage_name = '等待期'     THEN pc.standard_content END) AS waiting_period_detail,
                    MAX(CASE WHEN c.coverage_name = '重疾赔付次数' THEN pc.standard_content END) AS critical_pay_times,
                    MAX(CASE WHEN c.coverage_name = '轻症赔付次数' THEN pc.standard_content END) AS mild_pay_times
                FROM cmb_product p
                LEFT JOIN cmb_product_coverage pc
                    ON p.product_id COLLATE utf8mb4_unicode_ci = pc.product_id AND pc.is_deleted = 0
                LEFT JOIN cmb_coverage c
                    ON pc.coverage_id = c.coverage_id
                    AND c.coverage_name IN (
                        '投保年龄','保险期间','交费期间','等待期','重疾赔付次数','轻症赔付次数'
                    )
                    AND c.is_deleted = 0
                WHERE p.is_deleted = 0
                  AND p.product_status = 'RELEASED'
                GROUP BY p.product_id, p.product_name, p.company_name,
                         p.sale_status, p.long_short_term, p.tag
                ORDER BY p.product_id
                LIMIT 50
            """)
            products = await cur.fetchall()

            # 2. 查询各产品病种数量（按 disease_category 分组）
            await cur.execute("""
                SELECT
                    product_id,
                    disease_category,
                    COUNT(*) AS disease_count
                FROM cmb_product_disease
                GROUP BY product_id, disease_category
            """)
            disease_rows = await cur.fetchall()

    except Exception as e:
        _cache_fail_count += 1
        logger.warning(f"查询 my_ensure 数据库失败（第{_cache_fail_count}次）: {e}")
        conn.close()
        if _cache_fail_count >= _CACHE_FAIL_LIMIT:
            _products_cache = ""
        return ""
    finally:
        conn.close()

    # 整理病种数据
    disease_map: dict[str, dict[str, int]] = {}
    for row in disease_rows:
        pid = str(row["product_id"])
        category = row.get("disease_category") or "其他"
        count = row.get("disease_count", 0)
        if pid not in disease_map:
            disease_map[pid] = {}
        disease_map[pid][category] = count

    # 格式化输出
    if not products:
        _products_cache = ""
        return ""

    lines = ["【重疾险产品数据库】", ""]
    for p in products:
        pid = str(p["product_id"])
        name = p.get("product_name") or "未知产品"
        company = p.get("company_name") or "未知公司"
        on_sale = "在售" if p.get("sale_status") == "Y" else "已停售"
        long_short = p.get("long_short_term")
        term_str = "长期险" if long_short == 1 else ("短期险" if long_short == 0 else "")
        tag = p.get("tag") or ""

        age_range        = p.get("age_range") or ""
        insurance_period = p.get("insurance_period") or ""
        payment_period   = p.get("payment_period") or ""
        waiting_detail   = p.get("waiting_period_detail") or ""
        critical_times   = p.get("critical_pay_times") or ""
        mild_times       = p.get("mild_pay_times") or ""

        disease_info = disease_map.get(pid, {})
        disease_parts = [f"{cat}{cnt}种" for cat, cnt in disease_info.items()]
        disease_str = "、".join(disease_parts) if disease_parts else "病种信息待查"

        lines.append(f"● {name}（{company}）[{on_sale}]")
        meta = "、".join(filter(None, [term_str, tag]))
        if meta:
            lines.append(f"  - 产品特点：{meta}")
        if age_range:
            lines.append(f"  - 投保年龄：{age_range}")
        if insurance_period:
            lines.append(f"  - 保险期间：{insurance_period}")
        if payment_period:
            lines.append(f"  - 交费期间：{payment_period}")
        if waiting_detail:
            lines.append(f"  - 等待期：{waiting_detail}")
        if critical_times:
            lines.append(f"  - 重疾赔付：{critical_times}")
        if mild_times:
            lines.append(f"  - 轻症赔付：{mild_times}")
        lines.append(f"  - 病种覆盖：{disease_str}")
        lines.append("")

    result = "\n".join(lines)
    _products_cache = result
    return result


def clear_cache() -> None:
    """清除产品数据缓存（可在需要刷新时调用）"""
    global _products_cache, _cache_fail_count
    _products_cache = None
    _cache_fail_count = 0


# ---------- 评分专用查询 ----------

def _parse_age_range(text: str) -> tuple[int, int]:
    """从文本解析投保年龄范围，返回 (min_age, max_age)"""
    import re
    if not text:
        return (0, 999)
    nums = re.findall(r'\d+', text)
    if len(nums) >= 2:
        return (int(nums[0]), int(nums[1]))
    if len(nums) == 1:
        return (0, int(nums[0]))
    return (0, 999)


def _parse_waiting_days(text: str) -> int:
    """从等待期文本解析天数，返回整数天数，默认 180"""
    import re
    if not text:
        return 180
    m = re.search(r'(\d+)\s*天', text)
    if m:
        return int(m.group(1))
    m = re.search(r'(\d+)\s*日', text)
    if m:
        return int(m.group(1))
    m = re.search(r'(\d+)\s*个月', text)
    if m:
        return int(m.group(1)) * 30
    m = re.search(r'(\d+)\s*月', text)
    if m:
        return int(m.group(1)) * 30
    return 180


async def fetch_products_for_scoring(age: int, gender: str,
                                     budget_annual: int = 8000,
                                     preferred_company: str = "") -> list[dict]:
    """
    为产品评分引擎提供结构化产品数据。
    返回 list[dict]，每项含：product_id, product_name, company_name,
    sale_status, min_age, max_age, waiting_period(天), disease_counts,
    has_minor_ci, has_moderate_ci, annual_premium(元，50万基准)
    """
    try:
        import aiomysql
    except ImportError:
        return []

    host = os.getenv("MYSQL_HOST", "localhost")
    port = int(os.getenv("MYSQL_PORT", "3306"))
    user = os.getenv("MYSQL_USER", "aix")
    password = os.getenv("MYSQL_PASSWORD", "aix_secret")
    db = os.getenv("PRODUCT_DB_DATABASE", "my_ensure")

    try:
        conn = await aiomysql.connect(
            host=host, port=port, user=user, password=password, db=db,
            charset="utf8mb4", autocommit=True, connect_timeout=5,
        )
    except Exception as e:
        logger.warning(f"fetch_products_for_scoring: 无法连接数据库: {e}")
        return []

    try:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            # 1. 产品基本信息 + 条款字段
            await cur.execute("""
                SELECT
                    p.product_id,
                    p.product_name,
                    p.company_name,
                    p.sale_status,
                    MAX(CASE WHEN c.coverage_name = '投保年龄'    THEN pc.standard_content END) AS age_range,
                    MAX(CASE WHEN c.coverage_name = '等待期'      THEN pc.standard_content END) AS waiting_period_detail,
                    MAX(CASE WHEN c.coverage_name = '轻症赔付次数' THEN pc.standard_content END) AS mild_pay_times,
                    MAX(CASE WHEN c.coverage_name = '中症赔付次数' THEN pc.standard_content END) AS moderate_pay_times
                FROM cmb_product p
                LEFT JOIN cmb_product_coverage pc
                    ON p.product_id COLLATE utf8mb4_unicode_ci = pc.product_id AND pc.is_deleted = 0
                LEFT JOIN cmb_coverage c
                    ON pc.coverage_id = c.coverage_id
                    AND c.coverage_name IN ('投保年龄','等待期','轻症赔付次数','中症赔付次数')
                    AND c.is_deleted = 0
                WHERE p.is_deleted = 0
                  AND p.product_status = 'RELEASED'
                GROUP BY p.product_id, p.product_name, p.company_name, p.sale_status
                ORDER BY p.product_id
                LIMIT 50
            """)
            products = await cur.fetchall()

            # 2. 病种数量
            await cur.execute("""
                SELECT product_id, disease_category, COUNT(*) AS cnt
                FROM cmb_product_disease
                GROUP BY product_id, disease_category
            """)
            disease_rows = await cur.fetchall()

            # 3. 费率表查询（50万保额，按年龄+性别取最匹配一条）
            db_gender = 11 if gender == "male" else 10
            await cur.execute("""
                SELECT product_id, rate
                FROM cmb_product_rate
                WHERE age = %s AND gender IN (%s, 0)
                ORDER BY FIELD(gender, %s, 0)
                LIMIT 200
            """, (age, db_gender, db_gender))
            rate_rows = await cur.fetchall()

    except Exception as e:
        logger.warning(f"fetch_products_for_scoring 查询失败: {e}")
        return []
    finally:
        conn.close()

    # 整理数据
    disease_map: dict[str, dict] = {}
    for row in disease_rows:
        pid = str(row["product_id"])
        cat = row.get("disease_category") or "其他"
        if pid not in disease_map:
            disease_map[pid] = {}
        disease_map[pid][cat] = int(row.get("cnt", 0))

    rate_map: dict[str, float] = {}
    for row in rate_rows:
        pid = str(row["product_id"])
        if pid not in rate_map:
            rate = float(row.get("rate", 0) or 0)
            rate_map[pid] = rate * 50  # 50万保额年保费（费率×10000存储，实际=rate/10000*500000=rate*50）

    result = []
    for p in products:
        pid = str(p["product_id"])
        min_age, max_age = _parse_age_range(p.get("age_range") or "")
        waiting_days = _parse_waiting_days(p.get("waiting_period_detail") or "")
        disease_counts = disease_map.get(pid, {})
        has_minor_ci = bool(p.get("mild_pay_times"))
        has_moderate_ci = bool(p.get("moderate_pay_times"))
        annual_premium = rate_map.get(pid, 0.0)

        result.append({
            "product_id": pid,
            "product_name": p.get("product_name") or "",
            "company_name": p.get("company_name") or "",
            "sale_status": p.get("sale_status") or "N",
            "min_age": min_age,
            "max_age": max_age,
            "waiting_period": waiting_days,
            "disease_counts": disease_counts,
            "has_minor_ci": has_minor_ci,
            "has_moderate_ci": has_moderate_ci,
            "annual_premium": annual_premium,
        })

    return result
