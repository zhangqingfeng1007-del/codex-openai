#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

try:
    import fitz
except ImportError:  # pragma: no cover - optional dependency in local env
    fitz = None

from parse_md_blocks import parse_markdown, serialize_blocks_payload


DEGRADED_BLOCK_THRESHOLD = 10
DEFAULT_DPI = 300
OCR_PYTHON = Path("/Users/zqf-openclaw/codex-openai/development/.venv_ocr/bin/python")
PADDLE_PDX_CACHE_HOME = Path("/Users/zqf-openclaw/codex-openai/development/.cache/paddlex")
FALLBACK_PADDLE_CACHE_HOME = Path.home() / ".paddlex"


def utc_now() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def bbox_to_rect(bbox: list[list[float]]) -> tuple[float, float, float, float]:
    xs = [float(point[0]) for point in bbox]
    ys = [float(point[1]) for point in bbox]
    return min(xs), min(ys), max(xs), max(ys)


def rect_height(rect: tuple[float, float, float, float]) -> float:
    return max(1.0, rect[3] - rect[1])


def rect_center_x(rect: tuple[float, float, float, float]) -> float:
    return (rect[0] + rect[2]) / 2.0


def normalize_text(text: str) -> str:
    return " ".join((text or "").replace("\u00a0", " ").split()).strip()


def pdf_to_page_images(pdf_path: Path, temp_dir: Path, dpi: int = DEFAULT_DPI) -> list[dict]:
    if fitz is None:
        raise RuntimeError("fitz unavailable")
    try:
        doc = fitz.open(str(pdf_path))
    except Exception as exc:  # pragma: no cover - runtime dependency behavior
        raise RuntimeError(f"fitz open failed: {exc}") from exc

    scale = dpi / 72.0
    matrix = fitz.Matrix(scale, scale)
    pages: list[dict] = []
    try:
        for page_index, page in enumerate(doc):
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            image_path = temp_dir / f"page_{page_index + 1:04d}.png"
            pix.save(str(image_path))
            pages.append(
                {
                    "page_index": page_index + 1,
                    "image_path": image_path,
                    "width": float(pix.width),
                    "height": float(pix.height),
                }
            )
    finally:
        doc.close()
    return pages


def build_ocr_engine():
    local_model_marker = PADDLE_PDX_CACHE_HOME / "official_models" / "PP-LCNet_x1_0_doc_ori" / "inference.yml"
    cache_home = PADDLE_PDX_CACHE_HOME if local_model_marker.exists() else FALLBACK_PADDLE_CACHE_HOME
    os.environ["PADDLE_PDX_CACHE_HOME"] = str(cache_home)
    cache_home.mkdir(parents=True, exist_ok=True)
    try:
        from paddleocr import PaddleOCR
    except ImportError as exc:  # pragma: no cover - runtime dependency behavior
        raise RuntimeError(
            f"paddleocr unavailable; create OCR venv and install dependencies first at {OCR_PYTHON}"
        ) from exc
    return PaddleOCR(lang="ch")


