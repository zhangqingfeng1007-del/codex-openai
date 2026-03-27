# 人工复核模块状态机 V2（Codex 版）

**版本：** V2.0-Codex  
**目的：** 用任务级 + 字段级双状态机支撑真实复核流转

---

## 一、状态机结论

V2 不能再把状态放在前端临时存储里。  
状态必须由后端持久化，并且每次裁决都形成事件。

状态机应分为三层：

1. 任务级 `TaskStatus`
2. 字段级 `CoverageItemStatus`
3. 入库决策级 `ImportStatus`

---

## 二、任务级状态机

### 2.1 状态定义

| 状态 | 含义 |
|---|---|
| `pending_review` | 任务已创建，未开始复核 |
| `in_review` | 已进入复核过程 |
| `waiting_materials` | 资料缺失，等待补充 |
| `review_completed` | 字段裁决完成，可提交入库 |
| `import_submitted` | 已发起入库 |
| `import_failed` | 入库失败，需回到复核 |
| `archived` | 任务关闭 |

### 2.2 状态转移

```text
pending_review -> in_review
in_review -> waiting_materials
waiting_materials -> in_review
in_review -> review_completed
review_completed -> import_submitted
import_submitted -> archived
import_submitted -> import_failed
import_failed -> in_review
```

### 2.3 转移条件

1. `pending_review -> in_review`
   - 用户进入任务
2. `in_review -> waiting_materials`
   - 至少一个关键字段被标记为需补资料
3. `in_review -> review_completed`
   - 所有字段进入终态
   - 且不存在阻断入库项
4. `review_completed -> import_submitted`
   - 用户点击提交入库
5. `import_failed -> in_review`
   - 入库失败后人工重新处理

---

## 三、字段级状态机

### 3.1 状态定义

| 状态 | 含义 | 阻断入库 |
|---|---|---|
| `candidate_ready` | 系统候选已生成 | 是 |
| `review_required` | 需人工判断 | 是 |
| `accepted` | 人工接受系统值 | 否 |
| `modified` | 人工修改后接受 | 否 |
| `rejected` | 人工驳回 | 是 |
| `cannot_extract` | 资料中未提到或未能提取 | 视字段配置 |
| `cannot_extract_from_clause` | 条款不适用或条款无此项 | 否 |
| `waiting_materials` | 需补资料后再处理 | 是 |

### 3.2 终态定义

字段终态：
1. `accepted`
2. `modified`
3. `cannot_extract`
4. `cannot_extract_from_clause`
5. `rejected`

但其中：
1. `rejected`
2. `waiting_materials`
3. 某些 `cannot_extract`

仍可能阻断任务完成。

### 3.3 转移规则

```text
candidate_ready -> accepted
candidate_ready -> modified
candidate_ready -> rejected
candidate_ready -> cannot_extract
candidate_ready -> cannot_extract_from_clause
candidate_ready -> waiting_materials

review_required -> accepted
review_required -> modified
review_required -> rejected
review_required -> cannot_extract
review_required -> cannot_extract_from_clause
review_required -> waiting_materials

rejected -> review_required
waiting_materials -> review_required
accepted -> review_required
modified -> review_required
```

---

## 四、入库决策规则

### 4.1 允许提交入库

必须同时满足：

1. `task_status == review_completed`
2. 所有字段均已进入终态
3. 不存在 `rejected`
4. 不存在 `waiting_materials`
5. 不存在阻断型 `cannot_extract`

### 4.2 `cannot_extract` 的处理

V2 不应把所有 `cannot_extract` 一刀切。

建议字段配置里增加：

```json
{
  "coverage_name": "交费频率",
  "allow_null_import": false
}
```

若 `allow_null_import=false`，则该字段 `cannot_extract` 阻断入库。  
若 `allow_null_import=true`，则允许空值入库并记录原因。

---

## 五、依赖触发规则

### 5.1 重疾责任链

当 `重疾赔付次数` 改变时：
1. 重新检查 `重疾分组`
2. 重新检查 `重疾数量` 是否异常

### 5.2 投保年龄来源链

当 `投保年龄.final_value` 匹配 `^0-\d+周岁$` 且来源为费率表时：
1. 触发警告
2. 不自动改值
3. 要求复核员确认条款/说明书/核保文件

### 5.3 交费三联

当 `交费期间` 包含 `趸交` 时：
1. 检查 `交费频率`
2. 检查是否同时存在 `年交/月交`

---

## 六、前端状态管理要求

V2 前端不应再依赖 `localStorage` 作为主状态存储。

建议：
1. 页面初始化 `GET /review/tasks/{task_id}`
2. 每次字段裁决 `POST /review/items/{item_id}/decision`
3. 任务级动作 `POST /review/tasks/{task_id}/transition`

前端只保留：
1. 当前选中字段
2. 未提交表单草稿
3. 视图折叠状态

---

## 七、事件日志要求

状态机必须有事件流，不然无法追溯。

```json
{
  "event_id": "evt_001",
  "task_id": "task_20260326_001",
  "item_id": "cov_age",
  "event_type": "decision_submitted",
  "from_status": "review_required",
  "to_status": "modified",
  "operator": "ops_01",
  "comment": "依据说明书补齐28天"
}
```

---

## 八、V1 vs V2

| 维度 | V1 | V2 |
|---|---|---|
| 状态来源 | 前端临时状态 | 后端持久化状态机 |
| 入库判断 | 页面按钮启停 | 明确规则判断 |
| 依赖联动 | 无 | 状态变更触发 |
| 追溯能力 | 弱 | 事件级日志 |

---

## 九、实施顺序

1. 先冻结状态枚举
2. 再设计后端 transition API
3. 再让前端接状态机，不允许直接写 UI 状态

---

## 十、判断

V2 是否稳定，关键不在 UI，而在状态机是否完整。  
如果状态机没定清，页面再漂亮也无法支撑真实复核流。 
