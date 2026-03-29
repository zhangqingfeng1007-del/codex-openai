# 保险条款智能拆解系统 — Claude Code 项目规范

> 本文件由项目 PM 维护，Claude Code 进入此项目目录后自动加载。
> 所有开发任务必须在此约束框架内执行，不得绕过。

---

## 零、接手第一步（新开发者必读）

**第一步：拉代码确认状态**
```bash
git pull
git log --oneline -6
# 应看到最新 commit: e4309fbf docs: add CLAUDE.md for project handoff
```

**第二步：验证 Tier A 提取链**
```bash
python3 development/scripts/extract_tier_a_rules.py \
  --manifest development/data/manifests/sample_manifest.json \
  --output development/data/extractions/tier_a_merged_candidates_v1.json
# 应输出：wrote 10 products
```

**第三步：验证 Tier B 提取链**
```bash
python3 development/scripts/extract_responsibility_fields.py
# 应输出：tier_b_responsibility_candidates_v1.json，10款产品
```

**第四步：验证匹配链 dry-run**
```bash
python3 development/scripts/write_to_db.py \
  --dry-run \
  --candidates development/data/extractions/tier_a_merged_candidates_v1.json \
  --candidates-b development/data/extractions/tier_b_responsibility_candidates_v1.json
# 应输出：matched_review_required=131, unmatched_new_value=1, unmatched_new_item=0
```

**第五步：验证数据库连接（仅 Claude Code，Codex 禁止执行）**
```python
# 数据库凭证由 PM 单独提供，不存储在代码库中
# 请向 PM 获取连接信息后验证
```

**当前从哪里继续开发：**
`extract_responsibility_fields.py` → 继续扩 Tier B 字段（轻症分组规则待确认，参考第六节）

---

## 一、项目定位

**项目名称：** 保险条款智能拆解系统（Insurance Clause Extraction Pipeline）
**代码库：** `~/codex-openai/`
**当前阶段：** 一期 — 重疾险 Tier A 链路跑通，Tier B 责任字段提取进行中
**最终目标：** 全险种条款自动拆解 → 标准项精确匹配 → 人工审核后入库 → 驱动精算定价引擎

**与 AIX 智能体的关系：**
- 本系统是 `~/code/aix-engine/` 的数据供给端
- 拆解产物最终写入 `ensure_recognize.cmb_product_coverage`，供 AIX 推荐和精算使用
- 两个项目独立开发，不共享代码库

---

## 二、角色分工（移交后）

| 角色 | 职责 |
|------|------|
| **Claude Code** | 主开发，负责脚本实现、规则调试、数据库查询 |
| **Codex** | 审查/监督，检查交付物是否符合规范，不直接接触阿里云数据库 |
| **PM（用户）** | 业务验收、人工审核标准值、架构决策 |

**数据库安全边界（硬规则）：**
- 阿里云只读库 `ensure_recognize`：**只有 Claude Code 可以直接连接**
- Codex 及其他 AI 禁止直接访问，需要数据时向 Claude 申请查询
- 违反此规则 = 安全边界被破坏

---

## 三、数据库连接信息

**凭证由 PM 单独提供，不存储在代码库中。**

**关键表：**
- `cmb_coverage`：标准项字段树（depth1/2/3，共960条）
- `cmb_product_coverage`：每款产品的拆解值
- `cmb_coverage_standard`：标准值详情（含 standard_id）
- `cmb_product`：产品主表（重疾险 aix_category_id=6001）

**JOIN 注意：**
`cmb_product.product_id` = utf8mb4_general_ci，其他表 = utf8mb4_unicode_ci
跨表必须加：`ON x.product_id COLLATE utf8mb4_unicode_ci = p.product_id`

---

## 四、系统架构（5层解析链）

```
原始文件目录
    ↓ file_router.py（text_pdf / scan_pdf 分流）
pdf_text_extractor.py / pdf_ocr_extractor.py
    ↓
parse_md_blocks.py → {product_id}_blocks.json
                   → {product_id}_说明书_blocks.json
                   → {product_id}_underwriting_blocks.json
    ↓
rate_table_extractor.py → {product_id}_structured_table.json
    ↓
extract_tier_a_rules.py → tier_a_merged_candidates_v1.json（Tier A 通用字段）
extract_responsibility_fields.py → tier_b_responsibility_candidates_v1.json（Tier B 责任字段）
    ↓
write_to_db.py --dry-run → matched_rows_preview.json
                          → unmatched_new_values_review.json
                          → unmatched_new_items_review.json
```

