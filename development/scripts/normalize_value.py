#!/usr/bin/env python3
import re


NORMALIZE_TEST_CASES = [
    ("保险期间", "10年，20年，30年", "10/20/30年"),
    ("保险期间", "10/20/30年", "10/20/30年"),
    ("保险期间", "终身", "终身"),
    ("保险期间", "至65周岁，终身", "至65周岁，终身"),
    ("交费期间", "趸交，5年，10年，20年，30年", "趸交，5/10/20/30年交"),
    ("交费期间", "趸交，3/5/10/20年交", "趸交，3/5/10/20年交"),
    ("交费期间", "10年交", "10年交"),
    ("交费频率", "年交", "年交"),
    ("交费频率", "年缴，月缴", "年交，月交"),
    ("交费频率", "一次性付清", "趸交"),
    ("投保年龄", "0-60周岁", "0-60周岁"),
    ("投保年龄", "0（28天）-60周岁", "0（28天）-60周岁"),
    ("等待期", "非意外90天，意外0天", "非意外90天，意外0天"),
    ("重疾数量", "120种重大疾病", "120种"),
    ("重疾数量", "162种", "162种"),
]

_FREQUENCY_MAP = {
    "一次性付清": "趸交",
    "趸交": "趸交",
    "年缴": "年交",
    "年交": "年交",
    "月缴": "月交",
    "月交": "月交",
    "半年缴": "半年交",
    "半年交": "半年交",
    "季缴": "季交",
    "季交": "季交",
}


def _split_parts(value: str) -> list[str]:
    return [part.strip() for part in re.split(r"[，、,]", value) if part.strip()]


def _normalize_period(value: str, coverage_name: str) -> str:
    if "/" in value:
        return value

    parts = _split_parts(value)
    if not parts:
        return value

    numeric_years = []
    normalized_parts = []
    suffix = "年交" if coverage_name == "交费期间" else "年"

    for part in parts:
        year_match = re.fullmatch(r"(\d+)年(?:交)?", part)
        if year_match:
            numeric_years.append(year_match.group(1))
        else:
            normalized_parts.append(part)

    if not numeric_years:
        return value

    joined = "/".join(numeric_years) + suffix
    inserted = False
    result = []
    for part in normalized_parts:
        if not inserted and part != "趸交":
            result.append(joined)
            inserted = True
        result.append(part)
    if not inserted:
        result.append(joined)

    if normalized_parts and normalized_parts[0] == "趸交":
        result = ["趸交", joined] + normalized_parts[1:]

    return "，".join(result)


def _normalize_frequency(value: str) -> str:
    parts = _split_parts(value)
    normalized = []
    for part in parts:
        normalized.append(_FREQUENCY_MAP.get(part, part))
    return "，".join(normalized) if normalized else value


def _normalize_age(value: str) -> str:
    compact = re.sub(r"\s+", "", value)
    if re.fullmatch(r"\d+（\d+[天日]）-\d+周岁", compact):
        return compact.replace("日", "天")
    if re.fullmatch(r"\d+-\d+周岁", compact):
        return compact

    m = re.fullmatch(r"0至(\d+)周岁", compact)
    if m:
        return f"0-{m.group(1)}周岁"
    m = re.fullmatch(r"0周岁至(\d+)周岁", compact)
    if m:
        return f"0-{m.group(1)}周岁"
    m = re.fullmatch(r"(\d+)[天日]-(\d+)周岁", compact)
    if m:
        return f"0（{m.group(1)}天）-{m.group(2)}周岁"
    m = re.fullmatch(r"出生满(\d+)[天日]至(\d+)岁?", compact)
    if m:
        return f"0（{m.group(1)}天）-{m.group(2)}周岁"
    m = re.fullmatch(r"出生满(\d+)[天日]至(\d+)周岁", compact)
    if m:
        return f"0（{m.group(1)}天）-{m.group(2)}周岁"
    return value.strip()


def _normalize_waiting_period(value: str) -> str:
    compact = re.sub(r"\s+", "", value)
    if compact == "无":
        return "无"
    if re.fullmatch(r"非意外\d+[天年]，意外0天", compact):
        return compact
    m = re.fullmatch(r"疾病(\d+[天年])，意外0天", compact)
    if m:
        return f"非意外{m.group(1)}，意外0天"
    m = re.fullmatch(r"非意外(\d+[天年])", compact)
    if m:
        return f"非意外{m.group(1)}，意外0天"
    m = re.fullmatch(r"(\d+[天年])", compact)
    if m:
        return f"非意外{m.group(1)}，意外0天"
    return value.strip()


def _normalize_ci_count(value: str) -> str:
    compact = re.sub(r"\s+", "", value)
    m = re.search(r"(\d+)种", compact)
    if m:
        return f"{m.group(1)}种"
    return value.strip()


def normalize_value(coverage_name: str, raw_value: str) -> str:
    value = (raw_value or "").strip()
    if not value or value == "—":
        return value

    if coverage_name in {"保险期间", "交费期间"}:
        return _normalize_period(value, coverage_name)
    if coverage_name == "交费频率":
        return _normalize_frequency(value)
    if coverage_name == "投保年龄":
        return _normalize_age(value)
    if coverage_name in {"等待期", "等待期（简化）"}:
        return _normalize_waiting_period(value)
    if coverage_name == "重疾数量":
        return _normalize_ci_count(value)
    return value


def run_tests():
    failures = 0
    for coverage_name, raw, expected in NORMALIZE_TEST_CASES:
        result = normalize_value(coverage_name, raw)
        ok = result == expected
        if not ok:
            failures += 1
        status = "✓" if ok else f"✗ got '{result}'"
        print(f"[{status}] {coverage_name} | '{raw}' → '{expected}'")
    return failures


if __name__ == "__main__":
    raise SystemExit(run_tests())
