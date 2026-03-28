# 原始文件解析器开发规范 V1
编写时间：2026-03-28
适用仓库：`/Users/zqf-openclaw/codex-openai`
基线分支：`main`
开发分支：`codex/dev`
监督分支：`claude/data-fixes`

## 第 1 章：模块总览

| 模块文件名 | 职责一句话 | 输入 | 输出 | 依赖的现有脚本 |
|-----------|-----------|------|------|--------------|
| `development/scripts/file_router.py` | 按文件后缀、文件名关键词、文档类别决定解析链路 | 原始文件路径、`doc_category` | 路由结果字典 | 无 |
| `development/scripts/pdf_text_extractor.py` | 将文字型 PDF 转成带 `_meta` 的 `blocks.json` | 条款/说明书/核保规则 PDF | `development/data/blocks/*_blocks.json` | `parse_md_blocks.py` |
| `development/scripts/pdf_ocr_extractor.py` | 处理扫描型 PDF，输出与文字型 PDF 相同的 `blocks.json` 契约 | 扫描版 PDF | `development/data/blocks/*_blocks_degraded.json` | 无，Phase 2 实现 |
| `development/scripts/rate_table_extractor.py` | 统一提取费率表 PDF/XLS/XLSX 的结构化字段和表格 | 费率表 PDF/XLS/XLSX | `development/data/tables/*_structured_table.json` | 取代 `extract_tier_a_rules.py` 中的 3 个内联函数 |
| `development/scripts/build_product_manifest.py` | 扫描产品目录，生成供提取脚本消费的 manifest | 产品目录根路径 | `development/data/manifests/product_manifest_v2.json` | 无 |
| `development/scripts/parse_md_blocks.py` | 将 Markdown 切成 block 序列，Phase 1 需支持 `_meta` 包装输出 | Markdown 文件 | `blocks.json` | 现有脚本 |
| `development/scripts/extract_tier_a_rules.py` | 只消费 `blocks.json` 和 `structured_table.json` 做字段规则提取 | manifest、blocks、structured_table | `tier_a_rule_candidates_v2.json` | 现有脚本 |
| `development/scripts/merge_candidates.py` | 合并规则候选，保持与主链兼容 | `tier_a_rule_candidates_v2.json` | `tier_a_merged_candidates_v1.json` | 现有脚本 |

命名约定：
1. 本文档统一使用 `cash_value` 表示现价/现金价值类文件。
2. 旧架构稿 `raw_parser_architecture_v1.md` 中出现的 `price_table`，在实现时一律视为 `cash_value` 同义名。

## 第 2 章：数据契约

### 2.1 `blocks.json`（升级后）

Phase 1 统一输出为顶层对象，保留 `_meta` 和 `blocks`。真实示例如下：

```json
{
  "_meta": {
    "product_id": "889",
    "doc_category": "clause",
    "source_file": "/Users/zqf-openclaw/Desktop/开发材料/10款重疾/889-中信保诚「惠康」重大疾病保险（至诚少儿版）/889-中信保诚「惠康」重大疾病保险（至诚少儿版）-条款.pdf",
    "parse_method": "markitdown",
    "parse_quality": "text_pdf",
    "char_count": 81264,
    "page_count": 46,
    "generated_at": "2026-03-28T10:00:00+08:00"
  },
  "blocks": [
    {
      "block_id": "889_p1_b1",
      "page": 1,
      "block_type": "paragraph",
      "title_path": [],
      "text": "中信保诚人寿[2022]疾病保险027",
      "char_count": 19,
      "cross_page_candidate": false
    },
    {
      "block_id": "889_p1_b4",
      "page": 1,
      "block_type": "title",
      "title_path": [
        "第一条 合同构成"
      ],
      "text": "第一条 合同构成",
      "char_count": 9,
      "cross_page_candidate": false
    },
    {
      "block_id": "889_p1_b5",
      "page": 1,
      "block_type": "paragraph",
      "title_path": [
        "第一条 合同构成"
      ],
      "text": "本主险合同由保险单、保险条款、投保单、与本主险合同有关的投保文件、合法有效的声明、批注、批单及与本主险合同有关的其他书面协议共同构成。",
      "char_count": 76,
      "cross_page_candidate": false
    }
  ]
}
```

