import cgi
import json
import os
import re
import subprocess
from collections import defaultdict
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse


ROOT = Path(__file__).resolve().parent
TASKS_DIR = ROOT.parent / "data" / "review_tasks"
UPLOADS_DIR = ROOT.parent / "data" / "uploads"
MANIFESTS_DIR = ROOT.parent / "data" / "manifests"
EXTRACTIONS_DIR = ROOT.parent / "data" / "extractions"
PORT = int(os.environ.get("PORT", "8793"))

BLIND_TEST_MANIFEST = MANIFESTS_DIR / "blind_test_manifest_20260330.json"
BLIND_TEST_TIER_A = EXTRACTIONS_DIR / "blind_test_tier_a_r5.json"
BLIND_TEST_TIER_B = EXTRACTIONS_DIR / "blind_test_tier_b_r11.json"
STANDARD_VALUES_EXPORT = MANIFESTS_DIR / "coverage_standard_full_from_db_filtered_20260330.json"

SOURCE_TYPE_LABELS = {
    "clause": "clause",
    "raw_rate": "raw_rate",
    "processed_rate": "processed_rate",
    "product_brochure": "product_brochure",
    "underwriting_rule": "underwriting_rule",
    "cash_value": "cash_value",
    "other": "other",
}

CI_REVIEW_GROUPS = [
    {
        "group_type": "tier_a_basic",
        "group_name": "基础规则字段",
        "items": [
            "合同名称（条款名称）",
            "投保年龄",
            "保险期间",
            "交费期间",
            "交费频率",
            "等待期",
            "等待期（简化）",
            "犹豫期",
            "宽限期",
            "保额要求",
            "保费要求",
            "是否保证续保",
            "保证续保期限",
            "最大续保年龄",
            "停售是否可以续保",
        ],
    },
    {
        "group_type": "tier_ci_core",
        "group_name": "重疾核心责任",
        "items": [
            "重疾数量",
            "重疾赔付次数",
            "重疾分组",
            "重疾赔付时间间隔",
            "重疾保障说明",
        ],
    },
    {
        "group_type": "tier_ci_light_medium",
        "group_name": "轻症/中症责任",
        "items": [
            "轻症数量",
            "轻症赔付次数",
            "轻症分组",
            "轻症赔付时间间隔",
            "轻症保障说明",
            "中症数量",
            "中症赔付次数",
            "中症分组",
            "中症赔付时间间隔",
            "中症保障说明",
        ],
    },
    {
        "group_type": "tier_ci_ext",
        "group_name": "重疾扩展责任",
        "items": [
            "特定重疾数量",
            "特定重疾保障说明",
            "恶性肿瘤具体病种",
            "恶性肿瘤状态",
            "恶性肿瘤多次给付次数",
            "恶性肿瘤多次给付间隔期",
            "恶性肿瘤多次给付保障说明",
            "终末期疾病保障说明",
            "长期护理保障说明",
        ],
    },
    {
        "group_type": "tier_policy_rights",
        "group_name": "保单功能",
        "items": [
            "转换权",
            "保单贷款",
            "减保",
            "减额交清",
            "指定第二投保人",
        ],
    },
    {
        "group_type": "tier_waiver",
        "group_name": "豁免责任",
        "items": [
            "投保人身故豁免",
            "投保人全残豁免",
            "被保险人重疾豁免",
            "被保险人中症豁免",
            "被保险人轻症豁免",
            "豁免其他责任原文标题",
            "豁免其他责任保障说明",
        ],
    },
    {
        "group_type": "tier_exemption",
        "group_name": "责任免除",
        "items": [
            "身故免责数量",
            "身故具体免责条款",
            "全残免责数量",
            "全残具体免责条款",
            "疾病免责数量",
            "疾病具体免责条款",
            "豁免免责数量",
            "豁免具体免责条款",
            "护理免责数量",
            "护理具体免责条款",
            "其他免责原文标题",
            "其他免责数量",
            "其他免责具体免责条款",
        ],
    },
    {
        "group_type": "tier_other",
        "group_name": "其他责任说明",
        "items": [
            "身故责任保障说明",
            "全残责任保障说明",
            "疾病其他责任原文标题",
            "疾病其他责任保障说明",
            "排他项说明",
            "产品说明",
        ],
    },
]

STATUS_PRIORITY = {
    "review_required": 0,
    "candidate_ready": 1,
    "accepted": 2,
    "modified": 3,
    "rejected": 4,
    "pending_materials": 5,
    "cannot_extract": 6,
    "cannot_extract_from_clause": 7,
    "not_extracted": 8,
    "not_applicable": 9,
}


class ReviewModuleHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def _send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _load_task(self, product_id):
        task_file = TASKS_DIR / f"{product_id}_review_task_v2.json"
        if not task_file.exists():
            generated = build_blind_test_task(product_id)
            if generated is not None:
                return generated, task_file
            return None, task_file
        return json.loads(task_file.read_text(encoding="utf-8")), task_file

    def _save_task(self, task_data, task_file):
        task_file.write_text(json.dumps(task_data, ensure_ascii=False, indent=2), encoding="utf-8")

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_DELETE(self):
        parsed = urlparse(self.path)
        m = re.match(r'^/tasks/([^/]+)/file/(.+)$', parsed.path)
        if not m:
            self.send_error(404, "Not Found")
            return
        product_id = m.group(1)
        filename = unquote(m.group(2))

        task_data, task_file = self._load_task(product_id)
        if task_data is None:
            self.send_error(404, f"Task not found: {product_id}")
            return

        pkg = task_data.setdefault("document_package", {"document_package_id": f"pkg_{product_id}_001", "files": []})
        pkg["files"] = [f for f in pkg.get("files", []) if f.get("file_name") != filename]
        self._save_task(task_data, task_file)
        self._send_json({"ok": True, "document_package": pkg})

    def do_POST(self):
        parsed = urlparse(self.path)

        # POST /tasks/{product_id}/upload — multipart file upload
        m = re.match(r'^/tasks/([^/]+)/upload$', parsed.path)
        if m:
            product_id = m.group(1)
            task_data, task_file = self._load_task(product_id)
            if task_data is None:
                self.send_error(404, f"Task not found: {product_id}")
                return

            content_type = self.headers.get("Content-Type", "")
            if "multipart/form-data" not in content_type:
                self.send_error(400, "Expected multipart/form-data")
                return

            form = cgi.FieldStorage(
                fp=self.rfile,
                headers=self.headers,
                environ={"REQUEST_METHOD": "POST", "CONTENT_TYPE": content_type},
            )
            if "file" not in form:
                self.send_error(400, "Missing file field")
                return

            file_item = form["file"]
            source_type = form.getvalue("source_type", "other")
            filename = Path(file_item.filename).name  # strip any path component

            upload_dir = UPLOADS_DIR / product_id
            upload_dir.mkdir(parents=True, exist_ok=True)
            save_path = upload_dir / filename
            save_path.write_bytes(file_item.file.read())

            pkg = task_data.setdefault("document_package", {"document_package_id": f"pkg_{product_id}_001", "files": []})
            # Replace existing entry with same filename
            pkg["files"] = [f for f in pkg.get("files", []) if f.get("file_name") != filename]
            pkg["files"].append({
                "source_type": source_type,
                "file_name": filename,
                "parse_quality": "uploaded",
                "local_path": str(save_path),
            })
            self._save_task(task_data, task_file)
            self._send_json({"ok": True, "document_package": pkg})
            return

        if parsed.path != "/__open":
            self.send_error(404, "Not Found")
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(content_length) if content_length > 0 else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            self.send_error(400, "Invalid JSON")
            return

        file_path = payload.get("path")
        if not file_path:
            self.send_error(400, "Missing path")
            return

        target = Path(file_path).expanduser()
        if not target.exists():
            self.send_error(404, "File not found")
            return

        subprocess.run(["open", str(target)], check=False)
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps({"ok": True, "path": str(target)}).encode("utf-8"))

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/__health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True, "port": PORT}).encode("utf-8"))
            return
        if parsed.path.startswith("/tasks/"):
            product_id = parsed.path[len("/tasks/"):].strip("/")
            task_data, task_file = self._load_task(product_id)
            if task_data is None:
                self.send_error(404, f"Task not found: {product_id}")
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(task_data, ensure_ascii=False).encode("utf-8"))
            return
        if parsed.path == "/standard_values":
            if not STANDARD_VALUES_LOOKUP:
                self.send_error(404, "standard_values file not found")
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(STANDARD_VALUES_LOOKUP, ensure_ascii=False).encode("utf-8"))
            return
        if parsed.path == "/tasks":
            blind_products = list_blind_test_products()
            if blind_products:
                payload = {
                    "product_ids": [p["product_id"] for p in blind_products],
                    "products": blind_products,
                }
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
                return
            files = sorted(TASKS_DIR.glob("*_review_task_v2.json")) if TASKS_DIR.exists() else []
            product_ids = [f.name.replace("_review_task_v2.json", "") for f in files]
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"product_ids": product_ids}).encode("utf-8"))
            return
        return super().do_GET()


