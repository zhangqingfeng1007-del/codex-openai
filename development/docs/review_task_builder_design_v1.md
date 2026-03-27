# review_task_builder 设计 V1

**版本：** V1.0  
**目标：** 生成可直接供人工复核前端加载的 `ReviewTask` JSON，解决“只看已抽取候选”的问题，把产品预期 coverage 全集、抽取结果、动态分组和统计信息统一建模。

---

## 一、输入规格

```python
product_id: str                     # DB product_id，例如 "1010003851"
extracted_candidates: list[dict]    # 当前本地实际来自 blind_test_results_v1.json 的 items
document_package_info: dict         # 资料包文件清单 files[]
catalog_version: str                # 默认 "v1.2"
task_id: str                        # 可选，不传则自动生成
```

### 当前本地执行口径

指令文档里把抽取层输入写成 `tier_a_rule_candidates_v2.json`。  
但当前本地可直接用于 `1010003851` 的实际输入是：

1. `development/data/blind_test_v1/blind_test_results_v1.json`
2. `development/data/manifests/full_coverage_dump.json`
3. `development/data/manifests/coverage_whitelist_v1.json`

原因：
1. `tier_a_rule_candidates_v2.json` 中没有 `1010003851`
2. `blind_test_results_v1.json` 已包含该产品的候选、来源文件和状态

脚本会按本地真实输入落地，并在后续可平滑替换为统一抽取层输出。

---

## 二、核心处理步骤

### Step A：加载 coverage template

从 `full_coverage_dump.json` 过滤：

```python
row["product_id"] == target_product_id
```

得到 `template_fields[]`：

```json
{
  "coverage_id": "504414287641837568",
  "coverage_name": "重疾赔付次数",
  "standard_content": "2次"
}
```

然后再补：
1. `is_tier_a`
2. `default_review_mode`
3. `group_level_1`
4. `group_level_2`
5. `group_type`

来源：
1. `coverage_whitelist_v1.json`
2. 本地分组映射规则

### Step B：构建 extracted index

当前抽取结果是按 `coverage_name` 输出，尚未带 `coverage_id`。  
因此当前版本采用：

```python
extracted_index = {
  coverage_name: [candidate1, candidate2, ...]
}
```

如果未来抽取层补出 `coverage_id`，应切换为：
1. `coverage_id` 主索引
2. `coverage_name` 仅兜底

### Step C：计算每个 template field 的状态

规则：

```python
if coverage_name in extracted_index:
    if candidate_count > 1 and normalized_values_differ:
        status = "review_required"
        conflict = True
    elif winning_candidate.confidence >= 0.90:
        status = "candidate_ready"
    else:
        status = "review_required"
else:
    status = "not_extracted"
```

说明：
1. `candidate_ready` 不代表最终可入库，只表示机器候选质量较高
2. `not_extracted` 是 task 创建层补出的完整性状态

### Step D：分配 review_priority

```python
conflict=true                     -> priority=1
status == "not_extracted"        -> priority=2
status == "manually_added"       -> priority=3
is_tier_a and is_linked          -> priority=4
status == "review_required"      -> priority=5
status == "candidate_ready"      -> priority=6
```

### Step E：构建 field_groups

静态分组：
1. `items[]` 真正承载字段对象

动态分组：
1. `dynamic_not_extracted`
2. `dynamic_missing`

动态分组只保存：

```json
{
  "group_type": "dynamic_not_extracted",
  "group_name": "未抽取字段",
  "is_dynamic": true,
  "item_ids": ["item_xxx", "item_yyy"]
}
```

不复制 item 对象。

### Step F：计算统计字段

```python
total_items = len(all_static_items)
conflict_count = sum(1 for i in items if i["source_count"] > 1 and any(s["conflict"] for s in i["sources"]))
missing_count = sum(1 for i in items if i["status"] == "cannot_extract")
not_extracted_count = sum(1 for i in items if i["status"] == "not_extracted")
pending_review_count = sum(1 for i in items if i["status"] in {"review_required", "candidate_ready"})
```

