# 原始文件解析器总体设计 V1

编写时间：2026-03-28
状态：设计稿，待 Codex 实现
作者：Claude（架构分析与设计）

---

## 一、为什么需要这份设计

当前管道的真实结构是：

```
PDF → (人工) markitdown → Markdown → parse_md_blocks.py → blocks.json
                                                                ↓
费率 XLSX/PDF ──────── locate_rate_xlsx/pdf ──→ extract_tier_a_rules.py
                                （内联，无标准化）
```

**三个根本问题**：

1. **文件解析无路由**：所有文件都被强行转成 blocks，费率表（结构化数据源）和条款（文本来源）用同一套流程，适配性差。
2. **费率表没有自己的链路**：`extract_pay_info_from_rate_pdf` 和 `extract_pay_frequency_from_rate_xlsx` 是内嵌在字段提取脚本里的一次性函数，无法复用、无法独立扩展、无法直接入库。
3. **解析质量没有标记**：blocks.json 不知道自己是从文字型 PDF 来的还是从扫描件 OCR 来的，下游无法据此调整信任度。

---

## 二、目标架构（五层）

```
原始文件（PDF / XLSX / 图片）
        │
        ▼
┌─────────────────────────────────────┐
│  Layer 1：文件识别层                 │
│  file_router.py                      │
│  输出：file_type + doc_category      │
│  + is_raw 标记                       │
└───────────────┬─────────────────────┘
                │
        ┌───────┴──────────┐
        ▼                  ▼
┌──────────────┐   ┌──────────────────┐
│ Layer 2a     │   │ Layer 2b         │
│ 文本内容提取  │   │ 表格内容提取      │
│ pdf_text_    │   │ rate_table_      │
│ extractor.py │   │ extractor.py     │
│ (文字PDF→MD) │   │ (XLSX/PDF→行列)  │
└──────┬───────┘   └────────┬─────────┘
       │                    │
       ▼                    ▼
┌──────────────┐   ┌──────────────────┐
│ Layer 3a     │   │ Layer 3b         │
│ 结构化切分层  │   │ 表结构规范化层    │
│ parse_md_    │   │ table_           │
│ blocks.py    │   │ normalizer.py    │
│ → blocks.json│   │ → structured_    │
│              │   │   table.json     │
└──────┬───────┘   └────────┬─────────┘
       │                    │
       ▼                    ▼
┌──────────────┐   ┌──────────────────┐
│ Layer 4a     │   │ Layer 4b（未来）  │
│ 语义增强层    │   │ 入库链路          │
│ (跨块合并/   │   │ (normalized_rows │
│  标题识别)   │   │  → DB)           │
└──────┬───────┘   └──────────────────┘
       │
       ▼
┌──────────────────────────────────────┐
│ Layer 5：字段抽取层                   │
│ extract_tier_a_rules.py              │
│ （只消费 blocks.json +               │
│   structured_table.json）            │
└──────────────────────────────────────┘
```

---

## 三、四个必须先固定的契约

### 3.1 统一输出契约

#### A. blocks.json（文本文档产物）

在现有格式基础上增加顶层元数据：

```json
{
  "_meta": {
    "product_id": "889",
    "doc_category": "clause",
    "source_file": "/Users/.../889-...-条款.pdf",
    "parse_method": "markitdown",
    "parse_quality": "text_pdf",
    "char_count": 42000,
    "page_count": 47,
    "generated_at": "2026-03-28T12:00:00"
  },
  "blocks": [
    {
      "block_id": "889_p1_b1",
      "page": 1,
      "block_type": "paragraph",
      "title_path": [],
      "text": "...",
      "char_count": 120,
      "cross_page_candidate": false
    }
    // ...
  ]
}
```

**注**：当前 blocks.json 是纯数组（无 `_meta`），需要向后兼容——提取脚本识别"有 `_meta` 键则取 `blocks` 字段，否则把整个数组当 blocks"。

