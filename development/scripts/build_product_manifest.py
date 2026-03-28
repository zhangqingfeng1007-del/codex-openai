#!/usr/bin/env python3
"""
build_product_manifest.py — Auto-scan product directories and generate manifest.

Given one or more root directories, scans each immediate subdirectory as one product,
calls file_router.route_file() for every file, groups results into files[], and
outputs a manifest JSON consumable by extract_tier_a_rules.py.

CLI usage:
    python3 build_product_manifest.py \\
        --input-dir ~/Desktop/开发材料/10款重疾 \\
        --output data/manifests/sample_manifest_v2.json

    # Multiple root directories (merged output):
    python3 build_product_manifest.py \\
        --input-dir ~/Desktop/开发材料/10款重疾 \\
        --input-dir ~/Desktop/开发材料/招行数据 \\
        --output data/manifests/batch_manifest.json

    # Single product mode (treat input-dir itself as one product, no recursion):
    python3 build_product_manifest.py \\
        --input-dir ~/Desktop/开发材料/10款重疾/889-中信保诚... \\
        --single-product \\
        --output data/manifests/889_manifest.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Resolve file_router location
# ---------------------------------------------------------------------------
_SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(_SCRIPT_DIR))
from file_router import route_file  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Regex to extract product_id from directory or file name prefix.
# Matches patterns like: 889, 851A, 1548A, 1010003676
_PRODUCT_ID_RE = re.compile(r'^(\d+[A-Z]?)-')

# doc_categories that go into files[] (all others are logged in warnings only)
_SOURCE_CATEGORIES = frozenset(
    {"clause", "product_brochure", "raw_rate", "cash_value", "underwriting_rule"}
)

# Supported file extensions to scan (others are silently ignored)
_SCAN_EXTENSIONS = frozenset({".pdf", ".xlsx", ".xls"})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_product_id(dirname: str) -> str | None:
    """
    Extract product_id from a directory name.

    Priority:
    1. Directory name prefix matching r'^(\\d+[A-Z]?)-'
    2. Returns None if no match.
    """
    m = _PRODUCT_ID_RE.match(dirname)
    return m.group(1) if m else None


def _extract_product_name(dirname: str) -> str:
    """
    Extract human-readable product name from directory name.
    Strips the product_id prefix (e.g., "889-中信保诚..." → "中信保诚...").
    """
    m = _PRODUCT_ID_RE.match(dirname)
    if m:
        return dirname[m.end():]
    return dirname


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Core scan logic
# ---------------------------------------------------------------------------

def scan_product_directory(dir_path: Path) -> dict:
    """
    Scan a single product directory and return a manifest entry dict.

    Schema:
      product_id       : str | null
      product_name     : str
      db_product_id    : null   (not populated; requires DB lookup)
      directory        : str    (absolute path)
      scan_time        : str    (ISO 8601 UTC)
      files            : list[dict]
      warnings         : list[str]
      phase1_eligible  : null   (must be set manually after review)
      status           : "pending_review"
    """
    warnings: list[str] = []

    product_id = _extract_product_id(dir_path.name)
    if product_id is None:
        warnings.append(f"cannot_extract_product_id: '{dir_path.name}'")

    product_name = _extract_product_name(dir_path.name)

    files: list[dict] = []

    # Scan direct children only (no recursion into sub-subdirectories)
    try:
        entries = sorted(dir_path.iterdir(), key=lambda p: p.name)
    except PermissionError as exc:
        warnings.append(f"permission_error: {exc}")
        entries = []

    for entry in entries:
        if not entry.is_file():
            continue
        if entry.suffix.lower() not in _SCAN_EXTENSIONS:
            continue

        result = route_file(entry)

        if not result["is_raw"]:
            matched = next(
                (w for w in result["warnings"] if w.startswith("processed_file_detected")),
                "processed_file_detected",
            )
            warnings.append(f"skipped_processed_file: {entry.name} ({matched})")
            continue

        doc_category = result["doc_category"]

        if doc_category == "other":
            warnings.append(f"skipped_other: {entry.name}")
            continue

        if doc_category not in _SOURCE_CATEGORIES:
            warnings.append(f"unknown_doc_category: {entry.name} → {doc_category}")
            continue

        file_entry = {
            "doc_category": doc_category,
            "source_file": str(entry),
            "file_name": entry.name,
            "parse_quality": result["parse_quality"],
            "is_raw": result["is_raw"],
            "parser_route": result["extractor"],
            "phase": result["phase"],
        }

        if result["warnings"]:
            file_entry["router_warnings"] = result["warnings"]

        files.append(file_entry)

    files.sort(key=lambda item: (item["doc_category"], item["file_name"]))

    clause_pdf_path = next(
        (item["source_file"] for item in files if item["doc_category"] == "clause"),
        None,
    )

    return {
        "product_id": product_id,
        "product_name": product_name,
        "db_product_id": None,
        "directory": str(dir_path),
        "scan_time": _now_iso(),
        "files": files,
        "clause_pdf_path": clause_pdf_path,
        "warnings": warnings,
        "phase1_eligible": None,
        "status": "pending_review",
    }


def build_manifest(
    input_dirs: list[Path],
    single_product: bool = False,
) -> list[dict]:
    """
    Build a full manifest list from one or more root directories.

    Args:
        input_dirs: List of root directories to scan.
        single_product: If True, treat each input_dir itself as a product
                        directory (no subdirectory enumeration).

    Returns:
        List of product manifest entry dicts.
    """
    entries: list[dict] = []

    for root in input_dirs:
        root = root.expanduser().resolve()
        if not root.is_dir():
            print(f"[WARN] Not a directory, skipping: {root}", file=sys.stderr)
            continue

        if single_product:
            entries.append(scan_product_directory(root))
        else:
            # Each immediate subdirectory = one product
            subdirs = sorted(
                (p for p in root.iterdir() if p.is_dir()),
                key=lambda p: p.name,
            )
            if not subdirs:
                print(
                    f"[WARN] No subdirectories found in {root}; "
                    "use --single-product if this is itself a product directory.",
                    file=sys.stderr,
                )
            for subdir in subdirs:
                entries.append(scan_product_directory(subdir))

    return entries


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scan product directories and generate a manifest JSON."
    )
    parser.add_argument(
        "--input-dir",
        dest="input_dirs",
        action="append",
        required=True,
        metavar="DIR",
        help="Root directory to scan (can be specified multiple times).",
    )
    parser.add_argument(
        "--output",
        required=True,
        metavar="FILE",
        help="Output manifest JSON file path.",
    )
    parser.add_argument(
        "--single-product",
        action="store_true",
        default=False,
        help=(
            "Treat each --input-dir as a single product directory "
            "(no subdirectory enumeration)."
        ),
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        default=True,
        help="Pretty-print output JSON (default: true).",
    )
    args = parser.parse_args()

    input_dirs = [Path(d) for d in args.input_dirs]
    output_path = Path(args.output).expanduser()

    manifest = build_manifest(input_dirs, single_product=args.single_product)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        indent = 2 if args.pretty else None
        json.dump(manifest, f, ensure_ascii=False, indent=indent)

    # Summary
    total = len(manifest)
    no_id = sum(1 for e in manifest if e["product_id"] is None)
    with_warnings = sum(1 for e in manifest if e["warnings"])
    print(f"Scanned {total} product(s). Written to: {output_path}")
    if no_id:
        print(f"  [WARN] {no_id} product(s) could not extract product_id")
    if with_warnings:
        print(f"  [INFO] {with_warnings} product(s) have warnings (check manifest)")


if __name__ == "__main__":
    main()