def _load_json(path):
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def build_standard_values_lookup():
    full = _load_json(STANDARD_VALUES_EXPORT) or []
    flat = {}

    def walk(nodes):
        for node in nodes:
            coverage_name = node.get("coverage_name")
            standard_values = node.get("standard_values") or []
            if coverage_name and standard_values:
                values = []
                seen = set()
                sorted_values = sorted(
                    standard_values,
                    key=lambda x: (-int(x.get("product_count", 0)), str(x.get("value", ""))),
                )
                for item in sorted_values:
                    value = str(item.get("value", "")).strip()
                    if not value or value in seen:
                        continue
                    seen.add(value)
                    values.append(value)
                flat[coverage_name] = values
            walk(node.get("children") or [])

    walk(full)
    return flat


def _load_coverage_ids():
    mapping = {}
    id_map = _load_json(MANIFESTS_DIR / "coverage_id_mapping.json") or {}
    mapping.update(id_map)
    path_map = _load_json(MANIFESTS_DIR / "coverage_path_mapping.json") or {}
    for key, value in path_map.items():
        suffix = key.split("__")[-1]
        if suffix not in mapping:
            mapping[suffix] = value
    return mapping


COVERAGE_ID_LOOKUP = _load_coverage_ids()
STANDARD_VALUES_LOOKUP = build_standard_values_lookup()


def _scan_document_package(manifest_entry):
    files = []
    seen = set()
    parent_dirs = {
        Path(f["source_file"]).expanduser().resolve().parent
        for f in manifest_entry.get("files", [])
        if f.get("source_file")
    }
    for folder in parent_dirs:
        if not folder.exists():
            continue
        for path in sorted(folder.iterdir()):
            if not path.is_file():
                continue
            if path.name in seen:
                continue
            seen.add(path.name)
            files.append(
                {
                    "source_type": infer_file_source_type(path.name),
                    "file_name": path.name,
                    "parse_quality": "uploaded" if "uploads" in path.parts else "local",
                    "local_path": str(path),
                }
            )
    return files


def infer_file_source_type(file_name):
    if "条款" in file_name:
        return "clause"
    if "说明书" in file_name or "简要说明" in file_name:
        return "product_brochure"
    if "投核保规则" in file_name or "核保" in file_name:
        return "underwriting_rule"
    if "费率表" in file_name:
        return "raw_rate"
    if "现价表" in file_name:
        return "cash_value"
    return "other"


def infer_candidate_source_type(candidate):
    note = candidate.get("note", "")
    if "table" in note or "rate" in note:
        return "raw_rate"
    return "clause"


def choose_source_file(document_files, source_type):
    for f in document_files:
        if f.get("source_type") == source_type:
            return f.get("file_name")
    return document_files[0]["file_name"] if document_files else None


def build_candidate_source(item_id, candidate, document_files, index, conflict):
    source_type = infer_candidate_source_type(candidate)
    return {
        "source_id": f"src_{item_id}_{index}",
        "source_type": source_type,
        "file_name": choose_source_file(document_files, source_type),
        "page": candidate.get("page"),
        "block_id": candidate.get("block_id"),
        "title_path": [],
        "source_raw_value": candidate.get("evidence_text", ""),
        "md_text": candidate.get("evidence_text", ""),
        "block_text": candidate.get("evidence_text", ""),
        "raw_value": candidate.get("value", ""),
        "normalized_value": candidate.get("value", ""),
        "confidence": candidate.get("confidence", 0),
        "extract_method": candidate.get("note", ""),
        "conflict": conflict,
    }


def build_item_status(coverage_name, grouped_candidates, no_coverage_fields):
    if coverage_name in no_coverage_fields:
        return "not_applicable"
    candidates = grouped_candidates.get(coverage_name, [])
    if not candidates:
        return "not_extracted"
    unique_values = {c.get("value", "") for c in candidates if c.get("value", "")}
    if len(unique_values) > 1:
        return "review_required"
    return "candidate_ready"