#### B. structured_table.json（费率/现价文档产物）

```json
{
  "_meta": {
    "product_id": "889",
    "doc_category": "raw_rate",
    "source_file": "/Users/.../889-...-费率表.pdf",
    "parse_method": "pdfplumber_table",
    "table_format": "row_style",
    "parse_quality": "text_pdf",
    "generated_at": "2026-03-28T12:00:00"
  },
  "tables": [
    {
      "table_id": "tbl_1",
      "page": 1,
      "schema": ["缴费期", "投保年龄（岁）", "保额1万元年缴保费（元）"],
      "rows": [
        {"缴费期": "5年", "投保年龄（岁）": "0", "保额1万元年缴保费（元）": "120.5"}
      ]
    }
  ],
  "extracted_fields": {
    "pay_periods":     ["趸交", "5年交", "10年交", "15年交", "20年交", "25年交", "30年交"],
    "pay_frequencies": ["趸交", "年交", "半年交", "季交", "月交"],
    "insurance_periods": []
  },
  "notes": ["1年映射为趸交"]
}
```

### 3.2 输入路由规则

```
给定 (file_path, doc_category) → 决定走哪条链路

后缀 .xlsx / .xls → excel_extractor
后缀 .pdf
  doc_category in {clause, brochure, underwriting}
    → check parse_quality:
        text_pdf  → pdf_text_extractor → parse_md_blocks → blocks.json
        scan_pdf  → [Phase 2] pdf_ocr_extractor
  doc_category in {raw_rate, price_table}
    → rate_table_extractor → table_normalizer → structured_table.json
```

**路由表（明确版）**：

| 后缀 | doc_category | 链路 | Phase |
|------|------|------|------|
| .pdf | clause / brochure | pdf_text_extractor → blocks | 1 |
| .pdf | clause / brochure（扫描件） | pdf_ocr_extractor → blocks | 2 |
| .pdf | raw_rate / price_table | rate_table_extractor → structured_table | 1 |
| .xlsx/.xls | raw_rate / price_table | excel_extractor → structured_table | 1 |
| .pdf | raw_rate（扫描件） | [手工处理] | 3 |

### 3.3 表格处理策略

**两类表格，两种处理方式，不可混淆**：

| 表格类型 | 位置 | 处理方式 | 产物 |
|---------|------|---------|------|
| 条款/说明书内嵌表格 | clause/brochure PDF 内 | 作为特殊 block_type="table" 保留在 blocks.json | blocks.json |
| 独立费率/现价表文件 | raw_rate/price_table 文件 | 独立 rate_table_extractor 链路 | structured_table.json |

**条款内嵌表格**（如等待期表）：
- 当前 parse_md_blocks.py 将表格内容合并为文本 block
- Phase 3 增强：识别 `|` 分隔的 markdown 表格行，产出 `block_type: "table"` 节点

**费率表**：
- 不进 blocks 链路
- 目标是产出 `extracted_fields.pay_periods` / `pay_frequencies` 等已规范化的字段
- 长期目标：normalized_rows 直接入库（Phase 3/4）

### 3.4 解析质量标记

```
parse_quality 枚举值：
  text_pdf    — pdfplumber 提取首页 > 50 字符
  scan_pdf    — pdfplumber 提取首页 ≤ 50 字符（OCR 候选）
  xlsx        — openpyxl 成功打开
  unknown     — 依赖库缺失或解析异常
  degraded    — 解析成功但 blocks < 10（内容可能残缺）

parse_method 枚举值：
  markitdown           — markitdown 工具解析 PDF→Markdown
  pdfplumber_text      — pdfplumber 直接提取文本
  pdfplumber_table     — pdfplumber 提取表格结构
  openpyxl             — openpyxl 读取 XLSX
  fitz_text            — PyMuPDF 提取文本（当前 rate PDF 用此）
  ocr                  — [Phase 2] OCR 识别
```

---

## 四、Phase 1 实现范围

