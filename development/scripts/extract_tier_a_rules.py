#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from openpyxl import load_workbook


TARGET_FIELDS = [
    "投保年龄",
    "保险期间",
    "交费期间",
    "交费频率",
    "等待期",
    "等待期（简化）",
    "宽限期",
    "犹豫期",
    "重疾赔付次数",
    "重疾分组",
    "重疾数量",
]


CHINESE_DIGITS = {
    "零": 0,
    "〇": 0,
    "一": 1,
    "二": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}

PAY_FREQ_ORDER = ["趸交", "年交", "半年交", "季交", "月交"]
WAITING_PRIORITY_TITLES = ("等待期", "观察期", "投保须知")
WAITING_SKIP_HINTS = ("案例", "举例", "示例", "利益演示", "演示")
WAITING_SKIP_TEXT_HINTS = ("确诊日起满", "保单周年日", "小王", "案例")
PAY_PERIOD_TITLES = [
    "交费期间", "交费期限", "交费年期",
    "缴费期间", "缴费期限", "缴费年期",
    "保险费缴纳期间", "缴费方式",
]
RATE_SEARCH_ROOTS = [
    Path("/Users/zqf-openclaw/Desktop/开发材料/10款重疾"),
    Path("/Users/zqf-openclaw/Desktop/开发材料/招行数据"),
]
EXCLUDED_SHEET_KEYWORDS = ("次标准", "次标准体", "优选体")


def chinese_to_int(text: str) -> int | None:
    if not text:
        return None
    if text.isdigit():
        return int(text)
    if text == "十":
        return 10
    if "百" in text:
        left, right = text.split("百", 1)
        hundreds = CHINESE_DIGITS.get(left, 1 if left == "" else None)
        if hundreds is None:
            return None
        remainder = chinese_to_int(right) if right else 0
        if remainder is None:
            return None
        return hundreds * 100 + remainder
    if "十" in text:
        left, right = text.split("十", 1)
        tens = CHINESE_DIGITS.get(left, 1 if left == "" else None)
        if tens is None:
            return None
        ones = CHINESE_DIGITS.get(right, 0) if right else 0
        return tens * 10 + ones
    total = 0
    for ch in text:
        if ch not in CHINESE_DIGITS:
            return None
        total = total * 10 + CHINESE_DIGITS[ch]
    return total


def normalize_spaces(text: str) -> str:
    return re.sub(r"\s+", "", text)


def normalize_cell_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def add_candidate(results: dict, field: str, value: str | None, block: dict | None, confidence: float, note: str) -> None:
    if not value:
        return
    if confidence <= 0:
        return
    entry = {
        "coverage_name": field,
        "value": value,
        "confidence": round(confidence, 2),
        "note": note,
        "source_type": None,
        "block_id": block["block_id"] if block else None,
        "page": block["page"] if block else None,
        "evidence_text": block["text"] if block else None,
    }
    current = results.get(field)
    if current is None or entry["confidence"] > current["confidence"]:
        results[field] = entry


def set_candidate(results: dict, field: str, value: str, block: dict | None, confidence: float, note: str, status: str | None = None) -> None:
    entry = {
        "coverage_name": field,
        "value": value,
        "confidence": round(confidence, 2),
        "note": note,
        "source_type": None,
        "block_id": block.get("block_id") if block else None,
        "page": block.get("page") if block else None,
        "evidence_text": block.get("text") or block.get("evidence_text") if block else None,
    }
    if status:
        entry["status"] = status
    results[field] = entry


def extract_age(text: str) -> str | None:
    compact = normalize_spaces(text)
    m = re.search(r"(?:投保年龄.*?为|出生满)(\d+)(?:天|日).*?(\d+)周岁", compact)
    if m:
        return f"0（{m.group(1)}天）-{m.group(2)}周岁"
    m = re.search(r"(?:投保年龄.*?为|接受的投保年龄为)?(\d+)周岁至(\d+)周岁", compact)
    if m:
        return f"{m.group(1)}-{m.group(2)}周岁"
    m = re.search(r"出生([一二三四五六七八九十百零〇]+)日以上.*?([一二三四五六七八九十百零〇\d]+)周岁以下", compact)
    if m:
        low = chinese_to_int(m.group(1))
        high = chinese_to_int(m.group(2))
        if low is not None and high is not None:
            return f"0（{low}天）-{high}周岁"
    m = re.search(r"([一二三四五六七八九十百零〇\d]+)周岁以下", compact)
    if "投保年龄" in compact and m:
        high = chinese_to_int(m.group(1))
        if high is not None:
            return f"-{high}周岁"
    return None


