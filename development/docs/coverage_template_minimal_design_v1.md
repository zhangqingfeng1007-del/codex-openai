# coverage_template 最小设计 V1

**版本：** V1.0  
**目标：** 在不新建 template 表的前提下，为人工复核任务提供“应审字段全集”，并支撑大规模字段分组、优先级排序和遗漏发现。

---

## 一、设计定位

当前复核页只看“已抽取候选”，无法发现从未被抽取的字段。  
`coverage_template` 在本项目中不是新建数据库对象，而是 **task 创建时由 `cmb_product_coverage` + `cmb_coverage` 动态生成的产品级字段全集快照**。

它解决两件事：
1. 给 review task 一个完整的应审字段集合
2. 给左栏分组、优先级、Tier A/Tier B、遗漏发现提供统一数据基础

---

## 二、数据来源

### 2.1 来源表

1. `cmb_product_coverage`
   - 定义某个 `product_id` 当前已入库的 coverage 集合
   - 可视为该产品的“预期字段全集”
2. `cmb_coverage`
   - 定义 coverage 目录树、层级、分类和排序
   - 用于构建一级/二级分组

### 2.2 查询结果即 template

对任意 `product_id` 执行：

```sql
SELECT
  pc.product_id,
  pc.coverage_id,
  c.name AS coverage_name,
  c.depth,
  c.parent_id,
  cp.name AS parent_name,
  pc.standard_content
FROM cmb_product_coverage pc
JOIN cmb_coverage c ON pc.coverage_id = c.id
LEFT JOIN cmb_coverage cp ON c.parent_id = cp.id
WHERE pc.product_id = :product_id
ORDER BY c.lft;
```

返回结果就是该产品在 task 创建时的 `coverage_template` 基础集。

---

## 三、template 输出结构

最小输出结构如下：

```json
{
  "coverage_id": "504414287641837568",
  "coverage_name": "重疾赔付次数",
  "depth": 2,
  "parent_name": "疾病责任",
  "standard_content": "2次",
  "is_tier_a": true,
  "review_priority": 3,
  "catalog_version": "v1.2"
}
```

建议扩展为任务内部使用结构：

```json
{
  "coverage_id": "504414287641837568",
  "coverage_name": "重疾赔付次数",
  "depth": 2,
  "parent_name": "疾病责任",
  "group_level_1": "疾病责任",
  "group_level_2": "重疾责任",
  "standard_content": "2次",
  "is_tier_a": true,
  "review_priority": 4,
  "risk_level": "high",
  "is_required": true,
  "catalog_version": "v1.2"
}
```

---

## 四、is_tier_a 定义

### 4.1 强制 Tier A

以下字段无论置信度如何，都必须逐项人工裁决：

1. 投核保规则字段
   - 投保年龄
   - 保险期间
   - 交费期间
   - 交费频率
   - 等待期
   - 宽限期
   - 犹豫期
2. 核心责任字段
   - 重疾赔付次数
   - 重疾分组
   - 重疾数量
   - 轻症赔付次数
   - 中症赔付次数
3. 数量类高风险字段
   - 特定重疾数量
   - 少儿重大疾病数量
4. 动态升级字段
   - `conflict=true`
   - `source_count=0`
   - `dependency_group` 成员
   - `manually_added`

### 4.2 可归入 Tier B 的字段

同时满足以下条件时，允许进入 Tier B 批量快速处理：

1. `confidence >= 0.90`
2. `conflict=false`
3. `source_count=1`
4. 不在任何 `dependency_group`
5. 属于说明性或权益类字段
   - 保单贷款
   - 减保
   - 减额交清
   - 转换权

结论：Tier A 由“业务风险”定义，不由“抽取难度”定义。

---

## 五、review_priority 分级

| priority | 适用字段 | 含义 |
|---|---|---|
| 1 | `conflict=true` | 多来源矛盾，最高优先 |
| 2 | `not_extracted` | 模板中存在但抽取层完全未产出 |
| 3 | `manually_added` | 复核员补录项，需重点审计 |
| 4 | Tier A 且 `dependency_group` 成员 | 核心联动字段 |
| 5 | `review_required` | 一般需复核字段 |
| 6 | `candidate_ready` | 高置信候选 |