字段要求：

| 字段 | 类型 | 含义 |
|------|------|------|
| `_meta.product_id` | `str` | 逻辑产品 ID，例如 `889` |
| `_meta.doc_category` | `str` | `clause` / `product_brochure` / `underwriting_rule` |
| `_meta.source_file` | `str` | 原始文件绝对路径 |
| `_meta.parse_method` | `str` | `markitdown` / `pdfplumber_text` / `fitz_text` / `ocr` |
| `_meta.parse_quality` | `str` | `text_pdf` / `scan_pdf` / `degraded` / `unknown` |
| `_meta.char_count` | `int` | 全文字符数 |
| `_meta.page_count` | `int` | 页数 |
| `_meta.generated_at` | `str` | ISO-8601 时间戳，带时区 |
| `blocks[].block_id` | `str` | `product_id_p{page}_b{index}` |
| `blocks[].page` | `int` | 页码 |
| `blocks[].block_type` | `str` | `title` / `paragraph` / `list` / `table` |
| `blocks[].title_path` | `list[str]` | 当前 block 所属标题路径 |
| `blocks[].text` | `str` | 原文文本 |
| `blocks[].char_count` | `int` | block 文本长度 |
| `blocks[].cross_page_candidate` | `bool` | 是否为潜在跨页截断块 |

### 2.2 `structured_table.json`

费率/现价文件不进入 `blocks` 主链，统一产出结构化表。真实示例如下：

```json
{
  "_meta": {
    "product_id": "889",
    "doc_category": "raw_rate",
    "source_file": "/Users/zqf-openclaw/Desktop/开发材料/10款重疾/889-中信保诚「惠康」重大疾病保险（至诚少儿版）/889-中信保诚「惠康」重大疾病保险（至诚少儿版）-费率表.pdf",
    "parse_method": "fitz_text",
    "table_format": "rate_grid",
    "parse_quality": "text_pdf",
    "generated_at": "2026-03-28T10:05:00+08:00"
  },
  "tables": [
    {
      "table_id": "889_rate_tbl_1",
      "page": 1,
      "schema": [
        "缴费期",
        "投保年龄",
        "保额1万元年缴保费（男）"
      ],
      "rows": [
        {
          "缴费期": "1年",
          "投保年龄": "0",
          "保额1万元年缴保费（男）": "1680.00"
        },
        {
          "缴费期": "20年",
          "投保年龄": "0",
          "保额1万元年缴保费（男）": "221.00"
        },
        {
          "缴费期": "25年",
          "投保年龄": "0",
          "保额1万元年缴保费（男）": "188.00"
        },
        {
          "缴费期": "30年",
          "投保年龄": "0",
          "保额1万元年缴保费（男）": "168.00"
        }
      ]
    }
  ],
  "extracted_fields": {
    "pay_periods": [
      "趸交",
      "5年交",
      "10年交",
      "15年交",
      "20年交",
      "25年交",
      "30年交"
    ],
    "pay_frequencies": [
      "趸交",
      "年交",
      "半年交",
      "季交",
      "月交"
    ],
    "insurance_periods": []
  },
  "notes": [
    "缴费期列中的1年统一映射为趸交",
    "年缴/月缴/季缴/半年缴来自费率表首页说明文字"
  ]
}
```

`extracted_fields` 契约：

| 键 | 类型 | 说明 |
|----|------|------|
| `pay_periods` | `list[str]` | 已标准化的交费期间值，元素形如 `趸交`、`20年交` |
| `pay_frequencies` | `list[str]` | 已标准化的交费频率值，顺序必须按 `趸交/年交/半年交/季交/月交` |
| `insurance_periods` | `list[str]` | 从费率文件可直接确认的保险期间 |

### 2.3 `manifest.json`（`build_product_manifest.py` 输出）

真实示例如下：