**只做文字型 PDF + 原始 Excel，扫描件推后。**

### Phase 1 新增模块

| 模块 | 状态 | 说明 |
|------|------|------|
| `file_router.py` | **新建** | 文件识别 + 路由决策，输出 file_type/doc_category/is_raw/quality |
| `pdf_text_extractor.py` | **新建** | 封装 markitdown（或 pdfplumber） + parse_md_blocks，输入 PDF，输出 blocks.json（含 _meta） |
| `rate_table_extractor.py` | **新建** | 取代 extract_pay_info_from_rate_pdf + extract_pay_frequency_from_rate_xlsx，输入费率 PDF/XLSX，输出 structured_table.json |
| `build_product_manifest.py` | **新建** | 目录扫描，调用 file_router，输出 manifest.json |
| `parse_md_blocks.py` | 现有，**微调** | 添加 `_meta` 顶层节点；向后兼容 |
| `extract_tier_a_rules.py` | 现有，**微调** | 支持读取 `_meta` 包装格式；支持读取 structured_table.json 补充字段 |

### Phase 1 不做

- 扫描件 OCR（pdf_ocr_extractor.py）
- 费率表入库链路（table_normalizer + DB writer）
- 条款内嵌表格结构化（block_type="table"）
- 跨页/跨 block 语义增强（保留在现有规则兜底逻辑）

---

## 五、各模块详细规范

### 5.1 `file_router.py`

**职责**：给定文件路径，返回路由决策。

**输入**：`file_path: str`，可选 `doc_category_hint: str`（来自文件名分类）

**输出**：
```python
{
    "file_type": "text_pdf" | "scan_pdf" | "xlsx" | "image" | "unknown",
    "doc_category": "clause" | "brochure" | "raw_rate" | "price_table" | "underwriting" | "other",
    "is_raw": True | False,
    "extractor": "pdf_text_extractor" | "rate_table_extractor" | "pdf_ocr_extractor" | "unsupported",
    "quality_hint": "text_pdf" | "scan_pdf" | "xlsx" | "unknown",
    "warnings": []
}
```

**分类逻辑**：
```
后缀 → file_type（xlsx/xls → xlsx，pdf → 待检测，其他 → unknown）
文件名关键词 → doc_category（见 §3.2 路由规则）
pdfplumber 首页字符数 → text_pdf 或 scan_pdf
PROCESSED_FLAGS 检查 → is_raw
extractor → 由 file_type + doc_category 组合查路由表决定
```

---

### 5.2 `pdf_text_extractor.py`

**职责**：文字型 PDF → blocks.json（含 `_meta`）。

**CLI**：
```bash
python pdf_text_extractor.py \
  --input ~/Desktop/.../889-...-条款.pdf \
  --product-id 889 \
  --doc-category clause \
  --output data/blocks/889_blocks.json
```

**内部流程**：
```
PDF → markitdown（subprocess 调用）→ Markdown 文本
    → parse_md_blocks.parse_markdown(product_id, md_text)
    → blocks 列表
    → 包装 _meta → 写 JSON
```

**质量检查**：
- 若 blocks 数量 < 10 → `_meta.parse_quality = "degraded"`，标准输出打印警告
- 若 markitdown 失败 → fallback 到 pdfplumber 逐页文本提取

---

### 5.3 `rate_table_extractor.py`

**职责**：费率表 PDF 或 XLSX → structured_table.json。
这是最关键的新模块，取代 extract_tier_a_rules.py 内的三个内联函数。

**CLI**：
```bash
python rate_table_extractor.py \
  --input ~/Desktop/.../889-...-费率表.pdf \
  --product-id 889 \
  --output data/rate_tables/889_structured_table.json
```

**XLSX 链路**：
```
openpyxl 读取所有 sheet
→ 对每个 sheet：
    收集前 6 行（表头区）→ 识别"交费期间"列或"缴费期"列
    识别频率关键词行（年缴/月缴/趸交）
→ 规范化：
    "1年" / "一次性" / "趸交" → "趸交"
    "N年" → "N年交"
→ extracted_fields.pay_periods / pay_frequencies
→ 输出 structured_table.json
```

