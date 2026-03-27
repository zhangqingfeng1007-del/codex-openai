#!/usr/bin/env python3
import argparse
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from normalize_value import normalize_value

ROOT = Path("/Users/zqf-openclaw/codex-openai/development")
DEFAULT_BLIND_TEST = ROOT / "data" / "blind_test_v1" / "blind_test_results_v1.json"
DEFAULT_COVERAGE_DUMP = ROOT / "data" / "manifests" / "full_coverage_dump.json"
DEFAULT_WHITELIST = ROOT / "data" / "manifests" / "coverage_whitelist_v1.json"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "review_tasks"


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def slugify_coverage_name(name: str) -> str:
    if not name:
        return "unknown"
    return "".join(ch for ch in name if ch.isalnum())[:24] or "coverage"


def infer_company_name(product_name: str) -> str:
    prefixes = [
        "招商信诺", "国寿", "中国人寿", "中信保诚", "阳光人寿", "中意", "国华", "北京人寿", "金小葵"
    ]
    for prefix in prefixes:
        if product_name.startswith(prefix):
            return prefix
    return product_name[:8]


def load_coverage_template(product_id: str, dump_rows: list[dict], whitelist_by_name: dict, catalog_version: str) -> list[dict]:
    rows = [row for row in dump_rows if str(row.get("product_id")) == str(product_id)]
    template_fields = []
    for row in rows:
        coverage_name = row["coverage_name"]
        whitelist_row = whitelist_by_name.get(coverage_name)
        group_level_1, group_level_2, group_type = map_group(coverage_name)
        is_tier_a = bool(whitelist_row and whitelist_row.get("tier") == "A")
        template_fields.append(
            {
                "coverage_id": str(row["coverage_id"]),
                "coverage_name": coverage_name,
                "standard_content": row.get("standard_content") or "",
                "is_tier_a": is_tier_a,
                "default_review_mode": (whitelist_row or {}).get("default_review_mode", "review"),
                "group_level_1": group_level_1,
                "group_level_2": group_level_2,
                "group_type": group_type,
                "catalog_version": catalog_version,
            }
        )
    return template_fields


def load_whitelist(whitelist_rows: list[dict]) -> dict:
    return {row["coverage_name"]: row for row in whitelist_rows}


def load_standard_values() -> dict:
    """
    加载标准值字典，以 coverage_name 为 key。
    返回：{coverage_name: {"coverage_id": ..., "values": [...], "count": N}}
    """
    path = ROOT / "data" / "manifests" / "coverage_standard_values_v1.json"
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        raw = json.load(f)
    flat = {}
    for group_fields in raw.get("groups", {}).values():
        flat.update(group_fields)
    flat.update(raw.get("ungrouped", {}))
    return flat


def validate_against_standard(coverage_name: str, candidate_value: str, standard_values: dict) -> str:
    """
    检查候选值是否在已知标准值列表中。
    返回：
      "standard"   : 值在已知集合中，可信度高
      "new_value"  : 值不在已知集合中，但格式可能合法，可能是新标准值
      "no_standard": 该字段无已知标准值库（ungrouped 或未覆盖字段）
    """
    entry = standard_values.get(coverage_name)
    if not entry:
        return "no_standard"
    known = entry.get("values", [])
    if not known:
        return "no_standard"
    if candidate_value in known:
        return "standard"
    return "new_value"


def load_extracted_candidates(product_id: str, blind_test_path: Path) -> tuple[list[dict], dict, str]:
    payload = load_json(blind_test_path)
    products = payload["products"] if isinstance(payload, dict) else payload
    row = next((r for r in products if str(r.get("product_id")) == str(product_id)), None)
    if not row:
        raise ValueError(f"未在 blind_test_results_v1.json 中找到 product_id={product_id}")
    return row.get("items", []), row.get("used_sources", {}), row.get("product_name", "")


def build_document_package(product_id: str, used_sources: dict) -> dict:
    files = []
    seen = set()
    for source_type, paths in used_sources.items():
        for path in paths:
            if not path or path in seen:
                continue
            seen.add(path)
            files.append(
                {
                    "source_type": source_type,
                    "file_name": Path(path).name,
                    "parse_quality": "good",
                    "local_path": path,
                }
            )
    return {
        "document_package_id": f"pkg_{product_id}_001",
        "files": files,
    }


