import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CANDIDATES = ROOT / "data" / "extractions" / "tier_a_merged_candidates_v1.json"
DEFAULT_STANDARD_FULL = ROOT / "data" / "manifests" / "coverage_standard_full.json"
DEFAULT_ID_MAPPING = ROOT / "data" / "manifests" / "coverage_id_mapping.json"
DEFAULT_PATH_MAPPING = ROOT / "data" / "manifests" / "coverage_path_mapping.json"
DEFAULT_PRODUCT_ID_MAPPING = ROOT / "data" / "manifests" / "product_id_mapping.json"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "db_write_preview"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


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


def match_standard(value: str, candidates):
    v = (value or "").strip()
    for c in candidates or []:
        if v == str(c).strip():
            return c
    return None


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


def process_candidates(candidates_data, standard_by_id, id_mapping, path_mapping, name_to_ids, product_id_mapping):
    matched_rows = []
    unmatched_new_values = []
    unmatched_new_items = []

    for product in candidates_data:
        for candidate in product.get("candidates", []):
            if not (candidate.get("value") or "").strip() or candidate.get("confidence", 1.0) == 0.0:
                continue

            db_product_id = (
                product.get("db_product_id")
                or product_id_mapping.get(product.get("product_id"))
            )
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
            matched_value = match_standard(candidate.get("value", ""), standard_values)
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

    return matched_rows, unmatched_new_values, unmatched_new_items


def write_outputs(output_dir: Path, matched_rows, unmatched_new_values, unmatched_new_items):
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs = {
        "matched_rows_preview.json": matched_rows,
        "unmatched_new_values_review.json": unmatched_new_values,
        "unmatched_new_items_review.json": unmatched_new_items,
    }
    for name, payload in outputs.items():
        (output_dir / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Dry-run match candidates into coverage standard tree.")
    parser.add_argument("--candidates", type=Path, default=DEFAULT_CANDIDATES)
    parser.add_argument("--standard-full", type=Path, default=DEFAULT_STANDARD_FULL)
    parser.add_argument("--id-mapping", type=Path, default=DEFAULT_ID_MAPPING)
    parser.add_argument("--path-mapping", type=Path, default=DEFAULT_PATH_MAPPING)
    parser.add_argument("--product-id-mapping", type=Path, default=DEFAULT_PRODUCT_ID_MAPPING)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not args.dry_run:
        raise SystemExit("Only --dry-run is implemented in Phase 1.")

    candidates_data = load_json(args.candidates)
    standard_full = load_json(args.standard_full)
    id_mapping = load_json(args.id_mapping)
    path_mapping = load_json(args.path_mapping)
    product_id_mapping = load_json(args.product_id_mapping)
    standard_by_id, _, name_to_ids = build_standard_indexes(standard_full)

    matched_rows, unmatched_new_values, unmatched_new_items = process_candidates(
        candidates_data,
        standard_by_id,
        id_mapping,
        path_mapping,
        name_to_ids,
        product_id_mapping,
    )
    write_outputs(args.output_dir, matched_rows, unmatched_new_values, unmatched_new_items)

    summary = {
        "products": len(candidates_data),
        "matched_review_required": len(matched_rows),
        "matched_auto_insertable": 0,
        "unmatched_new_value": len(unmatched_new_values),
        "unmatched_new_item": len(unmatched_new_items),
        "output_dir": str(args.output_dir),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