def extract_duration_days(text: str, keyword: str) -> str | None:
    compact = normalize_spaces(text)
    if keyword not in compact:
        return None
    m = re.search(r"(\d+)[天日]", compact)
    if m:
        return f"{m.group(1)}天"
    m = re.search(r"([一二三四五六七八九十百零〇]+)[天日]", compact)
    if m:
        val = chinese_to_int(m.group(1))
        if val is not None:
            return f"{val}天"
    return None


def extract_waiting(text: str) -> tuple[str | None, str | None]:
    compact = normalize_spaces(text)
    if "等待期" not in compact and "观察期" not in compact:
        return None, None
    m = re.search(r"(\d+)[天日]内", compact)
    if not m:
        m = re.search(r"(\d+)[天日]", compact)
    if not m:
        m_cn = re.search(r"([一二三四五六七八九十百零〇]+)[天日]", compact)
        if m_cn:
            val = chinese_to_int(m_cn.group(1))
            if val is not None:
                days = str(val)
                simplified = f"{days}天"
                if "意外" in compact:
                    return f"非意外{days}天，意外0天", simplified
                return simplified, simplified
        return None, None
    days = m.group(1)
    simplified = f"{days}天"
    if "意外" in compact:
        return f"非意外{days}天，意外0天", simplified
    return simplified, simplified


def should_skip_waiting_block(block: dict) -> bool:
    title_path = "".join(block.get("title_path", []))
    text = block.get("text", "")
    skip_titles = ("举例", "示例", "案例", "理赔案例", "保险金给付案例")
    skip_texts = ("小王", "小明", "案例", "举例说明")
    return any(hint in title_path for hint in skip_titles) or any(hint in text for hint in skip_texts)


def waiting_block_confidence(block: dict) -> float:
    title_path = "".join(block.get("title_path", []))
    text = block["text"]
    if should_skip_waiting_block(block):
        return 0.0
    if any(hint in title_path for hint in WAITING_SKIP_HINTS):
        return 0.0
    if any(hint in text for hint in WAITING_SKIP_TEXT_HINTS):
        return 0.0
    if any(keyword in title_path for keyword in WAITING_PRIORITY_TITLES):
        return 0.97
    return 0.93


def extract_insurance_period(text: str) -> str | None:
    compact = normalize_spaces(text)
    if "保险期间" not in compact and "保障期间" not in compact:
        return None
    m = re.search(r"终身[，,]或.*?至被保险人([一二三四五六七八九十百]+)周岁", compact)
    if m:
        age = chinese_to_int(m.group(1))
        if age is not None:
            return f"至{age}周岁，终身"
    m = re.search(r"至被保险人([一二三四五六七八九十百]+)周岁.*?终身", compact)
    if m:
        age = chinese_to_int(m.group(1))
        if age is not None:
            return f"至{age}周岁，终身"
    m = re.search(r"至(\d+)周岁[，,]终身", compact)
    if m:
        return f"至{m.group(1)}周岁，终身"
    m = re.search(r"终身[或和及/]至(\d+)周岁", compact)
    if m:
        return f"至{m.group(1)}周岁，终身"
    m = re.search(r"至(\d+)周岁", compact)
    age_part = f"至{m.group(1)}周岁" if m else None
    m = re.search(r"保(?:至|到)(\d+)岁", compact)
    if not age_part and m:
        age_part = f"至{m.group(1)}周岁"
    has_lifetime = "终身" in compact
    if age_part and has_lifetime:
        return f"{age_part}，终身"
    if has_lifetime:
        return "终身"
    if age_part:
        return age_part
    # 支持"至被保险人 25 周岁"（阿拉伯数字）
    m = re.search(r"至被保险人\s*(\d+)\s*周岁", compact)
    if m:
        age_part = f"至{m.group(1)}周岁"
        if "终身" in compact:
            return f"{age_part}，终身"
        return age_part
    return None


