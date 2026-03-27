# 人工复核信息架构 V2（Codex 版）

**版本：** V2.0-Codex  
**定位：** 为产品级复核工作台定义清晰的信息层级和展示密度

---

## 一、信息层级

推荐层级不是简单的 `Task -> Item`，而是 5 层：

```text
ReviewTask
  -> ProductSnapshot
  -> DocumentPackage
  -> FieldGroup
  -> CoverageItem
  -> SourceCandidate
```

### 1. ReviewTask

任务级上下文和审核状态。

### 2. ProductSnapshot

当前产品的标准化快照，避免页面直接拼库表。

### 3. DocumentPackage

资料包与来源文件列表。

### 4. FieldGroup

字段分组和动态风险聚合。

### 5. CoverageItem / SourceCandidate

单标准项和其多来源候选。

---

## 二、各层字段定义

### 2.1 Task

```json
{
  "task_id": "task_20260326_001",
  "task_status": "in_review",
  "reviewer": "ops_01",
  "rule_version": "rule_v2",
  "model_version": "llm_v2",
  "created_at": "2026-03-26T10:00:00+08:00",
  "updated_at": "2026-03-26T10:15:00+08:00"
}
```

### 2.2 ProductSnapshot

```json
{
  "product_id": "1010003851",
  "product_name": "招商信诺真惠保重大疾病保险（互联网专属）",
  "company_name": "招商信诺",
  "aix_category_id": 6001
}
```

### 2.3 DocumentPackage

```json
{
  "document_package_id": "pkg_1010003851_001",
  "files": [
    {
      "document_id": "doc_clause_001",
      "source_type": "clause",
      "file_name": "条款.pdf",
      "is_required": true
    }
  ]
}
```

### 2.4 FieldGroup

```json
{
  "group_id": "priority_conflict",
  "group_name": "冲突字段",
  "group_status": "warning",
  "item_count": 2,
  "collapsed": false
}
```

### 2.5 CoverageItem

```json
{
  "item_id": "cov_age",
  "coverage_id": 1001,
  "coverage_name": "投保年龄",
  "item_status": "review_required",
  "raw_value": "",
  "normalized_value": "",
  "final_value": "",
  "winning_source_id": "src_rate_001",
  "conflict_type": "annotation_missing",
  "dependency_group_ids": ["age_source_chain"]
}
```

### 2.6 SourceCandidate

```json
{
  "source_id": "src_rate_001",
  "source_type": "processed_rate",
  "source_file": "结果费率表.xlsx",
  "source_page": null,
  "source_raw_value": "0-65周岁",
  "raw_value": "0-65周岁",
  "normalized_value": "0-65周岁",
  "confidence": 0.98,
  "extract_method": "processed_rate:distinct_age_range",
  "md_text": null,
  "block_id": null,
  "title_path": []
}
```

---

## 三、展示层级控制

### 3.1 清单层

清单只显示做决策需要的摘要：
1. 状态
2. 字段名
3. 当前最终值或候选值摘要
4. 冲突/缺失标记
5. 来源数

### 3.2 详情层

详情层显示：
1. 多来源证据卡片
2. 判定链路
3. 依赖警告
4. 裁决控件

### 3.3 默认展开规则

默认展开：
1. 冲突字段组
2. 缺失字段组
3. 当前选中字段

默认折叠：
1. 低风险已接受字段组
2. 长原文内容

---

## 四、来源类型与可信度

| source_type | 可信度 | 适用范围 | 限制 |
|---|---|---|---|
| `clause` | 高 | 条款责任、等待期、次数、分组 | 可能缺费率和天数细节 |
| `product_brochure` | 中高 | 产品说明、起保天数、销售定义 | 可能有营销化表述 |
| `underwriting_rule` | 中高 | 投保限制、年龄天数、核保规则 | 不一定每产品都有 |
| `processed_rate` | 高 | 费率结构、交费期间、保险期间编码 | 投保年龄天数不可靠 |
| `raw_rate` | 中 | 原始费率附注、月交/季交线索 | 解析质量波动大 |

设计要求：
1. 页面必须展示可信度来源，不只展示值
2. 系统不能把 `processed_rate` 的 `0-X周岁` 当作天数完整值

---

## 五、冲突分类

V2 应明确区分 4 类冲突：

1. `source_value_diff`
   - 多来源值完全不同
2. `format_diff`
   - 语义相同但格式不同
3. `annotation_missing`
   - 主范围一致，但缺附注，如缺 `28天`
4. `dependency_conflict`
   - 字段之间互相矛盾

这四类冲突在界面上应分开显示，因为处理动作不同。

---

## 六、依赖关系模型

### 6.1 重疾责任链

```json
{
  "dependency_group_id": "ci_chain",
  "members": ["重疾赔付次数", "重疾分组", "重疾数量"],
  "warnings": []
}
```

### 6.2 投保年龄来源链

```json
{
  "dependency_group_id": "age_source_chain",
  "members": ["投保年龄"],
  "warnings": [
    "当前年龄来自费率表，缺少起保天数来源"
  ]
}
```

### 6.3 交费三联

```json
{
  "dependency_group_id": "payment_chain",
  "members": ["交费期间", "交费频率", "保险期间"],
  "warnings": []
}
```

### 6.4 少儿责任链

```json
{
  "dependency_group_id": "minor_ci_chain",
  "members": ["少儿重大疾病", "少儿特定重大疾病", "特定疾病"],
  "warnings": []
}
```

---

## 七、页面密度原则

1. 清单层负责导航，不负责承载全部证据
2. 详情层负责解释，不负责展示整产品所有字段
3. 原文、md、block、raw、normalized、final 只能在当前字段详情中展开
4. 多来源证据默认最多显示 3 张卡片，超出折叠

---

## 八、V1 vs V2

| 维度 | V1 | V2 |
|---|---|---|
| 信息层级 | Task -> Candidate | Task -> Product -> Package -> Group -> Item -> Source |
| 冲突表达 | 弱 | 显式冲突分类 |
| 依赖关系 | 只在脑中处理 | 页面内建依赖组 |
| 展示密度 | 线性堆叠 | 清单摘要 + 详情展开 |

---

## 九、实施顺序

1. 先定义接口 JSON
2. 再定义前端 state shape
3. 再做清单层
4. 再接多来源证据层和依赖组

---

## 十、判断

V2 的关键价值不是“信息更多”，而是“信息分层更清楚”。  
否则复核员会看到很多内容，但仍然无法快速裁决。