def build_extracted_index(candidates: list[dict]) -> dict[str, list[dict]]:
    index = defaultdict(list)
    for candidate in candidates:
        index[candidate["coverage_name"]].append(candidate)
    return index


def source_type_from_candidate(candidate: dict) -> str:
    if candidate.get("source_type"):
        return candidate["source_type"]
    block_id = candidate.get("block_id") or ""
    if str(block_id).startswith("brochure_"):
        return "product_brochure"
    return "clause"


def build_source(candidate: dict) -> dict:
    evidence = candidate.get("evidence", {})
    page = candidate.get("page")
    if page is None:
        page = evidence.get("page")
    block_text = evidence.get("text") or candidate.get("evidence_text") or evidence.get("summary") or ""
    raw_value = candidate.get("value") or ""
    return {
        "source_id": f"src_{candidate['coverage_name']}_{abs(hash((candidate.get('source_file'), candidate.get('block_id'), raw_value))) % 10_000_000}",
        "source_type": source_type_from_candidate(candidate),
        "file_name": Path(candidate.get("source_file", "")).name if candidate.get("source_file") else "",
        "page": page,
        "block_id": candidate.get("block_id"),
        "title_path": [],
        "source_raw_value": candidate.get("evidence_text") or evidence.get("text") or evidence.get("summary") or raw_value,
        "md_text": candidate.get("evidence_text") or evidence.get("text") or "",
        "block_text": block_text,
        "raw_value": raw_value,
        "normalized_value": raw_value,
        "confidence": candidate.get("confidence", 0),
        "extract_method": candidate.get("extract_method") or candidate.get("note") or "",
        "conflict": False,
    }


def pick_status(candidates: list[dict], has_conflict: bool) -> str:
    if not candidates:
      return "not_extracted"
    max_confidence = max(candidate.get("confidence", 0) for candidate in candidates)
    if has_conflict:
        return "review_required"
    return "candidate_ready" if max_confidence >= 0.90 else "review_required"


def build_coverage_item(template_field: dict, candidates: list[dict], whitelist: dict, standard_values: dict) -> dict:
    sources = [build_source(candidate) for candidate in candidates]
    source_values = {source["normalized_value"] for source in sources if source["normalized_value"]}
    has_conflict = len(source_values) > 1
    for source in sources:
        source["conflict"] = has_conflict

    status = pick_status(candidates, has_conflict)
    is_linked = template_field["coverage_name"] in {"重疾赔付次数", "重疾分组", "重疾数量"}
    if has_conflict:
        review_priority = 1
    elif status == "not_extracted":
        review_priority = 2
    elif template_field["is_tier_a"] and is_linked:
        review_priority = 4
    elif status == "review_required":
        review_priority = 5
    else:
        review_priority = 6

    winning_candidate = max(candidates, key=lambda x: x.get("confidence", 0), default=None)
    candidate_summary = winning_candidate.get("value", "—") if winning_candidate else "—"
    normalized_candidate = normalize_value(
        template_field["coverage_name"],
        candidate_summary
    )
    std_result = validate_against_standard(
        template_field["coverage_name"],
        normalized_candidate,
        standard_values
    )
    if std_result == "new_value" and status == "candidate_ready":
        status = "review_required"
    normalization_trace = []
    if normalized_candidate != candidate_summary:
        normalization_trace.append(f"格式归一：'{candidate_summary}' → '{normalized_candidate}'")
    if std_result == "standard":
        normalization_trace.append(f"归一后值'{normalized_candidate}'在已知标准值列表中 ✓")
    elif std_result == "new_value":
        normalization_trace.append(f"归一后值'{normalized_candidate}'不在已知标准值列表中，可能为新标准值，请人工确认")
    elif std_result == "no_standard":
        normalization_trace.append("该字段暂无已知标准值库，跳过校验")
    risk_level = "high" if template_field["is_tier_a"] or has_conflict else ("medium" if status == "review_required" else "low")

    return {
        "item_id": f"item_{template_field['coverage_id']}_{slugify_coverage_name(template_field['coverage_name'])}",
        "coverage_id": template_field["coverage_id"],
        "coverage_name": template_field["coverage_name"],
        "status": status,
        "candidate_summary": candidate_summary,
        "normalized_value": normalized_candidate,
        "final_value": "",
        "is_tier_a": template_field["is_tier_a"],
        "review_priority": review_priority,
        "group_level_1": template_field["group_level_1"],
        "group_level_2": template_field["group_level_2"],
        "group_type": template_field["group_type"],
        "risk_level": risk_level,
        "is_required": True,
        "is_linked": is_linked,
        "source_count": len(sources),
        "catalog_version": template_field["catalog_version"],
        "sources": sources,
        "logic_trace": {
            "priority_trace": [
                f"template 来源标准值：{template_field['standard_content'] or '—'}",
                "匹配方式：当前版本按 coverage_name 对齐抽取候选"
            ],
            "normalization_trace": normalization_trace,
            "mapping_trace": [
                f"coverage_id={template_field['coverage_id']}",
                f"coverage_name={template_field['coverage_name']}"
            ],
            "standard_value_check": std_result
        }
    }


