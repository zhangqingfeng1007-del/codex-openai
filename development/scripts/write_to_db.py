import argparse
import json
import re
from pathlib import Path
from typing import Optional


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CANDIDATES = ROOT / "data" / "extractions" / "tier_a_merged_candidates_v1.json"
DEFAULT_CANDIDATES_B = ROOT / "data" / "extractions" / "tier_b_responsibility_candidates_v1.json"
DEFAULT_STANDARD_FULL = ROOT / "data" / "manifests" / "coverage_standard_full.json"
DEFAULT_ID_MAPPING = ROOT / "data" / "manifests" / "coverage_id_mapping.json"
DEFAULT_PATH_MAPPING = ROOT / "data" / "manifests" / "coverage_path_mapping.json"
DEFAULT_PRODUCT_ID_MAPPING = ROOT / "data" / "manifests" / "product_id_mapping.json"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "db_write_preview"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def merge_candidate_sources(*datasets):
    merged = {}
    order = []
    for dataset in datasets:
        if not dataset:
            continue
        for product in dataset:
            product_id = product["product_id"]
            if product_id not in merged:
                merged[product_id] = {
                    "product_id": product_id,
                    "db_product_id": product.get("db_product_id"),
                    "product_name": product.get("product_name"),
                    "source_blocks": product.get("source_blocks"),
                    "candidates": [],
                    "missing_fields": [],
                }
                order.append(product_id)
            entry = merged[product_id]
            if not entry.get("db_product_id") and product.get("db_product_id"):
                entry["db_product_id"] = product.get("db_product_id")
            if not entry.get("product_name") and product.get("product_name"):
                entry["product_name"] = product.get("product_name")
            if not entry.get("source_blocks") and product.get("source_blocks"):
                entry["source_blocks"] = product.get("source_blocks")
            # Dedup candidates by coverage_name: keep higher confidence
            existing_by_name = {c["coverage_name"]: i for i, c in enumerate(entry["candidates"])}
            for c in product.get("candidates", []):
                name = c.get("coverage_name")
                if name in existing_by_name:
                    idx = existing_by_name[name]
                    if c.get("confidence", 0) > entry["candidates"][idx].get("confidence", 0):
                        entry["candidates"][idx] = c
                else:
                    existing_by_name[name] = len(entry["candidates"])
                    entry["candidates"].append(c)
            existing_missing = set(entry.get("missing_fields", []))
            for field in product.get("missing_fields", []):
                if field not in existing_missing:
                    entry["missing_fields"].append(field)
                    existing_missing.add(field)
    return [merged[product_id] for product_id in order]


def normalize_path_key(value):
    if value is None:
        return None
    if isinstance(value, list):
        return "__".join(str(x).strip() for x in value if str(x).strip())
    text = str(value).strip()
    if not text:
        return None
    return text.replace(" > ", "__")


def build_standard_indexes(standard_full):
    by_id = {}
    by_path = {}
    name_to_ids = {}

    def walk(node, path):
        current_path = "__".join(path + [node["coverage_name"]])
        by_id[node["coverage_id"]] = node
        by_path[current_path] = node
        name_to_ids.setdefault(node["coverage_name"], []).append(node["coverage_id"])
        for child in node.get("children", []):
            walk(child, path + [node["coverage_name"]])

    for root in standard_full:
        walk(root, [])
    return by_id, by_path, name_to_ids


def locate_coverage(candidate, id_mapping, path_mapping, name_to_ids):
    coverage_name = candidate.get("coverage_name", "").strip()
    if coverage_name and coverage_name in id_mapping:
        return id_mapping[coverage_name], coverage_name, None

    for key in ("coverage_path", "standard_path", "coverage_path_text"):
        path_key = normalize_path_key(candidate.get(key))
        if path_key and path_key in path_mapping:
            return path_mapping[path_key], coverage_name, path_key

    if coverage_name and len(name_to_ids.get(coverage_name, [])) == 1:
        return name_to_ids[coverage_name][0], coverage_name, None

    return None, coverage_name, None


def get_standard_values(node):
    values = []
    for raw in node.get("standard_values", []) or []:
        if isinstance(raw, dict):
            values.append(str(raw.get("value", "")).strip())
        else:
            values.append(str(raw).strip())
    return values


def match_standard(value: str, candidates, coverage_name: Optional[str] = None):
    v = (value or "").strip().replace("\r\n", "\n")
    for c in candidates or []:
        c_norm = str(c).strip().replace("\r\n", "\n")
        if v == c_norm:
            return c
    return None


