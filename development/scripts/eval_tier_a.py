#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path


def normalize_value(value: str | None) -> str:
    if value is None:
        return ""
    return "".join(str(value).split())


def load_candidates(path: Path) -> dict:
    rows = json.loads(path.read_text(encoding="utf-8"))
    by_product = {}
    for row in rows:
        by_product[row["product_id"]] = {
            candidate["coverage_name"]: candidate["value"]
            for candidate in row.get("candidates", [])
        }
    return by_product


def load_gold(gold_dir: Path) -> dict:
    by_product = {}
    for path in sorted(gold_dir.glob("*_gold.json")):
        product_id = path.stem.replace("_gold", "")
        if product_id == "1548A":
            continue
        if product_id == "889":
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        by_product[product_id] = {
            item["coverage_name"]: item["standard_content"]
            for item in data.get("items", [])
        }
    return by_product


def load_tier_a_whitelist(path: Path) -> list[dict]:
    items = json.loads(path.read_text(encoding="utf-8"))
    return [item for item in items if item.get("tier") == "A"]


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate Tier A extraction results against gold data.")
    parser.add_argument("--candidates", required=True)
    parser.add_argument("--gold-dir", required=True)
    parser.add_argument("--whitelist", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    candidates = load_candidates(Path(args.candidates))
    gold = load_gold(Path(args.gold_dir))
    whitelist = load_tier_a_whitelist(Path(args.whitelist))

    product_ids = sorted(set(candidates.keys()) & set(gold.keys()))
    results = []

    for field in whitelist:
        coverage_name = field["coverage_name"]
        clause_sufficiency = field["clause_sufficiency"]

        if clause_sufficiency == "not_self_sufficient":
            miss_products = []
            hit_count = 0
            for product_id in product_ids:
                candidate_value = candidates.get(product_id, {}).get(coverage_name)
                gold_value = gold.get(product_id, {}).get(coverage_name)
                if candidate_value and gold_value and normalize_value(candidate_value) == normalize_value(gold_value):
                    hit_count += 1
                else:
                    miss_products.append(product_id)

            result = {
                "coverage_name": coverage_name,
                "clause_sufficiency": clause_sufficiency,
                "note": "条款内不自足，不评命中率，应输出 cannot_extract_from_clause",
                "hit_count": hit_count,
                "miss_not_self_sufficient_count": len(miss_products),
                "miss_products": miss_products,
            }
            results.append(result)
            continue

        hit_products = []
        miss_extractable_products = []
        mismatch_products = []

        for product_id in product_ids:
            gold_value = gold.get(product_id, {}).get(coverage_name)
            candidate_value = candidates.get(product_id, {}).get(coverage_name)

            if not gold_value:
                continue

            if candidate_value and normalize_value(candidate_value) == normalize_value(gold_value):
                hit_products.append(product_id)
            elif not candidate_value:
                miss_extractable_products.append(product_id)
            else:
                mismatch_products.append(product_id)

        denominator = len(hit_products) + len(miss_extractable_products) + len(mismatch_products)
        hit_rate = round(hit_products.__len__() / denominator, 4) if denominator else 0.0

        result = {
            "coverage_name": coverage_name,
            "clause_sufficiency": clause_sufficiency,
            "hit_count": len(hit_products),
            "miss_extractable_count": len(miss_extractable_products),
            "mismatch_count": len(mismatch_products),
            "miss_products": miss_extractable_products,
            "mismatch_products": mismatch_products,
            "hit_rate": hit_rate,
        }
        results.append(result)

    output = {
        "evaluated_at": datetime.now().isoformat(timespec="seconds"),
        "product_count": len(product_ids),
        "results": results,
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

    for result in results:
        if result["clause_sufficiency"] == "not_self_sufficient":
            print(
                f"{result['coverage_name']}: clause_sufficiency=not_self_sufficient "
                f"hit={result['hit_count']} miss_not_self_sufficient={result['miss_not_self_sufficient_count']}"
            )
        else:
            print(
                f"{result['coverage_name']}: hit={result['hit_count']} "
                f"miss_extractable={result['miss_extractable_count']} "
                f"mismatch={result['mismatch_count']} hit_rate={result['hit_rate']:.2%}"
            )


if __name__ == "__main__":
    main()