```json
[
  {
    "product_id": "889",
    "db_product_id": "1530003475",
    "product_name": "中信保诚「惠康」重大疾病保险（至诚少儿版）",
    "status": "gold_ready",
    "phase1_eligible": true,
    "files": [
      {
        "doc_category": "clause",
        "source_file": "/Users/zqf-openclaw/Desktop/开发材料/10款重疾/889-中信保诚「惠康」重大疾病保险（至诚少儿版）/889-中信保诚「惠康」重大疾病保险（至诚少儿版）-条款.pdf",
        "parser_route": "pdf_text_extractor",
        "is_raw": true
      },
      {
        "doc_category": "raw_rate",
        "source_file": "/Users/zqf-openclaw/Desktop/开发材料/10款重疾/889-中信保诚「惠康」重大疾病保险（至诚少儿版）/889-中信保诚「惠康」重大疾病保险（至诚少儿版）-费率表.pdf",
        "parser_route": "rate_table_extractor",
        "is_raw": true
      }
    ],
    "gold_result_path": "/Users/zqf-openclaw/codex-openai/development/data/gold/889_gold.json"
  }
]
```

### 2.4 向后兼容说明

当前仓库已有 `blocks.json` 是纯数组格式，例如：

- `/Users/zqf-openclaw/codex-openai/development/data/blocks/889_blocks.json`

兼容读取规则必须固定为：

```python
def load_blocks_compatible(path: Path) -> tuple[dict | None, list[dict]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict) and "blocks" in raw:
        return raw.get("_meta"), raw["blocks"]
    if isinstance(raw, list):
        return None, raw
    raise ValueError(f"unsupported blocks payload: {path}")
```

要求：
1. `extract_tier_a_rules.py` Phase 1 必须支持两种格式同时读取。
2. 新模块统一写新格式。
3. 不允许把旧数组文件批量回写成新格式，避免污染历史基线。

当前仓库已有 `manifest` 仍是旧格式，例如：

- `/Users/zqf-openclaw/codex-openai/development/data/manifests/sample_manifest.json`

旧格式关键字段：
1. `product_id`
2. `db_product_id`
3. `product_name`
4. `clause_pdf_path`
5. `gold_result_path`
6. `phase1_eligible`
7. `status`

Phase 1 必须增加 manifest 兼容读取，规则固定为：

```python
def load_manifest_compatible(path: Path) -> list[dict]:
    """Read either legacy sample_manifest rows or new product_manifest_v2 rows and normalize to one internal schema."""
```

兼容要求：
1. 若条目存在 `files` 数组，则按新格式读取。
2. 若条目不存在 `files` 但存在 `clause_pdf_path`，则按旧格式读取，并在内存中转换成：
   - `files=[{"doc_category": "clause", "source_file": clause_pdf_path, "parser_route": "pdf_text_extractor", "is_raw": true}]`
3. `phase1_eligible`、`status`、`gold_result_path` 等旧字段必须保留，不允许在 Phase 1 做一次性全量迁移。

## 第 3 章：各模块接口规范

### 3.1 `file_router.py`

**CLI 用法**

```bash
python3 /Users/zqf-openclaw/codex-openai/development/scripts/file_router.py \
  --file "/Users/zqf-openclaw/Desktop/开发材料/10款重疾/889-中信保诚「惠康」重大疾病保险（至诚少儿版）/889-中信保诚「惠康」重大疾病保险（至诚少儿版）-费率表.pdf" \
  --doc-category raw_rate
```

**核心函数签名**

```python
def route_file(file_path: Path, doc_category: str) -> dict:
    """Return parser_route, parse_quality, is_raw, suffix and normalized doc_category for one source file."""
```

**处理流程**
1. 读取文件后缀。
2. 按文件名关键词规范化 `doc_category`。
3. 判断是否为原始文件而非处理产物。
4. 若为 PDF，尝试首屏文本探测，区分 `text_pdf` 与 `scan_pdf`。
5. 结合 `(suffix, doc_category, parse_quality)` 查路由表。
6. 返回单文件路由结果字典。

**异常处理规则**
1. 文件不存在：`exit(1)`。
2. 后缀不支持：写 warning，返回 `parser_route="skip"`。
3. PDF 无法探测文本：返回 `parse_quality="unknown"`，不崩溃。

### 3.2 `pdf_text_extractor.py`

**CLI 用法**

