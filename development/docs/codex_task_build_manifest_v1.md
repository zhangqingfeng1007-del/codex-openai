# Codex 任务：build_product_manifest.py — 原始文件自动扫描建 Manifest

任务版本：V1
编写时间：2026-03-28
优先级：P0（核心基础能力）
新建文件：`development/scripts/build_product_manifest.py`

---

## 背景

当前 `data/manifests/sample_manifest.json` 是手工维护的。每接入新产品需要手动填写文件路径、文档类型、product_id，且容易误入"费率解析结果表.xlsx"等人工处理结果文件（违反方法论原则6）。

本任务新建 `build_product_manifest.py`，给定一个或多个目录，自动扫描 → 识别 → 输出标准 manifest JSON，供 `extract_tier_a_rules.py` 消费。

---

## 验收标准

1. 对 `~/Desktop/开发材料/10款重疾` 运行，输出 10 条产品条目，每条都有 clause 文件
2. 每条的 `parse_quality` 正确区分 `text_pdf` 和 `scanned_pdf`
3. 处理结果文件（如文件名含"解析结果"）不进入 `source_files`，只在 `warnings` 中记录
4. 生成的 manifest 传给 `extract_tier_a_rules.py`（手动将 `phase1_eligible` 设为 `true`）后，eval 结果与 V18 基线完全一致

---

## 一、输出 JSON 格式

每产品一条，整体是 JSON 数组：

```json
[
  {
    "product_id": "889",
    "product_name": "中信保诚「惠康」重大疾病保险（至诚少儿版）",
    "db_product_id": null,
    "directory": "/Users/zqf-openclaw/Desktop/开发材料/10款重疾/889-中信保诚.../",
    "scan_time": "2026-03-28T12:00:00",
    "source_files": {
      "clause":   [{"file_name": "...-条款.pdf",   "local_path": "...", "parse_quality": "text_pdf", "is_raw": true}],
      "raw_rate": [{"file_name": "...-费率表.pdf",  "local_path": "...", "parse_quality": "text_pdf", "is_raw": true},
                   {"file_name": "...-费率表.xlsx", "local_path": "...", "parse_quality": "xlsx",     "is_raw": true}],
      "brochure": [],
      "price_table": [],
      "other":    []
    },
    "warnings": [],
    "phase1_eligible": null,
    "status": "pending_review"
  }
]
```

**说明**：
- `phase1_eligible: null` + `status: "pending_review"` → 需要人工确认后才进提取链路
- `db_product_id: null` → 无法自动填写，需要数据库查询后补
- `is_raw: false` 的文件**不进** `source_files`，只记录在 `warnings`

---

## 二、核心常量

```python
# 文档类型分类规则（顺序匹配，先匹配先赢）
TYPE_RULES = [
    (["条款", "保险条款"],     "clause"),
    (["说明书", "产品说明"],   "brochure"),
    (["费率表"],               "raw_rate"),
    (["现价表", "利益演示"],   "price_table"),
    (["核保", "投保须知"],     "underwriting"),
    # 无匹配 → "other"
]

# 处理结果文件特征词（命中则 is_raw=False）
PROCESSED_FLAGS = ["解析结果", "整理版", "汇总", "处理结果", "导出"]

# 支持的文件后缀
SUPPORTED_EXTENSIONS = {".pdf", ".xlsx", ".xls"}

# PDF 文字判定阈值（第1页提取字符数）
TEXT_PDF_MIN_CHARS = 50
```

---

## 三、函数实现规范

### 3.1 `extract_product_id(dirname: str, filenames: list[str]) -> str | None`

```
优先级：
1. 目录名前缀：re.match(r'^(\d+[A-Z]?)-', dirname)  → group(1)
2. 文件名前缀：对 filenames 排序后依次匹配同一正则，取第一个命中
3. 两者都失败  → return None
```

### 3.2 `extract_product_name(dirname: str, product_id: str) -> str`

```
从目录名中去掉 "{product_id}-" 前缀，返回剩余部分作为产品名。
若目录名不含前缀，则返回目录名原值。
```

### 3.3 `classify_doc_type(filename: str) -> str`

```
遍历 TYPE_RULES，检查 filename 是否包含任意关键词（用 in 判断即可）。
第一个命中的类型胜出。无命中返回 "other"。
```

### 3.4 `is_raw_file(filename: str, filepath: str) -> bool`

**两步检查**：
1. **文件名检查**：filename 是否含 PROCESSED_FLAGS 中任意词 → 返回 False
2. **XLSX sheet 检查**（仅 .xlsx/.xls）：
   - 用 `openpyxl.load_workbook(filepath, read_only=True)` 读取 sheet 名
   - 若任意 sheet 名含 PROCESSED_FLAGS 中词 → 返回 False
   - openpyxl 导入失败则跳过此步
3. 否则返回 True

### 3.5 `check_parse_quality(filepath: str) -> str`

- 后缀 `.xlsx/.xls` → 直接返回 `"xlsx"`
- 后缀 `.pdf`：
  ```python
  try:
      import pdfplumber
      with pdfplumber.open(filepath) as pdf:
          if not pdf.pages:
              return "scanned_pdf"
          text = pdf.pages[0].extract_text() or ""
          return "text_pdf" if len(text.strip()) > TEXT_PDF_MIN_CHARS else "scanned_pdf"
  except Exception:
      return "unknown"
  ```

