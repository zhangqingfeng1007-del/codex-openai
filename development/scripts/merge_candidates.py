#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path


PROJECT_ROOT = Path.home() / "codex-openai"
RULE_CANDIDATES_PATH = PROJECT_ROOT / "development/data/extractions/tier_a_rule_candidates_v2.json"
RATE_TABLE_PATH = PROJECT_ROOT / "development/data/extractions/rate_table_candidates_v1.json"
OUTPUT_PATH = PROJECT_ROOT / "development/data/extractions/tier_a_merged_candidates_v1.json"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def format_pay_periods(pay_periods: list[str]) -> str | None:
    if not pay_periods:
        return None

    has_lump_sum = "趸交" in pay_periods
    year_values: list[int] = []
    for item in pay_periods:
        match = re.fullmatch(r"(\d+)年交", item)
        if match:
            year_values.append(int(match.group(1)))

    year_values = sorted(set(year_values))
    parts: list[str] = []
    if has_lump_sum:
        parts.append("趸交")
    if year_values:
        year_part = "/".join(str(value) for value in year_values) + "年交"
        parts.append(year_part)
    if not parts:
        return None
    return "，".join(parts)


def build_rate_table_index(rate_rows: list[dict]) -> dict[str, dict]:
    return {row["product_id"]: row for row in rate_rows}


def has_pay_period_candidate(row: dict) -> bool:
    return any(candidate.get("coverage_name") == "交费期间" for candidate in row.get("candidates", []))


def build_rate_table_candidate(value: str) -> dict:
    return {
        "coverage_name": "交费期间",
        "value": value,
        "confidence": 0.85,
        "note": "source: rate_table",
        "block_id": None,
        "page": None,
        "evidence_text": None,
    }


def main() -> None:
    rule_rows = load_json(RULE_CANDIDATES_PATH)
    rate_rows = load_json(RATE_TABLE_PATH)
    rate_index = build_rate_table_index(rate_rows)

    merged_rows: list[dict] = []
    for row in rule_rows:
        product_id = row["product_id"]
        new_row = dict(row)
        candidates = [dict(candidate) for candidate in row.get("candidates", [])]

        if not has_pay_period_candidate(row):
            rate_row = rate_index.get(product_id)
            if rate_row and rate_row.get("status") == "ok":
                value = format_pay_periods(rate_row.get("pay_periods") or [])
                if value:
                    candidates.append(build_rate_table_candidate(value))

        new_row["candidates"] = candidates
        merged_rows.append(new_row)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(merged_rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
