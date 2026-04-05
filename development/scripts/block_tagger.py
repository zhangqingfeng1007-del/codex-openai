"""Runtime block tagger — returns tagged copies of blocks, does NOT mutate the input.

tag_blocks(blocks) returns a new list of shallow-copied dicts, each with an
added "_tags" key.  The original blocks list and its dicts are never modified.
Callers must use the returned list (not the original) to access tags:

    tagged = tag_blocks(blocks)   # new list; original blocks unchanged
    if tagged[i]["_tags"]["is_example"]:
        ...

This module does NOT alter blocks.json on disk.
"""
from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Marker sets (union of all previously scattered skip/filter constants)
# ---------------------------------------------------------------------------

# Title-path markers → is_example
_EXAMPLE_TITLE_MARKERS = frozenset([
    "举例", "示例", "案例", "理赔案例", "保险金给付案例", "利益演示", "演示",
])

# Text markers → is_example
_EXAMPLE_TEXT_MARKERS = frozenset([
    "小王", "小明", "以上举例仅供",
])

# Title-path markers → is_toc
_TOC_TITLE_MARKERS = frozenset([
    "条款目录", "目录", "阅读指引",
])

# Title-path / text markers → is_definition
_DEFINITION_TITLE_MARKERS = frozenset([
    "释义", "名词解释", "术语定义",
])

# Text hints that indicate definition/explanation context (not actual clauses)
_DEFINITION_TEXT_MARKERS = frozenset([
    "确诊日起满", "保单周年日",
])

# Positive clause markers (block likely contains actual policy terms)
_CLAUSE_MARKERS = frozenset([
    "确诊", "罹患", "等待期", "观察期", "意外",
    "保险费", "保险金", "豁免", "给付", "赔付",
    "责任免除", "免除责任",
])


def _normalize(text: str) -> str:
    """Remove whitespace for matching."""
    return re.sub(r"\s+", "", text)


def tag_block(block: dict) -> dict:
    """Return a shallow copy of *block* with an added ``_tags`` dict.

    Tags:
        is_example   — example / case study block (skip for extraction)
        is_toc       — table of contents or reading guide
        is_definition— glossary / definition section
        is_clause    — contains actual policy clause markers
        is_matchable — not example, not toc → eligible for field extraction
    """
    title_path_raw = block.get("title_path") or []
    title_joined = "".join(title_path_raw)
    text = block.get("text", "")
    compact = _normalize(text)

    # --- is_example ---
    is_example = (
        any(m in title_joined for m in _EXAMPLE_TITLE_MARKERS)
        or any(m in compact for m in _EXAMPLE_TEXT_MARKERS)
    )
    # Extra heuristic: block text ends with example-closing pattern
    if not is_example and "举例" in compact:
        is_example = True

    # --- is_toc ---
    is_toc = any(m in title_joined for m in _TOC_TITLE_MARKERS)
    if not is_toc and "条款目录" in compact[:40]:
        is_toc = True

    # --- is_definition ---
    is_definition = (
        any(m in title_joined for m in _DEFINITION_TITLE_MARKERS)
        or any(m in compact for m in _DEFINITION_TEXT_MARKERS)
    )

    # --- is_clause ---
    is_clause = any(m in compact for m in _CLAUSE_MARKERS)

    # --- is_matchable ---
    is_matchable = not is_example and not is_toc

    tagged = dict(block)  # shallow copy
    tagged["_tags"] = {
        "is_example": is_example,
        "is_toc": is_toc,
        "is_definition": is_definition,
        "is_clause": is_clause,
        "is_matchable": is_matchable,
    }
    return tagged


def tag_blocks(blocks: list[dict]) -> list[dict]:
    """Tag all blocks in a list. Returns new list (does not mutate input)."""
    return [tag_block(b) for b in blocks]