def extract_pay_period(text: str) -> str | None:
    compact = normalize_spaces(text)
    if not any(k in compact for k in PAY_PERIOD_TITLES + ["交费方式和交费期间", "保险费的支付"]):
        return None
    return format_pay_periods_from_text(compact)


def format_pay_periods_from_text(compact: str) -> str | None:
    freqs: list[str] = []
    if "趸交" in compact or "一次性交付" in compact or "一次性付清" in compact:
        freqs.append("趸交")

    years = {int(x) for x in re.findall(r"(\d+)年交", compact)}
    if not years:
        m = re.search(r"交费期间分为(.+?)(?:两种|三种|四种|五种|六种|七种|八种|九种|十种|，|。)", compact)
        if m:
            segment = m.group(1)
            years |= {int(x) for x in re.findall(r"(\d+)年", segment)}
            for raw in re.findall(r"([一二三四五六七八九十百零〇]+)年", segment):
                val = chinese_to_int(raw)
                if val is not None:
                    years.add(val)
    if years:
        freqs.append("/".join(str(y) for y in sorted(years)) + "年交")

    age_match = re.search(r"交至(\d+)(?:周岁|岁)", compact)
    if age_match:
        freqs.append(f"交至{age_match.group(1)}周岁")

    if not freqs:
        return None
    # 去重并保序
    ordered: list[str] = []
    for item in freqs:
        if item not in ordered:
            ordered.append(item)
    return "，".join(ordered)


def locate_rate_xlsx(product_id: str) -> Path | None:
    for root in RATE_SEARCH_ROOTS:
        if not root.exists():
            continue
        matches = sorted(root.rglob(f"*{product_id}*费率表.xlsx"))
        if matches:
            return matches[0]
    return None


def select_rate_sheet(workbook) -> str:
    if "费率表" in workbook.sheetnames:
        return "费率表"
    candidates = [s for s in workbook.sheetnames if not any(k in s for k in EXCLUDED_SHEET_KEYWORDS)]
    return candidates[0] if candidates else workbook.sheetnames[0]


def extract_pay_period_from_rate_xlsx(product_id: str) -> tuple[str | None, Path | None, str | None]:
    path = locate_rate_xlsx(product_id)
    if path is None:
        return None, None, None
    try:
        workbook = load_workbook(path, read_only=True, data_only=True)
    except Exception:
        return None, path, None
    sheet_name = select_rate_sheet(workbook)
    ws = workbook[sheet_name]
    texts: list[str] = []
    for row in ws.iter_rows(min_row=1, max_row=10, values_only=True):
        for value in row:
            text = normalize_cell_text(value)
            if text:
                texts.append(text)
    compact = normalize_spaces(" ".join(texts))
    compact = compact.replace("一次性付清", "趸交")
    value = format_pay_periods_from_text(compact)
    return value, path, sheet_name


def extract_pay_frequency(text: str) -> str | None:
    compact = normalize_spaces(text)
    definition_like_patterns = [
        "保险费约定支付日",
        "指保险合同生效日在每月或每年对应的日期",
        "指保险合同生效日在每月或每年对应的日",
        "保险费约定支付日为本合同生效日之后每月每季每半年或者每年对应的日期",
        "保险费约定支付日为本合同生效日之后每月每季每半年或每年对应的日期",
    ]
    if any(pattern in compact for pattern in definition_like_patterns):
        return None
    if "指保险合同生效日在每月或每年" in compact and "对应日" in compact:
        return None
    if not any(k in compact for k in ["交费频率", "交费方式", "保险费的支付"]):
        if not any(k in compact for k in ["每月", "每季", "每半年", "每年", "趸交"]):
            return None
    found = [freq for freq in PAY_FREQ_ORDER if freq in compact]
    mapped = [
        ("每月", "月交"),
        ("每季", "季交"),
        ("每半年", "半年交"),
        ("每年", "年交"),
    ]
    for token, freq in mapped:
        if token in compact and freq not in found:
            found.append(freq)
    found = [freq for freq in PAY_FREQ_ORDER if freq in found]
    return "，".join(found) if found else None