def parse_ocr_result(raw_result) -> list[dict]:
    """Parse PaddleOCR result into [{text, bbox, confidence}].

    Supports:
    - PaddleOCR v3: result[0] is an OCRResult with rec_texts/rec_scores/rec_polys
    - PaddleOCR v2: result[0] is list of [bbox, (text, confidence)]
    """
    parsed: list[dict] = []
    if not raw_result:
        return parsed

    ocr_res = raw_result[0] if raw_result else None
    if ocr_res is None:
        return parsed

    # PaddleOCR v3: OCRResult object with rec_texts / rec_polys / rec_scores
    if hasattr(ocr_res, "keys") and all(k in ocr_res for k in ("rec_texts", "rec_scores", "rec_polys")):
        texts = list(ocr_res.get("rec_texts") or [])
        scores = list(ocr_res.get("rec_scores") or [])
        polys = list(ocr_res.get("rec_polys") or [])
        for i, text in enumerate(texts):
            text = normalize_text(text)
            if not text:
                continue
            confidence = float(scores[i]) if i < len(scores) else 0.0
            poly = polys[i] if i < len(polys) else []
            # poly is ndarray shape (4,2); convert to [[x,y], ...]
            bbox = [[float(pt[0]), float(pt[1])] for pt in poly] if len(poly) else []
            parsed.append({"text": text, "bbox": bbox, "confidence": confidence})
        return parsed

    # PaddleOCR v2 fallback: result[0] is list of [bbox, (text, confidence)]
    rows = ocr_res if isinstance(ocr_res, list) else []
    for row in rows:
        if not row:
            continue

        bbox = None
        rec = None

        if isinstance(row, (list, tuple)) and len(row) >= 2:
            bbox, rec = row[0], row[1]
        elif isinstance(row, dict):
            bbox = row.get("bbox") or row.get("box") or row.get("points")
            rec = row.get("rec") or row.get("text")

        if not bbox or rec is None:
            continue

        if isinstance(rec, str):
            text = normalize_text(rec)
            confidence = 0.0
        elif isinstance(rec, (list, tuple)) and rec:
            text = normalize_text(rec[0])
            confidence = float(rec[1]) if len(rec) > 1 and isinstance(rec[1], (int, float)) else 0.0
        elif isinstance(rec, dict):
            text = normalize_text(rec.get("text", ""))
            confidence = float(rec.get("confidence", 0.0) or 0.0)
        else:
            text = ""
            confidence = 0.0

        if not text:
            continue

        parsed.append(
            {
                "text": text,
                "bbox": [[float(x), float(y)] for x, y in bbox],
                "confidence": confidence,
            }
        )

    return parsed


def ocr_page(image_path: Path, ocr_engine) -> list[dict]:
    raw_result = ocr_engine.ocr(str(image_path))
    return parse_ocr_result(raw_result)


def maybe_insert_space(prev_text: str, next_text: str, gap: float, avg_height: float) -> str:
    if not prev_text or not next_text:
        return ""
    if gap > avg_height * 0.8:
        return " "
    if prev_text[-1].isascii() and next_text[0].isascii():
        return " "
    if prev_text[-1].isdigit() and not next_text[0].isdigit():
        return " "
    if prev_text[-1] in ").）】" or next_text[0] in "([（【":
        return " "
    return ""


def cluster_columns(items: list[dict], page_width: float) -> list[list[dict]]:
    if len(items) < 4:
        return [items]

    centers = sorted(
        ((rect_center_x(item["rect"]), item) for item in items),
        key=lambda pair: pair[0],
    )
    max_gap = 0.0
    split_index = -1
    for index in range(len(centers) - 1):
        gap = centers[index + 1][0] - centers[index][0]
        if gap > max_gap:
            max_gap = gap
            split_index = index

    if max_gap <= page_width * 0.3 or split_index < 0:
        return [items]

    left = [item for _, item in centers[: split_index + 1]]
    right = [item for _, item in centers[split_index + 1 :]]
    if not left or not right:
        return [items]
    return [left, right]


def column_items_to_lines(items: list[dict]) -> list[str]:
    if not items:
        return []

    ordered = sorted(items, key=lambda item: (item["rect"][1], item["rect"][0]))
    rows: list[dict] = []
    for item in ordered:
        height = rect_height(item["rect"])
        if not rows:
            rows.append({"items": [item], "y": item["rect"][1], "height": height})
            continue

        prev = rows[-1]
        y_diff = abs(item["rect"][1] - prev["y"])
        threshold = max(prev["height"], height) * 0.5
        if y_diff < threshold:
            prev["items"].append(item)
            prev["y"] = min(prev["y"], item["rect"][1])
            prev["height"] = max(prev["height"], height)
        else:
            rows.append({"items": [item], "y": item["rect"][1], "height": height})

    lines: list[str] = []
    prev_bottom: float | None = None
    prev_height: float | None = None
    for row in rows:
        row_items = sorted(row["items"], key=lambda item: item["rect"][0])
        if prev_bottom is not None and prev_height is not None:
            gap_y = row["y"] - prev_bottom
            if gap_y > prev_height * 1.5:
                lines.append("")

        parts: list[str] = []
        prev_right: float | None = None
        prev_text: str = ""
        row_avg_height = sum(rect_height(item["rect"]) for item in row_items) / max(1, len(row_items))
        for item in row_items:
            text = item["text"]
            if not text:
                continue
            if prev_right is None:
                parts.append(text)
            else:
                gap_x = item["rect"][0] - prev_right
                parts.append(maybe_insert_space(prev_text, text, gap_x, row_avg_height) + text)
            prev_right = item["rect"][2]
            prev_text = text

        merged = "".join(parts).strip()
        if merged:
            lines.append(merged)
            prev_bottom = max(item["rect"][3] for item in row_items)
            prev_height = max(rect_height(item["rect"]) for item in row_items)

    return lines


