#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


CHINESE_DIGITS = {
    "零": 0,
    "〇": 0,
    "一": 1,
    "二": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}


def chinese_to_int(text: str) -> int | None:
    if not text:
        return None
    if text.isdigit():
        return int(text)
    if text == "十":
        return 10
    if "百" in text:
        parts = text.split("百", 1)
        hundreds = CHINESE_DIGITS.get(parts[0], 1 if parts[0] == "" else None)
        if hundreds is None:
            return None
        remainder = chinese_to_int(parts[1]) if parts[1] else 0
        if remainder is None:
            return None
        return hundreds * 100 + remainder
    if "十" in text:
        parts = text.split("十", 1)
        tens = CHINESE_DIGITS.get(parts[0], 1 if parts[0] == "" else None)
        if tens is None:
            return None
        ones = CHINESE_DIGITS.get(parts[1], 0) if parts[1] else 0
        return tens * 10 + ones
    total = 0
    for ch in text:
        if ch not in CHINESE_DIGITS:
            return None
        total = total * 10 + CHINESE_DIGITS[ch]
    return total


PAGE_RE = re.compile(r"第([一二三四五六七八九十百零〇0-9]+)页")
MD_TITLE_RE = re.compile(r"^(#{1,3})\s+(.+?)\s*$")
ARTICLE_TITLE_RE = re.compile(r"^第[一二三四五六七八九十百零〇0-9]+(条|章|部分)\s+.+$")
OUTLINE_TITLE_RE = re.compile(r"^(\d+(?:\.\d+){0,2})\s+(.+)$")
OUTLINE_INLINE_TITLE_RE = re.compile(r"^(\d+(?:\.\d+){0,2})\s+(.+?)(?:\s{2,}|\t+)(.+)$")
LIST_RE = re.compile(r"^(?:[-*]\s+|\d+\.\s+).+")
TABLE_RE = re.compile(r"^\|.*\|$")
TABLE_SEPARATOR_RE = re.compile(r"^\|\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?$")
BLOCK_JOINER_RE = re.compile(r"\s+")


def normalize_inline_text(text: str) -> str:
    text = text.replace("\u000c", " ").replace("\u00a0", " ")
    text = BLOCK_JOINER_RE.sub(" ", text)
    return text.strip()


def is_probable_title(line: str) -> tuple[int, str] | None:
    match = MD_TITLE_RE.match(line)
    if match:
        return len(match.group(1)), match.group(2).strip()

    stripped = line.strip()
    if ARTICLE_TITLE_RE.match(stripped):
        return 1, stripped

    match = OUTLINE_TITLE_RE.match(stripped)
    if match and len(stripped) <= 80:
        level = min(max(match.group(1).count("."), 1), 3)
        return level, stripped

    return None


def split_inline_outline_title(line: str) -> tuple[int, str, str] | None:
    stripped = line.strip()
    match = OUTLINE_INLINE_TITLE_RE.match(stripped)
    if not match:
        return None
    outline = match.group(1)
    title_text = f"{outline} {match.group(2).strip()}"
    remainder = match.group(3).strip()
    if len(title_text) > 60 or len(remainder) < 8:
        return None
    level = min(max(outline.count("."), 1), 3)
    return level, title_text, remainder


def extract_page_number(page_text: str, fallback_page: int) -> int:
    match = PAGE_RE.search(page_text)
    if not match:
        return fallback_page
    page_no = chinese_to_int(match.group(1))
    return page_no if page_no is not None else fallback_page


def next_title_stack(current_stack: list[str], level: int, title_text: str) -> list[str]:
    if title_text[:1].isdigit() or title_text.startswith("第"):
        return [title_text]
    stack = current_stack[: level - 1]
    stack.append(title_text)
    return stack


def build_block(product_id: str, page: int, block_index: int, block_type: str, title_path: list[str], text: str, cross_page_candidate: bool = False) -> dict:
    block = {
        "block_id": f"{product_id}_p{page}_b{block_index}",
        "page": page,
        "block_type": block_type,
        "title_path": title_path[:],
        "text": text,
        "char_count": len(text),
    }
    if cross_page_candidate:
        block["cross_page_candidate"] = True
    return block


def flush_buffer(product_id: str, page: int, block_index: int, block_type: str | None, title_stack: list[str], lines: list[str], cross_page_candidate: bool = False) -> tuple[dict | None, int]:
    if not lines or not block_type:
        return None, block_index
    text = normalize_inline_text("\n".join(lines))
    if not text:
        return None, block_index
    block = build_block(product_id, page, block_index, block_type, title_stack, text, cross_page_candidate)
    return block, block_index + 1