def infer_frequency_from_pay_period(pay_period_value: str) -> str | None:
    """
    当条款/费率表无法直接抽到交费频率时，从交费期间推断。
    规则：
      - 有"趸交" AND 有"年交/交至" -> 趸交，年交
      - 只有"趸交"                 -> 趸交
      - 有"年交/交至"，无趸交       -> 年交
    注意：无法推断月交/季交/半年交，这些需费率表来源。
    """
    if not pay_period_value:
        return None
    has_dunce = "趸交" in pay_period_value
    has_annual = "年交" in pay_period_value or "交至" in pay_period_value
    if has_dunce and has_annual:
        return "趸交，年交"
    if has_dunce:
        return "趸交"
    if has_annual:
        return "年交"
    return None


def extract_ci_pay_times(text: str) -> str | None:
    compact = normalize_spaces(text)
    if "重大疾病" not in compact and "重度疾病" not in compact:
        return None
    CI_BENEFIT = ["重大疾病保险金", "重度疾病保险金"]

    single_markers = ["本合同终止", "本项责任终止", "1次"]
    optional_multi_markers = ["选择多次给付", "附加多次给付", "可选择多次", "多次给付责任"]
    if any(marker in compact for marker in single_markers) and any(
        marker in compact for marker in optional_multi_markers
    ):
        numbers = [int(num) for num in re.findall(r"(\d+)次", compact) if int(num) > 1]
        if numbers:
            return f"1次（若选择多次给付责任，{numbers[0]}次）"

    _CN_NUM = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
               "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
    m = re.search(r"(?:最多|至多|共|仅|只)(?:给付|赔付|赔偿).{0,10}?([一二三四五六七八九十]|\d+)次", compact)
    if m:
        raw = m.group(1)
        num = _CN_NUM.get(raw, raw)
        return f"{num}次"

    m_all = re.findall(r"(?:累计给付次数|保险金的累计给付次数)以([一二三四五六七八九十\d]+)次为限", compact)
    if m_all:
        nums = [_CN_NUM[r] if r in _CN_NUM else int(r) if r.isdigit() else 0 for r in m_all]
        num = max(nums) if "分组重大疾病保险金" in compact else nums[0]
        return f"{num}次"

    negative_markers = [
        "多次给付重大疾病保险金",
        "第二次重大疾病保险金",
        "第二次重疾",
        "多次重疾",
    ]
    has_negative = any(marker in compact for marker in negative_markers) or re.search(
        r"再次发生.{0,10}重大疾病", compact
    )
    positive = (any(k in compact for k in CI_BENEFIT) and "本合同终止" in compact) or (
        any(k in compact for k in ["重大疾病", "重度疾病"]) and "本项责任终止" in compact and "合同" in compact and "有效" in compact
    )
    if not has_negative and positive:
        return "1次"
    return None


def extract_ci_grouping(text: str) -> str | None:
    compact = normalize_spaces(text)
    if "分组" not in compact:
        return None
    if "不分组" in compact:
        return "不分组"
    if "分组重大疾病保险金" in compact:
        return "涉及分组"
    if "不同组" in compact or "分为" in compact:
        return "涉及分组"
    return None


def is_multi_ci_pay_times(value: str | None) -> bool | None:
    if not value:
        return None
    compact = normalize_spaces(value)
    if any(token in compact for token in ["多次", "多赔", "无限次", "无限"]):
        return True
    for num in re.findall(r"\d+", compact):
        if int(num) >= 2:
            return True
    if compact in {"1", "1次"}:
        return False
    if "次" in compact:
        return False
    return False