**一键入口：**
```bash
python3 development/scripts/build_all.py --product-dir <目录>
```

---

## 五、关键文件路径

```
development/scripts/
  build_all.py                    ← 一键入口（manifest + blocks + tables）
  file_router.py                  ← PDF 类型判断（text_pdf / scan_pdf）
  pdf_text_extractor.py           ← 可复制文字 PDF 解析
  pdf_ocr_extractor.py            ← OCR PDF 解析（PaddleOCR v3）
  parse_md_blocks.py              ← Markdown → blocks.json
  rate_table_extractor.py         ← 费率表结构化
  extract_tier_a_rules.py         ← Tier A 通用字段提取（投核保规则字段）
  extract_responsibility_fields.py← Tier B 责任字段提取
  write_to_db.py                  ← 干跑匹配链（--dry-run 模式）

development/data/
  blocks/                         ← {product_id}_blocks.json
  tables/                         ← {product_id}_structured_table.json
  extractions/
    tier_a_merged_candidates_v1.json
    tier_b_responsibility_candidates_v1.json
  manifests/
    coverage_standard_full.json   ← 全量标准项+标准值字典（917节点，6936条）
    coverage_id_mapping.json      ← Tier A 快速字段映射（10条）
    coverage_path_mapping.json    ← 全树路径映射（917条）
    product_id_mapping.json       ← 内部ID → db_product_id（10款样本）
  db_write_preview/
    matched_rows_preview.json     ← dry-run 命中结果（100+31=131条）
    unmatched_new_values_review.json
    unmatched_new_items_review.json
  gold/                           ← 人工标注标准答案（eval 用）
  eval/                           ← eval 历史基线（当前 V21）
```

---

## 六、当前进度（2026-03-29）

### Tier A（投核保规则类字段）✅ 已完成
- 10 个字段：投保年龄/保险期间/交费期间/交费频率/等待期/宽限期/犹豫期/重疾数量/重疾赔付次数/重疾分组
- 10 款样本，100 条 matched，1 条 unmatched（889 交费期间已知噪音）
- V21 eval 基线：投保年龄 77.8%，其余字段 88.9%~100%

### Tier B（责任树字段）进行中
- 第一批 ✅ commit c12fd03d：重疾数量/重疾赔付次数/轻症赔付次数/轻症数量，25/25 命中
- 第二批 ✅ commit 0fe3b7a9：中症赔付次数/中症数量，31/31 命中
- **待处理：轻症分组**（组数在附表，主条款正文不显式写"X组"，待人工确认提取规则）

### 匹配链 ✅ 已验证
- write_to_db.py --dry-run 支持 Tier A + Tier B 合并输入
- 匹配规则：先定位 coverage_id，再在该字段内字符级精确匹配标准值
- 三类输出：matched / unmatched_new_values / unmatched_new_items

---

## 七、标准项体系（拆解库三级结构）

```
depth=1（38个大类）：身故责任、疾病责任、投核保规则、年金责任 ...
  depth=2（147个字段）：投保年龄、保险期间、重疾责任、轻症责任 ...
    depth=3（732个细项）：重疾赔付次数、重疾数量、轻症保障说明 ...
```

**匹配规则（硬要求）：**
1. 先通过 coverage_id_mapping.json（快速）或 coverage_path_mapping.json（全树）定位 coverage_id
2. 再只在该 coverage_id 的 standard_values[] 内字符级精确匹配
3. 命中 → matched_review_required
4. 字段存在但值不在库 → unmatched_new_value（人工审核，机器给出建议值）
5. 字段不存在 → unmatched_new_item（人工审核，不得自动创建字段）
6. **严禁模糊匹配、跨字段匹配、自动创建标准项/标准值**

