# 抽取管道现状 V4（2026-03-28）

更新自：extraction_pipeline_status_v3.md（V20 基线）

---

## 管道架构（当前）

```
原始文件目录
    ↓
build_all.py（一键批量入口）
    ├── build_product_manifest.py  → manifest_latest.json
    ├── pdf_text_extractor.py      → data/blocks/{id}_blocks.json（text_pdf）
    ├── pdf_ocr_extractor.py       → data/blocks/{id}_说明书_blocks.json（scan_pdf）← Phase 2 新增
    └── build_rate_tables_batch.py → data/tables/{id}_structured_table.json
    ↓
extract_tier_a_rules.py（条款 blocks + 说明书 blocks + structured_table fallback）
    ↓
tier_a_rule_candidates.json
    ↓
eval_tier_a.py（对照 gold）
    ↓
tier_a_eval_v21.json  ← 当前基线
```

---

## 关键脚本清单

| 脚本 | 用途 | 状态 |
|------|------|------|
| `file_router.py` | 文件识别与解析器路由 | ✅ 完成 |
| `build_product_manifest.py` | 自动扫描产品目录建档（files[] 格式）| ✅ 完成 |
| `build_all.py` | 一键批量入口：manifest + blocks + tables | ✅ 完成 |
| `pdf_text_extractor.py` | text_pdf → blocks.json（markitdown/fitz）| ✅ 完成 |
| `pdf_ocr_extractor.py` | scan_pdf → blocks.json（PaddleOCR v3，双栏版面重建）| ✅ 完成（Phase 2）|
| `parse_md_blocks.py` | Markdown → structured blocks | ✅ 完成 |
| `build_rate_tables_batch.py` | 批量生成 structured_table.json | ✅ 完成 |
| `rate_table_extractor.py` | 单文件费率表结构化提取（格式A/B/C，数字列头/xlsx token 修复）| ✅ 完成 |
| `verify_structured_tables.py` | structured_table 集成验证 | ✅ 完成 |
| `extract_tier_a_rules.py` | 规则提取主脚本（含 structured_table fallback + list block + specificity 评分）| ✅ 完成 |
| `eval_tier_a.py` | 评估候选与 gold 匹配 | ✅ 稳定 |

---

## 当前基线：V21（2026-03-28 确立，9产品）

| 字段 | hit | miss | mismatch | hit_rate | V20→V21 |
|------|-----|------|----------|---------|---------|
| 重疾数量 | 9 | 0 | 0 | **100%** | = |
| 等待期 | 9 | 0 | 0 | **100%** | = |
| 等待期（简化）| 9 | 0 | 0 | **100%** | = |
| 保险期间 | 9 | 0 | 0 | **100%** | = |
| 交费期间 | 8 | 0 | 1 | 88.9% | =（mismatch: 889，既有口径问题）|
| 宽限期 | 8 | 1 | 0 | 88.9% | = |
| 犹豫期 | 8 | 1 | 0 | 88.9% | = |
| 重疾赔付次数 | 8 | 1 | 0 | 88.9% | = |
| 重疾分组 | 8 | 1 | 0 | 88.9% | = |
| 交费频率 | 8 | 0 | 1 | 88.9% | =（mismatch: 1803，资料缺口）|
| **投保年龄** | **7** | **2** | **0** | **77.8%** | **↑+11.1%（1803 OCR 说明书生效）** |

**V20 原有 10 字段：零回归。**

### V21 关键改进

- **1803 产品说明书 OCR 打通**：PaddleOCR v3，28 blocks，全 5 页覆盖
- **投保年龄新命中**：1803 说明书提取到 `18-60周岁`
- **1568 交费期间回归已修复**：pay_period_specificity 评分，费率表更完整候选覆盖说明书候选

---

## 已知 miss/mismatch（可接受，非代码 bug）

| 产品 | 字段 | 类型 | 根因 |
|------|------|------|------|
| 1134 | 投保年龄 | miss | 无产品说明书，费率表仅得 0-50，无法还原"28天" |
| 889 | 投保年龄 | miss | 非标天数格式，条款/说明书均无"28天"文字 |
| 889 | 交费期间 | mismatch | rate_pdf 噪音，既有问题，来源文件限制 |
| 1803 | 交费频率 | mismatch | 资料缺口：核保文件缺失，月/季/半年频率无文字来源 |
| 1464 | 犹豫期 | miss | 条款无犹豫期文字 |
| 1568 | 投保年龄 | miss | 非标天数，说明书 scan_pdf，OCR 未命中 |

---

## Phase 2 OCR 链路状态

| 项目 | 状态 |
|------|------|
| `pdf_ocr_extractor.py` | ✅ 完成，PaddleOCR v3 兼容 |
| `build_all.py` OCR 路由 | ✅ scan_pdf → `pdf_ocr_extractor.py`（`.venv_ocr`）|
| 1803 说明书验证 | ✅ 28 blocks，全 5 页，投保年龄命中 |
| 小样本稳定性验证 | 🔲 待做：再挑 1-2 个 scan_pdf 样本验证 |
| `_meta` 补全 | 🔲 技术债：缺 `char_count`、`page_count` |

---

## 技术债（已知，不阻塞当前 eval）

| 项目 | 描述 | 优先级 |
|------|------|--------|
| OCR `_meta` 补全 | `char_count`、`page_count` 缺失 | P3 |
| `parser_route` / `extractor` 命名统一 | manifest 与脚本内字段名不一致 | P3 |
| structured_table candidate schema | 比其他候选多 3 个字段 | P3 |
| PDF tables[].rows 为空 | rate_table_extractor 行数据未填充 | P3 |
| 1578 交费期间 | 自然费率表，无缴费期列，须从条款提取 | P4 |
| OCR 小样本稳定验证 | 仅验证了 1803，需扩至 1-2 个其他 scan_pdf | Phase 2 |

---

## 下一步优先级

1. **OCR 小样本稳定验证**：再找 1-2 个 scan_pdf 样本，确认 `pdf_ocr_extractor.py` 不只对 1803 有效
2. **技术债收口**（P3，小成本）：`_meta` 补全，命名统一
3. **核保文件补充**（待排期）：1803/889 交费频率完整值
