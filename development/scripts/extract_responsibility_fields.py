#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


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
]


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
    return None


def extract_for_product(blocks: list[dict]) -> tuple[list[dict], list[str]]:
    extractors = [
        extract_ci_pay_times,
        extract_ci_count,
        extract_mild_pay_times,
        extract_mild_count,
        extract_mild_group,
    ]
    candidates = []
    present = set()
    for extractor in extractors:
        candidate = extractor(blocks)
        if candidate:
            candidates.append(candidate)
            present.add(candidate["coverage_name"])
    missing = [name for name, _ in TARGET_FIELDS if name not in present]
    return candidates, missing


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
                }
            )
            continue

        blocks = load_blocks_compatible(block_path)
        candidates, missing = extract_for_product(blocks)
        results.append(
            {
                "product_id": product_id,
                "db_product_id": item.get("db_product_id"),
                "product_name": item.get("product_name"),
                "source_blocks": str(block_path),
                "candidates": candidates,
                "missing_fields": missing,
            }
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {len(results)} products to {args.output}")


if __name__ == "__main__":
    main()