def build_item(item_id_prefix, coverage_name, group_meta, grouped_candidates, no_coverage_fields, document_files):
    status = build_item_status(coverage_name, grouped_candidates, no_coverage_fields)
    candidates = grouped_candidates.get(coverage_name, [])
    unique_values = []
    for candidate in candidates:
        value = candidate.get("value", "")
        if value and value not in unique_values:
            unique_values.append(value)
    conflict = len(unique_values) > 1
    item_id = f"{item_id_prefix}_{coverage_name}"
    sources = [
        build_candidate_source(item_id, candidate, document_files, idx, conflict)
        for idx, candidate in enumerate(candidates, start=1)
    ]
    final_value = "不涉及" if status == "not_applicable" else ""
    candidate_summary = "；".join(unique_values) if unique_values else ("不涉及" if status == "not_applicable" else "")
    return {
        "item_id": item_id,
        "coverage_id": COVERAGE_ID_LOOKUP.get(coverage_name),
        "coverage_name": coverage_name,
        "status": status,
        "candidate_summary": candidate_summary,
        "final_value": final_value,
        "is_tier_a": group_meta["group_type"].startswith("tier_a"),
        "review_priority": 1 if status in {"review_required", "candidate_ready"} else 2,
        "group_level_1": group_meta["group_name"],
        "group_level_2": "—",
        "group_type": group_meta["group_type"],
        "risk_level": "high" if status in {"review_required", "candidate_ready"} else "medium",
        "is_required": True,
        "is_linked": False,
        "source_count": len(sources),
        "catalog_version": "blind_test_20260402_r13",
        "sources": sources,
        "logic_trace": {
            "priority_trace": [candidate.get("note", "") for candidate in candidates] or ["当前无候选值"],
            "normalization_trace": [f"候选标准值={value}" for value in unique_values],
            "mapping_trace": [f"coverage_name={coverage_name}"],
            "standard_value_check": "review_required" if status in {"review_required", "candidate_ready"} else status,
        },
    }


def _sort_items(items):
    return sorted(
        items,
        key=lambda item: (
            STATUS_PRIORITY.get(item.get("status", ""), 99),
            item.get("coverage_name", ""),
        ),
    )


def list_blind_test_products():
    manifest = _load_json(BLIND_TEST_MANIFEST)
    if not manifest:
        return []
    products = []
    for entry in manifest:
        products.append(
            {
                "product_id": entry.get("dir_db_id") or entry.get("product_id"),
                "product_name": entry.get("product_name", ""),
            }
        )
    return products


def build_blind_test_task(product_id):
    manifest = _load_json(BLIND_TEST_MANIFEST) or []
    tier_a = _load_json(BLIND_TEST_TIER_A) or []
    tier_b = _load_json(BLIND_TEST_TIER_B) or []
    manifest_entry = next((entry for entry in manifest if (entry.get("dir_db_id") or entry.get("product_id")) == product_id), None)
    if not manifest_entry:
        return None

    internal_product_id = manifest_entry.get("product_id")
    tier_a_entry = next((entry for entry in tier_a if entry.get("product_id") == internal_product_id), {})
    tier_b_entry = next((entry for entry in tier_b if entry.get("product_id") == internal_product_id), {})
    document_files = _scan_document_package(manifest_entry)

    grouped_candidates = defaultdict(list)
    for entry in (tier_a_entry, tier_b_entry):
        for candidate in entry.get("candidates", []):
            grouped_candidates[candidate.get("coverage_name", "")].append(candidate)

    no_coverage_fields = set(tier_b_entry.get("no_coverage_fields", []))
    field_groups = []
    all_items = []
    for group_meta in CI_REVIEW_GROUPS:
        items = [
            build_item(
                f"item_{product_id}",
                coverage_name,
                group_meta,
                grouped_candidates,
                no_coverage_fields,
                document_files,
            )
            for coverage_name in group_meta["items"]
        ]
        items = _sort_items(items)
        field_groups.append(
            {
                "group_type": group_meta["group_type"],
                "group_name": group_meta["group_name"],
                "items": items,
            }
        )
        all_items.extend(items)

    conflict_count = sum(1 for item in all_items if item["status"] == "review_required")
    missing_count = sum(1 for item in all_items if item["status"] == "not_extracted")
    pending_review_count = sum(1 for item in all_items if item["status"] in {"review_required", "candidate_ready", "not_extracted"})

    return {
        "task": {
            "task_id": f"task_{product_id}_blind_test_r13",
            "task_status": "pending_review",
            "rule_version": "blind_test_r13",
        },
        "catalog_version_at_creation": "blind_test_20260402_r13",
        "product": {
            "product_id": product_id,
            "product_name": manifest_entry.get("product_name", ""),
            "company_name": "重疾险盲测样本",
            "aix_category_id": 6001,
        },
        "document_package": {
            "document_package_id": f"pkg_{product_id}_blind_test",
            "files": document_files,
        },
        "field_groups": field_groups,
        "dependency_groups": [],
        "conflict_count": conflict_count,
        "missing_count": missing_count,
        "not_extracted_count": missing_count,
        "pending_review_count": pending_review_count,
        "total_items": len(all_items),
    }


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", PORT), ReviewModuleHandler)
    print(f"review-module server listening on http://127.0.0.1:{PORT}")
    server.serve_forever()
