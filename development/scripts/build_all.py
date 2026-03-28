#!/usr/bin/env python3
"""
build_all.py — 从产品目录一键生成 manifest + blocks + structured_tables。

Phase 1 批量入口：给定一个或多个产品根目录，依次执行：
  1. build_product_manifest  → manifest.json
  2. pdf_text_extractor       → data/blocks/{product_id}_{doc_category}_blocks.json
  3. build_rate_tables_batch  → data/tables/{product_id}_structured_table.json

用法：
    python3 build_all.py --input-dir ~/Desktop/开发材料/10款重疾
    python3 build_all.py --input-dir DIR1 --input-dir DIR2 --output-manifest /tmp/manifest.json
    python3 build_all.py --input-dir DIR --skip-blocks      # 只跑 manifest + tables
    python3 build_all.py --input-dir DIR --skip-tables     # 只跑 manifest + blocks
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).parent
_REPO_ROOT = _SCRIPT_DIR.parent

BLOCKS_DIR    = _REPO_ROOT / "data" / "blocks"
TABLES_DIR    = _REPO_ROOT / "data" / "tables"
MANIFEST_DEFAULT = _REPO_ROOT / "data" / "manifests" / "manifest_latest.json"

# doc_category 值映射到 blocks 文件名（{product_id}_{name} 或 {product_id}_blocks.json）
# 与 extract_tier_a_rules.py 消费路径保持一致：
#   clause           → {product_id}_blocks.json
#   product_brochure → {product_id}_说明书_blocks.json
#   underwriting_rule→ {product_id}_underwriting_blocks.json（主链暂未消费）
_BLOCKS_FILENAME: dict[str, str] = {
    "clause":            "{product_id}_blocks.json",
    "product_brochure":  "{product_id}_说明书_blocks.json",
    "underwriting_rule": "{product_id}_underwriting_blocks.json",
}

# 只有这些 doc_category 需要生成 blocks
_TEXT_CATEGORIES = frozenset(_BLOCKS_FILENAME.keys())


def run(cmd: list[str], label: str) -> bool:
    """Run subprocess, print status. Returns True on success."""
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  [FAIL] {label}")
        if result.stderr:
            print(f"         {result.stderr.strip()[:200]}")
        return False
    # Print last line of stdout as summary
    last = (result.stdout or "").strip().split("\n")[-1]
    if last:
        print(f"  [OK]   {label}: {last}")
    else:
        print(f"  [OK]   {label}")
    return True


def step_manifest(input_dirs: list[Path], output: Path) -> bool:
    cmd = [sys.executable, str(_SCRIPT_DIR / "build_product_manifest.py")]
    for d in input_dirs:
        cmd += ["--input-dir", str(d)]
    cmd += ["--output", str(output)]
    return run(cmd, f"manifest → {output.name}")


def step_blocks(manifest_path: Path, skip: bool) -> dict[str, int]:
    """Generate blocks.json for each text-category file in manifest.
    Returns {product_id: blocks_written} summary."""
    if skip:
        print("  [SKIP] blocks (--skip-blocks)")
        return {}

    with manifest_path.open(encoding="utf-8") as f:
        manifest = json.load(f)

    BLOCKS_DIR.mkdir(parents=True, exist_ok=True)
    summary: dict[str, int] = {}

    for item in manifest:
        product_id = item.get("product_id") or "UNKNOWN"
        files = item.get("files", [])
        for entry in files:
            cat = entry.get("doc_category", "")
            if cat not in _TEXT_CATEGORIES:
                continue
            if entry.get("parse_quality") == "scan_pdf":
                print(f"  [SKIP] {product_id} {cat}: scan_pdf (Phase 2)")
                continue
            if not entry.get("is_raw"):
                continue

            source = Path(entry["source_file"])
            out = BLOCKS_DIR / _BLOCKS_FILENAME[cat].format(product_id=product_id)

            # Skip if already up-to-date (source older than output)
            if out.exists() and out.stat().st_mtime >= source.stat().st_mtime:
                print(f"  [SKIP] {product_id} {cat}: up-to-date")
                continue

            cmd = [
                sys.executable,
                str(_SCRIPT_DIR / "pdf_text_extractor.py"),
                "--input", str(source),
                "--product-id", product_id,
                "--doc-category", cat,
                "--output", str(out),
            ]
            ok = run(cmd, f"{product_id} {cat}")
            if ok:
                summary[f"{product_id}_{cat}"] = 1

    return summary


def step_tables(input_dirs: list[Path], skip: bool) -> bool:
    if skip:
        print("  [SKIP] structured_tables (--skip-tables)")
        return True
    TABLES_DIR.mkdir(parents=True, exist_ok=True)
    # build_rate_tables_batch.py takes a single --input-root; run once per directory.
    ok = True
    for i, d in enumerate(input_dirs):
        summary_name = f"batch_summary_{i}.json" if len(input_dirs) > 1 else "batch_summary.json"
        cmd = [
            sys.executable,
            str(_SCRIPT_DIR / "build_rate_tables_batch.py"),
            "--output-dir", str(TABLES_DIR),
            "--summary", str(TABLES_DIR / summary_name),
            "--input-root", str(d),
        ]
        if not run(cmd, f"structured_tables {d.name}"):
            ok = False
    return ok


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Phase 1 一键批量生成：manifest + blocks + structured_tables"
    )
    parser.add_argument(
        "--input-dir",
        dest="input_dirs",
        action="append",
        required=True,
        metavar="DIR",
        help="产品根目录（可重复）",
    )
    parser.add_argument(
        "--output-manifest",
        default=str(MANIFEST_DEFAULT),
        metavar="FILE",
        help=f"manifest 输出路径（默认：{MANIFEST_DEFAULT}）",
    )
    parser.add_argument(
        "--skip-blocks",
        action="store_true",
        help="跳过 blocks 生成（pdf_text_extractor）",
    )
    parser.add_argument(
        "--skip-tables",
        action="store_true",
        help="跳过 structured_table 生成（rate_table_extractor batch）",
    )
    args = parser.parse_args()

    input_dirs = [Path(d).expanduser().resolve() for d in args.input_dirs]
    manifest_path = Path(args.output_manifest).expanduser()
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"\n=== build_all: {len(input_dirs)} 目录 ===\n")

    # Step 1: manifest
    print("Step 1: 生成 manifest")
    if not step_manifest(input_dirs, manifest_path):
        sys.exit(1)

    # Step 2: blocks
    print("\nStep 2: 生成 blocks.json")
    step_blocks(manifest_path, args.skip_blocks)

    # Step 3: structured tables
    print("\nStep 3: 生成 structured_table.json")
    step_tables(input_dirs, args.skip_tables)

    print(f"\n=== 完成 ===")
    print(f"manifest: {manifest_path}")
    print(f"blocks:   {BLOCKS_DIR}/")
    print(f"tables:   {TABLES_DIR}/")


if __name__ == "__main__":
    main()