**PDF 链路**：
```
pdfplumber 提取每页表格（page.extract_tables()）
→ 若有表格：走 table_parser（识别行列结构）
→ 若无表格：fallback fitz 文本提取（现有 extract_pay_info_from_rate_pdf 逻辑）
→ 规范化同上
→ 输出 structured_table.json
```

**格式自动检测**：
```
检查 schema 行（第一行或第一列）：
  含"交费期间"/"缴费期间" 且值在列头 → column_style（格式A）
  含"缴费期"/"交费期" 且值在行内 → row_style（格式B）
  无法判断 → format_unknown
```

---

### 5.4 `build_product_manifest.py`

**职责**：目录扫描 + 调用 file_router → manifest.json。

已有详细设计（`codex_task_build_manifest_v1.md`），在此基础上：
- 改为调用 `file_router.classify_file()` 而不是内联分类逻辑
- 输出 `source_files` 中每个文件加 `extractor` 字段（来自路由结果）

---

## 六、extract_tier_a_rules.py 的微调

**目标**：不重写，只加入对新格式的兼容读取。

**改动 1**：读取 blocks 时支持 `_meta` 包装格式
```python
def load_blocks(path: str) -> list[dict]:
    data = json.loads(Path(path).read_text())
    if isinstance(data, dict) and "blocks" in data:
        return data["blocks"]  # 新格式
    return data  # 旧格式（纯数组）
```

**改动 2**：支持从 structured_table.json 读取费率字段（替代内联 locate_rate_xlsx/pdf）
```python
def load_rate_candidates_from_structured_table(product_id: str) -> dict:
    """查找 data/rate_tables/{product_id}_structured_table.json，读取 extracted_fields。"""
    path = RATE_TABLES_DIR / f"{product_id}_structured_table.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text())
    return data.get("extracted_fields", {})
```

改动后，`locate_rate_xlsx` 和 `locate_rate_pdf` 可以逐步废弃（保留兜底，不删除）。

---

## 七、阶段计划

### Phase 1（当前，先跑通）

**目标**：文字型 PDF + 原始 XLSX 链路完整，eval 结果与 V18 基线完全一致。

```
新建：file_router.py
新建：pdf_text_extractor.py
新建：rate_table_extractor.py
新建：build_product_manifest.py（调用 file_router）
微调：parse_md_blocks.py（加 _meta）
微调：extract_tier_a_rules.py（支持新格式读取）
```

验收：`build_product_manifest.py` → manifest → `pdf_text_extractor` 生成 blocks → `rate_table_extractor` 生成 structured_table → `extract_tier_a_rules` → eval V19 = V18（零差异）

### Phase 2（下一阶段）

```
新建：pdf_ocr_extractor.py（扫描件 OCR → blocks）
增强：1548A 接入（有扫描件降级的产品）
```

### Phase 3（长期）

```
增强：block_enhancer.py（条款内嵌表格结构化、跨页合并）
增强：table_normalizer.py → normalized_rows → DB 写入
```

---

## 八、关键路径文件

```
development/scripts/
├── file_router.py                 ← 新建 (Phase 1)
├── pdf_text_extractor.py          ← 新建 (Phase 1)
├── rate_table_extractor.py        ← 新建 (Phase 1)
├── build_product_manifest.py      ← 新建 (Phase 1)
├── parse_md_blocks.py             ← 微调 (Phase 1)
├── extract_tier_a_rules.py        ← 微调 (Phase 1)
│
development/data/
├── blocks/                        ← 现有，格式升级加 _meta
├── rate_tables/                   ← 新建目录，存 structured_table.json
└── manifests/
    └── sample_manifest_v2.json    ← 由 build_product_manifest.py 生成
```