```bash
python3 /Users/zqf-openclaw/codex-openai/development/scripts/pdf_text_extractor.py \
  --product-id 889 \
  --doc-category clause \
  --input "/Users/zqf-openclaw/Desktop/开发材料/10款重疾/889-中信保诚「惠康」重大疾病保险（至诚少儿版）/889-中信保诚「惠康」重大疾病保险（至诚少儿版）-条款.pdf" \
  --output "/Users/zqf-openclaw/codex-openai/development/data/blocks/889_blocks.json"
```

**核心函数签名**

```python
def extract_pdf_to_blocks(product_id: str, doc_category: str, input_pdf: Path, output_json: Path) -> dict:
    """Extract a text PDF to markdown, parse it into blocks, and write wrapped blocks.json with _meta."""
```

**处理流程**
1. 判断 PDF 是否为文字型。
2. 优先调用 `markitdown` 生成 Markdown。
3. 将 Markdown 临时文件交给 `parse_md_blocks.py`。
4. 若 `markitdown` 不可用，则切换到“逐行纯文本 -> 简化 block”降级路径，不再依赖 `parse_md_blocks.py` 的标题识别。
5. 计算 `_meta.char_count`、`_meta.page_count`。
6. 以新格式写入 `blocks.json`。

**异常处理规则**
1. `markitdown` 不可用：写 warning，尝试 `pdfplumber` 降级。
2. 解析后 blocks 为空：`exit(1)`。
3. 解析成功但 blocks < 10：`parse_quality="degraded"`，继续写文件。
4. `pdfplumber` 降级路径产出的 `title_path` 允许全空，但必须在 `_meta.parse_method` 中明确标注 `pdfplumber_text`。

### 3.3 `pdf_ocr_extractor.py`

**CLI 用法**

```bash
python3 /Users/zqf-openclaw/codex-openai/development/scripts/pdf_ocr_extractor.py \
  --product-id 1548A \
  --doc-category clause \
  --input "/Users/zqf-openclaw/Desktop/开发材料/10款重疾/1548A-北京人寿大黄蜂12号少儿重疾险（焕新版）-保终身/1548A-北京人寿大黄蜂12号少儿重疾险（焕新版）-保终身-条款.pdf" \
  --output "/Users/zqf-openclaw/codex-openai/development/data/blocks/1548A_blocks_degraded.json"
```

**核心函数签名**

```python
def extract_ocr_pdf_to_blocks(product_id: str, doc_category: str, input_pdf: Path, output_json: Path) -> dict:
    """OCR a scanned PDF and write blocks.json with degraded quality markers."""
```

**处理流程**
1. 渲染 PDF 页图。
2. 执行 OCR。
3. 合并 OCR 文本框为 Markdown 或段落文本。
4. 复用 `parse_md_blocks.py` 生成 blocks。
5. 写出 `_meta.parse_quality="scan_pdf"`。

**异常处理规则**
1. Phase 1 不实现正文 OCR：直接输出 `NotImplementedError` 并退出。
2. Phase 2 启用后，OCR 库缺失则写 warning 并 `exit(1)`。

### 3.4 `rate_table_extractor.py`

**CLI 用法**

```bash
python3 /Users/zqf-openclaw/codex-openai/development/scripts/rate_table_extractor.py \
  --product-id 889 \
  --doc-category raw_rate \
  --input "/Users/zqf-openclaw/Desktop/开发材料/10款重疾/889-中信保诚「惠康」重大疾病保险（至诚少儿版）/889-中信保诚「惠康」重大疾病保险（至诚少儿版）-费率表.pdf" \
  --output "/Users/zqf-openclaw/codex-openai/development/data/tables/889_rate_structured_table.json"
```

**核心函数签名**

```python
def extract_rate_table(product_id: str, doc_category: str, input_file: Path, output_json: Path) -> dict:
    """Extract PDF/XLS/XLSX rate or cash-value files into structured_table.json and normalized extracted_fields."""
```

```python
def locate_rate_source(item: dict) -> Path | None:
    """Resolve the best raw rate file for one manifest item, replacing locate_rate_xlsx() and locate_rate_pdf()."""
```