# ---------------------------------------------------------------------------
# 范围补全特例 — semantic candidate matching (whitelist only)
# ---------------------------------------------------------------------------
# When exact match fails, attempt controlled semantic matching for whitelisted
# fields where the candidate value is missing a conventional range qualifier
# (e.g. 意外/非意外) that standard values commonly include.
#
# Rules:
#   - candidate_value is preserved unchanged
#   - suggested_standard_value is the range-completed standard value
#   - match_type = "semantic_candidate_match"
#   - Final human review required

_SEMANTIC_RULES: dict[str, list[tuple[re.Pattern, str]]] = {
    "等待期": [
        # "90天" → "非意外90天，意外0天"
        (re.compile(r"^(\d+)天$"), "非意外{0}天，意外0天"),
        # "180天" → "非意外180天，意外0天"
        (re.compile(r"^(\d+)年$"), "非意外{0}年，意外0天"),
    ],
    "被保险人中症豁免": [
        # "中症，豁免余期保费" → "意外或等待期后中症，豁免余期保费"
        (re.compile(r"^中症，(.+)$"), "意外或等待期后中症，{0}"),
    ],
    "被保险人轻症豁免": [
        # "轻症，豁免余期保费" → "意外或等待期后轻症，豁免余期保费"
        (re.compile(r"^轻症，(.+)$"), "意外或等待期后轻症，{0}"),
    ],
    "被保险人重疾豁免": [
        # "重疾，豁免主险余期保费" → "意外或等待期后重疾，豁免主险余期保费"
        (re.compile(r"^重疾，(.+)$"), "意外或等待期后重疾，{0}"),
    ],
}


def try_semantic_match(coverage_name: str, candidate_value: str, standard_values: list[str]):
    """Attempt range-completion semantic match for whitelisted fields.

    Returns (suggested_standard_value, note) if matched, else (None, None).
    The suggested value must exist in the standard_values list.
    """
    rules = _SEMANTIC_RULES.get(coverage_name)
    if not rules:
        return None, None
    v = (candidate_value or "").strip()
    for pattern, template in rules:
        m = pattern.match(v)
        if not m:
            continue
        suggested = template.format(*m.groups())
        # Must exist in standard values — no fabrication
        if any(suggested == str(sv).strip() for sv in standard_values):
            note = f"范围补全特例：原值「{v}」补全为「{suggested}」"
            return suggested, note
    return None, None


def build_evidence(candidate):
    return {
        "block_id": candidate.get("block_id"),
        "page": candidate.get("page"),
        "evidence_text": candidate.get("evidence_text"),
    }


def build_base_record(product, candidate, db_product_id):
    return {
        "product_id": product.get("product_id"),
        "db_product_id": db_product_id,
        "product_name": product.get("product_name"),
        "coverage_name": candidate.get("coverage_name"),
        "candidate_value": candidate.get("value"),
        "confidence": candidate.get("confidence"),
        "note": candidate.get("note"),
        "reviewer_action": None,
        "evidence": build_evidence(candidate),
    }


    # Fields that are product-unique values — bypass standard-value matching entirely.
DIRECT_EXTRACT_FIELDS = {"合同名称（条款名称）"}