def build_gap_item(template_field: dict) -> dict:
    is_linked = template_field["coverage_name"] in {"重疾赔付次数", "重疾分组", "重疾数量"}
    return {
        "item_id": f"item_gap_{template_field['coverage_id']}",
        "coverage_id": template_field["coverage_id"],
        "coverage_name": template_field["coverage_name"],
        "status": "not_extracted",
        "candidate_summary": "—",
        "final_value": "",
        "is_tier_a": template_field["is_tier_a"],
        "review_priority": 2,
        "group_level_1": template_field["group_level_1"],
        "group_level_2": template_field["group_level_2"],
        "group_type": template_field["group_type"],
        "risk_level": "high" if template_field["is_tier_a"] else "medium",
        "is_required": True,
        "is_linked": is_linked,
        "source_count": 0,
        "catalog_version": template_field["catalog_version"],
        "sources": [],
        "logic_trace": {
            "priority_trace": [
                "template 中存在该字段，但抽取层未产出候选"
            ],
            "normalization_trace": [],
            "mapping_trace": [
                f"coverage_id={template_field['coverage_id']}",
                f"coverage_name={template_field['coverage_name']}"
            ]
        }
    }


def build_field_groups(items: list[dict]) -> list[dict]:
    grouped = defaultdict(list)
    for item in items:
        grouped[(item["group_type"], item["group_level_1"], item["group_level_2"])].append(item)

    static_groups = []
    for (group_type, group_level_1, group_level_2), group_items in sorted(grouped.items(), key=lambda x: (x[0][0], x[0][1], x[0][2])):
        group_name = group_level_1 if group_level_2 in {"", "—"} else f"{group_level_1} / {group_level_2}"
        static_groups.append(
            {
                "group_type": group_type,
                "group_name": group_name,
                "items": sorted(group_items, key=lambda item: (item["review_priority"], item["coverage_name"]))
            }
        )

    not_extracted_ids = [item["item_id"] for item in items if item["status"] == "not_extracted"]
    missing_ids = [item["item_id"] for item in items if item["status"] == "cannot_extract"]
    dynamic_groups = []
    if not_extracted_ids:
        dynamic_groups.append(
            {
                "group_type": "dynamic_not_extracted",
                "group_name": "未抽取字段",
                "is_dynamic": True,
                "item_ids": not_extracted_ids,
            }
        )
    if missing_ids:
        dynamic_groups.append(
            {
                "group_type": "dynamic_missing",
                "group_name": "缺失字段",
                "is_dynamic": True,
                "item_ids": missing_ids,
            }
        )
    return dynamic_groups + static_groups


def compute_stats(items: list[dict]) -> dict:
    return {
        "total_items": len(items),
        "conflict_count": sum(1 for item in items if item["source_count"] > 1 and any(source["conflict"] for source in item["sources"])),
        "missing_count": sum(1 for item in items if item["status"] == "cannot_extract"),
        "not_extracted_count": sum(1 for item in items if item["status"] == "not_extracted"),
        "pending_review_count": sum(1 for item in items if item["status"] in {"review_required", "candidate_ready"}),
    }