def extract_ci_count(text: str) -> str | None:
    compact = normalize_spaces(text)
    if "重大疾病" not in compact and "重度疾病" not in compact:
        return None
    m = re.search(r"重大疾病（共(\d+)种）", compact)
    if m:
        return f"{m.group(1)}种"
    m = re.search(r"重大疾病共有(\d+)种", compact)
    if m:
        return f"{m.group(1)}种"
    m = re.search(r"共计(\d+)种", compact)
    if m:
        return f"{m.group(1)}种"
    m = re.search(r"(\d+)种重大疾病", compact)
    if m:
        return f"{m.group(1)}种"
    m = re.search(r"共计([一二三四五六七八九十百零〇]+)种", compact)
    if m:
        val = chinese_to_int(m.group(1))
        if val is not None:
            return f"{val}种"
    return None


def ci_count_confidence(text: str) -> float:
    compact = normalize_spaces(text)
    if any(pat in compact for pat in ["重大疾病（共", "重大疾病共有", "我们提供保障的重大疾病共有"]):
        return 0.95
    if "种重大疾病" in compact or "共计" in compact:
        return 0.86
    return 0.8


def get_ci_count_from_db(product_id: str, counts_path: Path) -> dict | None:
    """
    从 product_disease_counts_v1.json 读取产品重疾数量。
    返回格式：
      {"value": "120种", "source_type": "product_disease_db", "confidence": 0.99}
    复杂产品（含少儿重大疾病）：
      {"value": "120种重大疾病；20种少儿重大疾病", ...}
    未找到返回 None。
    """
    if not counts_path.exists():
        return None
    data = json.loads(counts_path.read_text(encoding="utf-8"))
    cats = data.get("products", {}).get(product_id, {})
    ci = cats.get("重大疾病", 0)
    if ci == 0:
        return None
    pediatric = cats.get("少儿重大疾病", 0)
    if pediatric:
        value = f"{ci}种重大疾病；{pediatric}种少儿重大疾病"
    else:
        value = f"{ci}种"
    return {"value": value, "source_type": "product_disease_db", "confidence": 0.99}


def get_coverage_from_db(product_id: str, coverage_name: str, db_path: Path) -> dict | None:
    """
    从 product_coverage_db_v1.json 读取产品字段标准值。
    db_path: data/manifests/product_coverage_db_v1.json
    返回格式：{"value": "...", "source_type": "product_coverage_db", "confidence": 0.99}
    未找到返回 None。
    """
    if not db_path.exists():
        return None
    data = json.loads(db_path.read_text(encoding="utf-8"))
    value = data.get("products", {}).get(product_id, {}).get(coverage_name)
    if not value:
        return None
    return {"value": value, "source_type": "product_coverage_db", "confidence": 0.99}