def page_items_to_text(page_items: list[dict], page_width: float) -> str:
    columns = cluster_columns(page_items, page_width)
    column_texts: list[str] = []
    for column in columns:
        lines = column_items_to_lines(column)
        if lines:
            column_texts.append("\n".join(lines))
    return "\n".join(text for text in column_texts if text).strip()


def ocr_lines_to_markdown(ocr_pages: list[dict], warnings: list[str]) -> tuple[str, bool]:
    page_texts: list[str] = []
    saw_double_column = False

    for page in ocr_pages:
        items: list[dict] = []
        for result in page["results"]:
            rect = bbox_to_rect(result["bbox"])
            items.append({**result, "rect": rect})

        if not items:
            warnings.append(f"page_{page['page_index']}:no_ocr_text")
            page_texts.append("")
            continue

        columns = cluster_columns(items, page["width"])
        if len(columns) == 2:
            saw_double_column = True

        text = page_items_to_text(items, page["width"])
        page_texts.append(text)

    return "\f".join(page_texts), saw_double_column


def build_meta(
    product_id: str,
    doc_category: str,
    source_file: Path,
    char_count: int,
    page_count: int | None,
    warnings: list[str],
) -> dict:
    return {
        "product_id": product_id,
        "doc_category": doc_category,
        "source_file": str(source_file),
        "parse_method": "paddleocr",
        "parse_quality": "scan_pdf",
        "char_count": char_count,
        "page_count": page_count,
        "generated_at": utc_now(),
        "warnings": warnings,
    }


def extract_markdown_by_ocr(input_path: Path, warnings: list[str]) -> tuple[str, bool]:
    with tempfile.TemporaryDirectory(prefix="pdf_ocr_extractor_") as temp_dir:
        temp_path = Path(temp_dir)
        pages = pdf_to_page_images(input_path, temp_path, dpi=DEFAULT_DPI)
        ocr_engine = build_ocr_engine()
        ocr_pages: list[dict] = []
        for page in pages:
            results = ocr_page(page["image_path"], ocr_engine)
            ocr_pages.append({**page, "results": results})
        return ocr_lines_to_markdown(ocr_pages, warnings)


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract scan PDF to blocks.json with OCR.")
    parser.add_argument("--input", required=True, help="Input PDF path.")
    parser.add_argument("--product-id", required=True, help="Product ID.")
    parser.add_argument("--doc-category", required=True, help="Document category, e.g. clause/product_brochure.")
    parser.add_argument("--output", required=True, help="Output blocks.json path.")
    args = parser.parse_args()

    input_path = Path(args.input).expanduser().resolve()
    output_path = Path(args.output).expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    warnings: list[str] = []
    md_text, saw_double_column = extract_markdown_by_ocr(input_path, warnings)
    if saw_double_column:
        warnings.append("layout:double_column_detected")

    blocks = parse_markdown(args.product_id, md_text)
    char_count = sum(len((block.get("text") or "")) for block in blocks)
    page_count = len(md_text.split("\f")) if md_text else 0
    meta = build_meta(
        product_id=args.product_id,
        doc_category=args.doc_category,
        source_file=input_path,
        char_count=char_count,
        page_count=page_count,
        warnings=warnings,
    )
    if len(blocks) < DEGRADED_BLOCK_THRESHOLD:
        meta["parse_quality"] = "degraded"
        warnings.append(f"too_few_blocks:{len(blocks)}")

    payload = serialize_blocks_payload(blocks, meta)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {len(blocks)} blocks to {output_path}")


if __name__ == "__main__":
    main()
