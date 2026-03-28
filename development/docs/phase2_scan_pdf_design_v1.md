# Phase 2：扫描型 PDF / OCR 解析器设计方案 v1

**日期**：2026-03-28
**范围**：`parse_quality = scan_pdf` 的文档，使用 OCR 提取文字后接入现有 blocks 链路

---

## 1. 背景与已知 scan_pdf 清单

Phase 1 已处理所有 `text_pdf`（可直接提取文字）和 XLSX 文件。
当前 10 款样本中唯一 scan_pdf：

| 产品 | doc_category | 文件 | 影响字段 |
|------|-------------|------|---------|
| 1803 | product_brochure | 新华健康无忧C款产品说明书.pdf | 投保年龄（28天-45周岁）、交费频率 |

**Phase 2 目标**：给 `pdf_text_extractor.py` 加 OCR 分支，使扫描型 PDF 能生成 blocks.json，进入现有提取链路。

---

## 2. 技术选型

### 推荐方案：PaddleOCR（离线，中文效果优）

```
pip install paddlepaddle paddleocr
```

优点：
- 纯离线，无 API 费用
- 中文识别率领先，适合保险条款格式
- 输出带坐标，可做版面分析（列/段落重建）

备选：
- **Azure Document Intelligence**：云服务，精度高，但需联网 + 费用
- **Tesseract + pytesseract**：老牌，中文效果一般，不推荐
- **markitdown**：本身不做 OCR，对 scan_pdf 无效

---

## 3. 新增模块：`pdf_ocr_extractor.py`

### 位置
`development/scripts/pdf_ocr_extractor.py`

### CLI 接口（与 pdf_text_extractor.py 保持一致）
```bash
python3 pdf_ocr_extractor.py \
  --input /path/to/scan.pdf \
  --product-id 1803 \
  --doc-category product_brochure \
  --output data/blocks/1803_brochure_blocks.json
```

### 主要流程
```
scan PDF
  → pdf_to_images（每页 → PNG，300 dpi）
  → PaddleOCR（per page）→ [{"text": "...", "bbox": [...]}]
  → ocr_lines_to_markdown（版面重建 → Markdown 文本）
  → parse_markdown（现有模块，复用）
  → serialize_blocks_payload（现有模块，复用）
  → blocks.json
```

### 关键函数清单

| 函数 | 职责 |
|------|------|
| `pdf_to_images(pdf_path, dpi=300)` | fitz 将每页转为 PIL Image |
| `ocr_page(image, ocr_engine)` → list[dict] | 对单页图像调用 PaddleOCR，返回 [{text, bbox, confidence}] |
| `ocr_lines_to_markdown(ocr_results)` → str | 将 OCR 结果按 y 坐标排序重建为 Markdown 文本（含 \f 分页符） |
| `build_meta(...)` | 与 pdf_text_extractor.py 相同接口，parse_method="paddleocr" |
| `main()` | CLI 入口 |

---

## 4. 版面重建策略（ocr_lines_to_markdown）

扫描 PDF 的 OCR 结果是散乱的 bbox 文本块，需要还原为线性文本：

```
1. 按页分组
2. 每页内：按 bbox 顶部 y 坐标排序（从上到下）
3. 同一行（y 差 < 行高 × 0.5）的块：按 x 坐标合并为一行
4. 相邻行间距 > 行高 × 1.5 → 插入空行（段落分隔）
5. 输出：纯文本，页间用 \f 分隔（与 pdf_text_extractor 输出格式一致）
```

**注意**：版面重建的精度决定了后续 parse_markdown 的效果。保险说明书一般是单栏或双栏，需要对双栏做特殊处理（左栏先，右栏后）。

---

## 5. 与现有链路的集成

### 5.1 `pdf_text_extractor.py` 扩展（可选）

可以在 `pdf_text_extractor.py` 中增加 scan_pdf 分支，自动路由到 OCR：

```python
parse_quality = detect_parse_quality(input_path)
if parse_quality == "scan_pdf":
    # Phase 2: OCR branch
    from pdf_ocr_extractor import extract_text_by_ocr
    md_text = extract_text_by_ocr(input_path)
    parse_method = "paddleocr"
else:
    # Phase 1: text PDF branch (existing)
    ...
```

### 5.2 `build_all.py` 的 scan_pdf 跳过逻辑

当前 `build_all.py` 对 scan_pdf 打印 `(Phase 2)` 并跳过。
Phase 2 完成后，去掉这个跳过分支即可，零改其他逻辑。

```python
# Phase 2 完成后删除此判断：
if entry.get("parse_quality") == "scan_pdf":
    print(f"  [SKIP] {product_id} {cat}: scan_pdf (Phase 2)")
    continue
```

### 5.3 `file_router.py` 无需改动

`parse_quality` 已由 file_router 在建 manifest 时赋值，OCR 模块只是新的 parser，不影响路由逻辑。

---

## 6. 验收标准

| 测试项 | 标准 |
|--------|------|
| 1803 product_brochure 生成 blocks.json | ≥ 20 blocks，无 degraded |
| 1803 投保年龄提取 | hit（28天-45周岁） |
| 1803 交费频率提取 | hit（月交/季交/半年交/年交）|
| V20 → V21 eval | 零回归，1803相关字段 hit_rate 提升 |
| `build_all.py` 端到端 | scan_pdf 文件不再被跳过 |

---

## 7. 依赖与环境

```bash
# 新增依赖（建议加入 requirements.txt）
paddlepaddle
paddleocr
Pillow  # pdf_to_images 用到

# 已有依赖（不需要新增）
PyMuPDF (fitz)  # pdf_to_images 复用
```

PaddleOCR 首次运行会自动下载模型文件（~500MB）。建议在开发机上预下载：
```python
from paddleocr import PaddleOCR
PaddleOCR(use_angle_cls=True, lang='ch')  # 触发模型下载
```

---

## 8. 开发顺序建议

1. `pip install paddlepaddle paddleocr` + 验证环境
2. 写 `pdf_ocr_extractor.py`（独立脚本，先不集成）
3. 对 1803 产品说明书跑一遍，人工检查 OCR 质量
4. 调整 `ocr_lines_to_markdown` 版面重建逻辑直到 blocks 质量合格
5. 跑 `extract_tier_a_rules.py` → 确认 1803 投保年龄/交费频率 hit
6. 集成到 `pdf_text_extractor.py`（自动路由）
7. 去掉 `build_all.py` 的 scan_pdf 跳过
8. 跑 V21 eval，更新基线

---

## 9. 不做的事

- 不做版面还原为结构化表格（OCR 结果里的表格仍输出为文本块，由 parse_markdown 的 table 逻辑处理）
- 不做 Azure/云 OCR（保持离线原则）
- 不处理手写内容（保险文档均为印刷体）
- 不修改 `parse_md_blocks.py`（OCR 输出的 Markdown 必须符合现有格式，问题在版面重建层解决）
