#!/usr/bin/env python3
"""
file_router.py — Raw file identification and parser routing.

Given a file path and optional doc_category hint, determines:
  - file_type    : text_pdf | scan_pdf | xlsx | image | unsupported
  - doc_category : clause | product_brochure | raw_rate | cash_value |
                   underwriting_rule | other
  - is_raw       : True if the file is a raw source file (not a pipeline output)
  - extractor    : pdf_text_extractor | rate_table_extractor | skip | unsupported
  - parse_quality: text_pdf | scan_pdf | xlsx | unknown
  - warnings     : list[str]

CLI usage:
    python3 file_router.py --file /path/to/file.pdf [--doc-category clause]
    python3 file_router.py --file /path/to/file.pdf --json  # machine-readable output
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants (shared with other modules — keep in sync with constants.py once
# that file is created; do NOT redeclare with different values elsewhere)
# ---------------------------------------------------------------------------

# Ordered list of (keyword, doc_category) — first match wins.
# "产品说明书" must precede "说明书" to avoid partial match shadowing.
DOCUMENT_TYPE_RULES: list[tuple[str, str]] = [
    ("产品说明书", "product_brochure"),
    ("说明书",     "product_brochure"),
    ("条款",       "clause"),
    ("费率表",     "raw_rate"),
    ("现价表",     "cash_value"),
    ("现金价值",   "cash_value"),
    ("核保",       "underwriting_rule"),
    ("投保规则",   "underwriting_rule"),
]

# Substrings in a filename that indicate a pipeline output / processed result.
# Files matching any of these are NOT raw source files.
PROCESSED_FLAGS: list[str] = [
    # Pipeline output file patterns
    "_blocks.json",
    "_blocks_degraded.json",
    "_structured_table.json",
    "_review_task_v2.json",
    "_gold.json",
    "_eval_v",
    "tier_a_rule_candidates",
    "tier_a_merged_candidates",
    # Human-processed result indicators
    "解析结果",
    "整理版",
    "汇总",
    "处理结果",
    "导出",
]

SUPPORTED_EXTENSIONS: frozenset[str] = frozenset(
    {".pdf", ".xlsx", ".xls", ".md", ".png", ".jpg", ".jpeg"}
)

IMAGE_EXTENSIONS: frozenset[str] = frozenset({".png", ".jpg", ".jpeg"})

# A PDF page with fewer than this many characters is treated as scan_pdf.
TEXT_PDF_MIN_CHARS = 50

# doc_categories that belong to the "structured table" pipeline
RATE_CATEGORIES: frozenset[str] = frozenset({"raw_rate", "cash_value"})

# doc_categories that belong to the "text → blocks" pipeline
TEXT_CATEGORIES: frozenset[str] = frozenset(
    {"clause", "product_brochure", "underwriting_rule"}
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _classify_doc_category(filename: str, hint: str | None) -> str:
    """
    Determine doc_category from filename keywords.
    If a hint is provided it is used only as a tiebreaker when the filename
    gives no match — the filename always takes precedence.
    """
    for keyword, category in DOCUMENT_TYPE_RULES:
        if keyword in filename:
            return category
    if hint and hint in (
        "clause", "product_brochure", "raw_rate", "cash_value",
        "underwriting_rule", "other",
    ):
        return hint
    return "other"


def _is_raw_file(filename: str) -> bool:
    """Return False if the filename contains any processed-file indicator."""
    for flag in PROCESSED_FLAGS:
        if flag in filename:
            return False
    return True


def _check_pdf_quality(filepath: Path) -> str:
    """
    Probe the first page of a PDF to decide text_pdf vs scan_pdf.
    Uses PyMuPDF (fitz) as primary; falls back to 'unknown' if unavailable.
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        return "unknown"

    try:
        doc = fitz.open(str(filepath))
    except Exception:
        return "unknown"

    try:
        if not doc.page_count:
            return "unknown"
        page = doc[0]
        text = page.get_text("text") or ""
        return "text_pdf" if len(text.strip()) > TEXT_PDF_MIN_CHARS else "scan_pdf"
    except Exception:
        return "unknown"
    finally:
        doc.close()


# ---------------------------------------------------------------------------
# Route table
# ---------------------------------------------------------------------------
# Key: (suffix, doc_category_bucket, parse_quality_bucket)
# Value: (extractor, phase, note)
#
# doc_category_bucket: "text" | "rate" | "other"
# parse_quality_bucket: "text" | "scan" | "xlsx" | "any"

