#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from block_tagger import tag_blocks


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "data" / "manifests" / "sample_manifest.json"
DEFAULT_BLOCKS_DIR = ROOT / "data" / "blocks"
DEFAULT_OUTPUT = ROOT / "data" / "extractions" / "tier_b_responsibility_candidates_v1.json"


TARGET_FIELDS = [
    ("重疾赔付次数", "疾病责任__重疾责任__重疾赔付次数"),
    ("重疾数量", "疾病责任__重疾责任__重疾数量"),
    ("轻症赔付次数", "疾病责任__轻症责任__轻症赔付次数"),
    ("轻症数量", "疾病责任__轻症责任__轻症数量"),
    ("轻症分组", "疾病责任__轻症责任__轻症分组"),
    ("中症赔付次数", "疾病责任__中症责任__中症赔付次数"),
    ("中症数量", "疾病责任__中症责任__中症数量"),
    ("中症分组", "疾病责任__中症责任__中症分组"),
    # 保单功能
    ("减额交清", "其他责任__保单功能__减额交清"),
    ("指定第二投保人", "其他责任__保单功能__指定第二投保人"),
    ("转换权", "其他责任__保单功能__转换权"),
    ("保单贷款", "其他责任__保单功能__保单贷款"),
    ("减保", "其他责任__保单功能__减保"),
    # 免责数量
    ("身故免责数量", "责任免除（人身险）__身故免责__身故免责数量"),
    ("疾病免责数量", "责任免除（人身险）__疾病免责__疾病免责数量"),
    ("豁免免责数量", "责任免除（人身险）__豁免免责__豁免免责数量"),
    ("全残免责数量", "责任免除（人身险）__全残免责__全残免责数量"),
    # 豁免开关
    ("投保人身故豁免", "豁免责任__投保人豁免__投保人身故豁免"),
    ("投保人全残豁免", "豁免责任__投保人豁免__投保人全残豁免"),
    ("被保险人重疾豁免", "豁免责任__被保险人豁免__被保险人重疾豁免"),
    ("被保险人中症豁免", "豁免责任__被保险人豁免__被保险人中症豁免"),
    ("被保险人轻症豁免", "豁免责任__被保险人豁免__被保险人轻症豁免"),
    # 保障说明
    ("重疾保障说明", "疾病责任__重疾责任__重疾保障说明"),
    ("轻症保障说明", "疾病责任__轻症责任__轻症保障说明"),
    ("中症保障说明", "疾病责任__中症责任__中症保障说明"),
    # 基本信息
    ("合同名称（条款名称）", "基本信息__合同名称（条款名称）"),
]

# Fields whose absence may indicate "product has no such coverage" when the
# keyword never appears anywhere in the full text.
COVERAGE_PRESENCE_KEYWORDS: dict[str, list[str]] = {
    "轻症赔付次数": ["轻症", "轻度疾病"],
    "轻症数量": ["轻症", "轻度疾病"],
    # 轻症分组: extractor 内部已处理 no_keyword → "不涉及"，不再需要关键词守卫
    "中症赔付次数": ["中症", "中度疾病"],
    "中症数量": ["中症", "中度疾病"],
    # 中症分组: extractor 内部已处理 no_keyword → "不涉及"，不再需要关键词守卫
    "轻症保障说明": ["轻症", "轻度疾病"],
    "中症保障说明": ["中症", "中度疾病"],
}