**处理流程**
1. 判断输入是 PDF 还是 XLS/XLSX。
2. XLS/XLSX 用 `openpyxl` 读取 sheet、表头、前 6 行和末尾说明。
3. PDF 用 `fitz` 或 `pdfplumber` 提取表头文本和说明文字。
4. 标准化 `缴费期`、`交费频率`、`保险期间` 等字段。
5. 写出 `structured_table.json`。
6. 输出 `extracted_fields.pay_periods` 和 `pay_frequencies`。

**异常处理规则**
1. 文件不存在：`exit(1)`。
2. `openpyxl` 缺失且输入为 XLS/XLSX：写 warning 并 `exit(1)`。
3. `fitz/pdfplumber` 缺失且输入为 PDF：写 warning 并 `exit(1)`。
4. 表结构提取失败但说明文字存在：允许 `tables=[]`，只写 `extracted_fields`。

`rate_table_extractor.py` 必须覆盖并取代当前内联能力：
1. `locate_rate_xlsx(item)`
2. `locate_rate_pdf(item)`
3. `extract_pay_info_from_rate_pdf(item)`
4. `extract_pay_frequency_from_rate_xlsx(item)`

### 3.5 `build_product_manifest.py`

**CLI 用法**

```bash
python3 /Users/zqf-openclaw/codex-openai/development/scripts/build_product_manifest.py \
  --root "/Users/zqf-openclaw/Desktop/开发材料/10款重疾" \
  --output "/Users/zqf-openclaw/codex-openai/development/data/manifests/product_manifest_v2.json"
```

**核心函数签名**

```python
def build_manifest(root: Path, output_path: Path) -> list[dict]:
    """Scan raw product directories and write normalized manifest entries with routed source files."""
```

**处理流程**
1. 扫描产品目录。
2. 识别产品 ID 和产品名。
3. 对每个文件调用 `route_file()`。
4. 过滤处理产物和不支持文件。
5. 组装产品级 manifest。
6. 写出 JSON。

**异常处理规则**
1. 根目录不存在：`exit(1)`。
2. 单产品目录文件命名异常：写 warning，跳过单文件，不中断全局。

### 3.6 `parse_md_blocks.py`

**CLI 用法**

```bash
python3 /Users/zqf-openclaw/codex-openai/development/scripts/parse_md_blocks.py \
  --product-id 889 \
  --input "/Users/zqf-openclaw/codex-openai/development/data/md_cache/889_clause_pdf.md" \
  --output "/Users/zqf-openclaw/codex-openai/development/data/blocks/889_blocks.json"
```

**核心函数签名**

```python
def parse_markdown(product_id: str, md_text: str) -> list[dict]:
    """Split markdown text into ordered blocks with title_path, block_type, page and char_count."""
```

**处理流程**
1. 按分页符拆页。
2. 识别页码。
3. 识别标题、列表、表格和正文块。
4. 生成 block 列表。
5. Phase 1 调整输出包装，允许上层写 `_meta`。

**异常处理规则**
1. 输入 Markdown 为空：`exit(1)`。
2. 单页无法识别标题：继续，以正文块写出。

### 3.7 `extract_tier_a_rules.py`

**CLI 用法**

```bash
python3 /Users/zqf-openclaw/codex-openai/development/scripts/extract_tier_a_rules.py \
  /Users/zqf-openclaw/codex-openai/development/data/manifests/sample_manifest.json \
  /Users/zqf-openclaw/codex-openai/development/data/extractions/tier_a_rule_candidates_v2.json \
  --blocks-dir /Users/zqf-openclaw/codex-openai/development/data/blocks
```

**核心函数签名**

```python
def extract_candidates(blocks: list[dict], product_id: str) -> dict[str, dict]:
    """Extract Tier A field candidates from parsed blocks for one product."""
```

```python
def load_blocks_compatible(path: Path) -> tuple[dict | None, list[dict]]:
    """Read either wrapped blocks.json or legacy array blocks.json without changing caller semantics."""
```

```python
def load_manifest_compatible(path: Path) -> list[dict]:
    """Read either legacy sample_manifest rows or new product_manifest_v2 rows and normalize them before extraction."""
```

**处理流程**
1. 读取 manifest，并通过 `load_manifest_compatible()` 统一格式。
2. 对每个产品加载主条款 `blocks.json`。
3. 如存在说明书 blocks，按字段做兜底。
4. 如存在 `structured_table.json`，从中补充交费期间、交费频率、保险期间。
5. 运行字段规则提取。
6. 输出候选和缺失字段。

