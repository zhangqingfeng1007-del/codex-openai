#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

try:
    import fitz
except ImportError:  # pragma: no cover - optional dependency in local env
    fitz = None

from parse_md_blocks import parse_markdown, serialize_blocks_payload


TEXT_PDF_MIN_CHARS = 50
TEXT_PDF_STRONG_PAGE_CHARS = 150
TEXT_PDF_PROBE_PAGES = 3
DEGRADED_BLOCK_THRESHOLD = 10
VENDOR_DOC_TO_MD_DIR = Path("/Users/zqf-openclaw/codex-openai/development/vendor/doc_to_md")
DOC_TO_MD_PYTHON = Path("/Users/zqf-openclaw/codex-openai/development/.venv_doc_to_md/bin/python")


def utc_now() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def detect_parse_quality(pdf_path: Path) -> str:
    if fitz is None:
        return "unknown"
    try:
        doc = fitz.open(str(pdf_path))
    except Exception:
        return "unknown"
    try:
        if not doc.page_count:
            return "unknown"
        total_chars = 0
        page_limit = min(doc.page_count, TEXT_PDF_PROBE_PAGES)
        for page_index in range(page_limit):
            text = (doc[page_index].get_text("text") or "").strip()
            char_count = len(text)
            if char_count >= TEXT_PDF_STRONG_PAGE_CHARS:
                return "text_pdf"
            total_chars += char_count
        return "scan_pdf" if total_chars <= TEXT_PDF_MIN_CHARS else "text_pdf"
    finally:
        doc.close()


def convert_pdf_to_markdown(pdf_path: Path, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    expected = output_dir / f"{pdf_path.stem}.md"
    if expected.exists():
        return expected

    with tempfile.TemporaryDirectory(prefix="pdf_text_extractor_") as temp_dir:
        temp_input_dir = Path(temp_dir)
        temp_input_file = temp_input_dir / pdf_path.name
        shutil.copy2(pdf_path, temp_input_file)
        cmd = [
            str(DOC_TO_MD_PYTHON),
            "-m",
            "doc_to_md.cli",
            "convert",
            "--input-path",
            str(temp_input_dir),
            "--output-path",
            str(output_dir),
            "--engine",
            "markitdown",
        ]
        subprocess.run(cmd, check=True, cwd=str(VENDOR_DOC_TO_MD_DIR))
    if not expected.exists():
        raise FileNotFoundError(f"Markdown not generated: {expected}")
    return expected


def extract_text_by_fitz(pdf_path: Path) -> str:
    if fitz is None:
        raise RuntimeError("fitz unavailable")
    try:
        doc = fitz.open(str(pdf_path))
    except Exception as exc:  # pragma: no cover - runtime dependency behavior
        raise RuntimeError(f"fitz open failed: {exc}") from exc
    pages: list[str] = []
    try:
        for page in doc:
            pages.append(page.get_text("text") or "")
    finally:
        doc.close()
    return "\f".join(pages)


def build_meta(
    product_id: str,
    doc_category: str,
    source_file: Path,
    parse_method: str,
    parse_quality: str,
    warnings: list[str],
) -> dict:
    return {
        "product_id": product_id,
        "doc_category": doc_category,
        "source_file": str(source_file),
        "parse_method": parse_method,
        "parse_quality": parse_quality,
        "generated_at": utc_now(),
        "warnings": warnings,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract text PDF to blocks.json with _meta.")
    parser.add_argument("--input", required=True, help="Input PDF path.")
    parser.add_argument("--product-id", required=True, help="Product ID.")
    parser.add_argument("--doc-category", required=True, help="Document category, e.g. clause/product_brochure.")
    parser.add_argument("--output", required=True, help="Output blocks.json path.")
    args = parser.parse_args()

    input_path = Path(args.input).expanduser().resolve()
    output_path = Path(args.output).expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    parse_quality = detect_parse_quality(input_path)
    warnings: list[str] = []
    parse_method = "markitdown"

    try:
        md_dir = output_path.parent / "_md_cache"
        md_path = convert_pdf_to_markdown(input_path, md_dir)
        md_text = md_path.read_text(encoding="utf-8")
        blocks = parse_markdown(args.product_id, md_text)
    except Exception as exc:
        parse_method = "fitz_text"
        warnings.append(f"markitdown_failed: {exc}")
        md_text = extract_text_by_fitz(input_path)
        blocks = parse_markdown(args.product_id, md_text)

    if len(blocks) < DEGRADED_BLOCK_THRESHOLD:
        parse_quality = "degraded"
        warnings.append(f"too_few_blocks:{len(blocks)}")

    meta = build_meta(
        product_id=args.product_id,
        doc_category=args.doc_category,
        source_file=input_path,
        parse_method=parse_method,
        parse_quality=parse_quality,
        warnings=warnings,
    )
    payload = serialize_blocks_payload(blocks, meta)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {len(blocks)} blocks to {output_path}")


if __name__ == "__main__":
    main()
