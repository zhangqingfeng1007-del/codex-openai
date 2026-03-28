# 原始文件路由样本矩阵 V1

编写时间：2026-03-28
来源：对 10款重疾全量文件运行 file_router.py --json 的真实输出
用途：file_router.py 及后续 extractor 的验收基准

---

## 一、样本路由真值表（全量，29 个文件）

所有路径已用 file_router.py 真实运行验证，结果为实测值。

| # | 产品 ID | 文件名 | doc_category | parse_quality | extractor | is_raw | Phase | 备注 |
|---|---------|--------|--------------|--------------|-----------|--------|-------|------|
| 1 | 1134 | 1134-国华康佑保B终身重疾计划-条款.pdf | clause | text_pdf | pdf_text_extractor | ✅ | 1 | |
| 2 | 1134 | 1134-国华康佑保B终身重疾计划-费率表.pdf | raw_rate | text_pdf | rate_table_extractor | ✅ | 1 | |
| 3 | 1464 | 1464-国寿康欣终身重大疾病保险-条款.pdf | clause | text_pdf | pdf_text_extractor | ✅ | 1 | |
| 4 | 1464 | 1464-国寿康欣终身重大疾病保险-费率表.pdf | raw_rate | text_pdf | rate_table_extractor | ✅ | 1 | |
| 5 | 1548A | 1548A-北京人寿大黄蜂12号少儿重疾险（焕新版）-保终身-产品说明书.pdf | product_brochure | text_pdf | pdf_text_extractor | ✅ | 1 | |
| 6 | 1548A | 1548A-北京人寿大黄蜂12号少儿重疾险（焕新版）-保终身-条款.pdf | clause | text_pdf | pdf_text_extractor | ✅ | 1 | ⚠ 见注释A |
| 7 | 1548A | 1548A-北京人寿大黄蜂12号少儿重疾险（焕新版）-保终身-费率表.pdf | raw_rate | text_pdf | rate_table_extractor | ✅ | 1 | |
| 8 | 1568 | 1568-招商信诺爱享未来少儿重大疾病保险A款-产品说明书.pdf | product_brochure | text_pdf | pdf_text_extractor | ✅ | 1 | |
| 9 | 1568 | 1568-招商信诺爱享未来少儿重大疾病保险A款-条款.pdf | clause | text_pdf | pdf_text_extractor | ✅ | 1 | |
| 10 | 1568 | 1568-招商信诺爱享未来少儿重大疾病保险A款-费率表.xlsx | raw_rate | xlsx | rate_table_extractor | ✅ | 1 | |
| 11 | 1568 | **1568-招商信诺爱享未来少儿重大疾病保险A款-利益演示.xlsx** | **other** | xlsx | **skip** | ✅ | 1 | ⚠ 见注释B |
| 12 | 1578 | 1578-金小葵·少儿长期重疾险-产品说明书.pdf | product_brochure | text_pdf | pdf_text_extractor | ✅ | 1 | |
| 13 | 1578 | 1578-金小葵·少儿长期重疾险-条款.pdf | clause | text_pdf | pdf_text_extractor | ✅ | 1 | |
| 14 | 1578 | 1578-金小葵·少儿长期重疾险-现价表.pdf | cash_value | text_pdf | rate_table_extractor | ✅ | 1 | |
| 15 | 1578 | 1578-金小葵·少儿长期重疾险-费率表.pdf | raw_rate | text_pdf | rate_table_extractor | ✅ | 1 | |
| 16 | 1578 | 1578-金小葵·少儿长期重疾险-费率表.xlsx | raw_rate | xlsx | rate_table_extractor | ✅ | 1 | ⚠ 见注释C |
| 17 | 1803 | **1803-中意悦享安康（悠享版）重大疾病保险-产品说明书.pdf** | product_brochure | **scan_pdf** | **skip** | ✅ | 2 | ⚠ 唯一已确认扫描件 |
| 18 | 1803 | 1803-中意悦享安康（悠享版）重大疾病保险-条款.pdf | clause | text_pdf | pdf_text_extractor | ✅ | 1 | |
| 19 | 1803 | **1803-中意悦享安康（悠享版）重大疾病保险-利益演示.xlsx** | **other** | xlsx | **skip** | ✅ | 1 | ⚠ 见注释B |
| 20 | 1803 | 1803-中意悦享安康（悠享版）重大疾病保险-现价表.xls | cash_value | xlsx | rate_table_extractor | ✅ | 1 | |
| 21 | 1803 | 1803-中意悦享安康（悠享版）重大疾病保险-费率表.xlsx | raw_rate | xlsx | rate_table_extractor | ✅ | 1 | |
| 22 | 851A | 851A-金小葵少儿长期重疾-条款.pdf | clause | text_pdf | pdf_text_extractor | ✅ | 1 | |
| 23 | 851A | 851A-金小葵少儿长期重疾-费率表.pdf | raw_rate | text_pdf | rate_table_extractor | ✅ | 1 | |
| 24 | 864 | 864-招商信诺爱享康健（2023）终身重大疾病保险-条款.pdf | clause | text_pdf | pdf_text_extractor | ✅ | 1 | |
| 25 | 864 | 864-招商信诺爱享康健（2023）终身重大疾病保险-费率表.pdf | raw_rate | text_pdf | rate_table_extractor | ✅ | 1 | |
| 26 | 889 | 889-中信保诚「惠康」重大疾病保险（至诚少儿版）-条款.pdf | clause | text_pdf | pdf_text_extractor | ✅ | 1 | |
| 27 | 889 | 889-中信保诚「惠康」重大疾病保险（至诚少儿版）-费率表.pdf | raw_rate | text_pdf | rate_table_extractor | ✅ | 1 | |
| 28 | 919A | 919A-招商信诺爱享无忧重大疾病保险-条款.pdf | clause | text_pdf | pdf_text_extractor | ✅ | 1 | |
| 29 | 919A | 919A-招商信诺爱享无忧重大疾病保险-费率表.xlsx | raw_rate | xlsx | rate_table_extractor | ✅ | 1 | |
| — | meta | **产品总表-10款重疾.xlsx** | **other** | xlsx | **skip** | ✅ | 1 | ⚠ 见注释D |

