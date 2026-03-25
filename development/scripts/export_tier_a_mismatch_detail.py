#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path


TARGET_FIELDS = {"保险期间", "等待期", "等待期（简化）", "重疾分组"}


def normalize_value(value: str | None) -> str:
    if value is None:
        return ""
    return "".join(str(value).split())


def main() -> None:
    base = Path("/Users/zqf-openclaw/codex-openai/development/data")
    eval_path = base / "extractions" / "tier_a_eval_v1.json"
    candidates_path = base / "extractions" / "tier_a_rule_candidates_v1.json"
    gold_dir = base / "gold"
    output_path = base / "extractions" / "tier_a_mismatch_detail.json"

    eval_data = json.loads(eval_path.read_text(encoding="utf-8"))
    candidate_rows = json.loads(candidates_path.read_text(encoding="utf-8"))
    candidates = {row["product_id"]: row for row in candidate_rows}

    mismatch_pairs = []
    for result in eval_data["results"]:
        coverage_name = result["coverage_name"]
        if coverage_name not in TARGET_FIELDS:
            continue
        for product_id in result.get("mismatch_products", []):
            mismatch_pairs.append((coverage_name, product_id))

    details = []
    for coverage_name, product_id in mismatch_pairs:
        row = candidates[product_id]
        candidate = next(c for c in row["candidates"] if c["coverage_name"] == coverage_name)
        gold_path = gold_dir / f"{product_id}_gold.json"
        gold_data = json.loads(gold_path.read_text(encoding="utf-8"))
        gold_value = None
        for item in gold_data.get("items", []):
            if item["coverage_name"] == coverage_name:
                gold_value = item["standard_content"]
                break

        details.append(
            {
                "coverage_name": coverage_name,
                "product_id": product_id,
                "rule_extracted_value": candidate["value"],
                "gold_value": gold_value,
                "block_id": candidate["block_id"],
                "page": candidate["page"],
                "evidence_text": candidate["evidence_text"],
            }
        )

    output_path.write_text(json.dumps(details, ensure_ascii=False, indent=2), encoding="utf-8")

    for item in details:
        print(f"coverage_name={item['coverage_name']}")
        print(f"product_id={item['product_id']}")
        print(f"rule_extracted_value={item['rule_extracted_value']}")
        print(f"gold_value={item['gold_value']}")
        print(f"block_id={item['block_id']}")
        print(f"page={item['page']}")
        print(f"evidence_text={item['evidence_text']}")
        print("---")


if __name__ == "__main__":
    main()
