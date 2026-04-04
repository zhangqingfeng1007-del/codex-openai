"""Minimal field rule config loader — Phase 1 pilot.

Loads field_rules_v1.json and provides lookup by coverage_name.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

DEFAULT_RULES_PATH = Path(__file__).resolve().parents[1] / "data" / "field_rules" / "field_rules_v1.json"


def load_field_rules(path: Path = DEFAULT_RULES_PATH) -> dict[str, dict]:
    """Load field rules config, return dict keyed by coverage_name."""
    data = json.loads(path.read_text(encoding="utf-8"))
    return {f["coverage_name"]: f for f in data.get("fields", [])}


def get_section_hints(rules: dict[str, dict], coverage_name: str) -> list[str]:
    """Get section_hints for a field from config. Returns [] if not configured."""
    rule = rules.get(coverage_name)
    if not rule:
        return []
    return rule.get("section_hints", [])


def get_value_normalization(rules: dict[str, dict], coverage_name: str) -> list[dict]:
    """Get value_normalization ops for a field."""
    rule = rules.get(coverage_name)
    if not rule:
        return []
    return rule.get("value_normalization", [])


def apply_value_normalization(value: str, ops: list[dict]) -> str:
    """Apply value_normalization operations to extracted value.

    Supported ops:
      - {"strip_suffix": ["str1", "str2"]}  — remove first matching tail
      - {"precision": "year_only"}           — strip day/month from age ranges
      - {"replace": {"from": "X", "to": "Y"}}
      - {"trim": true}                       — strip whitespace + trailing punctuation
    """
    if not value or not ops:
        return value
    for op in ops:
        if "strip_suffix" in op:
            for suffix in op["strip_suffix"]:
                if value.endswith(suffix):
                    value = value[: -len(suffix)]
                    break
        elif "precision" in op:
            if op["precision"] == "year_only":
                # "0（28天）-55周岁" → "0-55周岁"
                value = re.sub(r"（[^）]*[天月][^）]*）", "", value)
                value = re.sub(r"\([^)]*[天月][^)]*\)", "", value)
        elif "replace" in op:
            r = op["replace"]
            value = value.replace(r.get("from", ""), r.get("to", ""))
        elif "trim" in op and op["trim"]:
            value = value.strip().rstrip("，。、；：")
    return value


def get_match_strategy(rules: dict[str, dict], coverage_name: str) -> str | None:
    """Get match_strategy for a field."""
    rule = rules.get(coverage_name)
    if not rule:
        return None
    return rule.get("match_strategy")


def get_extraction_strategy(rules: dict[str, dict], coverage_name: str) -> str | None:
    """Get extraction_strategy for a field."""
    rule = rules.get(coverage_name)
    if not rule:
        return None
    return rule.get("extraction_strategy")


def is_field_enabled(rules: dict[str, dict], coverage_name: str) -> bool:
    """Check if a field is enabled in config."""
    rule = rules.get(coverage_name)
    if not rule:
        return True  # Not in config → default enabled (backward compat)
    return rule.get("enabled", True) is True