---

## 二、注释（高风险命名样本）

### 注释A — 1548A 条款.pdf：路由正确，提取降级
路由结果为 `text_pdf → pdf_text_extractor`，是正确的。
但该 PDF 提取后产出 `_blocks_degraded.json`（blocks 数量极少）。
**结论**：降级在提取层判断，不在路由层。路由器不需要修改。

### 注释B — 利益演示.xlsx：当前 `other → skip`，待决策
1568 和 1803 各有一个"利益演示.xlsx"，文件名无匹配关键词，路由为 `other → skip`。
`利益演示` 是保单利益演示表，性质接近 `cash_value`，但当前 11 个 Tier A 字段不需要从中提取。
**结论（Phase 1）**：`skip` 是正确行为，无需修改规则。
**待决策（Phase 2+）**：若未来需要从利益演示提取字段，需在 `DOCUMENT_TYPE_RULES` 增加：
```python
("利益演示", "cash_value"),
```

### 注释C — 1578 同时有费率表.pdf 和费率表.xlsx
两个文件名相同（后缀不同），路由分别正确。
`build_product_manifest.py` 在聚合时需要将两者都列入 `raw_rate`，不能只取其一。

### 注释D — 产品总表-10款重疾.xlsx：元数据文件，正确 skip
这是人工整理的产品汇总表，不是原始保险文件，`other → skip` 完全正确。

---

## 三、高风险命名清单（DOCUMENT_TYPE_RULES 校准依据）

以下命名在真实样本或可预期的新产品中存在误判风险。

| 文件名关键词 | 当前路由结果 | 风险描述 | 建议 |
|------------|------------|---------|------|
| `产品说明书` | product_brochure ✅ | 无风险，规则中排在"说明书"之前 | 保持 |
| `说明书` | product_brochure ✅ | 若文件名含"说明书"但非投保说明（如"操作说明书"），会误判 | 可接受，实际样本中未出现 |
| `现价表` | cash_value ✅ | 无风险 | 保持 |
| `现金价值` | cash_value ✅ | 规则中已覆盖，但当前样本中无该命名 | 保持 |
| `利益演示` | **other（skip）** | Phase 1 无影响；Phase 2 若需提取需补规则 | 暂不加 |
| `核保` | underwriting_rule ✅ | 当前样本中无该文件；若来自招行数据，命名可能是"核保规则.pdf" | 待实际遇到时验证 |
| `投保规则` | underwriting_rule ✅ | 同上 | 待实际遇到时验证 |
| `_blocks.json` | PROCESSED ✅ | is_raw=False，正确屏蔽 | 保持 |
| `_gold.json` | PROCESSED ✅ | is_raw=False，正确屏蔽 | 保持 |
| `tier_a_rule_candidates` | PROCESSED ✅ | is_raw=False，正确屏蔽 | 保持 |
| `解析结果` | PROCESSED ✅ | is_raw=False，正确屏蔽 | 保持 |
| `产品总表` | other（skip）✅ | 正确，是人工汇总文件 | 保持 |

---

## 四、最小路由验收表（三分类）

### 必须走 pdf_text_extractor（14 个文件）

| 文件名 | 理由 |
|--------|------|
| *-条款.pdf（所有产品）| clause + text_pdf |
| *-产品说明书.pdf（1548A/1568/1578/1803）| product_brochure + text_pdf |
| *-说明书.pdf（若有）| product_brochure + text_pdf |

**例外**：`1803-产品说明书.pdf` → scan_pdf → **skip**（唯一扫描件，不走 pdf_text_extractor）

### 必须走 rate_table_extractor（12 个文件）

| 文件名 | 后缀 | 子类型 |
|--------|------|--------|
| *-费率表.pdf | .pdf | raw_rate |
| *-费率表.xlsx/.xls | .xlsx/.xls | raw_rate |
| *-现价表.pdf | .pdf | cash_value |
| *-现价表.xls | .xls | cash_value |

### 必须 skip（3 个文件）

| 文件名 | 原因 |
|--------|------|
| 1803-产品说明书.pdf | scan_pdf，Phase 2 |
| 1568/1803-利益演示.xlsx | other，Phase 1 不需要 |
| 产品总表-10款重疾.xlsx | other，元数据文件 |

---

## 五、DOCUMENT_TYPE_RULES 现状评估

当前规则已覆盖 10款重疾全量样本，无漏判、无误判（利益演示→other 属预期行为）。

**Phase 1 无需修改。**

唯一待决议项：
- `利益演示` → 暂时 `other`，Phase 2 决定是否加入 `cash_value`

---

## 六、已发现的一个实现 Bug

**1548A 条款.pdf 路由为 text_pdf，但实际 blocks 极少（降级）。**

这不是 file_router 的问题，而是下游 pdf_text_extractor 需要处理的情况：
- 路由正确（文件有文字，不是扫描件）
- 但 markitdown/pdfplumber 从该 PDF 提取的文字块质量差
- pdf_text_extractor 应在 blocks < 10 时将 `_meta.parse_quality` 设为 `degraded`

file_router 不需要改动。
