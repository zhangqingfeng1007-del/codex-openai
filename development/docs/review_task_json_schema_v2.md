# review_task JSON Schema V2

**版本：** V2.0  
**风格：** TypeScript interface  
**用途：** 作为 review task builder、前端复核工作台、后端任务接口之间的统一契约。

---

## 一、顶层结构

```ts
interface ReviewTask {
  task: TaskMeta;
  catalog_version_at_creation: string;
  product: ProductMeta;
  document_package: DocumentPackage;
  field_groups: FieldGroup[];
  dependency_groups: DependencyGroup[];
  conflict_count: number;
  missing_count: number;
  not_extracted_count: number;
  pending_review_count: number;
  total_items: number;
}
```

---

## 二、基础对象

```ts
interface TaskMeta {
  task_id: string;
  task_status: TaskStatus;
  rule_version: string;
}

interface ProductMeta {
  product_id: string;
  product_name: string;
  company_name: string;
  aix_category_id: number | string;
}

interface DocumentPackage {
  document_package_id: string;
  files: DocumentFile[];
}

interface DocumentFile {
  source_type: SourceType;
  file_name: string;
  parse_quality: string;
  local_path?: string | null;
}
```

---

## 三、FieldGroup

### 1. 静态分组

```ts
interface StaticFieldGroup {
  group_type: string;
  group_name: string;
  items: CoverageItem[];
  is_dynamic?: false;
}
```

### 2. 动态分组

```ts
interface DynamicFieldGroup {
  group_type: "dynamic_not_extracted" | "dynamic_missing";
  group_name: string;
  is_dynamic: true;
  item_ids: string[];
}
```

### 3. 联合类型

```ts
type FieldGroup = StaticFieldGroup | DynamicFieldGroup;
```

---

## 四、CoverageItem

```ts
interface CoverageItem {
  item_id: string;
  coverage_id: string;
  coverage_name: string;
  status: CoverageItemStatus;
  candidate_summary: string;
  final_value: string;
  is_tier_a: boolean;
  review_priority: number;
  group_level_1: string;
  group_level_2: string;
  group_type: string;
  risk_level: "high" | "medium" | "low";
  is_required: boolean;
  is_linked: boolean;
  source_count: number;
  catalog_version: string;
  sources: Source[];
  logic_trace: LogicTrace;
  manually_added_by?: string;
  manually_added_at?: string;
}
```

字段说明：
1. `coverage_id`
   - 正式目录项 ID
2. `candidate_summary`
   - 左栏摘要展示
3. `final_value`
   - 最终裁决值
4. `is_tier_a`
   - 是否强制逐项复核
5. `review_priority`
   - 默认排序权重
6. `group_level_1/group_level_2/group_type`
   - 左栏导航与动态分组支持
7. `risk_level`
   - 供前端做风险色标
8. `is_required`
   - 是否影响最终入库
9. `is_linked`
   - 是否属于 dependency group
10. `source_count`
   - 来源数量
11. `catalog_version`
   - task 创建时所用目录版本

---

## 五、Source

```ts
interface Source {
  source_id: string;
  source_type: SourceType;
  file_name: string;
  page: number | null;
  block_id: string | null;
  title_path: string[];
  source_raw_value: string;
  md_text: string;
  block_text: string;
  raw_value: string;
  normalized_value: string;
  confidence: number;
  extract_method: string;
  conflict: boolean;
}
```

---

## 六、LogicTrace

```ts
interface LogicTrace {
  priority_trace: string[];
  normalization_trace: string[];
  mapping_trace: string[];
}
```

---

## 七、DependencyGroup

```ts
interface DependencyGroup {
  dependency_group_id: string;
  group_name: string;
  members: string[];
  rules: string[];
}
```

---

## 八、状态枚举

### 1. TaskStatus

```ts
type TaskStatus =
  | "pending_review"
  | "in_review"
  | "review_completed"
  | "returned_for_materials"
  | "import_submitted"
  | "import_failed"
  | "archived";
```

### 2. CoverageItemStatus

```ts
type CoverageItemStatus =
  | "review_required"
  | "candidate_ready"
  | "accepted"
  | "modified"
  | "rejected"
  | "cannot_extract"
  | "cannot_extract_from_clause"
  | "pending_materials"
  | "not_extracted"
  | "manually_added";
```

> 当前字段状态共 **10 个**。  
> 如果按你们前面文档里的“9 个状态”口径执行，则应把 `manually_added` 视为 `accepted` 前的中间操作状态，不单列为常规状态。当前 schema 采用更完整的显式建模。

状态含义：
1. `review_required`
   - 有候选，需要人工复核
2. `candidate_ready`
   - 高置信候选，仍需人工确认
3. `accepted`
   - 人工接受
4. `modified`
   - 人工修改后接受
5. `rejected`
   - 人工驳回
6. `cannot_extract`
   - 尝试提取但无结果
7. `cannot_extract_from_clause`
   - 业务上确实不适用
8. `pending_materials`
   - 需要补资料
9. `not_extracted`
   - 模板中存在，但抽取层未产出
10. `manually_added`
   - 复核员补录项

---

## 九、SourceType 枚举

```ts
type SourceType =
  | "clause"
  | "product_brochure"
  | "processed_rate"
  | "raw_rate"
  | "underwriting_rule"
  | "manual";
```

---

## 十、统计字段规则

```ts
total_items: number;
conflict_count: number;
missing_count: number;
not_extracted_count: number;
pending_review_count: number;
```

计算规则：

1. `total_items`
   - 静态分组所有 `items` 之和
   - 不包含动态分组重复引用

2. `conflict_count`
   - `source_count > 1`
   - 且 `sources` 中至少一个 `conflict=true`

3. `missing_count`
   - `status == "cannot_extract"` 的 item 数量

4. `not_extracted_count`
   - `status == "not_extracted"` 的 item 数量

5. `pending_review_count`
   - `status in {"review_required", "candidate_ready"}` 的 item 数量

---

## 十一、一个最小示例

```ts
const example: ReviewTask = {
  task: {
    task_id: "task_20260326_001",
    task_status: "in_review",
    rule_version: "rule_v2.4"
  },
  catalog_version_at_creation: "v1.2",
  product: {
    product_id: "1010003851",
    product_name: "招商信诺真惠保重大疾病保险（互联网专属）",
    company_name: "招商信诺",
    aix_category_id: 6001
  },
  document_package: {
    document_package_id: "pkg_1010003851_001",
    files: []
  },
  field_groups: [],
  dependency_groups: [],
  conflict_count: 0,
  missing_count: 0,
  not_extracted_count: 0,
  pending_review_count: 0,
  total_items: 0
};
```

---

## 十二、与前端的直接契约要求

前端最关键的依赖点：
1. `field_groups` 必须同时支持静态与动态两种结构
2. `CoverageItem` 必须始终带 `coverage_id`
3. `sources[]` 可以为空
4. 动态分组只引用 `item_ids`
5. `total_items` 必须与静态分组 item 数完全一致

否则：
1. 进度会错
2. 动态分组会重复计数
3. 前端会误判是否可提交入库