**异常处理规则**
1. `blocks` 不存在：跳过该产品并写 warning。
2. `structured_table` 不存在：按文本链继续，不中断。
3. 单字段提取失败：只影响该字段，不影响整产品输出。

## 第 4 章：路由规则完整表

| 后缀 | `doc_category` | `parse_quality` | extractor | Phase | 行为 |
|------|----------------|-----------------|-----------|-------|------|
| `.pdf` | `clause` | `text_pdf` | `pdf_text_extractor.py` | 1 | 正常转 `blocks.json` |
| `.pdf` | `product_brochure` | `text_pdf` | `pdf_text_extractor.py` | 1 | 正常转 `blocks.json` |
| `.pdf` | `underwriting_rule` | `text_pdf` | `pdf_text_extractor.py` | 1 | 正常转 `blocks.json` |
| `.pdf` | `clause` | `scan_pdf` | `pdf_ocr_extractor.py` | 2 | Phase 2 |
| `.pdf` | `product_brochure` | `scan_pdf` | `pdf_ocr_extractor.py` | 2 | Phase 2 |
| `.pdf` | `underwriting_rule` | `scan_pdf` | `pdf_ocr_extractor.py` | 2 | Phase 2 |
| `.pdf` | `raw_rate` | `text_pdf` | `rate_table_extractor.py` | 1 | 直接产出 `structured_table.json` |
| `.pdf` | `cash_value` | `text_pdf` | `rate_table_extractor.py` | 1 | 直接产出 `structured_table.json` |
| `.pdf` | `raw_rate` | `scan_pdf` | `skip` | 2 | Phase 2 之前标记手工处理 |
| `.pdf` | `cash_value` | `scan_pdf` | `skip` | 2 | Phase 2 之前标记手工处理 |
| `.xlsx` | `raw_rate` | `xlsx` | `rate_table_extractor.py` | 1 | 直接产出 `structured_table.json` |
| `.xls` | `raw_rate` | `xlsx` | `rate_table_extractor.py` | 1 | 直接产出 `structured_table.json` |
| `.xlsx` | `cash_value` | `xlsx` | `rate_table_extractor.py` | 1 | 直接产出 `structured_table.json` |
| `.xls` | `cash_value` | `xlsx` | `rate_table_extractor.py` | 1 | 直接产出 `structured_table.json` |
| `.pdf/.xlsx/.xls` | `other` | `any` | `skip` | 1 | 非目标文件，记录 warning 后跳过 |
| `.md` | `clause` | `unknown` | `parse_md_blocks.py` | 1 | 仅内部中间文件，不作为原始输入 |
| `.png/.jpg/.jpeg` | `clause` / `product_brochure` / `underwriting_rule` | `unknown` | `skip` | 2 | 等 OCR 方案 |

规则补充：
1. `raw_rate` 和 `cash_value` 不走 `blocks` 链。
2. `product_brochure` 必须允许回填 `投保年龄` 与 `交费期间`。
3. `underwriting_rule` 在 Phase 1 只解析为 `blocks`，不单独做表格抽取。

## 第 5 章：常量与关键词表

建议新建公共常量文件：

- `/Users/zqf-openclaw/codex-openai/development/scripts/constants.py`

如果 Phase 1 不单独建文件，则每个模块使用同一份定义，不允许各自发散。

### 5.1 `DOCUMENT_TYPE_RULES`

```python
DOCUMENT_TYPE_RULES = {
    "条款": "clause",
    "产品说明书": "product_brochure",
    "说明书": "product_brochure",
    "费率表": "raw_rate",
    "现价表": "cash_value",
    "现金价值": "cash_value",
    "核保": "underwriting_rule",
    "投保规则": "underwriting_rule",
}
```

### 5.2 `PROCESSED_FLAGS`

```python
PROCESSED_FLAGS = [
    "_blocks.json",
    "_blocks_degraded.json",
    "_structured_table.json",
    "_review_task_v2.json",
    "_gold.json",
    "_eval_v",
    "tier_a_rule_candidates",
    "tier_a_merged_candidates",
]
```

