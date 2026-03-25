#!/usr/bin/env python3
"""Compare blind test results (blind_test_results_v1.json) against DB gold (blind_test_v1_gold.json).

Outputs:
  - Console: 10×10 hit/mismatch/miss matrix
  - JSON: ~/codex-openai/development/data/eval/blind_test_v1_eval.json
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

CORE_FIELDS = [
    "投保年龄",
    "保险期间",
    "交费期间",
    "交费频率",
    "等待期",
    "宽限期",
    "犹豫期",
    "重疾赔付次数",
    "重疾分组",
    "重疾数量",
]

RESULTS_PATH = Path("~/codex-openai/development/data/blind_test_v1/blind_test_results_v1.json").expanduser()
GOLD_PATH = Path("~/codex-openai/development/data/gold/blind_test_v1_gold.json").expanduser()
OUTPUT_PATH = Path("~/codex-openai/development/data/eval/blind_test_v1_eval.json").expanduser()


def normalize(value: str | None) -> str:
    if value is None:
        return ""
    return "".join(str(value).split())


def load_candidates(path: Path) -> dict[str, dict[str, dict]]:
    """Returns {product_id: {coverage_name: {value, source_type}}}"""
    data = json.loads(path.read_text(encoding="utf-8"))
    result = {}
    for product in data["products"]:
        pid = product["product_id"]
        fields = {}
        for item in product.get("items", []):
            name = item.get("coverage_name")
            if name and name not in fields:  # keep first occurrence
                fields[name] = {
                    "value": item.get("value"),
                    "source_type": item.get("source_type", "unknown"),
                }
        result[pid] = fields
    return result


def load_gold(path: Path) -> dict[str, dict[str, str]]:
    return json.loads(path.read_text(encoding="utf-8"))


def classify(candidate_norm: str, gold_norm: str) -> str:
    """Returns 'hit' or 'mismatch'."""
    return "hit" if candidate_norm == gold_norm else "mismatch"


def main() -> None:
    candidates = load_candidates(RESULTS_PATH)
    gold = load_gold(GOLD_PATH)

    product_ids = sorted(set(candidates.keys()) & set(gold.keys()))

    # Per-field stats
    results_by_field: dict[str, dict] = {}
    for field in CORE_FIELDS:
        results_by_field[field] = {"hit": 0, "mismatch": 0, "miss": 0, "details": []}

    # Per-product stats
    results_by_product: dict[str, dict] = {}
    for pid in product_ids:
        results_by_product[pid] = {"hit": 0, "mismatch": 0, "miss": 0}

    mismatch_detail = []

    # cell_status[pid][field] = "hit" | "MM" | "miss"
    cell_status: dict[str, dict[str, str]] = {pid: {} for pid in product_ids}

    for pid in product_ids:
        for field in CORE_FIELDS:
            gold_value = gold.get(pid, {}).get(field)
            cand_info = candidates.get(pid, {}).get(field)
            cand_value = cand_info["value"] if cand_info else None

            gold_norm = normalize(gold_value)
            cand_norm = normalize(cand_value)

            if not gold_norm:
                # No gold → skip (shouldn't happen for core fields)
                cell_status[pid][field] = "N/A"
                continue

            if not cand_norm:
                status = "miss"
                cell_status[pid][field] = "miss"
                results_by_field[field]["miss"] += 1
                results_by_product[pid]["miss"] += 1
                mismatch_detail.append({
                    "product_id": pid,
                    "coverage_name": field,
                    "candidate": None,
                    "gold": gold_value,
                    "source_type": None,
                    "status": "miss",
                })
            elif cand_norm == gold_norm:
                cell_status[pid][field] = "hit"
                results_by_field[field]["hit"] += 1
                results_by_product[pid]["hit"] += 1
                results_by_field[field]["details"].append({
                    "product_id": pid,
                    "status": "hit",
                    "source_type": cand_info["source_type"],
                })
            else:
                cell_status[pid][field] = "MM"
                results_by_field[field]["mismatch"] += 1
                results_by_product[pid]["mismatch"] += 1
                mismatch_detail.append({
                    "product_id": pid,
                    "coverage_name": field,
                    "candidate": cand_value,
                    "gold": gold_value,
                    "source_type": cand_info["source_type"] if cand_info else None,
                    "status": "mismatch",
                })

    # Compute hit rates
    for field in CORE_FIELDS:
        stats = results_by_field[field]
        denom = stats["hit"] + stats["mismatch"] + stats["miss"]
        stats["hit_rate"] = round(stats["hit"] / denom, 4) if denom else 0.0

    # ── Console matrix ──────────────────────────────────────────
    # Column headers (abbreviated)
    abbrev = {
        "投保年龄": "投保年龄",
        "保险期间": "保险期间",
        "交费期间": "交费期间",
        "交费频率": "交费频率",
        "等待期":   "等待期　",
        "宽限期":   "宽限期　",
        "犹豫期":   "犹豫期　",
        "重疾赔付次数": "重疾赔付",
        "重疾分组": "重疾分组",
        "重疾数量": "重疾数量",
    }
    col_w = 6
    pid_w = 14

    header = " " * pid_w + "".join(f"{abbrev.get(f, f):>{col_w}}" for f in CORE_FIELDS)
    print("\n" + header)
    print("-" * len(header))

    for pid in product_ids:
        row = f"{pid:<{pid_w}}"
        for field in CORE_FIELDS:
            s = cell_status[pid].get(field, "N/A")
            row += f"{s:>{col_w}}"
        print(row)

    print("-" * len(header))
    # Hit rate row
    rate_row = f"{'命中率':<{pid_w}}"
    for field in CORE_FIELDS:
        rate = results_by_field[field]["hit_rate"]
        rate_row += f"{rate:.0%}".rjust(col_w)
    print(rate_row)

    # ── Summary ──────────────────────────────────────────────────
    print("\n── 字段命中明细 ──")
    for field in CORE_FIELDS:
        s = results_by_field[field]
        print(f"  {field}: hit={s['hit']} mismatch={s['mismatch']} miss={s['miss']} rate={s['hit_rate']:.0%}")

    print("\n── mismatch/miss 明细 ──")
    for d in mismatch_detail:
        print(f"  [{d['status'].upper()}] {d['product_id']} / {d['coverage_name']}")
        print(f"    候选: {d['candidate']}  (source: {d['source_type']})")
        print(f"    gold: {d['gold']}")

    # ── JSON output ──────────────────────────────────────────────
    output = {
        "evaluated_at": datetime.now().isoformat(timespec="seconds"),
        "product_count": len(product_ids),
        "field_count": len(CORE_FIELDS),
        "results_by_field": results_by_field,
        "results_by_product": results_by_product,
        "mismatch_detail": mismatch_detail,
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n结果已写入: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