CN_NUM_MAP = {
    "零": 0,
    "〇": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_blocks_compatible(path: Path) -> list[dict]:
    raw = load_json(path)
    if isinstance(raw, dict) and "blocks" in raw:
        return raw["blocks"]
    if isinstance(raw, list):
        return raw
    raise ValueError(f"Unsupported blocks payload: {path}")


def chinese_to_int(text: str) -> int | None:
    text = text.strip()
    if not text:
        return None
    if text.isdigit():
        return int(text)
    total = 0
    if text == "十":
        return 10
    if "十" in text:
        left, _, right = text.partition("十")
        tens = CN_NUM_MAP.get(left, 1 if left == "" else None)
        ones = CN_NUM_MAP.get(right, 0 if right == "" else None)
        if tens is None or ones is None:
            return None
        return tens * 10 + ones
    if len(text) == 1:
        return CN_NUM_MAP.get(text)
    for ch in text:
        if ch not in CN_NUM_MAP:
            return None
        total = total * 10 + CN_NUM_MAP[ch]
    return total


def normalize_times(raw: str) -> str | None:
    raw = raw.strip()
    value = chinese_to_int(raw)
    if value is None:
        return None
    return f"{value}次"


def normalize_count(raw: str) -> str | None:
    raw = raw.strip()
    value = chinese_to_int(raw)
    if value is None:
        return None
    return f"{value}种"


def build_candidate(coverage_name: str, coverage_path: str, value: str, confidence: float, note: str, block: dict) -> dict:
    return {
        "coverage_name": coverage_name,
        "coverage_path": coverage_path,
        "value": value,
        "confidence": confidence,
        "note": note,
        "block_id": block.get("block_id"),
        "page": block.get("page"),
        "evidence_text": block.get("text", ""),
    }


def extract_ci_pay_times(blocks: list[dict]) -> dict | None:
    for idx, block in enumerate(blocks):
        text = block.get("text", "")
        if "重大疾病保险金" not in text and "重度疾病保险金" not in text:
            continue
        window = blocks[idx : idx + 8]
        for item in window:
            item_text = item.get("text", "")
            if "重大疾病" not in item_text and "重度疾病" not in item_text:
                continue
            if any(flag in item_text for flag in ("首次重度疾病保险金", "第二次重度疾病保险金", "第三次重度疾病保险金", "第四次重度疾病保险金", "重度疾病多次给付保险金")):
                continue
            match = re.search(r"最多给付([一二两三四五六七八九十\d]+)次", item_text)
            if not match:
                match = re.search(r"给付次数(?:以|为)?([一二两三四五六七八九十\d]+)次为限", item_text)
            if match:
                value = normalize_times(match.group(1))
                if value:
                    return build_candidate("重疾赔付次数", "疾病责任__重疾责任__重疾赔付次数", value, 0.96, "rule: ci_pay_times_pattern", item)
            if "本合同终止" in item_text or (("给付后" in item_text or "同时本合同效力终止" in item_text) and "合同效力终止" in item_text):
                return build_candidate("重疾赔付次数", "疾病责任__重疾责任__重疾赔付次数", "1次", 0.9, "rule: ci_pay_times_termination", item)
    return None


def extract_ci_count(blocks: list[dict]) -> dict | None:
    patterns = [
        r"重大疾病共有\s*([一二两三四五六七八九十\d]+)\s*种",
        r"重度疾病共有\s*([一二两三四五六七八九十\d]+)\s*种",
        r"重大疾病列表（([一二两三四五六七八九十\d]+)\s*种）",
        r"重大疾病（共\s*([一二两三四五六七八九十\d]+)\s*种）",
        r"共计([一二两三四五六七八九十\d]+)种",
    ]
    candidates: list[tuple[int, dict, str]] = []
    for idx, block in enumerate(blocks):
        text = block.get("text", "")
        if "轻症" in text or "轻度疾病" in text:
            continue
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                value = normalize_count(match.group(1))
                if value:
                    if pattern == patterns[-1]:
                        nearby = " ".join(b.get("text", "") for b in blocks[max(0, idx - 12) : idx + 1])
                        if "轻症" in nearby or "轻度疾病" in nearby:
                            continue
                        if "重大疾病" not in nearby and "重度疾病" not in nearby:
                            continue
                    count_num = chinese_to_int(match.group(1))
                    if count_num is not None:
                        candidates.append(
                            (
                                count_num,
                                block,
                                "rule: ci_count_pattern",
                            )
                        )
    if candidates:
        count_num, block, note = max(candidates, key=lambda item: item[0])
        return build_candidate("重疾数量", "疾病责任__重疾责任__重疾数量", f"{count_num}种", 0.97, note, block)

    for idx, block in enumerate(blocks):
        title_match = re.match(r"^\s*(\d+)\s+重[大度]疾病的定义及范围", block.get("text", ""))
        if not title_match:
            continue
        section_no = title_match.group(1)
        max_sub = 0
        hit_block = None
        for item in blocks[idx + 1 :]:
            item_text = item.get("text", "")
            for raw in re.findall(rf"\b{re.escape(section_no)}\.(\d{{1,3}})\b", item_text):
                max_sub = max(max_sub, int(raw))
                hit_block = item
        if max_sub >= 10 and hit_block:
            return build_candidate("重疾数量", "疾病责任__重疾责任__重疾数量", f"{max_sub}种", 0.95, "rule: ci_count_section_numbering", hit_block)
    return None


def extract_mild_pay_times(blocks: list[dict]) -> dict | None:
    patterns = [
        r"轻症疾病保险金的给付次数(?:以|为)?([一二两三四五六七八九十\d]+)次为限",
        r"累计给付的轻症疾病保险金达到([一二两三四五六七八九十\d]+)次",
        r"轻症疾病保险金的给付累计以([一二两三四五六七八九十\d]+)次为限",
    ]
    for block in blocks:
        text = block.get("text", "")
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                value = normalize_times(match.group(1))
                if value:
                    return build_candidate("轻症赔付次数", "疾病责任__轻症责任__轻症赔付次数", value, 0.95, "rule: mild_pay_times_pattern", block)

    for idx, block in enumerate(blocks):
        text = block.get("text", "")
        if "轻度疾病保险金" in text or "轻症疾病保险金" in text:
            window = blocks[idx : idx + 6]
            for item in window:
                item_text = item.get("text", "")
                match = re.search(r"累计给付次数(?:达到|以)([一二两三四五六七八九十\d]+)次", item_text)
                if match:
                    value = normalize_times(match.group(1))
                    if value:
                        return build_candidate("轻症赔付次数", "疾病责任__轻症责任__轻症赔付次数", value, 0.9, "rule: mild_pay_times_combined_limit", item)
    return None


def extract_mild_count(blocks: list[dict]) -> dict | None:
    for idx, block in enumerate(blocks):
        text = block.get("text", "")
        patterns = [
            r"轻症疾病共\s*([一二两三四五六七八九十\d]+)\s*种",
            r"轻症疾病共有\s*([一二两三四五六七八九十\d]+)\s*种",
            r"轻症疾病列表（([一二两三四五六七八九十\d]+)\s*种）",
            r"轻症疾病（共\s*([一二两三四五六七八九十\d]+)\s*种）",
            r"轻度疾病.*共计([一二两三四五六七八九十\d]+)种",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                value = normalize_count(match.group(1))
                if value:
                    return build_candidate("轻症数量", "疾病责任__轻症责任__轻症数量", value, 0.96, "rule: mild_count_pattern", block)

        if "共计" in text and "种" in text:
            nearby = " ".join(b.get("text", "") for b in blocks[max(0, idx - 2) : idx + 1])
            if "轻度疾病" in nearby or "轻症疾病" in nearby:
                match = re.search(r"共计([一二两三四五六七八九十\d]+)种", text)
                if match:
                    value = normalize_count(match.group(1))
                    if value:
                        return build_candidate("轻症数量", "疾病责任__轻症责任__轻症数量", value, 0.9, "rule: mild_count_section_context", block)
    return None


def extract_mild_group(blocks: list[dict]) -> dict | None:
    all_text = " ".join(b.get("text", "") for b in blocks)
    has_mild = "轻症" in all_text or "轻度疾病" in all_text
    if not has_mild:
        # 主险条款中完全无轻症/轻度疾病关键词 → 不涉及
        ref_block = blocks[0] if blocks else {"block_id": None, "page": None, "text": ""}
        return build_candidate("轻症分组", "疾病责任__轻症责任__轻症分组", "不涉及", 0.88,
                               "rule: mild_group_no_keyword", ref_block)

    # Pass 1: explicit patterns in 轻症-relevant blocks
    for block in blocks:
        text = block.get("text", "")
        if "轻症" not in text and "轻度疾病" not in text:
            continue
        if "不分组" in text:
            return build_candidate("轻症分组", "疾病责任__轻症责任__轻症分组", "不分组", 0.95, "rule: mild_group_pattern", block)
        match = re.search(r"分为([一二两三四五六七八九十\d]+)组", text)
        if match:
            value_num = chinese_to_int(match.group(1))
            if value_num is not None:
                return build_candidate("轻症分组", "疾病责任__轻症责任__轻症分组", f"{value_num}组", 0.95, "rule: mild_group_pattern", block)

    # Pass 2: "同组" evidence → grouping exists but count unknown → leave as missing
    if any("同组" in b.get("text", "") and ("轻" in b.get("text", ""))
           for b in blocks):
        return None

    # Pass 3: coverage exists, no grouping evidence → 不分组
    evidence_block = next(
        (b for b in blocks if "轻症" in b.get("text", "") or "轻度疾病" in b.get("text", "")),
        None,
    )
    if evidence_block:
        return build_candidate("轻症分组", "疾病责任__轻症责任__轻症分组", "不分组", 0.85,
                               "rule: mild_group_no_evidence", evidence_block)
    return None


def extract_middle_pay_times(blocks: list[dict]) -> dict | None:
    patterns = [
        r"中症疾病保险金的给付次数(?:以|为)?([一二两三四五六七八九十\d]+)次为限",
        r"累计给付的中症疾病保险金达到([一二两三四五六七八九十\d]+)次",
        r"中症疾病保险金的给付累计以([一二两三四五六七八九十\d]+)次为限",
    ]
    for block in blocks:
        text = block.get("text", "")
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                value = normalize_times(match.group(1))
                if value:
                    return build_candidate("中症赔付次数", "疾病责任__中症责任__中症赔付次数", value, 0.95, "rule: middle_pay_times_pattern", block)

    for idx, block in enumerate(blocks):
        text = block.get("text", "")
        if "中症疾病保险金" in text or "中度疾病保险金" in text:
            window = blocks[idx : idx + 6]
            for item in window:
                item_text = item.get("text", "")
                match = re.search(r"累计给付次数(?:达到|以)([一二两三四五六七八九十\d]+)次", item_text)
                if match:
                    value = normalize_times(match.group(1))
                    if value:
                        return build_candidate("中症赔付次数", "疾病责任__中症责任__中症赔付次数", value, 0.9, "rule: middle_pay_times_combined_limit", item)
    return None


def extract_middle_count(blocks: list[dict]) -> dict | None:
    for idx, block in enumerate(blocks):
        text = block.get("text", "")
        patterns = [
            r"中症疾病共\s*([一二两三四五六七八九十\d]+)\s*种",
            r"中症疾病共有\s*([一二两三四五六七八九十\d]+)\s*种",
            r"中症疾病列表（([一二两三四五六七八九十\d]+)\s*种）",
            r"中度疾病.*共计([一二两三四五六七八九十\d]+)种",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                value = normalize_count(match.group(1))
                if value:
                    return build_candidate("中症数量", "疾病责任__中症责任__中症数量", value, 0.96, "rule: middle_count_pattern", block)

        if "共计" in text and "种" in text:
            nearby = " ".join(b.get("text", "") for b in blocks[max(0, idx - 2) : idx + 1])
            if "中度疾病" in nearby or "中症疾病" in nearby:
                match = re.search(r"共计([一二两三四五六七八九十\d]+)种", text)
                if match:
                    value = normalize_count(match.group(1))
                    if value:
                        return build_candidate("中症数量", "疾病责任__中症责任__中症数量", value, 0.9, "rule: middle_count_section_context", block)
    return None


def extract_middle_group(blocks: list[dict]) -> dict | None:
    all_text = " ".join(b.get("text", "") for b in blocks)
    has_middle = "中症" in all_text or "中度疾病" in all_text
    if not has_middle:
        # 主险条款中完全无中症/中度疾病关键词 → 不涉及
        ref_block = blocks[0] if blocks else {"block_id": None, "page": None, "text": ""}
        return build_candidate("中症分组", "疾病责任__中症责任__中症分组", "不涉及", 0.88,
                               "rule: middle_group_no_keyword", ref_block)

    # Pass 1: explicit patterns in 中症-relevant blocks
    for block in blocks:
        text = block.get("text", "")
        if "中症" not in text and "中度疾病" not in text:
            continue
        if "不分组" in text:
            return build_candidate("中症分组", "疾病责任__中症责任__中症分组", "不分组", 0.95, "rule: middle_group_pattern", block)
        match = re.search(r"分为([一二两三四五六七八九十\d]+)组", text)
        if match:
            value_num = chinese_to_int(match.group(1))
            if value_num is not None:
                return build_candidate("中症分组", "疾病责任__中症责任__中症分组", f"{value_num}组", 0.95, "rule: middle_group_pattern", block)

    # Pass 2: "同组" evidence → grouping exists but count unknown → leave as missing
    if any("同组" in b.get("text", "") and ("中症" in b.get("text", "") or "中度" in b.get("text", ""))
           for b in blocks):
        return None

    # Pass 3: coverage exists, no grouping evidence → 不分组
    evidence_block = next(
        (b for b in blocks if "中症" in b.get("text", "") or "中度疾病" in b.get("text", "")),
        None,
    )
    if evidence_block:
        return build_candidate("中症分组", "疾病责任__中症责任__中症分组", "不分组", 0.85,
                               "rule: middle_group_no_evidence", evidence_block)
    return None


# ─────────────────────────────────────────────────────────────────
# 保单功能 extractors
# ─────────────────────────────────────────────────────────────────

def _compact(text: str) -> str:
    return re.sub(r"\s+", "", text)


_CN_ITEM = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
            "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


def _count_items_in_blocks(blocks: list[dict], start: int, max_window: int = 18) -> int:
    """Count max numbered item (Arabic or Chinese) in a window of blocks.

    Stops at section boundaries and footnote definitions.
    """
    max_n = 0
    for b in blocks[start:start + max_window]:
        if not isinstance(b, dict):
            continue
        text = b.get("text", "")
        c = _compact(text)
        # Stop at next major section
        if "其他免责条款" in c or "保险事故的通知" in c[:30]:
            break
        # Stop at footnote definitions (e.g. "11 毒品：..." "12 酒后驾驶：...")
        if re.match(r"^\d+\s+\S{2,}[:：]", text.lstrip()):
            break
        # Stop at new article/part headings (e.g. "第三部分", "第十一条")
        if re.match(r"^第[一二三四五六七八九十百]+(?:条|部分)", c):
            break
        # Arabic items: (1), (2), (3) ...
        for m in re.findall(r"[（(](\d+)[）)]", text):
            max_n = max(max_n, int(m))
        # Arabic items with dot: 1. 2. 3. (e.g. "1. 投保人...")
        for m in re.findall(r"(?:^|[\s；;])(\d+)\.\s", text):
            max_n = max(max_n, int(m))
        # Chinese items: 一、 二、 三、 ...
        for m in re.finditer(r"([一二三四五六七八九十])、", text):
            val = _CN_ITEM.get(m.group(1), 0)
            max_n = max(max_n, val)
    return max_n


def extract_jian_e_jiao_qing(blocks: list[dict]) -> dict | None:
    """减额交清"""
    for block in blocks:
        text = block.get("text", "")
        c = _compact(text)
        if "减额交清" not in c:
            continue
        denial = any(k in c for k in ["不支持减额交清", "不允许减额交清", "不提供减额交清"])
        if denial:
            return build_candidate("减额交清", "其他责任__保单功能__减额交清", "不支持", 0.88, "rule: jian_e_jiao_qing_no", block)
        return build_candidate("减额交清", "其他责任__保单功能__减额交清", "支持", 0.85, "rule: jian_e_jiao_qing_yes", block)
    return None


def extract_zhi_ding_di_er_tou_bao_ren(blocks: list[dict]) -> dict | None:
    """指定第二投保人"""
    for block in blocks:
        text = block.get("text", "")
        if "第二投保人" in text or "指定第二投保人" in text:
            return build_candidate("指定第二投保人", "其他责任__保单功能__指定第二投保人", "支持", 0.88, "rule: di_er_tou_bao_ren_yes", block)
    return None


def extract_zhuan_huan_quan(blocks: list[dict]) -> dict | None:
    """转换权 — extract the closest matching standard value."""
    KNOWN_PATTERNS = [
        # (keywords_required, value)
        (["满期保险金", "转换", "年金"], "满期保险金可全部或部分转换成年金"),
        (["保险金", "现金价值", "转换", "年金"], "保险金、现金价值可全部或部分转换成年金"),
        (["账户价值", "转换", "年金"], None),  # → extract raw or fallback
        (["转换", "年金"], None),
    ]
    for block in blocks:
        text = block.get("text", "")
        c = _compact(text)
        if "转换" not in c:
            continue
        # Check each pattern in specificity order
        for required_kws, standard_val in KNOWN_PATTERNS:
            if not all(k in c for k in required_kws):
                continue
            if standard_val:
                return build_candidate("转换权", "其他责任__保单功能__转换权", standard_val, 0.8, "rule: zhuan_huan_quan_pattern", block)
            # Try to extract age/period condition for more specific matching
            age_m = re.search(r"(\d+)个保单周年[日后]", c)
            age2_m = re.search(r"(\d+)周岁后", c)
            if age_m and age2_m:
                val = f"第{age_m.group(1)}个保单周年日及以后且{age2_m.group(1)}周岁后的现金价值可全部或部分转换成年金"
            elif age_m:
                val = f"第{age_m.group(1)}个保单周年日及以后，账户价值可全部或部分转换成年金"
            else:
                val = "保险金、现金价值可全部或部分转换成年金"
            return build_candidate("转换权", "其他责任__保单功能__转换权", val, 0.72, "rule: zhuan_huan_quan_inferred", block)
    return None


def _narrow_loan_evidence(text: str) -> str:
    """Extract the clause segment around 保单贷款 from a long block."""
    compact = text.replace("\n", "")
    # Find "保单贷款" and extract surrounding context
    idx = compact.find("保单贷款")
    if idx < 0:
        return text[:500]
    # Look back for section number (e.g., "6.2" or "第十一条")
    start = idx
    for marker in [r"\d+\.\d+\s*保单贷款", r"第[一二三四五六七八九十百]+条\s*保单贷款"]:
        m = re.search(marker, compact[:idx + 10])
        if m:
            start = m.start()
            break
    else:
        start = max(0, idx - 20)
    # Look forward for the end of the loan clause (next section start or 600 chars)
    remainder = compact[idx:]
    end_offset = len(remainder)
    for end_marker in [r"\n\d+\.\d+\s", r"\n第[一二三四五六七八九十百]+条\s"]:
        m = re.search(end_marker, remainder[10:])
        if m:
            end_offset = min(end_offset, m.start() + 10)
    end_offset = min(end_offset, 600)
    return compact[start:idx + end_offset].strip()


def extract_bao_dan_dai_kuan(blocks: list[dict]) -> dict | None:
    """保单贷款"""
    # Phase 1: find explicit "不支持" in any block
    for block in blocks:
        c = _compact(block.get("text", ""))
        if "保单贷款" not in c:
            continue
        if any(k in c for k in ["不支持保单贷款", "不提供保单贷款", "本合同不支持"]):
            return build_candidate("保单贷款", "其他责任__保单功能__保单贷款", "不支持", 0.88, "rule: bao_dan_dai_kuan_no", block)

    # Phase 2: find best clause block with actual loan terms
    # Skip TOC, cover page, example blocks
    best_block = None
    best_evidence = None
    fallback_block = None
    for block in blocks:
        text = block.get("text", "")
        c = _compact(text)
        if "保单贷款" not in c:
            continue
        if _is_skip_block_by_tags(block):
            continue
        # Prefer blocks with substantive loan clause content
        has_substance = any(k in c for k in [
            "现金价值", "贷款金额", "贷款期限", "利率", "利息",
        ])
        if not has_substance:
            if fallback_block is None:
                fallback_block = block
            continue
        # Extract ratio, duration, min amount from this block
        ratio_m = re.search(r"(?:百分之[一二三四五六七八九十]+|(\d+)[%％])", c)
        months_m = re.search(r"(?:不超过|最长不超过|不得超过)(\d+)个月", c)
        cn_months_m = re.search(r"(?:不超过|最长不超过|不得超过)(六|十二)个月", c)
        days_m = re.search(r"(?:最长不超过|不超过|期限不超过)(\d+)[日天]", c)
        min_m = re.search(r"(?:最低贷款金额|最低金额)[^，。；]{0,40}?(\d+)元", c)
        cn_min_m = re.search(r"(?:最低贷款金额|最低金额)[^，。；]{0,40}?(?:人民币)([壹贰叁肆伍陆柒捌玖拾佰仟万]+)元", c)
        if ratio_m:
            # Parse ratio: handle both "百分之七十" and "80%"
            if ratio_m.group(1):
                ratio = ratio_m.group(1)
            else:
                # Chinese fraction: 百分之七十 etc
                cn_ratio = ratio_m.group(0).replace("百分之", "")
                ratio = str(_cn_num(cn_ratio)) if _cn_num(cn_ratio) else cn_ratio
            # Duration: prefer digit match, then Chinese match
            if months_m:
                duration = f"{months_m.group(1)}个月"
            elif days_m:
                duration = f"{days_m.group(1)}天"
            elif cn_months_m:
                cn_dur = cn_months_m.group(1)
                dur_val = {"六": "6", "十二": "12"}.get(cn_dur, cn_dur)
                duration = f"{dur_val}个月"
            else:
                duration = "6个月"
            # Min amount: prefer digit match, then Chinese match
            min_amount = None
            if min_m:
                min_amount = min_m.group(1)
            elif cn_min_m:
                cn_amt = cn_min_m.group(1)
                amt_val = _cn_currency(cn_amt)
                if amt_val:
                    min_amount = str(amt_val)
            parts = [f"最高贷款金额：申请时现金价值净额的{ratio}%"]
            if min_amount:
                parts.append(f"最低贷款金额：不少于人民币{min_amount}元")
            parts.append(f"每次贷款最长期限：{duration}")
            val = "；\n".join(parts)
            evidence = _narrow_loan_evidence(text)
            candidate = build_candidate("保单贷款", "其他责任__保单功能__保单贷款", val, 0.7, "rule: bao_dan_dai_kuan_extract", block)
            candidate["evidence_text"] = evidence
            return candidate
        # Has substance but no ratio — still better than fallback
        if best_block is None:
            best_block = block
            best_evidence = _narrow_loan_evidence(text)

    # Phase 3: return best available with evidence
    chosen = best_block or fallback_block
    if chosen:
        evidence = best_evidence or _narrow_loan_evidence(chosen.get("text", ""))
        candidate = build_candidate("保单贷款", "其他责任__保单功能__保单贷款", "支持（详见条款）", 0.6, "rule: bao_dan_dai_kuan_present", chosen)
        candidate["evidence_text"] = evidence
        return candidate
    return None


def _cn_num(s: str) -> int | None:
    """Parse simple Chinese number like 七十, 八十, 九十."""
    mapping = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
               "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
    if s == "十":
        return 10
    if len(s) == 2 and s[1] == "十":
        return mapping.get(s[0], 0) * 10
    if len(s) == 3 and s[1] == "十":
        return mapping.get(s[0], 0) * 10 + mapping.get(s[2], 0)
    return mapping.get(s)


def _cn_currency(s: str) -> int | None:
    """Parse Chinese currency like 伍佰, 壹仟."""
    mapping = {"壹": 1, "贰": 2, "叁": 3, "肆": 4, "伍": 5,
               "陆": 6, "柒": 7, "捌": 8, "玖": 9}
    if s == "伍佰":
        return 500
    if s == "壹仟":
        return 1000
    if s == "贰仟":
        return 2000
    # Simple two-char: X佰 or X仟
    if len(s) == 2 and s[1] == "佰":
        return mapping.get(s[0], 0) * 100
    if len(s) == 2 and s[1] == "仟":
        return mapping.get(s[0], 0) * 1000
    return None


def extract_jian_bao(blocks: list[dict]) -> dict | None:
    """减保"""
    for block in blocks:
        text = block.get("text", "")
        c = _compact(text)
        if "减保" not in c:
            continue
        if any(k in c for k in ["不涉及减保", "不支持减保", "不提供减保"]):
            return build_candidate("减保", "其他责任__保单功能__减保", "不涉及", 0.88, "rule: jian_bao_no", block)
        # Detect if "减额" is adjacent — avoid confusing with 减额交清
        if "减保申请" in c or "减少保额" in c or "减少基本保险金额" in c or re.search(r"减保[^额]", c):
            # Check for timing condition
            policy_yr_m = re.search(r"第(\d+)个保单周年日及以后", c)
            if policy_yr_m:
                val = f"第{policy_yr_m.group(1)}个保单周年日及以后可申请，且不低于申请时保司规定的最低金额"
            else:
                val = "有效期内可申请，且不低于申请时保司规定的最低金额"
            return build_candidate("减保", "其他责任__保单功能__减保", val, 0.68, "rule: jian_bao_extract", block)
    return None


# ─────────────────────────────────────────────────────────────────
# 免责数量 extractors
# ─────────────────────────────────────────────────────────────────

def _count_exemption_items(blocks: list[dict], section_keyword: str, end_keywords: list[str]) -> int:
    """Count numbered exemption clauses in the section following *section_keyword*."""
    in_section = False
    max_seq = 0
    for block in blocks:
        text = block.get("text", "")
        c = _compact(text)
        if not in_section:
            if section_keyword in c:
                in_section = True
            else:
                continue
        # Stop at next major section
        if any(k in c for k in end_keywords) and section_keyword not in c:
            break
        # Count items like （1）（2）… or (1)(2)... or 第一条/第二条
        items = re.findall(r"[（(](\d+)[）)]", text)
        for n in items:
            max_seq = max(max_seq, int(n))
        # Also match "第N项"
        items2 = re.findall(r"第([一二三四五六七八九十]+)项", text)
        for raw in items2:
            cn_map = {"一":1,"二":2,"三":3,"四":4,"五":5,"六":6,"七":7,"八":8,"九":9,"十":10}
            val = cn_map.get(raw)
            if val:
                max_seq = max(max_seq, val)
    return max_seq


def _make_exemption_count_candidate(field_name: str, coverage_path: str, count: int, blocks: list[dict]) -> dict | None:
    if count <= 0:
        return None
    note = f"rule: {field_name.replace('数量','')}_count"
    evidence_block = blocks[0] if blocks else {"block_id": None, "page": None, "text": ""}
    return build_candidate(field_name, coverage_path, f"{count}条", 0.82, note, evidence_block)


def extract_shen_gu_mian_ze_count(blocks: list[dict]) -> dict | None:
    """身故免责数量"""
    coverage_path = "责任免除（人身险）__身故免责__身故免责数量"
    # Strategy 1: find a dedicated 身故免责 section
    count = _count_exemption_items(blocks, "身故免责", ["疾病免责", "全残免责", "豁免免责", "附件", "释义"])
    if count > 0:
        return _make_exemption_count_candidate("身故免责数量", coverage_path, count, blocks)

    # Strategy 2: range pattern — "第（X）至第（Y）项...身故...不承担"
    # This catches clauses like "因下列第(1)至第(6)项情形之一导致被保险人身故的，
    # 我们不承担给付身故保险金的责任"
    for block in blocks:
        text = block.get("text", "")
        c = _compact(text)
        m = re.search(r"第[（(](\d+)[）)]至第[（(](\d+)[）)]项[^。；]*身故[^。；]*不承担", c)
        if m:
            n = int(m.group(2)) - int(m.group(1)) + 1
            return _make_exemption_count_candidate("身故免责数量", coverage_path, n, [block])

    # Strategy 3: 责任免除 section (by title_path or text start) with 身故 + numbered items
    # Also match split titles like "保险责任的免" (page-break artifact for 责任免除)
    for block in blocks:
        text = block.get("text", "")
        c = _compact(text)
        tp_str = "".join(str(t) for t in block.get("title_path", []))
        is_mianchu = ("责任免除" in tp_str or "免除" in tp_str or "免责" in tp_str
                      or "责任免除" in c[:80])
        if not is_mianchu:
            continue
        if "身故" not in c or "不承担" not in c:
            continue
        items = re.findall(r"[（(](\d+)[）)]", text)
        if items:
            n = max(int(x) for x in items)
            return _make_exemption_count_candidate("身故免责数量", coverage_path, n, [block])

    # Strategy 4: block with 身故 + 不承担 + 责任 + numbered items (broad fallback)
    for block in blocks:
        text = block.get("text", "")
        c = _compact(text)
        if "身故" in c and "不承担" in c and "责任" in c:
            items = re.findall(r"[（(](\d+)[）)]", text)
            if items:
                n = max(int(x) for x in items)
                if n >= 3:  # require at least 3 items to avoid false positives
                    return _make_exemption_count_candidate("身故免责数量", coverage_path, n, [block])
    return None


def _extract_event_exemption_count(blocks: list[dict], event_keywords: list[str],
                                    section_keywords: list[str], end_keywords: list[str],
                                    field_name: str, coverage_path: str) -> dict | None:
    """Generic extractor for N条 exemption count fields.

    Strategy cascade:
      1. Dedicated subsection by section_keywords
      2a. Arabic range: 第(X)至第(Y)项...event...不承担
      2b. Arabic range in 责任免除 section (不承担 in adjacent block)
      2c. Chinese range: 第一至第八项...event...不承担
      3. Same-block: 责任免除 + event + 不承担 + items
      4. Broad fallback: event + 不承担 + 责任 + >=3 items
      5. Cross-block intro: intro with event + 不承担, items in following blocks
      6. Cross-block intro via title_path (889-style)
      7. "除上述" additional items (adds to base from S5/S6)
    """
    # Strategy 1: dedicated subsection
    for kw in section_keywords:
        count = _count_exemption_items(blocks, kw, end_keywords)
        if count > 0:
            return _make_exemption_count_candidate(field_name, coverage_path, count, blocks)

    # Build event regex alternation
    evt_pattern = "|".join(re.escape(k) for k in event_keywords)

    # Strategy 2a: Arabic range — 第(X)至第(Y)项...{event}...不承担
    for block in blocks:
        c = _compact(block.get("text", ""))
        m = re.search(
            r"第[（(](\d+)[）)]至第[（(](\d+)[）)]项[^。；]*(?:" + evt_pattern + r")[^。；]*不承担", c
        )
        if m:
            n = int(m.group(2)) - int(m.group(1)) + 1
            return _make_exemption_count_candidate(field_name, coverage_path, n, [block])

    # Strategy 2b: Arabic range in 责任免除 section (不承担 may be in adjacent block)
    for block in blocks:
        c = _compact(block.get("text", ""))
        tp_str = "".join(str(t) for t in block.get("title_path", []))
        if not ("责任免除" in tp_str or "免除" in tp_str or "免责" in tp_str):
            continue
        m = re.search(
            r"第[（(](\d+)[）)]至第[（(](\d+)[）)]项[^。；]*(?:" + evt_pattern + r")", c
        )
        if m:
            n = int(m.group(2)) - int(m.group(1)) + 1
            return _make_exemption_count_candidate(field_name, coverage_path, n, [block])

    # Strategy 2c: Chinese numeral range — 第一至第八项...event...不承担
    for block in blocks:
        c = _compact(block.get("text", ""))
        m = re.search(
            r"第([一二三四五六七八九十]+)至第([一二三四五六七八九十]+)项[^。；]*(?:" + evt_pattern + r")[^。；]*不承担", c
        )
        if m:
            start = _CN_ITEM.get(m.group(1), 0)
            end = _CN_ITEM.get(m.group(2), 0)
            if end > start:
                return _make_exemption_count_candidate(field_name, coverage_path,
                                                       end - start + 1, [block])

    # Strategy 3: same-block — 责任免除 + event + 不承担 + cross-block items
    for idx, block in enumerate(blocks):
        text = block.get("text", "")
        c = _compact(text)
        tp_str = "".join(str(t) for t in block.get("title_path", []))
        is_mianchu = ("责任免除" in tp_str or "免除" in tp_str or "免责" in tp_str
                      or "责任免除" in c[:80])
        if not is_mianchu:
            continue
        if not any(k in c for k in event_keywords):
            continue
        if "不承担" not in c:
            continue
        n = _count_items_in_blocks(blocks, idx)
        if n > 0:
            return _make_exemption_count_candidate(field_name, coverage_path, n, [block])

    # Strategy 4: broad fallback — event + 不承担 + 责任 + >=3 same-block items
    for block in blocks:
        text = block.get("text", "")
        c = _compact(text)
        if not any(k in c for k in event_keywords):
            continue
        if "不承担" not in c or "责任" not in c:
            continue
        items = re.findall(r"[（(](\d+)[）)]", text)
        cn_items = [_CN_ITEM.get(m.group(1), 0) for m in re.finditer(r"([一二三四五六七八九十])、", text)]
        n = max([0] + [int(x) for x in items] + cn_items)
        if n >= 3:
            return _make_exemption_count_candidate(field_name, coverage_path, n, [block])

    # Strategies 5-7: cross-block counting with intro detection
    # Collect all intro blocks: (idx, is_extra, item_count)
    intros: list[tuple[int, bool, int]] = []

    def _resolve_cross_ref(c: str, idx: int) -> int | None:
        """Handle '因本条第X款情形之一' cross-references.

        Returns the item count from the referenced paragraph, or None.
        """
        m = re.search(r"本条第([一二三四五六七八九十]+)款", c)
        if not m:
            return None
        target_ord = _CN_ITEM.get(m.group(1), 0)
        if target_ord < 1:
            return None
        # Scan backwards for the Nth paragraph intro: "N、因下列情形之一...不承担"
        cn_ord = {v: k for k, v in _CN_ITEM.items()}
        target_marker = cn_ord.get(target_ord, "")
        if not target_marker:
            return None
        for bi in range(idx - 1, max(idx - 30, -1), -1):
            bc = _compact(blocks[bi].get("text", ""))
            if f"{target_marker}、" in bc and "情形之一" in bc:
                return _count_items_in_blocks(blocks, bi)
        return None

    def _check_intro(idx: int, block: dict) -> None:
        c = _compact(block.get("text", ""))
        # Check this block + next 2 for event + 不承担
        window_intro = c
        for wi in range(1, 3):
            if idx + wi < len(blocks):
                window_intro += _compact(blocks[idx + wi].get("text", ""))
        if "不承担" not in window_intro:
            return
        if not any(k in window_intro for k in event_keywords):
            return
        # Try cross-reference resolution first (e.g. "因本条第二款情形之一")
        ref_n = _resolve_cross_ref(c, idx)
        if ref_n is not None and ref_n >= 1:
            intros.append((idx, False, ref_n))
            return
        n = _count_items_in_blocks(blocks, idx)
        if n < 1:
            return
        is_extra = "除上述" in c
        intros.append((idx, is_extra, n))

    # Strategy 5: 责任免除 context (broad detection)
    for idx, block in enumerate(blocks):
        c = _compact(block.get("text", ""))
        tp_str = "".join(str(t) for t in block.get("title_path", []))
        is_mianchu = ("责任免除" in tp_str or "免除" in tp_str or "免责" in tp_str
                      or "责任免除" in c[:80] or "除外责任" in c[:80]
                      or "不保什么" in tp_str)
        if is_mianchu:
            _check_intro(idx, block)

    # Strategy 6: title_path-based intro (889-style)
    for idx, block in enumerate(blocks):
        tp_str = "".join(str(t) for t in block.get("title_path", []))
        tp_c = _compact(tp_str)
        if "不承担" in tp_c and any(k in tp_c for k in event_keywords):
            _check_intro(idx, block)

    # Strategy 7: direct intro pattern (no context needed)
    for idx, block in enumerate(blocks):
        c = _compact(block.get("text", ""))
        if "情形之一" in c or "以下情形" in c:
            _check_intro(idx, block)

    # Compute total: best base + extras
    base_count = 0
    extra_count = 0
    best_block = None
    for idx, is_extra, n in intros:
        if is_extra:
            if n >= 1:
                extra_count = max(extra_count, n)
        else:
            if n >= 3 and n > base_count:
                base_count = n
                best_block = blocks[idx]

    total = base_count + extra_count
    if total >= 3 and best_block is not None:
        return _make_exemption_count_candidate(field_name, coverage_path, total, [best_block])
    return None


def extract_ji_bing_mian_ze_count(blocks: list[dict]) -> dict | None:
    """疾病免责数量"""
    return _extract_event_exemption_count(
        blocks,
        event_keywords=["重大疾病", "疾病", "轻症", "中症"],
        section_keywords=["疾病免责", "重大疾病免责", "疾病责任免除"],
        end_keywords=["身故免责", "全残免责", "豁免免责", "附件", "释义"],
        field_name="疾病免责数量",
        coverage_path="责任免除（人身险）__疾病免责__疾病免责数量",
    )


def extract_huo_mian_mian_ze_count(blocks: list[dict]) -> dict | None:
    """豁免免责数量"""
    return _extract_event_exemption_count(
        blocks,
        event_keywords=["豁免"],
        section_keywords=["豁免免责", "保险费豁免免责"],
        end_keywords=["身故免责", "疾病免责", "全残免责", "附件", "释义"],
        field_name="豁免免责数量",
        coverage_path="责任免除（人身险）__豁免免责__豁免免责数量",
    )


def extract_quan_can_mian_ze_count(blocks: list[dict]) -> dict | None:
    """全残免责数量"""
    return _extract_event_exemption_count(
        blocks,
        event_keywords=["全残"],
        section_keywords=["全残免责", "全残责任免除"],
        end_keywords=["身故免责", "疾病免责", "豁免免责", "附件", "释义"],
        field_name="全残免责数量",
        coverage_path="责任免除（人身险）__全残免责__全残免责数量",
    )


# ─────────────────────────────────────────────────────────────────
# 豁免开关 extractors
# ─────────────────────────────────────────────────────────────────

def _build_huo_mian_value(text: str, event_word: str, is_policyholder: bool) -> str | None:
    """
    Build a formatted waiver value from clause text.
    event_word: '身故' | '全残' | '重疾' | '中症' | '轻症'
    is_policyholder: True for 投保人, False for 被保险人
    """
    c = _compact(text)
    if event_word not in c or "豁免" not in c:
        return None

    # Waiver scope
    if "主附险余期保费" in c or ("主附险" in c and "余期保费" in c):
        scope = "豁免主附险余期保费"
    elif "主险余期保费" in c or ("主险" in c and "余期保费" in c):
        scope = "豁免主险余期保费"
    elif "约定合同" in c and "余期保费" in c:
        scope = "豁免约定合同余期保费"
    else:
        scope = "豁免余期保费"

    if is_policyholder:
        # 投保人豁免 — usually triggered by accident
        has_accident = "意外" in c
        days_m = re.search(r"(\d+)[天日]内", c)
        age_m = re.search(r"(\d+)周岁(?:前|保单周年日)", c)

        if has_accident and days_m and age_m:
            return f"{age_m.group(1)}周岁前意外且{days_m.group(1)}天内{event_word}，{scope}"
        if has_accident and days_m:
            return f"意外且{days_m.group(1)}天内{event_word}，{scope}"
        if has_accident:
            return f"意外{event_word}{scope}"
        if age_m:
            return f"{age_m.group(1)}周岁前{event_word}，{scope}"
        return f"{event_word}{scope}"
    else:
        # 被保险人豁免 — usually after waiting period
        has_waiting = "等待期" in c or "观察期" in c
        has_accident = "意外" in c

        if has_accident and has_waiting:
            return f"意外或等待期后{event_word}，{scope}"
        if has_waiting:
            return f"等待期后{event_word}，{scope}"
        if has_accident:
            return f"意外或{event_word}，{scope}"
        return f"{event_word}，{scope}"


def _narrow_policyholder_clause(text: str, trigger: str = "身故豁免") -> str:
    """Extract the sub-clause starting at trigger or at first '投保人...身故/豁免' sentence."""
    idx = text.find(trigger)
    if idx == -1:
        # fallback: find sentence containing 投保人 + 身故
        for sep in ["。", "\n"]:
            for sent in text.split(sep):
                sc = re.sub(r"\s+", "", sent)
                if "投保人" in sc and "身故" in sc and "豁免" in sc:
                    return sent.strip()
        return text
    # Walk back to sentence boundary
    start = max(0, idx - 50)
    for sep in ["。", "\n"]:
        pos = text.rfind(sep, 0, idx)
        if pos != -1 and pos + 1 > start:
            start = pos + 1
    # Walk forward to end of this sentence
    end = min(len(text), idx + 200)
    for sep in ["。", "\n"]:
        pos = text.find(sep, idx)
        if pos != -1 and pos + 1 < end:
            end = pos + 1
    return text[start:end].strip()


def extract_tou_bao_ren_shen_gu_huo_mian(blocks: list[dict]) -> dict | None:
    """投保人身故豁免"""
    for block in blocks:
        text = block.get("text", "")
        c = _compact(text)
        if "投保人" not in c and "身故豁免" not in c:
            continue
        if "身故" not in c or "豁免" not in c:
            continue
        # Avoid blocks about 被保险人 身故 only
        if "被保险人" in c and "投保人" not in c:
            continue
        # Block must contain waiver clause substance, not just footnotes/申请人 lists
        if not _is_valid_waiver_clause_block(c):
            continue
        # Require an explicit 投保人 waiver section — not just incidental mention in 责任免除
        if "被保险人" in c and "投保人" in c:
            has_policyholder_waiver_section = (
                "投保人身故豁免" in c
                or "投保人豁免保险费" in c
                or bool(re.search(r"投保人[^。]{0,20}(?:身故|意外)[^。]{0,40}豁免", c))
            )
            if not has_policyholder_waiver_section:
                continue
        # Narrow text to the 身故豁免 sub-clause to avoid contamination from adjacent sections
        narrow_text = _narrow_policyholder_clause(text, "身故豁免")
        val = _build_huo_mian_value(narrow_text, "身故", is_policyholder=True)
        if val:
            return build_candidate("投保人身故豁免", "豁免责任__投保人豁免__投保人身故豁免", val, 0.78, "rule: tou_bao_ren_shen_gu_huo_mian", block)
    return None


def extract_tou_bao_ren_quan_can_huo_mian(blocks: list[dict]) -> dict | None:
    """投保人全残豁免"""
    for block in blocks:
        text = block.get("text", "")
        c = _compact(text)
        if "投保人" not in c and "全残豁免" not in c:
            continue
        if "全残" not in c or "豁免" not in c:
            continue
        if "被保险人" in c and "投保人" not in c:
            continue
        val = _build_huo_mian_value(text, "全残", is_policyholder=True)
        if val:
            return build_candidate("投保人全残豁免", "豁免责任__投保人豁免__投保人全残豁免", val, 0.78, "rule: tou_bao_ren_quan_can_huo_mian", block)
    return None


_WAIVER_CLAUSE_MARKERS = frozenset(["确诊", "罹患", "等待期", "观察期", "意外"])


def _is_valid_waiver_clause_block(compact_text: str) -> bool:
    """Block must contain at least one trigger/clause marker; skip intro/summary blocks."""
    return any(m in compact_text for m in _WAIVER_CLAUSE_MARKERS)


def _is_skip_block_by_tags(block: dict) -> bool:
    """Use _tags from block_tagger when available."""
    tags = block.get("_tags")
    if tags:
        return not tags["is_matchable"]
    # Legacy fallback
    c = _compact(block.get("text", ""))
    return any(m in c for m in ("条款目录", "阅读指引", "举例"))


def extract_bei_bao_xian_ren_zhong_ji_huo_mian(blocks: list[dict]) -> dict | None:
    """被保险人重疾豁免"""
    for block in blocks:
        text = block.get("text", "")
        c = _compact(text)
        if _is_skip_block_by_tags(block):
            continue
        # Detect CI waiver clause:
        # 1. "重疾豁免" anywhere (covers standalone and compound "轻症重疾豁免")
        # 2. "重大疾病/重度疾病" near "豁免" (unified waiver clause, e.g. 851A)
        has_ci_waiver_clause = (
            "重疾豁免" in c
            or bool(re.search(r"(?:重大疾病|重度疾病)[^。]{0,80}豁免", c))
        )
        if not has_ci_waiver_clause:
            continue
        if not _is_valid_waiver_clause_block(c):
            continue
        # Exclude 责任免除 clauses ("不承担...豁免保险费的责任")
        if "不承担" in c and c.index("不承担") < c.index("豁免"):
            continue
        # Normalize 重大疾病/重度疾病 → 重疾 for value builder so output matches standard values
        text_for_value = text
        if "重疾" not in c:
            text_for_value = text.replace("重大疾病", "重疾").replace("重度疾病", "重疾")
        val = _build_huo_mian_value(text_for_value, "重疾", is_policyholder=False)
        if val:
            return build_candidate("被保险人重疾豁免", "豁免责任__被保险人豁免__被保险人重疾豁免", val, 0.75, "rule: bei_bao_xian_ren_zhong_ji_huo_mian", block)
    return None


def extract_bei_bao_xian_ren_zhong_zheng_huo_mian(blocks: list[dict]) -> dict | None:
    """被保险人中症豁免"""
    for block in blocks:
        text = block.get("text", "")
        c = _compact(text)
        if _is_skip_block_by_tags(block):
            continue
        if "中症豁免" not in c and not ("中症" in c and "豁免" in c) and not ("中度疾病" in c and "豁免" in c):
            continue
        if not _is_valid_waiver_clause_block(c):
            continue
        val = _build_huo_mian_value(text, "中症", is_policyholder=False)
        if val:
            return build_candidate("被保险人中症豁免", "豁免责任__被保险人豁免__被保险人中症豁免", val, 0.75, "rule: bei_bao_xian_ren_zhong_zheng_huo_mian", block)
    return None


def extract_bei_bao_xian_ren_qing_zheng_huo_mian(blocks: list[dict]) -> dict | None:
    """被保险人轻症豁免"""
    for block in blocks:
        text = block.get("text", "")
        c = _compact(text)
        if _is_skip_block_by_tags(block):
            continue
        if "轻症豁免" not in c and not ("轻症" in c and "豁免" in c) and not ("轻度疾病" in c and "豁免" in c):
            continue
        if not _is_valid_waiver_clause_block(c):
            continue
        val = _build_huo_mian_value(text, "轻症", is_policyholder=False)
        if val:
            return build_candidate("被保险人轻症豁免", "豁免责任__被保险人豁免__被保险人轻症豁免", val, 0.75, "rule: bei_bao_xian_ren_qing_zheng_huo_mian", block)
    return None


# ---------------------------------------------------------------------------
# 保障说明提取 — v0 implementation based on standard values dictionary
# NOTE: v0 实现基于标准值词典 + 当前条款样本反推，非规则文档完整版本
# ---------------------------------------------------------------------------

# Chinese number words → Arabic for payout multipliers
_CN_MULT = {"两": 2, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


def _find_waiting_period_block(blocks: list[dict], disease_keywords: list[str]) -> dict | None:
    """Find the block describing waiting period behavior for a disease type.

    Returns the block containing "等待期内" + disease keyword + action (退还/不承担).
    Prefers blocks with "等待期内" over generic "等待期" mentions.
    """
    # Pass 1: blocks with "等待期内" + disease/保险事故 + action
    for block in blocks:
        text = block.get("text", "")
        c = _compact(text)
        if _is_skip_block_by_tags(block):
            continue
        if "等待期内" not in c:
            continue
        has_disease = any(kw in c for kw in disease_keywords)
        if not has_disease and "保险事故" not in c:
            continue
        # "退还" = refund; "不承担" = no liability; "给付" + premium ref = pay premium amount
        has_premium = any(kw in c for kw in ("已交保", "所交保", "已支付", "已交纳", "已付保"))
        has_action = "退还" in c or "不承担" in c or ("给付" in c and has_premium)
        if not has_action:
            continue
        if "不承担给付" in c:
            continue
        return block

    # Pass 2: blocks with "等待期" + consequence keywords (退还/不承担) for generic preambles
    # e.g. "等待期...不承担保险责任...退还...保险费...合同终止"
    for block in blocks:
        text = block.get("text", "")
        c = _compact(text)
        if _is_skip_block_by_tags(block):
            continue
        if "等待期" not in c:
            continue
        if "退还" not in c and "不承担" not in c:
            continue
        if "不承担给付" in c:
            continue
        has_disease = any(kw in c for kw in disease_keywords)
        if not has_disease and "保险事故" not in c:
            continue
        # Must describe consequence, not just mention "等待期" in a list/intro
        if len(c) < 40:
            continue
        return block
    return None


def _parse_waiting_action(compact_text: str, disease_word: str) -> str | None:
    """Parse what happens during waiting period for the given disease.

    Returns standardized action string like "退还已交保费" or "不承担保险责任，合同继续有效".
    """
    # Pattern 1: 退还已交保费 (most common for 重疾)
    # Covers: 已交保险费/已交保费/所交保险费/已支付的保险费/已交纳的保险费/已付保险费
    has_premium_ref = any(kw in compact_text for kw in ("已交保", "所交保", "已支付", "已交纳", "已付保"))
    if "退还" in compact_text and has_premium_ref:
        if "主附险" in compact_text:
            return "退还主附险已交保费"
        if "附加险" in compact_text and "主险" not in compact_text:
            return "退还附加险已交保费"
        return "退还已交保费"

    # Pattern 2: 不承担保险责任
    if "不承担" in compact_text:
        # If contract terminates AND there's a refund, treat as "退还已交保费"
        # (e.g. "不承担保险责任，退还保费，合同终止" for 重疾 waiting period)
        contract_terminates = "合同终止" in compact_text or "合同效力终止" in compact_text
        if contract_terminates:
            if "退还" in compact_text and has_premium_ref:
                if "主附险" in compact_text:
                    return "退还主附险已交保费"
                if "附加险" in compact_text and "主险" not in compact_text:
                    return "退还附加险已交保费"
                return "退还已交保费"
            return None  # fall through to other patterns
        scope = ""
        if f"{disease_word}及{disease_word}豁免责任终止" in compact_text:
            scope = f"，{disease_word}及{disease_word}豁免责任终止，合同继续有效"
        elif f"{disease_word}责任终止" in compact_text:
            scope = f"，{disease_word}责任终止，合同继续有效"
        elif "重症、特药医疗及豁免责任终止" in compact_text:
            scope = "，重症、特药医疗及豁免责任终止，合同继续有效"
        elif "合同继续有效" in compact_text:
            scope = "，合同继续有效"
        return f"不承担保险责任{scope}"

    # Pattern 3: 给付 X% 已交保费 (e.g. 给付110%已交保费)
    m = re.search(r"给付(\d+)[%％][^。]*?(?:已交保|已支付|已交纳|已付保|所交保)", compact_text)
    if m:
        return f"给付{m.group(1)}%已交保费"

    # Pattern 4: 给付...已交保费 without percentage (= 退还已交保费 semantically)
    # e.g. "按照本合同已交纳的保险费...给付" or "给付...已交保费"
    if "给付" in compact_text and has_premium_ref:
        # Only if there's no "基本保险金额" (which would indicate a payout, not refund)
        if "基本保险金额" not in compact_text and "基本保额" not in compact_text:
            return "退还已交保费"

    return None


def _parse_payout_action(compact_text: str, disease_word: str) -> str | None:
    """Parse what happens after waiting period for the given disease.

    Returns standardized payout string like "给付基本保额" or "给付2倍基本保额".
    """
    # Normalize: 基本保险金额 → used for matching, output as 基本保额
    # First check for age-based split
    age_m = re.search(
        r"(?:未满|不满)(\d+)周岁.*?基本保险金额的?(\d+)倍.*?"
        r"(?:已满|满)(\d+)周岁.*?基本保险金额",
        compact_text,
    )
    if age_m:
        age = age_m.group(1)
        mult = age_m.group(2)
        # Check if second part also has a multiplier
        after_age = compact_text[age_m.start(3):]
        mult2_m = re.search(r"基本保险金额的?(\d+)倍", after_age)
        if mult2_m:
            return f"意外或等待期后：\n{age}周岁前{disease_word}，给付{mult}倍基本保额；\n{age}周岁及以后{disease_word}，给付{mult2_m.group(1)}倍基本保额"
        # Check for complex formula (两金取大/三金取大)
        if "两金取大" in after_age or "三金取大" in after_age:
            return None  # Too complex for v0
        return f"意外或等待期后：\n{age}周岁前{disease_word}，给付{mult}倍基本保额；\n{age}周岁及以后{disease_word}，给付基本保额"

    # Check for Chinese multiplier age split: e.g. "基本保险金额的两倍"
    age_cn = re.search(
        r"(?:未满|不满)(\d+)周岁.*?基本保险金额的?([两二三四五六七八九十])倍.*?"
        r"(?:已满|满)(\d+)周岁",
        compact_text,
    )
    if age_cn:
        age = age_cn.group(1)
        mult = _CN_MULT.get(age_cn.group(2), 2)
        return f"意外或等待期后：\n{age}周岁前{disease_word}，给付{mult}倍基本保额；\n{age}周岁及以后{disease_word}，给付基本保额"

    # Check for 60周岁-style split with 两金取大/三金取大
    age60_m = re.search(
        r"(?:未满|不满)(\d+)周岁.*?(?:两金取大|较大者).*?"
        r"(?:已满|满)\1周岁.*?(?:三金取大|较大者)",
        compact_text,
    )
    if age60_m:
        return None  # Too complex for v0

    # Multi-pay: "首次至第N次，分别给付X%基本保额" or "首次至第N次，分别给付基本保额"
    multi_m = re.search(r"首次至第([一二三四五六七八九十\d]+)次", compact_text)
    if multi_m:
        times_raw = multi_m.group(1)
        if times_raw.isdigit():
            times_str = f"第{times_raw}次"
        else:
            cn_val = _CN_ITEM.get(times_raw)
            if cn_val:
                times_str = f"第{times_raw}次"
            else:
                times_str = f"第{times_raw}次"

    # Check percentage payout: "基本保险金额的X%"
    pct_m = re.search(r"基本保险金额的?(\d+)[%％]", compact_text)
    if pct_m:
        pct = int(pct_m.group(1))
        # 100% = give full amount = "给付基本保额"
        if pct == 100:
            if multi_m:
                return f"首次至第{multi_m.group(1)}次，分别给付基本保额"
            return "给付基本保额"
        # ≥200% and clean multiple of 100 → use multiplier format (e.g. 300% → 3倍)
        if pct >= 200 and pct % 100 == 0:
            mult_val = pct // 100
            if multi_m:
                return f"首次至第{multi_m.group(1)}次，分别给付{mult_val}倍基本保额"
            return f"给付{mult_val}倍基本保额"
        if multi_m:
            times_raw = multi_m.group(1)
            return f"首次至第{times_raw}次，分别给付{pct}%基本保额"
        return f"给付{pct}%基本保额"

    # Check multiplier payout: "基本保险金额的X倍" or "X倍...基本保险金额"
    mult_m = re.search(r"基本保险金额的?(\d+)倍", compact_text)
    if not mult_m:
        mult_cn = re.search(r"基本保险金额的?([两二三四五六七八九十])倍", compact_text)
        if mult_cn:
            mult_val = _CN_MULT.get(mult_cn.group(1), 2)
            if multi_m:
                return f"首次至第{multi_m.group(1)}次，分别给付{mult_val}倍基本保额"
            return f"给付{mult_val}倍基本保额"
    elif mult_m:
        mult_val = mult_m.group(1)
        if multi_m:
            return f"首次至第{multi_m.group(1)}次，分别给付{mult_val}倍基本保额"
        return f"给付{mult_val}倍基本保额"

    # Disease-specific amount name BEFORE generic "基本保险金额" check
    # e.g. "重大疾病保险金额", "轻症疾病基本保险金额", "中症疾病保险金额"
    # These are NOT "基本保险金额" but a dedicated amount for that disease type
    disease_amount_kws = {
        "重疾": ["重大疾病基本保险金额", "重度疾病基本保险金额", "重大疾病保险金额", "重度疾病保险金额", "重疾保险金额"],
        "轻症": ["轻症疾病基本保险金额", "轻度疾病基本保险金额", "轻症疾病保险金额", "轻度疾病保险金额", "轻症保险金额"],
        "中症": ["中症疾病基本保险金额", "中度疾病基本保险金额", "中症疾病保险金额", "中度疾病保险金额", "中症保险金额"],
    }
    for kw in disease_amount_kws.get(disease_word, []):
        if kw in compact_text:
            paren_m = re.search(re.escape(kw) + r"[（(]([^）)]+)[）)]", compact_text)
            if paren_m:
                return f"给付{disease_word}基本保额（{paren_m.group(1)}）"
            return f"给付{disease_word}基本保额"

    # Simple payout: "基本保险金额" without percentage or multiplier (generic)
    if "基本保险金额" in compact_text or "基本保额" in compact_text:
        if multi_m:
            return f"首次至第{multi_m.group(1)}次，分别给付基本保额"
        return "给付基本保额"

    # Last resort: generic "保险金额" (without 基本) — treat as basic amount
    if "保险金额" in compact_text:
        if multi_m:
            return f"首次至第{multi_m.group(1)}次，分别给付基本保额"
        return "给付基本保额"

    return None


def _build_bao_zhang_shuo_ming(blocks: list[dict], disease_word: str,
                                disease_keywords: list[str],
                                benefit_keywords: list[str]) -> tuple[str | None, dict | None]:
    """Build 保障说明 value for a disease type.

    Returns (value_string, evidence_block) or (None, None).
    """
    # Strategy:
    # 1. Find post-waiting benefit block (primary evidence)
    # 2. Find waiting period block (may be same or separate)
    # 3. Construct: "等待期内{disease}，{waiting_action}；\n意外或等待期后{disease}，{payout_action}"

    benefit_block = None
    benefit_compact = None

    for block in blocks:
        text = block.get("text", "")
        c = _compact(text)
        if _is_skip_block_by_tags(block):
            continue
        if not any(kw in c for kw in benefit_keywords):
            continue
        if "给付" not in c:
            continue
        # Skip exclusion blocks
        if "不承担给付" in c:
            continue
        # Skip blocks that are just cross-references (too short)
        if len(c) < 30:
            continue
        # Skip example blocks (小王, 举例)
        if "小王" in c or "举例" in c or "示例" in c:
            continue
        # Must have payout amount info
        if "保险金额" not in c and "保额" not in c and "已交保" not in c and "所交保" not in c:
            continue
        benefit_block = block
        benefit_compact = c
        break

    if not benefit_block:
        return None, None

    # Try to parse payout from the benefit block
    payout = _parse_payout_action(benefit_compact, disease_word)
    if not payout:
        return None, None

    # Find waiting period action
    # First check if the benefit block itself contains waiting period info
    waiting_action = None
    if "等待期内" in benefit_compact:
        waiting_action = _parse_waiting_action(benefit_compact, disease_word)

    # If not found in benefit block, search for a separate waiting period block
    if not waiting_action:
        wp_block = _find_waiting_period_block(blocks, disease_keywords)
        if wp_block:
            wp_compact = _compact(wp_block.get("text", ""))
            waiting_action = _parse_waiting_action(wp_compact, disease_word)

    # Also check for combined blocks: "一百八十日内" = waiting period
    if not waiting_action and benefit_compact:
        # Pattern: 1464-style "X日内...给付...保险费...X日后...给付...保险金额"
        day_m = re.search(r"(?:一百八十|一百二十|九十|180|120|90)日内", benefit_compact)
        if day_m:
            # The text before "日后" describes waiting action, after describes payout
            # Try to parse waiting action from the segment before "日后"
            day_after_m = re.search(r"(?:一百八十|一百二十|九十|180|120|90)日后", benefit_compact)
            if day_after_m:
                waiting_segment = benefit_compact[:day_after_m.start()]
                if "已交保" in waiting_segment or "所交保" in waiting_segment:
                    if "退还" in waiting_segment:
                        waiting_action = "退还已交保费"
                    else:
                        waiting_action = "退还已交保费"  # "给付...已交保费" = same semantics

    # Build the value
    # If payout already includes the full "意外或等待期后：" prefix (age-split), don't duplicate
    payout_is_compound = payout.startswith("意外或等待期后：")
    if waiting_action and payout:
        if payout_is_compound:
            value = f"等待期内{disease_word}，{waiting_action}；\n{payout}"
        else:
            value = f"等待期内{disease_word}，{waiting_action}；\n意外或等待期后{disease_word}，{payout}"
    elif payout:
        if payout_is_compound:
            value = payout
        else:
            value = f"意外或等待期后{disease_word}，{payout}"
    else:
        return None, None

    return value, benefit_block


def extract_zhong_ji_bao_zhang_shuo_ming(blocks: list[dict]) -> dict | None:
    """重疾保障说明 — v0 based on standard values dictionary + clause samples."""
    value, block = _build_bao_zhang_shuo_ming(
        blocks,
        disease_word="重疾",
        disease_keywords=["重大疾病", "重度疾病", "重疾"],
        benefit_keywords=["重大疾病保险金", "重度疾病保险金"],
    )
    if value and block:
        return build_candidate(
            "重疾保障说明", "疾病责任__重疾责任__重疾保障说明",
            value, 0.65, "rule: zhong_ji_bao_zhang_shuo_ming_v0", block,
        )
    return None


def extract_qing_zheng_bao_zhang_shuo_ming(blocks: list[dict]) -> dict | None:
    """轻症保障说明 — v0 based on standard values dictionary + clause samples."""
    value, block = _build_bao_zhang_shuo_ming(
        blocks,
        disease_word="轻症",
        disease_keywords=["轻症疾病", "轻度疾病", "轻症"],
        benefit_keywords=["轻症疾病保险金", "轻度疾病保险金", "轻症重疾保险金"],
    )
    if value and block:
        return build_candidate(
            "轻症保障说明", "疾病责任__轻症责任__轻症保障说明",
            value, 0.65, "rule: qing_zheng_bao_zhang_shuo_ming_v0", block,
        )
    return None


def extract_zhong_zheng_bao_zhang_shuo_ming(blocks: list[dict]) -> dict | None:
    """中症保障说明 — v0 based on standard values dictionary + clause samples."""
    value, block = _build_bao_zhang_shuo_ming(
        blocks,
        disease_word="中症",
        disease_keywords=["中症疾病", "中度疾病", "中症"],
        benefit_keywords=["中症疾病保险金", "中度疾病保险金"],
    )
    if value and block:
        return build_candidate(
            "中症保障说明", "疾病责任__中症责任__中症保障说明",
            value, 0.65, "rule: zhong_zheng_bao_zhang_shuo_ming_v0", block,
        )
    return None


# ---------------------------------------------------------------------------
# 合同名称 (contract/clause name)
# ---------------------------------------------------------------------------
_COMPANY_SUFFIX_RE = re.compile(
    r"(?:保险股份有限公司|保险有限公司|人寿保险公司|财产保险公司)"
)
_CLAUSE_NAME_RE = re.compile(
    r"([\u4e00-\u9fffA-Za-z0-9（）()·「」\u300a\u300b]+保险[\u4e00-\u9fffA-Za-z0-9（）()]*?条款)"
)


_BEIAN_RE = re.compile(r"[\[〔\[]\d{4}[\]〕\]][\u4e00-\u9fff]+\d+号")
_NOISE_PREFIX_RE = re.compile(r"^[A-Za-z0-9]+")


def _clean_contract_name(raw: str) -> str | None:
    """Clean and validate a raw contract name candidate."""
    name = raw
    # Strip leading alphanumeric codes (e.g. "BA20220609", "1")
    name = _NOISE_PREFIX_RE.sub("", name)
    # Strip company name suffix (e.g. "XXX保险股份有限公司")
    cm = _COMPANY_SUFFIX_RE.search(name)
    if cm:
        name = name[cm.end():]
    # Strip trailing noise
    name = re.sub(r"(?:阅读指引|阅读提示).*$", "", name)
    name = re.sub(r"[A-Z]{2,}.*$", "", name)
    # Remove duplicate company name prefix (e.g. "招商信诺招商信诺..." → "招商信诺...")
    # Also handle single-char gap: "招商信诺1招商信诺..." → "招商信诺..."
    for pfx_len in range(2, min(8, len(name) // 2 + 1)):
        pfx = name[:pfx_len]
        if name[pfx_len:].startswith(pfx):
            name = name[pfx_len:]
            break
        if len(name) > pfx_len + 1 and name[pfx_len + 1:].startswith(pfx):
            name = name[pfx_len + 1:]
            break
    # If an earlier "条款" exists mid-name, take substring from after it
    # e.g. "神奇宝贝重疾条款泰康重大疾病保险条款" → "泰康重大疾病保险条款"
    if name.count("条款") > 1:
        last_idx = name.rfind("条款")
        mid_idx = name.find("条款")
        if mid_idx < last_idx:
            tail = name[mid_idx + 2:]
            if "保险" in tail and tail.endswith("条款") and len(tail) >= 8:
                name = tail
    # Must end with 条款 and contain 保险
    if not name.endswith("条款") or "保险" not in name:
        return None
    # Reject generic phrases
    if any(kw in name for kw in ("保险责任", "免除保险", "保险期间", "保险条款中", "几个保险")):
        return None
    # Reject if starts with non-CJK
    if name and not ("\u4e00" <= name[0] <= "\u9fff"):
        return None
    if len(name) < 8:
        return None
    return name


def extract_contract_name(blocks: list[dict]) -> dict | None:
    """合同名称 — extract official clause name from first ~80 blocks."""
    for block in blocks[:80]:
        text = block.get("text", "")
        c = _compact(text)
        # Strip noise prefixes and 备案号
        c = re.sub(r"请扫描以查询验证条款", "", c)
        c = _BEIAN_RE.sub("", c)
        for m in _CLAUSE_NAME_RE.finditer(c):
            name = _clean_contract_name(m.group(1))
            if name:
                return build_candidate(
                    "合同名称（条款名称）", "基本信息__合同名称（条款名称）", name, 0.90,
                    "rule: contract_name_from_title", block,
                )
    return None


def extract_for_product(blocks: list[dict]) -> tuple[list[dict], list[str], list[str]]:
    """Return (candidates, missing_fields, no_coverage_fields).

    no_coverage_fields: fields where the relevant keyword was never found in
    any block — strongly suggests the product has no such coverage, rather than
    a system extraction miss.
    """
    # Pre-compute full-text presence of coverage keywords
    all_text = " ".join(b.get("text", "") for b in blocks)
    keyword_present: dict[str, bool] = {
        field: any(kw in all_text for kw in kws)
        for field, kws in COVERAGE_PRESENCE_KEYWORDS.items()
    }

    extractors = [
        extract_ci_pay_times,
        extract_ci_count,
        extract_mild_pay_times,
        extract_mild_count,
        extract_mild_group,
        extract_middle_pay_times,
        extract_middle_count,
        extract_middle_group,
        # 保单功能
        extract_jian_e_jiao_qing,
        extract_zhi_ding_di_er_tou_bao_ren,
        extract_zhuan_huan_quan,
        extract_bao_dan_dai_kuan,
        extract_jian_bao,
        # 免责数量
        extract_shen_gu_mian_ze_count,
        extract_ji_bing_mian_ze_count,
        extract_huo_mian_mian_ze_count,
        extract_quan_can_mian_ze_count,
        # 豁免开关
        extract_tou_bao_ren_shen_gu_huo_mian,
        extract_tou_bao_ren_quan_can_huo_mian,
        extract_bei_bao_xian_ren_zhong_ji_huo_mian,
        extract_bei_bao_xian_ren_zhong_zheng_huo_mian,
        extract_bei_bao_xian_ren_qing_zheng_huo_mian,
        # 保障说明
        extract_zhong_ji_bao_zhang_shuo_ming,
        extract_qing_zheng_bao_zhang_shuo_ming,
        extract_zhong_zheng_bao_zhang_shuo_ming,
        # 基本信息
        extract_contract_name,
    ]
    candidates = []
    present = set()
    for extractor in extractors:
        candidate = extractor(blocks)
        if candidate:
            candidates.append(candidate)
            present.add(candidate["coverage_name"])

    missing = []
    no_coverage = []
    for name, _ in TARGET_FIELDS:
        if name in present:
            continue
        # If keyword was never in the full text, flag as "product likely has no such coverage"
        if name in COVERAGE_PRESENCE_KEYWORDS and not keyword_present.get(name, True):
            no_coverage.append(name)
        else:
            missing.append(name)
    return candidates, missing, no_coverage


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--blocks-dir", type=Path, default=DEFAULT_BLOCKS_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    manifest = load_json(args.manifest)
    results = []
    for item in manifest:
        product_id = item["product_id"]
        block_path = args.blocks_dir / f"{product_id}_blocks.json"
        if not block_path.exists():
            results.append(
                {
                    "product_id": product_id,
                    "db_product_id": item.get("db_product_id"),
                    "product_name": item.get("product_name"),
                    "source_blocks": str(block_path),
                    "candidates": [],
                    "missing_fields": [name for name, _ in TARGET_FIELDS],
                    "no_coverage_fields": [],
                }
            )
            continue

        blocks = load_blocks_compatible(block_path)
        blocks = tag_blocks(blocks)
        candidates, missing, no_coverage = extract_for_product(blocks)
        results.append(
            {
                "product_id": product_id,
                "db_product_id": item.get("db_product_id"),
                "product_name": item.get("product_name"),
                "source_blocks": str(block_path),
                "candidates": candidates,
                "missing_fields": missing,
                "no_coverage_fields": no_coverage,
            }
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {len(results)} products to {args.output}")


if __name__ == "__main__":
    main()