### 5.3 `SUPPORTED_EXTENSIONS`

```python
SUPPORTED_EXTENSIONS = {
    ".pdf",
    ".xlsx",
    ".xls",
    ".md",
    ".png",
    ".jpg",
    ".jpeg",
}
```

### 5.4 `PAY_PERIOD_ALIASES`

```python
PAY_PERIOD_ALIASES = {
    "趸交": "趸交",
    "一次交清": "趸交",
    "一次性付清": "趸交",
    "一次性交付": "趸交",
    "1年": "趸交"
}
```

### 5.5 `PAY_FREQ_ORDER`

```python
PAY_FREQ_ORDER = ["趸交", "年交", "半年交", "季交", "月交"]
```

### 5.6 `PAY_PERIOD_TITLES`

```python
PAY_PERIOD_TITLES = [
    "交费期间",
    "交费期限",
    "交费年期",
    "缴费期间",
    "缴费期限",
    "缴费年期",
    "保险费缴纳期间",
    "缴费方式",
]
```

### 5.7 `RATE_SEARCH_ROOTS`

```python
RATE_SEARCH_ROOTS = [
    Path("/Users/zqf-openclaw/Desktop/开发材料/10款重疾"),
    Path("/Users/zqf-openclaw/Desktop/开发材料/招行数据"),
]
```

## 第 6 章：依赖说明

| 库名 | 版本要求 | 用途 | 若缺失的降级行为 |
|------|---------|------|--------------|
| `pdfplumber` | `>=0.11` | 文字型 PDF 文本提取、表格提取备选 | `pdf_text_extractor.py` 改走 `markitdown` 或 `fitz`；若两者都不可用则 `exit(1)` |
| `openpyxl` | `>=3.1` | 读取 XLSX 费率表与现价表 | `rate_table_extractor.py` 对 `.xlsx/.xls` 直接 `exit(1)`，但其他文件类型不受影响 |
| `fitz`（PyMuPDF） | `>=1.24` | 费率 PDF 文本读取、PDF 首屏质量探测 | `rate_table_extractor.py` 改走 `pdfplumber`；若两者都不可用则 `exit(1)` |
| `markitdown` | 已装在本地环境 | 将文字 PDF 转 Markdown | 缺失时退到 `pdfplumber` 直接抽文本，`parse_method` 标注为 `pdfplumber_text` |
| `python-dateutil` | `>=2.9` | 生成稳定时间戳，可选 | 缺失时用标准库 `datetime`，不允许崩溃 |

降级规则必须明确：
1. **任何依赖缺失都不能让整个项目链路无提示崩溃**。
2. 单文件失败时，应输出可读 warning，包含文件路径和缺失库名。
3. `pdfplumber`/`fitz` 都缺失时，PDF 解析脚本对该文件 `exit(1)`；不允许写空文件冒充成功。
4. `openpyxl` 缺失时，只影响 Excel 文件；PDF 链路继续可跑。
5. `pdfplumber` 降级产物不得伪装成 Markdown 结果；必须明确走“纯文本简化 block”链路。

## 第 7 章：验收测试清单

### 7.1 单模块验收

```bash
# file_router.py：费率表 PDF 路由
python3 /Users/zqf-openclaw/codex-openai/development/scripts/file_router.py \
  --file "/Users/zqf-openclaw/Desktop/开发材料/10款重疾/889-中信保诚「惠康」重大疾病保险（至诚少儿版）/889-中信保诚「惠康」重大疾病保险（至诚少儿版）-费率表.pdf" \
  --doc-category raw_rate
# 预期：parser_route=rate_table_extractor, parse_quality=text_pdf, is_raw=true
```

```bash
# pdf_text_extractor.py：条款 PDF -> blocks.json
python3 /Users/zqf-openclaw/codex-openai/development/scripts/pdf_text_extractor.py \
  --product-id 889 \
  --doc-category clause \
  --input "/Users/zqf-openclaw/Desktop/开发材料/10款重疾/889-中信保诚「惠康」重大疾病保险（至诚少儿版）/889-中信保诚「惠康」重大疾病保险（至诚少儿版）-条款.pdf" \
  --output "/Users/zqf-openclaw/codex-openai/development/data/blocks/889_blocks_v2.json"
# 预期：输出对象包含 _meta，blocks 数量 > 1000
```