默认左栏排序：
1. `review_priority`
2. `group_level_1`
3. `group_level_2`
4. `coverage_name`

---

## 六、两层分组方案

### 6.1 分组模型

```text
group_level_1（对应 cmb_coverage 一级目录）
└── group_level_2（对应业务二级组）
    └── items[]
```

### 6.2 一级分组建议

重疾险产品至少应支持以下一级分组：

1. 基础规则
   - 投保年龄、保险期间、交费期间、交费频率、等待期、宽限期、犹豫期
2. 疾病责任
   - 重疾、轻症、中症、特定重疾、恶性肿瘤多次
3. 身故全残责任
   - 身故、全残
4. 豁免责任
   - 被保险人豁免、投保人豁免
5. 责任免除
   - 疾病免责、身故免责、全残免责
6. 保单权益
   - 转换权、保单贷款、减保、减额交清
7. 产品基本信息
   - 合同名称、条款编码、报备年度等

### 6.3 动态分组

为了保证复核效率，左栏顶部还应生成动态分组：

1. 冲突字段
2. 未抽取字段
3. 缺失字段
4. 依赖字段
5. 补录字段

动态分组优先于静态目录展示。

---

## 七、Item 结构扩展

在现有 CoverageItem 上新增：

```json
{
  "coverage_id": "504414287641837568",
  "is_tier_a": true,
  "review_priority": 4,
  "risk_level": "high",
  "is_required": true,
  "is_conflict": false,
  "is_missing": false,
  "source_count": 1,
  "is_linked": true,
  "catalog_version": "v1.2"
}
```

字段说明：

1. `is_tier_a`
   - 决定是否允许批量操作
2. `review_priority`
   - 决定排序和默认聚焦
3. `risk_level`
   - 用于 UI 红黄绿标识
4. `is_required`
   - 标识是否必须审完才可入库
5. `is_conflict` / `is_missing`
   - 支撑动态分组
6. `source_count`
   - 反映来源复杂度
7. `is_linked`
   - 反映是否属于依赖组
8. `catalog_version`
   - 保留历史追溯

---

## 八、catalog_version 管理

### 8.1 作用

`catalog_version` 用于记录 review task 创建时所依据的 coverage 目录版本。

它解决：
1. 历史任务重放
2. 目录增量对比
3. 新字段引入后的追溯问题

### 8.2 管理规则

| 事件 | 版本变更 |
|---|---|
| 新增 coverage 项 | `MINOR +1` |
| 新增标准值 | `PATCH +1` |
| 目录重大重构 | `MAJOR +1` |

### 8.3 task 侧记录

review task 创建时必须记录：

```json
{
  "catalog_version_at_creation": "v1.2",
  "rule_version": "rule_v2.4"
}
```

后续若当前目录版本发生变化，页面可提示：
“自任务创建以来，coverage catalog 新增了 N 个字段”。

---

## 九、对当前前端模块的直接影响

### 9.1 左栏不能再只吃 `field_groups`

还需要：
1. `review_priority`
2. `is_tier_a`
3. `is_conflict`
4. `is_missing`
5. `is_linked`
6. `catalog_version`

### 9.2 左栏需要支持 50-100 项

因此必须提供：
1. 搜索
2. 多条件过滤
3. 按优先级排序
4. 批量操作
5. 动态分组置顶

### 9.3 coverage_template 是完整性机制入口

没有这层，复核员永远只能看到“抽到了的世界”。  
有了这层，才可能把 `not_extracted` 字段也纳入任务。

---

## 十、当前阶段的最小落地建议

不需要一次性做 96 个 coverage 的全量规则。先落这三件事：

1. task 创建时，从 `cmb_product_coverage` 查询产品字段全集
2. 给每个字段补 `is_tier_a / review_priority / catalog_version`
3. 将模板差集字段加入审核列表

这三步做完，人工复核工作台才从“候选列表页”升级为“完整性可审的产品工作台”。
