#!/usr/bin/env python3
"""
verify_structured_tables.py — 集成验证脚本

Codex 批量生成 data/tables/{product_id}_structured_table.json 后运行此脚本，确认：
1. 覆盖率：哪些产品有产物，哪些缺失
2. pay_periods 内容合理性：非空、无明显异常值
3. 与主链集成效果：structured_table fallback 是否实际补充了 候选字段

用法：
    python3 verify_structured_tables.py
    python3 verify_structured_tables.py --manifest /tmp/manifest_new_format.json
    python3 verify_structured_tables.py --json    # 输出完整 JSON 报告
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).parent
_REPO_ROOT = _SCRIPT_DIR.parent
sys.path.insert(0, str(_SCRIPT_DIR))

from extract_tier_a_rules import (  # noqa: E402
    RATE_TABLES_DIR,
    build_candidates_from_structured_table,
    locate_structured_table_json,
    load_manifest_compatible,
)
from build_product_manifest import build_manifest  # noqa: E402

# 期望的 pay_periods 参考值（用于合理性检查）
EXPECTED_PAY_PERIODS: dict[str, list[str]] = {
    "889":   ["趸交", "5年交", "10年交", "15年交", "20年交", "25年交", "30年交"],
    "851A":  ["趸交", "5年交", "10年交", "15年交", "20年交", "30年交"],
    "864":   ["10年交", "15年交", "20年交", "30年交"],
    "1134":  ["10年交", "20年交", "30年交"],
    "1803":  ["趸交", "3年交", "5年交", "10年交", "15年交", "20年交", "30年交"],
}

# pay_periods 预期为空的产品及原因：
#   1578 — 自然费率表（按计划/逐年费率），无固定缴费期；交费期间须从条款提取
KNOWN_EMPTY: set[str] = {"1578"}

_FALLBACK_FIELDS = ("保险期间", "交费期间", "交费频率")


def check_pay_periods(product_id: str, pay_periods: list) -> list[str]:
    """返回合理性警告列表（空列表=无问题）。"""
    issues: list[str] = []
    if not pay_periods:
        if product_id in KNOWN_EMPTY:
            return []  # 已知，不报警
        issues.append("pay_periods 为空（非预期）")
        return issues

    # 检查是否含非字符串值
    bad = [v for v in pay_periods if not isinstance(v, str)]
    if bad:
        issues.append(f"pay_periods 含非字符串值: {bad}")

    # 对比期望值（若有参考）
    expected = EXPECTED_PAY_PERIODS.get(product_id)
    if expected:
        missing = [v for v in expected if v not in pay_periods]
        extra   = [v for v in pay_periods if v not in expected]
        if missing:
            issues.append(f"缺少期望值: {missing}")
        if extra:
            issues.append(f"多余非期望值: {extra}")

    return issues


def run_verification(manifest_path: Path | None) -> dict:
    """
    执行完整验证，返回报告 dict。
    """
    # ── 1. 加载 manifest ────────────────────────────────────────────────────
    if manifest_path:
        items = load_manifest_compatible(manifest_path)
    else:
        default_dir = Path("/Users/zqf-openclaw/Desktop/开发材料/10款重疾")
        if not default_dir.exists():
            sys.exit(f"[ERROR] 默认目录不存在: {default_dir}，请用 --manifest 指定")
        entries = build_manifest([default_dir])
        # build_manifest 输出已含 source_files，直接转为 compatible 格式
        tmp = Path("/tmp/_verify_manifest_tmp.json")
        tmp.write_text(json.dumps(entries, ensure_ascii=False), encoding="utf-8")
        items = load_manifest_compatible(tmp)

    # ── 2. 逐产品检查 ────────────────────────────────────────────────────────
    rows: list[dict] = []
    for item in items:
        product_id   = item.get("product_id") or "UNKNOWN"
        product_name = item.get("product_name", "")

        st_path = locate_structured_table_json(item, "raw_rate")
        has_file = st_path is not None and st_path.exists()

        row: dict = {
            "product_id":   product_id,
            "product_name": product_name,
            "file_found":   has_file,
            "file_path":    str(st_path) if st_path else None,
            "pay_periods":  [],
            "pay_frequencies": [],
            "insurance_periods": [],
            "issues":       [],
            "fallback_fields_added": [],
        }

        if not has_file:
            if st_path:
                row["issues"].append(f"文件路径已定位但不存在: {st_path.name}")
            else:
                row["issues"].append("locate_structured_table_json 返回 None（无匹配路径）")
            rows.append(row)
            continue

        # 读取内容
        try:
            raw = json.loads(st_path.read_text(encoding="utf-8"))
            ef  = raw.get("extracted_fields", {})
            row["pay_periods"]       = ef.get("pay_periods", [])
            row["pay_frequencies"]   = ef.get("pay_frequencies", [])
            row["insurance_periods"] = ef.get("insurance_periods", [])
        except Exception as exc:
            row["issues"].append(f"读取/解析失败: {exc}")
            rows.append(row)
            continue

        # 合理性检查
        row["issues"].extend(check_pay_periods(product_id, row["pay_periods"]))

        # 检查 fallback 是否能产生候选
        try:
            candidates = build_candidates_from_structured_table(st_path)
            row["fallback_fields_added"] = list(candidates.keys())
        except Exception as exc:
            row["issues"].append(f"build_candidates_from_structured_table 失败: {exc}")

        rows.append(row)

    # ── 3. 汇总统计 ─────────────────────────────────────────────────────────
    total      = len(rows)
    found      = sum(1 for r in rows if r["file_found"])
    with_issues = sum(1 for r in rows if r["issues"])
    known_empty_ok = sum(1 for r in rows if r["product_id"] in KNOWN_EMPTY and not r["pay_periods"])

    return {
        "summary": {
            "total":          total,
            "files_found":    found,
            "files_missing":  total - found,
            "with_issues":    with_issues,
            "known_empty_ok": known_empty_ok,
        },
        "products": rows,
    }


def print_report(report: dict) -> None:
    s = report["summary"]
    print(f"\n{'='*60}")
    print(f"structured_table 集成验证报告")
    print(f"{'='*60}")
    print(f"产品总数:     {s['total']}")
    print(f"文件已生成:   {s['files_found']}")
    print(f"文件缺失:     {s['files_missing']}")
    print(f"有问题:       {s['with_issues']}")
    print(f"已知空输出:   {s['known_empty_ok']} ({', '.join(KNOWN_EMPTY)})")
    print()

    for r in report["products"]:
        pid    = r["product_id"]
        status = "✅" if r["file_found"] and not r["issues"] else ("⚠️" if r["file_found"] else "❌")
        pp     = r["pay_periods"]
        fb     = r["fallback_fields_added"]

        pp_str = f"{len(pp)}项: {pp}" if pp else "[]"
        fb_str = ", ".join(fb) if fb else "—"

        print(f"  {status} {pid:8} | pay_periods={pp_str}")
        print(f"           | fallback补充字段: {fb_str}")
        if r["issues"]:
            for issue in r["issues"]:
                print(f"           | ⚠ {issue}")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="验证 data/tables/ 中 structured_table.json 的覆盖率和内容合理性"
    )
    parser.add_argument(
        "--manifest",
        metavar="FILE",
        help="指定 manifest JSON 路径（默认：自动扫描 10款重疾目录）",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="输出完整 JSON 报告",
    )
    args = parser.parse_args()

    manifest_path = Path(args.manifest).expanduser() if args.manifest else None
    report = run_verification(manifest_path)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_report(report)

    # 非零退出码：有缺失文件或非预期问题时
    s = report["summary"]
    if s["files_missing"] > 0 or s["with_issues"] > s["known_empty_ok"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