**coverage_standard_full.json 说明：**
- 来源：cmb_coverage × cmb_product_coverage
- 排除：基本信息/特色服务/续保信息/产品说明（产品唯一值，非标准项）
- 6936 条标准值条目，5467 个 distinct 值
- 最终用途：驱动精算定价引擎，字符差异直接导致定价逻辑无法命中

---

## 八、险种扩展路线（已确认）

难度排序（从难到易）：医疗险 > 重疾险 > 年金险 > 寿险（定期/终身）

**当前：** 重疾险（打样）
**下一步：** 年金险（与重疾共用投核保规则 ~60% 字段，新增年金责任）
**再下一步：** 寿险（共用 ~70% 字段，新增身故责任为主责任）
**暂不做：** 百万医疗险（最复杂，续保/免赔/社保协同，二期以后）

---

## 九、已知待处理问题

| 级别 | 问题 | 负责 |
|------|------|------|
| P1 | 889 交费期间噪音（rate_pdf_pay_period 路径多提了 55/63年交）| Claude |
| P1 | 1134 费率表纯数字列头未规范化（10/20/30 应补全为"X年交"）| Claude |
| P1 | 轻症分组提取规则（待人工确认样本标准值和条款写法）| PM + Claude |
| P2 | 1578 交费期间（自然费率表无缴费期列，须从条款提取）| Claude |
| P2 | 1803/889 交费频率（来自核保文件，当前缺失）| PM 提供文件 |
| 待做 | db_product_id 生成规范（当前手工映射，需规范化）| PM 提供规则 |
| 待做 | standard_id 补查（PENDING_LOOKUP，真实入库前需从 cmb_coverage_standard 查）| Claude |

---

## 十、研发治理原则（每次开发必须遵守）

1. **验收必须基于代码和文件，不接受口头描述** — 用 Read/Grep/Bash 直接查原始文件
2. **字段体系来自数据库，不自行创造** — 任何字段定位必须能回溯到 coverage_id
3. **标准值精确匹配，不模糊** — 字符差异直接影响精算，不可妥协
4. **最小模块化** — 每个脚本独立闭环，验收通过再接主链
5. **只做当前需求** — 不因"顺手"引入未要求的功能
6. **删除废弃代码** — 新增逻辑同时检查旧逻辑是否需要清理
7. **Codex 禁止连接阿里云数据库** — 需要数据时向 Claude 申请
8. **保障说明类字段（长文本）暂不做** — 等结构化字段全部跑通再处理

---

## 十一、业务领域关键约束

**重疾险分组判定规则：**
- 单次赔付 → 重疾分组 = "不涉及"
- 多次赔付 + 无分组 → "不分组"
- 多次赔付 + 有分组 → 具体组数
- 分组必须来自条款明确内容，不允许基于经验默认补值

**重疾赔付次数 = 1次 判定（双条件）：**
- 条件1（负向）：条款未出现"多次给付""第二次重大疾病"等字样
- 条件2（正向）：条款明确写"1次"或"给付后合同终止/本项责任终止"
- 两者同时满足才可规则判定，否则进入 review_required

**"不涉及" vs "不分组"：**
- "不涉及"：产品根本没有该利益
- "不分组"：有该功能但病种不分组
- 两者含义不同，不可混用

---

## 十二、样本产品（10款测试集）

位于：`~/Desktop/开发材料/10款重疾/`

| 内部ID | 产品名 | db_product_id |
|--------|--------|---------------|
| 1134 | 国华康佑保B终身重疾计划 | 1280003176 |
| 1464 | 北京人寿大黄蜂12号少儿重疾险（焕新版）-保30年 | 2800005 |
| 1548A | 北京人寿大黄蜂12号少儿重疾险（焕新版）-保终身 | 2800007 |
| 1568 | 中信保诚「臻享惠康」重大疾病保险B款 | 1530003621 |
| 1578 | 金小葵少儿长期重疾 | 1520003424 |
| 1803 | 中意悦享安康（悠享版）重大疾病保险 | — |
| 851A | 招商仁和仁心保贝重大疾病保险 | — |
| 864 | 平安福重大疾病保险 | — |
| 889 | 中信保诚「惠康」重大疾病保险（至诚少儿版）| 1530003475 |
| 919A | 太平洋人寿金佑人生终身寿险 | — |
