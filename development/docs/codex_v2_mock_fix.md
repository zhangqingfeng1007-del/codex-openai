# Codex 执行指令：修正 mock 重复 item 问题 + 动态分组改为引用式结构

**问题背景：**
当前 mock 中 `dynamic_not_extracted` 存储了与静态分组不同 item_id 的重复项（`item_gap_ci_interval` vs `item_ci_interval`），导致 `getAllItems()` 将两者都计入，进度计算出现分母/分子不一致。同时 `pending_review_count=8` 计算有误。

---

## 修改目标

1. **动态分组改为引用式结构**（item_ids 列表，不存完整对象）
2. **静态分组保留 not_extracted items**（唯一存储位置）
3. **修正 `pending_review_count`**
4. **修正 `total_items`**
5. **将 `cannot_extract` 和 `not_extracted` 分为两个动态分组**

---

## 任务 A：修改 review-task-v2.json

**文件路径：** `~/codex-openai/development/review-module/mock/review-task-v2.json`

### A1. 动态分组改为引用式

将 `dynamic_not_extracted` 和原来的 `missing` 分组改为如下结构：

```json
{
  "group_type": "dynamic_not_extracted",
  "group_name": "未抽取字段",
  "is_dynamic": true,
  "item_ids": ["item_ci_interval", "item_loan", "item_convert"]
},
{
  "group_type": "dynamic_missing",
  "group_name": "缺失字段",
  "is_dynamic": true,
  "item_ids": ["item_specific_disease_count"]
}
```

规则：
- `dynamic_*` 分组只有 `group_type / group_name / is_dynamic / item_ids` 四个字段，**没有 `items` 数组**
- `item_specific_disease_count`（`cannot_extract`）放入 `dynamic_missing`，不放入 `dynamic_not_extracted`
- 两个动态分组分别置顶（排在静态分组之前）

### A2. 静态分组保留完整 item 对象

- `tier_a_ci_extra` 保留 `item_ci_interval`（not_extracted）和 `item_ci_desc`（review_required），不变
- `tier_policy_rights` 保留 `item_loan`、`item_reduce`、`item_convert`，不变
- 删除原有 `dynamic_not_extracted` 中的完整 item 对象（`item_gap_ci_interval` / `item_gap_loan` / `item_gap_convert`）
- 删除原有独立 `missing` 分组（合并到 `dynamic_missing`）

### A3. 修正顶层统计字段

重新计算实际字段数（静态分组所有 items 之和）：

- tier_a_basic: 5 items（投保年龄、保险期间、交费期间、等待期、交费频率）
- tier_a_ci: 3 items（重疾赔付次数、重疾分组、重疾数量）
- tier_a_ci_extra: 2 items（重疾赔付时间间隔、重疾保障说明）
- tier_policy_rights: 3 items（保单贷款、减保、转换权）
- tier_exemption: 2 items（疾病免责数量、疾病具体免责条款）
- dynamic_not_extracted 引用原有 3 个 item_ids（不新增 item）
- dynamic_missing 引用原有 1 个 item_id（不新增 item）

总计静态 items = **15**，`item_specific_disease_count` 已在 `tier_exemption` 或需要补回（见下）

**注意**：`item_specific_disease_count`（特定疾病数量，cannot_extract）目前在旧 `missing` 分组中，需要决定它在静态分组中的归属：
- 应加入 `tier_a_ci_extra` 分组（它是疾病责任相关字段，cannot_extract 状态）
- 同时被 `dynamic_missing` 引用

调整后 `tier_a_ci_extra` 变为 3 items，静态总计 = **16**

顶层字段应为：
```json
"total_items": 16,
"conflict_count": 1,
"missing_count": 1,
"not_extracted_count": 3,
"pending_review_count": 12
```

`pending_review_count` 计算规则：`status ∈ {review_required, candidate_ready}` 的字段数量：
- review_required: 投保年龄(1), 交费频率(1), 重疾赔付次数(1), 重疾分组(1), 重疾保障说明(1), 疾病具体免责条款(1) = 6
- candidate_ready: 保险期间(1), 交费期间(1), 等待期(1), 重疾数量(1), 减保(1), 疾病免责数量(1) = 6
- 合计 = **12**

---

## 任务 B：修改 app.js

**文件路径：** `~/codex-openai/development/review-module/app.js`

### B1. 修改 `getAllItems()`

```js
function getAllItems() {
  // 只遍历非动态分组（没有 is_dynamic 标记的），避免重复计入引用式动态分组
  return state.task.field_groups
    .filter(group => !group.is_dynamic)
    .flatMap(group => group.items);
}
```

移除旧版的 `seen Set` dedup 逻辑——不再需要（因为动态分组不含完整 item 对象）。

### B2. 修改 `renderFieldGroups()` 支持两种分组类型

```js
function renderFieldGroups() {
  const activeItem = findItemById(state.selectedItemId);
  const linkedMembers = activeItem ? getLinkedMembers(activeItem) : new Set();
  const searchTerm = state.searchTerm.trim();

  fieldGroupList.innerHTML = "";

  // 动态分组优先（is_dynamic=true 排在前面）
  const groups = [...state.task.field_groups].sort((a, b) => {
    if (a.is_dynamic && !b.is_dynamic) return -1;
    if (!a.is_dynamic && b.is_dynamic) return 1;
    return 0;
  });

  groups.forEach((group) => {
    // 解析 items：动态分组从 item_ids 查找，静态分组直接用 items
    let items;
    if (group.is_dynamic) {
      items = (group.item_ids || [])
        .map(id => findItemById(id))
        .filter(Boolean);
    } else {
      items = group.items || [];
    }

    // 过滤搜索
    const visibleItems = items.filter((item) => {
      if (!searchTerm) return true;
      return item.coverage_name.includes(searchTerm) || getItemSummary(item).includes(searchTerm);
    });
    if (!visibleItems.length) return;

    // 动态分组图标
    const dynamicIcon = group.is_dynamic
      ? (group.group_type === "dynamic_not_extracted" ? "🟣 " : "⬜ ")
      : "";

    // ... 余下渲染逻辑不变，只把 group.group_name 前加 dynamicIcon
  });
}
```

### B3. 修改 `renderTopbar()` 展示 `not_extracted_count`

```js
taskStatusText.textContent = `${statusLabel(task.task_status)} · 未抽取 ${state.task.not_extracted_count || 0}`;
riskSummary.textContent = `冲突 ${state.task.conflict_count} · 缺失 ${state.task.missing_count} · 未抽取 ${state.task.not_extracted_count || 0} · 待审 ${state.task.pending_review_count}`;
```

---

## 验收标准

1. `getAllItems()` 不依赖 dedup，直接过滤 `is_dynamic=false` 的分组 ✓
2. `getAllItems()` 返回长度 = 16（与 `total_items` 一致）✓
3. 动态分组只有 `item_ids`，无 `items` 数组 ✓
4. `tier_a_ci_extra` 包含 3 items（含 `item_specific_disease_count`）✓
5. `pending_review_count=12`，`total_items=16`，`missing_count=1`，`not_extracted_count=3` ✓
6. 动态分组渲染时从 `item_ids` lookup，与静态分组渲染分支清晰区分 ✓
7. 不引入新的 item 对象（所有 item 只在静态分组中存储一次）✓
