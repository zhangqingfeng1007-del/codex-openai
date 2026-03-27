# Codex 执行指令：V2 原型更新 + 文档补充

**本轮工作范围：两件事并行**

1. 修正 `review_task_creation_gap_mechanism_v1.md` 中的 3 处问题
2. 更新 V2 前端原型（app.js + mock JSON），纳入新状态和真实规模字段

---

## 任务 A：修正 review_task_creation_gap_mechanism_v1.md

**文件路径：** `~/codex-openai/development/docs/review_task_creation_gap_mechanism_v1.md`

### A1. 补全 not_extracted 状态转移（修改 Section 二）

在状态区分表后，补充 `not_extracted` 完整的后续转移路径：

```
not_extracted 可以转移到：
1. manually_added   — 复核员在资料中找到该字段，手动补录
2. cannot_extract_from_clause — 复核员确认产品确实无此项（如少儿产品无"交费频率-月交"）
3. pending_materials — 复核员无法判断，需等待补充资料
4. review_required   — 系统重新跑提取（重新触发抽取层后，转为正常候选路径）
```

状态转移表补充：

| 从 | 到 | 条件 |
|---|---|---|
| `not_extracted` | `manually_added` | 复核员手动补录，填写 final_value 和来源证据 |
| `not_extracted` | `cannot_extract_from_clause` | 复核员判断：产品类型决定此项不适用 |
| `not_extracted` | `pending_materials` | 复核员判断：需补充资料才能确认 |
| `not_extracted` | `review_required` | 重新触发抽取层，产出候选值 |
| `manually_added` | `accepted` | 复核员本人或他人确认补录内容 |
| `manually_added` | `rejected` | 补录内容被驳回，reason_code 必填 |

### A2. 修正差集算法 key（修改 Section 七）

将 Section 7.3 伪代码中的 index key 从 `coverage_name` 改为 `coverage_id`：

```python
# 错误：用 coverage_name 做 key，扩展槽位（如疾病其他责任1/2/3）会碰撞
extracted_index = {c["coverage_name"]: c for c in extracted_candidates}

# 正确：优先用 coverage_id 做 key
extracted_index_by_id = {c["coverage_id"]: c for c in extracted_candidates}
# 注意：extracted_candidates 必须包含 coverage_id 字段才能用此策略
# 若候选来源暂时没有 coverage_id，则辅助用 coverage_name，但需在文档中标注此为临时方案
```

同时在伪代码中修改 `template_fields` 循环逻辑：
```python
for tf in template_fields:
    # 优先按 coverage_id 匹配
    if tf["coverage_id"] in extracted_index_by_id:
        item = build_item_from_candidate(extracted_index_by_id[tf["coverage_id"]], tf)
    else:
        item = build_gap_item(tf)
    items.append(item)
```

### A3. 明确 manually_added 确认规则（修改 Section 三）

在 Section 3.2 中补充默认规则：

```
manually_added 确认规则（默认）：
- 允许复核员本人在提交补录时直接转为 accepted（快速路径，适合置信度高的明确补录）
- 若 is_tier_a=true，强制要求同一任务内另一操作者或上级确认（双人确认）
- 若 is_tier_a=false，允许复核员自确认
```

---

## 任务 B：更新 V2 前端原型

### B1. 更新 mock JSON

**文件路径：** `~/codex-openai/development/review-module/mock/review-task-v2.json`

对当前 7 个字段的 mock，做以下扩展，模拟真实 37 项产品：

**新增字段（加到 field_groups 合适的分组中）：**

1. 在 `tier_a_basic` 分组中新增：
   - `item_pay_period`：交费期间，status=`candidate_ready`，candidate_summary="趸交，5/10/20/30年交"，1个来源，无冲突
   - `item_waiting_period`：等待期，status=`candidate_ready`，candidate_summary="非意外180天，意外0天"，1个来源