---

## 三、分组映射表

| coverage_name 关键词 | group_level_1 | group_level_2 | group_type |
|---|---|---|---|
| 投保年龄、保险期间、交费期间、交费频率、等待期、宽限期、犹豫期、保费要求、保额要求 | 基础规则 | — | tier_basic |
| 重疾赔付次数、重疾分组、重疾数量、重疾保障说明、重疾赔付时间间隔 | 疾病责任 | 重疾责任 | tier_ci |
| 特定重疾、恶性肿瘤 | 疾病责任 | 特定/高发重疾 | tier_ci_extra |
| 轻症 | 疾病责任 | 轻症责任 | tier_minor_ci |
| 中症 | 疾病责任 | 中症责任 | tier_mid_ci |
| 身故 | 身故全残责任 | 身故责任 | tier_death |
| 全残 | 身故全残责任 | 全残责任 | tier_disability |
| 豁免、投保人 | 豁免责任 | — | tier_waiver |
| 疾病免责、疾病具体免责 | 责任免除 | — | tier_exemption |
| 转换权、保单贷款、减保、减额交清 | 保单权益 | — | tier_rights |
| 合同名称、生效时间、报备年度、条款编码、长短险、指定第二投保人 | 产品基本信息 | — | tier_info |
| 其他/未匹配 | 其他 | — | tier_other |

这套映射是 builder 层的最小规则，不要求一步覆盖所有险种，只要先支撑重疾险 task 构建。

---

## 四、关键设计决策

### 1. coverage_id 是 template 主键

template 字段集合来自 `full_coverage_dump.json`，天然带 `coverage_id`。  
因此 builder 内部主键应以 `coverage_id` 为准。

但当前抽取层只输出 `coverage_name`，所以暂时采用：
1. template 侧：`coverage_id` 主键
2. candidate 侧：按 `coverage_name` 映射

后续抽取层一旦补 `coverage_id`，即可切换到纯 ID 对齐。

### 2. 动态分组必须是引用式

原因：
1. 避免重复存储
2. 避免进度和统计重复计数
3. 前端不再需要 dedup

### 3. DB 不可用时降级

当前 DB 无法直连时，优先级如下：
1. `full_coverage_dump.json`
2. 本地 document package 信息
3. blind test 抽取结果

不阻塞 builder 执行。

### 4. 多来源合并

当前 `blind_test_results_v1.json` 基本是一字段一来源。  
但 builder 设计必须支持：
1. 同一 `coverage_name` 多条来源候选
2. `sources[]` 全保留
3. `conflict=true` 在值不一致时触发

---

## 五、输出结构与前端兼容性

输出目标是：

```text
development/data/review_tasks/{product_id}_review_task_v2.json
```

要求：
1. 可直接被 `review-module/app.js -> loadTask()` 加载
2. 顶层结构兼容现有 V2 mock
3. 动态分组采用 `item_ids`
4. 静态分组 item 数必须和 `total_items` 一致

---

## 六、与当前本地数据的差异说明

指令验收写的是“应 ≥ 30 项”。  
但当前本地 `full_coverage_dump.json` 中，`1010003851` 实际只有 **28 条** coverage 记录。

这意味着当前可执行脚本的正确验收口径应改为：
1. 输出应覆盖 `full_coverage_dump.json` 中该产品的全部 28 项
2. `total_items == 28`

如果后续拿到更新的 dump 或 DB 白名单恢复，再按 30+ 的正式口径验收。

---

## 七、最小落地结论

Step 1 的 builder 不追求一次做成完整服务，只要满足：
1. 本地输入可运行
2. 输出是真正的 V2 `ReviewTask`
3. 能把 template 差集补进 task
4. 前端可直接加载

这样就能把人工复核模块从 mock 驱动推进到真实任务驱动。