def parse_page_blocks(product_id: str, page: int, page_text: str, title_stack: list[str], starting_block_index: int) -> tuple[list[dict], list[str], int]:
    blocks: list[dict] = []
    block_index = starting_block_index
    lines = page_text.splitlines()
    buffer_lines: list[str] = []
    buffer_type: str | None = None
    in_toc = "条款目录" in page_text

    def flush_current(cross_page_candidate: bool = False) -> None:
        nonlocal buffer_lines, buffer_type, block_index
        block, block_index = flush_buffer(
            product_id=product_id,
            page=page,
            block_index=block_index,
            block_type=buffer_type,
            title_stack=title_stack,
            lines=buffer_lines,
            cross_page_candidate=cross_page_candidate,
        )
        if block:
            blocks.append(block)
        buffer_lines = []
        buffer_type = None

    i = 0
    while i < len(lines):
        raw_line = lines[i].replace("\u0000", "")
        stripped = raw_line.strip()

        if not stripped:
            flush_current()
            i += 1
            continue

        inline_title = split_inline_outline_title(stripped)
        if inline_title and not in_toc:
            flush_current()
            level, title_text, remainder = inline_title
            title_stack = next_title_stack(title_stack, level, title_text)
            blocks.append(build_block(product_id, page, block_index, "title", title_stack, title_text))
            block_index += 1
            blocks.append(build_block(product_id, page, block_index, "paragraph", title_stack, remainder))
            block_index += 1
            i += 1
            continue

        title_match = is_probable_title(stripped)
        if title_match and not in_toc:
            flush_current()
            level, title_text = title_match
            title_stack = next_title_stack(title_stack, level, title_text)
            blocks.append(build_block(product_id, page, block_index, "title", title_stack, title_text))
            block_index += 1
            i += 1
            continue

        if TABLE_RE.match(stripped):
            flush_current()
            table_lines = [stripped]
            i += 1
            while i < len(lines) and lines[i].strip() and (TABLE_RE.match(lines[i].strip()) or TABLE_SEPARATOR_RE.match(lines[i].strip())):
                table_lines.append(lines[i].strip())
                i += 1
            block, block_index = flush_buffer(product_id, page, block_index, "table", title_stack, table_lines)
            if block:
                blocks.append(block)
            continue

        if LIST_RE.match(stripped):
            if buffer_type not in (None, "list"):
                flush_current()
            buffer_type = "list"
            buffer_lines.append(stripped)
            i += 1
            continue

        if buffer_type not in (None, "paragraph"):
            flush_current()
        buffer_type = "paragraph"
        buffer_lines.append(stripped)
        i += 1

    if buffer_lines:
        flush_current(cross_page_candidate=not page_text.endswith("\n"))

    return blocks, title_stack, block_index


def parse_markdown(product_id: str, md_text: str) -> list[dict]:
    page_segments = md_text.split("\f")
    all_blocks: list[dict] = []
    title_stack: list[str] = []
    block_index = 1

    for idx, segment in enumerate(page_segments, start=1):
        page_text = segment.strip("\n")
        if not page_text.strip():
            continue
        page = extract_page_number(page_text, idx)
        blocks, title_stack, block_index = parse_page_blocks(
            product_id=product_id,
            page=page,
            page_text=page_text,
            title_stack=title_stack,
            starting_block_index=block_index,
        )
        all_blocks.extend(blocks)
    return all_blocks


def serialize_blocks_payload(blocks: list[dict], meta: dict | None = None) -> dict | list[dict]:
    if not meta:
        return blocks
    return {
        "_meta": meta,
        "blocks": blocks,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Parse Markdown clause files into structured blocks.")
    parser.add_argument("--product-id", required=True, help="Logical product_id used in file names.")
    parser.add_argument("--input", required=True, help="Input Markdown file path.")
    parser.add_argument("--output", required=True, help="Output JSON file path.")
    parser.add_argument(
        "--meta-json",
        help="Optional JSON object to store as top-level _meta; preserves legacy block format under blocks[].",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    md_text = input_path.read_text(encoding="utf-8")
    blocks = parse_markdown(args.product_id, md_text)
    meta = json.loads(args.meta_json) if args.meta_json else None
    payload = serialize_blocks_payload(blocks, meta)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"wrote {len(blocks)} blocks to {output_path}")


if __name__ == "__main__":
    main()