### 3.6 `scan_product_directory(dir_path: Path) -> dict`

扫描单个产品目录，返回一条 manifest 条目：

```python
def scan_product_directory(dir_path: Path) -> dict:
    dirname = dir_path.name
    all_files = [f for f in sorted(dir_path.iterdir())
                 if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS]
    filenames = [f.name for f in all_files]

    product_id = extract_product_id(dirname, filenames)
    product_name = extract_product_name(dirname, product_id or "")

    source_files = {"clause": [], "raw_rate": [], "brochure": [],
                    "price_table": [], "underwriting": [], "other": []}
    warnings = []
    if product_id is None:
        warnings.append("cannot_extract_product_id")

    for f in all_files:
        if not is_raw_file(f.name, str(f)):
            warnings.append(f"processed_file_skipped: {f.name}")
            continue
        doc_type = classify_doc_type(f.name)
        quality = check_parse_quality(str(f))
        if quality == "scanned_pdf":
            warnings.append(f"scanned_pdf: {f.name}")
        entry = {
            "file_name": f.name,
            "local_path": str(f),
            "parse_quality": quality,
            "is_raw": True,
        }
        source_files.setdefault(doc_type, []).append(entry)

    if not source_files.get("clause"):
        warnings.append("no_clause_found")

    return {
        "product_id": product_id,
        "product_name": product_name,
        "db_product_id": None,
        "directory": str(dir_path),
        "scan_time": datetime.utcnow().isoformat(timespec="seconds"),
        "source_files": source_files,
        "warnings": warnings,
        "phase1_eligible": None,
        "status": "pending_review",
    }
```

### 3.7 `build_manifest(input_dirs: list[Path], single_product: bool) -> list[dict]`

```python
def build_manifest(input_dirs: list[Path], single_product: bool) -> list[dict]:
    entries = []
    for root in input_dirs:
        if single_product:
            # root 本身就是一个产品目录
            entries.append(scan_product_directory(root))
        else:
            # root 的每个子目录是一个产品
            for sub in sorted(root.iterdir()):
                if sub.is_dir():
                    entries.append(scan_product_directory(sub))
    return entries
```

### 3.8 `main()`

```python
def main():
    parser = argparse.ArgumentParser(description="Scan product directories and build manifest JSON.")
    parser.add_argument("--input-dir", action="append", dest="input_dirs", required=True,
                        help="Root directory to scan. Repeat for multiple roots.")
    parser.add_argument("--output", required=True, help="Output manifest JSON path.")
    parser.add_argument("--single-product", action="store_true",
                        help="Treat each --input-dir as a single product directory, not a root of many.")
    args = parser.parse_args()

    input_dirs = [Path(d).expanduser().resolve() for d in args.input_dirs]
    for d in input_dirs:
        if not d.is_dir():
            print(f"ERROR: not a directory: {d}", file=sys.stderr)
            sys.exit(1)

    entries = build_manifest(input_dirs, args.single_product)
    output_path = Path(args.output).expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")

    # 控制台摘要
    total = len(entries)
    has_clause = sum(1 for e in entries if e["source_files"].get("clause"))
    with_warnings = sum(1 for e in entries if e["warnings"])
    print(f"扫描完成：{total} 产品，{has_clause} 有条款文件，{with_warnings} 有警告")
    print(f"输出：{output_path}")
```

---

## 四、imports 清单

```python
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# 可选（失败时降级）：
try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False

try:
    import openpyxl
    HAS_OPENPYXL = True
except ImportError:
    HAS_OPENPYXL = False
```

`pdfplumber` 和 `openpyxl` 不做强依赖——若未安装，`check_parse_quality` 返回 `"unknown"`，`is_raw_file` XLSX sheet 检查跳过，脚本仍可运行。

---

## 五、不做的事

- 不自动将 `phase1_eligible` 设为 `true`
- 不自动填写 `db_product_id`
- 不生成 blocks（仅做文件识别）
- 不修改现有 `sample_manifest.json`（输出到新文件，人工比对后替换）
- 不递归超过一层子目录（每个产品的文件都在产品目录的根层）

---

## 六、快速验收命令

```bash
cd ~/codex-openai/development

# 步骤1：扫描 10款重疾
python scripts/build_product_manifest.py \
  --input-dir ~/Desktop/开发材料/10款重疾 \
  --output /tmp/test_manifest_10.json

# 步骤2：检查输出条数
python3 -c "import json; d=json.load(open('/tmp/test_manifest_10.json')); print(len(d), '产品'); [print(e['product_id'], e['warnings']) for e in d]"

# 步骤3：确认 10 产品，每条有 clause，无误报 processed
# 步骤4：手动将所有条目的 phase1_eligible 设为 true，复制到 data/manifests/test_manifest.json
# 步骤5：用该 manifest 重跑提取+eval，确认结果与 V18 一致
python scripts/extract_tier_a_rules.py \
  data/manifests/test_manifest.json \
  /tmp/test_candidates.json
python scripts/merge_candidates.py \
  /tmp/test_candidates.json \
  /tmp/test_merged.json
python scripts/eval_tier_a.py \
  /tmp/test_merged.json \
  data/gold \
  /tmp/test_eval.json
```
