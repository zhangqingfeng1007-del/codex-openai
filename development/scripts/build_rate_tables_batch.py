#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

from file_router import route_file  # noqa: E402
from rate_table_extractor import extract_rate_table  # noqa: E402


RAW_RATE_CATEGORY = "raw_rate"
SUPPORTED_RATE_SUFFIXES = {".pdf", ".xlsx", ".xls"}


def extract_product_id(dirname: str) -> str | None:
    parts = dirname.split("-", 1)
    if not parts:
        return None
    head = parts[0]
    if not head:
        return None
    if head[:-1].isdigit() and head[-1:].isalpha():
        return head
    if head.isdigit():
        return head
    return None


def choose_rate_file(product_dir: Path) -> tuple[str | None, Path | None, list[str]]:
    warnings: list[str] = []
    candidates: list[tuple[Path, dict]] = []

    for entry in sorted(product_dir.iterdir(), key=lambda p: p.name):
        if not entry.is_file():
            continue
        if entry.suffix.lower() not in SUPPORTED_RATE_SUFFIXES:
            continue
        routed = route_file(entry)
        if not routed.get("is_raw"):
            continue
        if routed.get("doc_category") != RAW_RATE_CATEGORY:
            continue
        candidates.append((entry, routed))

    if not candidates:
        return None, None, warnings

    xlsx_candidates = [item for item in candidates if item[0].suffix.lower() in {".xlsx", ".xls"}]
    pdf_candidates = [item for item in candidates if item[0].suffix.lower() == ".pdf"]

    if xlsx_candidates and pdf_candidates:
        warnings.append("xlsx_preferred_over_pdf")

    chosen_path, routed = (xlsx_candidates[0] if xlsx_candidates else pdf_candidates[0])
    return routed["doc_category"], chosen_path, warnings


def build_batch(input_root: Path, output_dir: Path) -> list[dict]:
    rows: list[dict] = []
    output_dir.mkdir(parents=True, exist_ok=True)

    for product_dir in sorted((p for p in input_root.iterdir() if p.is_dir()), key=lambda p: p.name):
        product_id = extract_product_id(product_dir.name)
        if not product_id:
            rows.append(
                {
                    "product_id": None,
                    "product_dir": str(product_dir),
                    "status": "skipped",
                    "reason": "cannot_extract_product_id",
                }
            )
            continue

        doc_category, source_file, warnings = choose_rate_file(product_dir)
        if not source_file or not doc_category:
            rows.append(
                {
                    "product_id": product_id,
                    "product_dir": str(product_dir),
                    "status": "skipped",
                    "reason": "no_raw_rate_file",
                }
            )
            continue

        output_file = output_dir / f"{product_id}_structured_table.json"
        try:
            payload = extract_rate_table(
                product_id=product_id,
                doc_category=doc_category,
                input_file=source_file,
                output_json=output_file,
            )
            rows.append(
                {
                    "product_id": product_id,
                    "product_dir": str(product_dir),
                    "status": "ok",
                    "doc_category": doc_category,
                    "source_file": str(source_file),
                    "output_file": str(output_file),
                    "warnings": warnings,
                    "extracted_fields": payload.get("extracted_fields", {}),
                }
            )
        except Exception as exc:  # pragma: no cover - batch robustness
            rows.append(
                {
                    "product_id": product_id,
                    "product_dir": str(product_dir),
                    "status": "error",
                    "doc_category": doc_category,
                    "source_file": str(source_file),
                    "output_file": str(output_file),
                    "warnings": warnings,
                    "error": str(exc),
                }
            )

    return rows


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Batch-generate structured_table.json from raw rate files.")
    parser.add_argument(
        "--input-root",
        default="/Users/zqf-openclaw/Desktop/开发材料/10款重疾",
        help="Root directory containing one product directory per child.",
    )
    parser.add_argument(
        "--output-dir",
        default="/Users/zqf-openclaw/codex-openai/development/data/tables",
        help="Output directory for {product_id}_structured_table.json files.",
    )
    parser.add_argument(
        "--summary",
        default="/Users/zqf-openclaw/codex-openai/development/data/tables/batch_summary.json",
        help="Summary JSON output path.",
    )
    parser.add_argument("--json", action="store_true", help="Print batch summary as JSON")
    return parser


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()

    input_root = Path(args.input_root).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    summary_path = Path(args.summary).expanduser().resolve()

    rows = build_batch(input_root, output_dir)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return

    ok_count = sum(1 for row in rows if row["status"] == "ok")
    skipped_count = sum(1 for row in rows if row["status"] == "skipped")
    error_count = sum(1 for row in rows if row["status"] == "error")
    print(f"wrote {ok_count} structured tables to {output_dir}")
    print(f"summary: {summary_path}")
    print(f"ok={ok_count} skipped={skipped_count} error={error_count}")


if __name__ == "__main__":
    main()