def _extractor_from_route(
    suffix: str,
    doc_category: str,
    parse_quality: str,
) -> tuple[str, int, str]:
    """
    Return (extractor_name, phase, note) for the given routing triple.
    extractor_name is one of: pdf_text_extractor | rate_table_extractor | skip | unsupported
    """
    if suffix in {".xlsx", ".xls"}:
        if doc_category in RATE_CATEGORIES:
            return "rate_table_extractor", 1, ""
        return "skip", 1, f"xlsx with doc_category={doc_category} not a rate file"

    if suffix == ".pdf":
        if doc_category in TEXT_CATEGORIES:
            if parse_quality == "text_pdf":
                return "pdf_text_extractor", 1, ""
            if parse_quality == "scan_pdf":
                return "skip", 2, "scan_pdf: Phase 2 OCR not yet implemented"
            # unknown quality — optimistically route to text extractor; it will
            # detect failure and set parse_quality=degraded in its output.
            return "pdf_text_extractor", 1, "parse_quality=unknown, routed optimistically"
        if doc_category in RATE_CATEGORIES:
            if parse_quality == "scan_pdf":
                return "skip", 2, "scanned rate table: Phase 2"
            return "rate_table_extractor", 1, ""
        # other
        return "skip", 1, f"pdf with doc_category={doc_category} has no Phase 1 extractor"

    if suffix in IMAGE_EXTENSIONS:
        return "skip", 2, "image files: Phase 2 OCR"

    if suffix == ".md":
        return "skip", 1, ".md is an internal intermediate file, not a raw input"

    return "unsupported", 0, f"unsupported extension: {suffix}"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def route_file(file_path: Path, doc_category_hint: str | None = None) -> dict:
    """
    Return a routing result dict for one source file.

    Schema:
      file_path     : str   — absolute path as given
      file_type     : str   — text_pdf | scan_pdf | xlsx | image | unsupported
      doc_category  : str   — clause | product_brochure | raw_rate | cash_value |
                              underwriting_rule | other
      is_raw        : bool  — False if file looks like a pipeline output
      extractor     : str   — pdf_text_extractor | rate_table_extractor | skip | unsupported
      parse_quality : str   — text_pdf | scan_pdf | xlsx | unknown
      phase         : int   — 1 = Phase 1 (implemented), 2 = future
      warnings      : list[str]
    """
    warnings: list[str] = []
    path = Path(file_path).expanduser().resolve()

    if not path.exists():
        return {
            "file_path": str(file_path),
            "file_type": "unknown",
            "doc_category": "unknown",
            "is_raw": False,
            "extractor": "unsupported",
            "parse_quality": "unknown",
            "phase": 0,
            "warnings": [f"file not found: {file_path}"],
        }

    suffix = path.suffix.lower()
    filename = path.name

    # --- is_raw ---
    is_raw = _is_raw_file(filename)
    if not is_raw:
        matched = next((f for f in PROCESSED_FLAGS if f in filename), "")
        warnings.append(f"processed_file_detected: matched flag '{matched}'")

    # --- doc_category ---
    doc_category = _classify_doc_category(filename, doc_category_hint)

    # --- parse_quality + file_type ---
    if suffix in {".xlsx", ".xls"}:
        parse_quality = "xlsx"
        file_type = "xlsx"
    elif suffix == ".pdf":
        parse_quality = _check_pdf_quality(path)
        file_type = parse_quality  # text_pdf | scan_pdf | unknown
    elif suffix in IMAGE_EXTENSIONS:
        parse_quality = "unknown"
        file_type = "image"
    elif suffix == ".md":
        parse_quality = "unknown"
        file_type = "markdown"
    else:
        parse_quality = "unknown"
        file_type = "unsupported"

    # --- extractor + phase ---
    extractor, phase, note = _extractor_from_route(suffix, doc_category, parse_quality)
    if note:
        warnings.append(note)

    return {
        "file_path": str(path),
        "file_type": file_type,
        "doc_category": doc_category,
        "is_raw": is_raw,
        "extractor": extractor,
        "parse_quality": parse_quality,
        "phase": phase,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Identify a raw source file and return its parser routing decision."
    )
    parser.add_argument("--file", required=True, help="Path to the file to route.")
    parser.add_argument(
        "--doc-category",
        default=None,
        help="Optional hint for doc_category when filename keywords are ambiguous.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="output_json",
        help="Output result as JSON (default: human-readable summary).",
    )
    args = parser.parse_args()

    result = route_file(Path(args.file), args.doc_category)

    if args.output_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    # Human-readable summary
    tag = "RAW" if result["is_raw"] else "PROCESSED"
    phase_tag = f"Phase {result['phase']}" if result["phase"] > 0 else "—"
    print(f"[{tag}] {Path(result['file_path']).name}")
    print(f"  doc_category  : {result['doc_category']}")
    print(f"  file_type     : {result['file_type']}")
    print(f"  parse_quality : {result['parse_quality']}")
    print(f"  extractor     : {result['extractor']}  ({phase_tag})")
    if result["warnings"]:
        for w in result["warnings"]:
            print(f"  ⚠  {w}")


if __name__ == "__main__":
    main()