def extract_candidates(blocks: list[dict], disease_lookup_id: str, counts_path: Path, product_id: str, coverage_db_path: Path) -> dict:
    results: dict = {}
    grouping_match: dict | None = None
    text_blocks: list[dict] = []
    for block in blocks:
        if block["block_type"] not in {"paragraph", "title"}:
            continue
        text = block["text"]
        text_blocks.append(block)

        add_candidate(results, "投保年龄", extract_age(text), block, 0.95 if "投保年龄" in text else 0.82, "rule: age_pattern")
        _ip_val = extract_insurance_period(text)
        _ip_conf = 0.97 if any("保险期间" in t for t in block.get("title_path", [])) else 0.93
        add_candidate(results, "保险期间", _ip_val, block, _ip_conf, "rule: insurance_period_pattern")
        add_candidate(results, "交费期间", extract_pay_period(text), block, 0.9, "rule: pay_period_pattern")
        add_candidate(results, "交费频率", extract_pay_frequency(text), block, 0.9, "rule: pay_frequency_pattern")

        waiting_raw, waiting_simple = extract_waiting(text)
        waiting_conf = waiting_block_confidence(block)
        add_candidate(results, "等待期", waiting_raw, block, waiting_conf, "rule: waiting_period_pattern")
        add_candidate(results, "等待期（简化）", waiting_simple, block, waiting_conf, "rule: waiting_period_simple")

        add_candidate(results, "宽限期", extract_duration_days(text, "宽限期"), block, 0.94, "rule: grace_period_pattern")
        add_candidate(results, "犹豫期", extract_duration_days(text, "犹豫期"), block, 0.94, "rule: cooling_off_pattern")
        add_candidate(results, "重疾赔付次数", extract_ci_pay_times(text), block, 0.82, "rule: ci_pay_times")
        grouping_value = extract_ci_grouping(text)
        if grouping_value:
            candidate = {
                "coverage_name": "重疾分组",
                "value": grouping_value,
                "confidence": 0.75,
                "note": "rule: ci_grouping",
                "block_id": block["block_id"],
                "page": block["page"],
                "evidence_text": block["text"],
            }
            if grouping_match is None or candidate["confidence"] > grouping_match["confidence"]:
                grouping_match = candidate
        if "重疾数量" not in results:
            count_value = extract_ci_count(text)
            add_candidate(results, "重疾数量", count_value, block, ci_count_confidence(text), "rule: ci_count")

    # 跨block兜底：重疾赔付次数单次判定
    if "重疾赔付次数" not in results:
        multi_markers = ["多次给付重大疾病", "第二次重大疾病", "多次重疾", "再次发生.*重大疾病"]
        all_text = " ".join(b["text"] for b in blocks)
        has_termination = any(k in all_text for k in ["本合同终止", "合同效力终止", "主合同终止", "本主险合同效力终止"])
        has_ci_termination = any(
            any(k in normalize_spaces(b["text"]) for k in ["本合同终止", "合同效力终止", "主合同终止", "本主险合同效力终止"])
            and any(ci in normalize_spaces(b["text"]) for ci in ["重大疾病保险金", "重度疾病保险金"])
            for b in blocks
        )
        has_ci = any(k in all_text for k in ["重大疾病保险金", "重度疾病保险金"])
        has_multi = any(m in all_text for m in multi_markers) or re.search(r"再次发生.{0,10}重大疾病", all_text)
        has_child_ci = any("少儿重大疾病" in b["text"] or "少儿特定疾病" in b["text"] for b in blocks)
        if has_ci and has_ci_termination and not has_multi and not has_child_ci:
            evidence_block = next(
                (b for b in blocks if any(k in normalize_spaces(b["text"]) for k in ["本合同终止", "合同效力终止", "主合同终止", "本主险合同效力终止"])
                 and any(ci in normalize_spaces(b["text"]) for ci in ["重大疾病保险金", "重度疾病保险金"])),
                next((b for b in blocks if any(k in normalize_spaces(b["text"]) for k in ["本合同终止", "合同效力终止", "主合同终止", "本主险合同效力终止"])), blocks[0])
            )
            add_candidate(results, "重疾赔付次数", "1次", evidence_block, 0.78, "rule: cross_block_single_pay")

    # 跨block兜底：可选多次赔付（如851A"可选部分的第二次重大疾病保险金"）
    if "重疾赔付次数" not in results:
        has_optional_part = any("可选部分" in b["text"] for b in blocks)
        has_second_pay = any(
            any(k in b["text"] for k in ["第二次重大疾病", "第二次重度疾病"])
            for b in blocks
        )
        if has_optional_part and has_second_pay:
            evidence_block = next(
                (b for b in blocks if any(k in b["text"] for k in ["第二次重大疾病", "第二次重度疾病"])),
                blocks[0]
            )
            add_candidate(results, "重疾赔付次数", "1次（若选择多次给付责任，2次）",
                          evidence_block, 0.78, "rule: cross_block_optional_multi")

    current_pay_times = results.get("重疾赔付次数", {}).get("value")
    if "重疾赔付次数" not in results or current_pay_times == "1次":
        ci_ord = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
                  "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
        all_text = " ".join(b["text"] for b in blocks)
        has_optional_lang = any(m in all_text for m in ["选择多次给付", "附加多次给付", "可选择多次"])
        if not has_optional_lang:
            ord_hits: set[int] = set()
            for cn, val in ci_ord.items():
                if f"第{cn}次重大疾病保险金" in all_text or f"第{cn}次重度疾病保险金" in all_text:
                    ord_hits.add(val)
            for d in re.findall(r"第(\d+)次重大疾病保险金", all_text):
                ord_hits.add(int(d))
            for d in re.findall(r"第(\d+)次重度疾病保险金", all_text):
                ord_hits.add(int(d))
            firm_count = max(ord_hits) if ord_hits else 0
            if firm_count >= 2:
                evidence_block = next(
                    (b for b in blocks if "第二次重大疾病保险金" in b["text"]
                     or "第二次重度疾病保险金" in b["text"]),
                    blocks[0],
                )
                set_candidate(
                    results,
                    "重疾赔付次数",
                    f"{firm_count}次",
                    evidence_block,
                    0.85,
                    "rule: cross_block_firm_multi",
                )

    # 保险期间兜底：从合同名称推断终身
    if "保险期间" not in results:
        for b in blocks:
            if b.get("page", 99) <= 2 and re.search(r"终身.{0,8}(?:重大疾病|疾病)保险", b.get("text", "")):
                add_candidate(results, "保险期间", "终身", b, 0.80, "rule: inferred_from_contract_name")
                break

    pay_times_value = results.get("重疾赔付次数", {}).get("value")
    multi_pay = is_multi_ci_pay_times(pay_times_value)
    all_compact_text = normalize_spaces(" ".join(b["text"] for b in text_blocks))
    has_grouped_ci_declaration = "分组重大疾病保险金" in all_compact_text
    if has_grouped_ci_declaration and "重疾赔付次数" in results:
        m_n = re.search(r"^(\d+)次$", pay_times_value or "")
        if m_n:
            n_groups = int(m_n.group(1))
            evidence_block = next(
                (b for b in text_blocks if "分组重大疾病保险金" in normalize_spaces(b["text"])),
                text_blocks[0] if text_blocks else None,
            )
            set_candidate(
                results,
                "重疾分组",
                f"{n_groups}组",
                evidence_block,
                0.82,
                "rule: ci_grouping_from_分组保险金_and_pay_times",
            )
            grouping_match = results["重疾分组"]
    if multi_pay is None:
        set_candidate(results, "重疾分组", "", None, 0.0, "rule: ci_grouping_review_required", status="review_required")
    elif multi_pay is False and not has_grouped_ci_declaration:
        pay_times_block = results.get("重疾赔付次数")
        set_candidate(
            results,
            "重疾分组",
            "不涉及",
            pay_times_block,
            0.9,
            "rule: ci_grouping_from_pay_times_single",
        )
    elif pay_times_value and "若选择多次给付责任" in pay_times_value:
        pay_times_block = results.get("重疾赔付次数")
        set_candidate(
            results,
            "重疾分组",
            "不分组",
            pay_times_block,
            0.75,
            "rule: ci_grouping_optional_multi",
        )
    elif multi_pay is True and "若选择多次给付责任" not in (pay_times_value or ""):
        if has_grouped_ci_declaration:
            pass
        else:
            pay_times_block = results.get("重疾赔付次数")
            set_candidate(
                results,
                "重疾分组",
                "不分组",
                pay_times_block,
                0.78,
                "rule: ci_grouping_firm_multi_no_group",
            )
    elif grouping_match is not None:
        results["重疾分组"] = grouping_match
    else:
        set_candidate(results, "重疾分组", "", None, 0.0, "rule: ci_grouping_review_required", status="review_required")

    # 等待期跨block升级：抽到纯天数但全文存在"意外无等待期"声明时，升级为完整格式
    if "等待期" in results:
        waiting_val = results["等待期"].get("value", "")
        if waiting_val and "意外" not in waiting_val:
            all_compact = normalize_spaces(" ".join(b["text"] for b in blocks))
            has_no_waiting_accident = (
                any("意外" in b["text"] and "无等待期" in b["text"] for b in blocks)
                or re.search(
                    r"意外伤害.*?无等待期|无等待期.*?意外伤害"
                    r"|因意外伤害.*?不受.*?限制"
                    r"|因意外伤害.*?不设.*?等待期"
                    r"|意外伤害事故.*?无等待期|无等待期.*?意外伤害事故",
                    all_compact,
                )
            )
            if has_no_waiting_accident:
                results["等待期"]["value"] = f"非意外{waiting_val}，意外0天"

    # 等待期跨block兜底：旧式条款用"X日内...若因意外...不受限制"表达等待期，无"等待期"关键词
    if "等待期" not in results:
        for b in blocks:
            compact_b = normalize_spaces(b["text"])
            m = re.search(r"之日起([一二三四五六七八九十百零〇]+|\d+)[日天]内", compact_b)
            if m and re.search(r"若因意外伤害.*不受", compact_b):
                raw = m.group(1)
                val = chinese_to_int(raw) if not raw.isdigit() else int(raw)
                if val:
                    simplified = f"{val}天"
                    add_candidate(results, "等待期", f"非意外{simplified}，意外0天", b, 0.75, "rule: waiting_embedded_coverage_clause")
                    add_candidate(results, "等待期（简化）", simplified, b, 0.75, "rule: waiting_embedded_coverage_clause")
                break

    if "交费频率" not in results:
        pay_period_value = results.get("交费期间", {}).get("value")
        inferred_frequency = infer_frequency_from_pay_period(pay_period_value)
        if inferred_frequency:
            results["交费频率"] = {
                "coverage_name": "交费频率",
                "value": inferred_frequency,
                "confidence": 0.6,
                "note": "rule: inferred_from_pay_period",
                "source_type": "inferred_from_pay_period",
                "block_id": results.get("交费期间", {}).get("block_id"),
                "page": results.get("交费期间", {}).get("page"),
                "evidence_text": results.get("交费期间", {}).get("evidence_text"),
            }

    if "交费期间" not in results:
        rate_value, rate_path, sheet_name = extract_pay_period_from_rate_xlsx(product_id)
        if rate_value:
            results["交费期间"] = {
                "coverage_name": "交费期间",
                "value": rate_value,
                "confidence": 0.82,
                "note": f"rule: raw_rate_xlsx_header{f'[{sheet_name}]' if sheet_name else ''}",
                "source_type": "raw_rate_xlsx",
                "block_id": None,
                "page": None,
                "evidence_text": str(rate_path) if rate_path else None,
            }

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract Tier A rule-based candidates from blocks.")
    parser.add_argument("manifest_pos", nargs="?")
    parser.add_argument("output_pos", nargs="?")
    parser.add_argument("--manifest")
    parser.add_argument("--blocks-dir")
    parser.add_argument("--output")
    args = parser.parse_args()

    manifest_path = args.manifest or args.manifest_pos
    output_path_arg = args.output or args.output_pos
    blocks_dir_arg = args.blocks_dir or str(Path(__file__).resolve().parents[1] / "data" / "blocks")
    counts_path = Path(__file__).resolve().parents[1] / "data" / "manifests" / "product_disease_counts_v1.json"
    coverage_db_path = Path(__file__).resolve().parents[1] / "data" / "manifests" / "product_coverage_db_v1.json"

    if not manifest_path or not output_path_arg:
        parser.error("must provide manifest and output, either as positional args or with --manifest/--output")

    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    rows = []
    for item in manifest:
        if item["product_id"] == "1548A":
            continue
        if item.get("phase1_eligible") is False:
            continue
        if item.get("status") == "phase1_excluded":
            continue
        blocks_path = Path(blocks_dir_arg) / f"{item['product_id']}_blocks.json"
        if not blocks_path.exists():
            continue
        blocks = json.loads(blocks_path.read_text(encoding="utf-8"))
        disease_lookup_id = str(item.get("db_product_id") or item["product_id"])
        extracted = extract_candidates(blocks, disease_lookup_id, counts_path, item["product_id"], coverage_db_path)
        rows.append(
            {
                "product_id": item["product_id"],
                "db_product_id": item.get("db_product_id"),
                "product_name": item["product_name"],
                "source_blocks": str(blocks_path),
                "candidates": [extracted[field] for field in TARGET_FIELDS if field in extracted],
                "missing_fields": [field for field in TARGET_FIELDS if field not in extracted],
            }
        )

    output_path = Path(output_path_arg)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {len(rows)} products to {output_path}")


if __name__ == "__main__":
    main()