2. 新增 `tier_a_ci_extra` 分组（重疾责任扩展），加入：
   - `item_ci_interval`：重疾赔付时间间隔，status=`not_extracted`，sources=[]，candidate_summary="—"
   - `item_ci_desc`：重疾保障说明，status=`review_required`，1个来源，candidate_summary="等待期内重疾退还已交保费；意外或等待期后给付基本保额"

3. 新增 `tier_policy_rights` 分组（保单权益），加入：
   - `item_loan`：保单贷款，status=`not_extracted`，sources=[]，candidate_summary="—"
   - `item_reduce`：减保，status=`candidate_ready`，candidate_summary="支持"，1个来源
   - `item_convert`：转换权，status=`not_extracted`，sources=[]，candidate_summary="—"

4. 新增 `tier_exemption` 分组（责任免除），加入：
   - `item_disease_exemption_count`：疾病免责数量，status=`candidate_ready`，candidate_summary="7条"，1个来源
   - `item_disease_exemption_detail`：疾病具体免责条款，status=`review_required`，1个来源（条款原文较长）

5. 保留现有的 `missing` 分组，将其重命名为：
   - group_type 改为 `dynamic_not_extracted`
   - group_name 改为 "未抽取字段"
   - 并加入以上三个 `not_extracted` 的 item（作为动态分组的聚合视图）

**更新顶层统计字段：**
- `conflict_count`：1（不变）
- `missing_count`：3（新增3个 not_extracted）
- `pending_review_count`：重新计算（所有 status 为 review_required + candidate_ready 的 items 数量）

**新增顶层字段：**
```json
"catalog_version_at_creation": "v1.2",
"total_items": 14
```

### B2. 更新 app.js

**文件路径：** `~/codex-openai/development/review-module/app.js`

**改动清单（只改这些，不要动其他逻辑）：**

1. `STATUS_LABELS` 新增两个状态：
   ```js
   not_extracted: { label: '未抽取', color: '#8B5CF6', bg: '#EDE9FE' },
   manually_added: { label: '已补录', color: '#D97706', bg: '#FEF3C7' },
   ```

2. `isTerminalStatus(status)` 函数：`manually_added` 不算终态（需要进一步确认），`not_extracted` 不算终态

3. 添加 `isBlockingStatus(status)` 函数（确定哪些状态阻断任务完成）：
   ```js
   function isBlockingStatus(status) {
     return ['review_required', 'candidate_ready', 'not_extracted',
             'pending_materials', 'rejected'].includes(status);
   }
   ```
   注意：`manually_added` 默认不阻断（配合双人确认规则，is_tier_a=true 的情况前端暂不处理）

4. 左栏分组渲染：支持 `group_type='dynamic_not_extracted'` 时，在分组标题前加 🟣 标识，并置顶显示（在其他静态分组之前）

5. Item 卡片渲染：
   - `status='not_extracted'` 时，显示灰色"未抽取"badge，卡片整体半透明，显示文字"模板存在，未被抽取"
   - `status='manually_added'` 时，显示橙色"已补录"badge，显示 `manually_added_by` 字段（如有）

6. 进度计算：分母使用 `total_items` 字段（如存在），而不是当前的 `field_groups` 遍历数

7. `pending_review_count` 展示：在页面顶部 task 信息行加一个小标签，展示 `missing_count`（未抽取字段数量）

---

## 验收标准

**文档修正：**
1. `not_extracted` 有完整的 4 条转移路径 ✓
2. 差集算法 key 改为 coverage_id，并注释临时方案 ✓
3. manually_added 确认规则明确（is_tier_a=true 双人，is_tier_a=false 自确认）✓

**前端原型：**
1. mock JSON 有 14 个字段（含 3 个 not_extracted，2 个 missing/缺失相关）✓
2. STATUS_LABELS 包含 not_extracted 和 manually_added ✓
3. not_extracted 分组置顶，有 🟣 标识 ✓
4. not_extracted item 卡片有半透明 + "模板存在，未被抽取"提示 ✓
5. 进度百分比分母用 total_items ✓
6. 页面顶部显示 missing_count 数量 ✓
7. 不引入 PDF 查看器、补录表单、catalog 搜索等后端依赖功能 ✓