```bash
# rate_table_extractor.py：费率表 PDF -> structured_table.json
python3 /Users/zqf-openclaw/codex-openai/development/scripts/rate_table_extractor.py \
  --product-id 889 \
  --doc-category raw_rate \
  --input "/Users/zqf-openclaw/Desktop/开发材料/10款重疾/889-中信保诚「惠康」重大疾病保险（至诚少儿版）/889-中信保诚「惠康」重大疾病保险（至诚少儿版）-费率表.pdf" \
  --output "/Users/zqf-openclaw/codex-openai/development/data/tables/889_rate_structured_table.json"
# 预期：extracted_fields.pay_periods 至少包含 趸交、5年交、10年交、15年交、20年交、25年交、30年交；pay_frequencies 包含 趸交、年交、半年交、季交、月交
```

```bash
# parse_md_blocks.py：Markdown -> legacy blocks
python3 /Users/zqf-openclaw/codex-openai/development/scripts/parse_md_blocks.py \
  --product-id 889 \
  --input "/Users/zqf-openclaw/codex-openai/development/data/md_cache/889_clause_pdf.md" \
  --output "/Users/zqf-openclaw/codex-openai/development/data/blocks/889_blocks_legacy_check.json"
# 预期：仍输出纯数组，保持向后兼容
```

```bash
# extract_tier_a_rules.py：兼容读取 wrapped blocks + structured_table
python3 /Users/zqf-openclaw/codex-openai/development/scripts/extract_tier_a_rules.py \
  /Users/zqf-openclaw/codex-openai/development/data/manifests/sample_manifest.json \
  /Users/zqf-openclaw/codex-openai/development/data/extractions/tier_a_rule_candidates_v2.json \
  --blocks-dir /Users/zqf-openclaw/codex-openai/development/data/blocks
# 预期：现有 889/1803/1548A 不因新契约回退
```

```bash
# merge_candidates.py：合并候选
python3 /Users/zqf-openclaw/codex-openai/development/scripts/merge_candidates.py
# 预期：输出 /Users/zqf-openclaw/codex-openai/development/data/extractions/tier_a_merged_candidates_v1.json
```

### 7.2 整链验收

```bash
cd /Users/zqf-openclaw/codex-openai/development
python3 scripts/extract_tier_a_rules.py
python3 scripts/merge_candidates.py
python3 scripts/eval_tier_a.py \
  --candidates data/extractions/tier_a_merged_candidates_v1.json \
  --gold-dir data/gold \
  --whitelist data/manifests/coverage_whitelist_v1.json \
  --output data/eval/tier_a_eval_v19.json
# 预期：Phase 1 解析器替换完成后，V19 与 V17 在可信字段上不回退；若有差异，必须在 PR 中逐条解释
```

### 7.3 GitHub 同步规范

开发流程固定为：

```bash
cd /Users/zqf-openclaw/codex-openai
git checkout codex/dev
git pull origin main
git add development/scripts development/docs
git commit -m "feat: raw parser phase1 scaffold"
git push origin codex/dev
```

规则：
1. `main` 只接合并，不直接开发。
2. Codex 只在 `codex/dev` 提交。
3. Claude 在 `claude/data-fixes` 负责数据文件和评测说明审查；若需提交，只允许改 `development/data/gold/`、`development/data/eval/`、`development/docs/`。
4. 合并前必须由 Claude review，用户决定是否并入 `main`。

### 7.4 备份规范

开发前和大改完成后都要检查自动备份目录：

- `/Users/zqf-openclaw/codex-openai/development/memory`

手动确认命令：

```bash
ls -1 /Users/zqf-openclaw/codex-openai/development/memory | tail
```

当前已知最近完整快照：

- `/Users/zqf-openclaw/codex-openai/development/memory/202603272229`

规则：
1. 解析器 Phase 1 每完成一个模块，至少生成一次新的 memory 快照。
2. 代码提交前，必须确认目标文件已被自动或手动备份。
3. 若当天新增了解析器核心模块，提交说明里必须写明对应备份时间戳。