def process_candidates(candidates_data, standard_by_id, id_mapping, path_mapping, name_to_ids, product_id_mapping):
    matched_rows = []
    semantic_matched_rows = []
    unmatched_new_values = []
    unmatched_new_items = []
    direct_extract_rows = []

    for product in candidates_data:
        for candidate in product.get("candidates", []):
            if not (candidate.get("value") or "").strip() or candidate.get("confidence", 1.0) == 0.0:
                continue

            db_product_id = (
                product.get("db_product_id")
                or product_id_mapping.get(product.get("product_id"))
            )

            # Product-unique fields: skip matching, store as direct extraction
            if candidate.get("coverage_name", "").strip() in DIRECT_EXTRACT_FIELDS:
                base = build_base_record(product, candidate, db_product_id)
                direct_extract_rows.append({
                    **base,
                    "status": "direct_extract",
                    "coverage_path": candidate.get("coverage_path") or candidate.get("standard_path"),
                })
                continue
            base = build_base_record(product, candidate, db_product_id)
            coverage_id, coverage_name, coverage_path = locate_coverage(candidate, id_mapping, path_mapping, name_to_ids)

            if not coverage_id:
                unmatched_new_items.append(
                    {
                        **base,
                        "status": "unmatched_new_item",
                        "coverage_id": None,
                        "coverage_path": coverage_path,
                        "reason": "coverage_item_not_found",
                        "suggested_path": None,
                    }
                )
                continue

            node = standard_by_id.get(coverage_id)
            if not node:
                unmatched_new_items.append(
                    {
                        **base,
                        "status": "unmatched_new_item",
                        "coverage_id": coverage_id,
                        "coverage_path": coverage_path,
                        "reason": "coverage_id_not_found_in_standard_tree",
                        "suggested_path": coverage_path,
                    }
                )
                continue

            standard_values = get_standard_values(node)
            matched_value = match_standard(candidate.get("value", ""), standard_values, coverage_name)
            if matched_value is not None:
                matched_rows.append(
                    {
                        **base,
                        "status": "matched_review_required",
                        "coverage_id": coverage_id,
                        "coverage_path": coverage_path,
                        "matched_standard_value": matched_value,
                        "standard_id": "PENDING_LOOKUP",
                        "is_optional_coverage": 0,
                    }
                )
            else:
                # Semantic fallback: range completion for whitelisted fields
                suggested, sem_note = try_semantic_match(
                    coverage_name, candidate.get("value", ""), standard_values
                )
                if suggested is not None:
                    semantic_matched_rows.append(
                        {
                            **base,
                            "status": "semantic_candidate_match",
                            "match_type": "semantic_candidate_match",
                            "coverage_id": coverage_id,
                            "coverage_path": coverage_path,
                            "candidate_value": candidate.get("value"),
                            "suggested_standard_value": suggested,
                            "note": sem_note,
                            "standard_id": "PENDING_LOOKUP",
                            "is_optional_coverage": 0,
                        }
                    )
                else:
                    unmatched_new_values.append(
                        {
                            **base,
                            "status": "unmatched_new_value",
                            "coverage_id": coverage_id,
                            "coverage_path": coverage_path,
                            "reason": "value_not_found_under_coverage",
                            "suggested_value": candidate.get("value"),
                            "known_standard_values_count": len(standard_values),
                        }
                    )

    return matched_rows, semantic_matched_rows, unmatched_new_values, unmatched_new_items, direct_extract_rows


def write_outputs(output_dir: Path, matched_rows, semantic_matched_rows, unmatched_new_values, unmatched_new_items, direct_extract_rows=None):
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs = {
        "matched_rows_preview.json": matched_rows,
        "semantic_matched_preview.json": semantic_matched_rows,
        "unmatched_new_values_review.json": unmatched_new_values,
        "unmatched_new_items_review.json": unmatched_new_items,
    }
    if direct_extract_rows is not None:
        outputs["direct_extract_preview.json"] = direct_extract_rows
    for name, payload in outputs.items():
        (output_dir / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Dry-run match candidates into coverage standard tree.")
    parser.add_argument("--candidates", type=Path, default=DEFAULT_CANDIDATES)
    parser.add_argument("--candidates-b", type=Path, default=None)
    parser.add_argument("--standard-full", type=Path, default=DEFAULT_STANDARD_FULL)
    parser.add_argument("--id-mapping", type=Path, default=DEFAULT_ID_MAPPING)
    parser.add_argument("--path-mapping", type=Path, default=DEFAULT_PATH_MAPPING)
    parser.add_argument("--product-id-mapping", type=Path, default=DEFAULT_PRODUCT_ID_MAPPING)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not args.dry_run:
        raise SystemExit("Only --dry-run is implemented in Phase 1.")

    candidates_a = load_json(args.candidates)
    candidates_b = load_json(args.candidates_b) if args.candidates_b else []
    candidates_data = merge_candidate_sources(candidates_a, candidates_b)
    standard_full = load_json(args.standard_full)
    id_mapping = load_json(args.id_mapping)
    path_mapping = load_json(args.path_mapping)
    product_id_mapping = load_json(args.product_id_mapping)
    standard_by_id, _, name_to_ids = build_standard_indexes(standard_full)

    matched_rows, semantic_matched_rows, unmatched_new_values, unmatched_new_items, direct_extract_rows = process_candidates(
        candidates_data,
        standard_by_id,
        id_mapping,
        path_mapping,
        name_to_ids,
        product_id_mapping,
    )
    write_outputs(args.output_dir, matched_rows, semantic_matched_rows, unmatched_new_values, unmatched_new_items, direct_extract_rows)

    summary = {
        "products": len(candidates_data),
        "matched_review_required": len(matched_rows),
        "semantic_candidate_match": len(semantic_matched_rows),
        "matched_auto_insertable": 0,
        "direct_extract": len(direct_extract_rows),
        "unmatched_new_value": len(unmatched_new_values),
        "unmatched_new_item": len(unmatched_new_items),
        "output_dir": str(args.output_dir),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