def build_review_task(product_id: str, coverage_dump_path: Path, blind_test_path: Path, whitelist_path: Path, catalog_version: str) -> dict:
    whitelist = load_whitelist(load_json(whitelist_path))
    standard_values = load_standard_values()
    template_fields = load_coverage_template(product_id, load_json(coverage_dump_path), whitelist, catalog_version)
    candidates, used_sources, product_name = load_extracted_candidates(product_id, blind_test_path)
    extracted_index = build_extracted_index(candidates)

    items = []
    for template_field in template_fields:
        matches = extracted_index.get(template_field["coverage_name"], [])
        if matches:
            item = build_coverage_item(template_field, matches, whitelist, standard_values)
        else:
            item = build_gap_item(template_field)
        items.append(item)

    document_package = build_document_package(product_id, used_sources)
    stats = compute_stats(items)
    product_name = product_name or (template_fields[0]["coverage_name"] if template_fields else product_id)

    return {
        "task": {
            "task_id": f"task_{product_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "task_status": "in_review",
            "rule_version": "rule_v2.4",
        },
        "catalog_version_at_creation": catalog_version,
        "product": {
            "product_id": product_id,
            "product_name": product_name,
            "company_name": infer_company_name(product_name),
            "aix_category_id": 6001,
        },
        "document_package": document_package,
        "field_groups": build_field_groups(items),
        "dependency_groups": [
            {
                "dependency_group_id": "ci_chain",
                "group_name": "重疾责任链",
                "members": ["重疾赔付次数", "重疾分组", "重疾数量"],
                "rules": [
                    "次数=1次 -> 分组通常为不涉及",
                    "次数>1次 -> 分组应为不分组或N组",
                ],
            }
        ],
        **stats,
    }


def map_group(coverage_name: str) -> tuple[str, str, str]:
    name = coverage_name
    if any(keyword in name for keyword in ["投保年龄", "保险期间", "交费期间", "交费频率", "等待期", "宽限期", "犹豫期", "保费要求", "保额要求"]):
        return "基础规则", "—", "tier_basic"
    if any(keyword in name for keyword in ["重疾赔付次数", "重疾分组", "重疾数量", "重疾保障说明", "重疾赔付时间间隔"]):
        return "疾病责任", "重疾责任", "tier_ci"
    if any(keyword in name for keyword in ["特定重疾", "恶性肿瘤", "特定重疾数量", "特定重疾保障说明", "特定重疾"]):
        return "疾病责任", "特定/高发重疾", "tier_ci_extra"
    if "轻症" in name:
        return "疾病责任", "轻症责任", "tier_minor_ci"
    if "中症" in name:
        return "疾病责任", "中症责任", "tier_mid_ci"
    if "身故" in name:
        return "身故全残责任", "身故责任", "tier_death"
    if "全残" in name:
        return "身故全残责任", "全残责任", "tier_disability"
    if "豁免" in name or "投保人" in name:
        return "豁免责任", "—", "tier_waiver"
    if "免责" in name:
        return "责任免除", "—", "tier_exemption"
    if any(keyword in name for keyword in ["转换权", "保单贷款", "减保", "减额交清"]):
        return "保单权益", "—", "tier_rights"
    if any(keyword in name for keyword in ["合同名称", "生效时间", "报备年度", "条款编码", "长短险", "指定第二投保人"]):
        return "产品基本信息", "—", "tier_info"
    return "其他", "—", "tier_other"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--product_id", required=True)
    parser.add_argument("--blind_test", default=str(DEFAULT_BLIND_TEST))
    parser.add_argument("--coverage_dump", default=str(DEFAULT_COVERAGE_DUMP))
    parser.add_argument("--whitelist", default=str(DEFAULT_WHITELIST))
    parser.add_argument("--catalog_version", default="v1.2")
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    output_path = Path(args.output) if args.output else DEFAULT_OUTPUT_DIR / f"{args.product_id}_review_task_v2.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    review_task = build_review_task(
        product_id=args.product_id,
        coverage_dump_path=Path(args.coverage_dump),
        blind_test_path=Path(args.blind_test),
        whitelist_path=Path(args.whitelist),
        catalog_version=args.catalog_version,
    )

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(review_task, f, ensure_ascii=False, indent=2)

    print(f"written: {output_path}")
    print(f"total_items={review_task['total_items']}")
    print(f"not_extracted_count={review_task['not_extracted_count']}")
    print(f"pending_review_count={review_task['pending_review_count']}")


if __name__ == "__main__":
    main()
