# 人工复核工作台 V2 — 产品级设计（Codex 版）

**版本：** V2.0-Codex  
**状态：** 设计稿  
**目的：** 替代 V1 单字段编辑器，按产品级任务组织复核工作

---

## 一、设计结论

V2 不应再以“单条 candidate”作为页面主对象，而应以 `ReviewTask(Product)` 作为主对象，以 `CoverageItem` 作为子对象。  
页面核心不是“编辑一条字段”，而是完成一次**产品级审单**：

1. 先看资料包是否完整
2. 再看字段分组和高风险项
3. 最后做字段级裁决

---

## 二、V2 的五区工作台

### 1. 顶部任务栏

职责：
1. 显示产品、任务、资料包、审核进度
2. 承载任务级动作

建议字段：

```json
{
  "task_id": "task_20260326_001",
  "product_id": "1010003851",
  "product_name": "招商信诺真惠保重大疾病保险（互联网专属）",
  "document_package_id": "pkg_1010003851_001",
  "task_status": "in_review",
  "review_progress": {
    "done": 7,
    "total": 11,
    "conflict_count": 2,
    "missing_count": 1
  }
}
```

任务级动作：
1. 暂存复核
2. 打回补资料
3. 标记已完成
4. 提交入库

### 2. 左栏：字段导航区

职责：
1. 提供整个产品的字段地图
2. 让复核员优先处理冲突和缺失

分组建议：
1. `priority_conflict`：冲突字段
2. `priority_missing`：缺失字段
3. `basic_fields`：基础规则字段
4. `ci_fields`：重疾责任链
5. `minor_fields`：少儿责任链
6. `rate_fields`：费率类字段

单行最小信息：
1. 字段名
2. 当前候选摘要
3. 当前审核状态
4. 来源数
5. 是否存在依赖警告

### 3. 中栏上半：多来源证据区

职责：
1. 同时呈现该字段在多来源中的候选值
2. 让复核员看到“为什么冲突”

每个来源卡片必须显示：
1. `source_type`
2. `source_file`
3. `source_page`
4. `source_raw_value`
5. `raw_value`
6. `normalized_value`
7. `confidence`
8. `extract_method`

### 4. 中栏下半：判定链路区

职责：
1. 呈现从来源选择到最终入库映射的全过程
2. 给业务解释，也给技术排障

建议链路：
1. 来源优先级评估
2. 规则/模型命中
3. 规范化步骤
4. 依赖联动检查
5. 最终入库映射

### 5. 右栏：人工裁决区

职责：
1. 形成单字段最终裁决
2. 记录人工修改与错因

最小动作：
1. `accept`
2. `modify`
3. `reject`
4. `cannot_extract`
5. `hold_for_materials`

---

## 三、产品级检查流程

V2 页面加载后，先做产品级检查，再进入字段复核。

### 3.1 检查项

1. 资料包完整性  
   是否有条款、说明书、费率、必要补充文件
2. 核心字段覆盖率  
   核心字段是否都有候选或明确缺失说明
3. 冲突风险  
   是否存在来源冲突或依赖冲突
4. 不可入库项  
   是否存在阻断字段

### 3.2 产品级决策

```json
{
  "task_gate": {
    "material_complete": true,
    "core_fields_ready": false,
    "blocking_items": ["投保年龄", "交费频率"],
    "suggested_action": "continue_review"
  }
}
```

---

## 四、多来源展示规则

### 4.1 来源优先级

默认优先级：

1. `clause`
2. `product_brochure`
3. `underwriting_rule`
4. `processed_rate`
5. `raw_rate`

### 4.2 重要例外

1. `投保年龄`
   - 费率表可提供 `0-X周岁`
   - 但不能提供 `出生满XX天`
   - 天数只能来自条款、说明书或核保文件

2. `交费频率`
   - 结果费率表不一定含月交/季交/半年交
   - 原始费率附注和说明书可能更关键

3. `重疾分组`
   - 不能脱离 `重疾赔付次数` 单独裁决

### 4.3 冲突展示

冲突不只显示“不同”，还要分型：

1. `value_conflict`
2. `annotation_missing`
3. `format_diff`
4. `dependency_conflict`

---

## 五、字段分组与依赖组

### 5.1 普通分组

```json
{
  "group_id": "basic_fields",
  "group_name": "基础规则字段",
  "item_ids": ["cov_age", "cov_term", "cov_pay_years", "cov_pay_freq", "cov_waiting"]
}
```

### 5.2 依赖组

V2 需要显式支持“联动审核组”：

```json
{
  "dependency_group_id": "ci_chain",
  "group_name": "重疾责任链",
  "members": [
    "重疾赔付次数",
    "重疾分组",
    "重疾数量"
  ],
  "rules": [
    "次数=1次 -> 分组通常为不涉及",
    "次数>1次 -> 分组应为不分组或N组"
  ]
}
```

---

## 六、任务接口契约

```json
{
  "task": {
    "task_id": "task_20260326_001",
    "product_id": "1010003851",
    "product_name": "招商信诺真惠保重大疾病保险（互联网专属）",
    "task_status": "in_review",
    "document_package_id": "pkg_1010003851_001",
    "review_progress": {
      "done": 7,
      "total": 11,
      "conflict_count": 2,
      "missing_count": 1
    }
  },
  "groups": [
    {
      "group_id": "priority_conflict",
      "group_name": "冲突字段",
      "items": ["cov_age", "cov_pay_freq"]
    },
    {
      "group_id": "basic_fields",
      "group_name": "基础规则字段",
      "items": ["cov_age", "cov_term", "cov_pay_years", "cov_pay_freq"]
    }
  ],
  "items": [
    {
      "item_id": "cov_age",
      "coverage_id": 1001,
      "coverage_name": "投保年龄",
      "item_status": "review_required",
      "final_value": "",
      "winning_source_type": "processed_rate",
      "source_candidates": [],
      "dependency_warnings": [
        "费率表仅给出0周岁，不含起保天数"
      ]
    }
  ]
}
```

---

## 七、V1 vs V2

| 维度 | V1 | V2 |
|---|---|---|
| 主对象 | 单字段 candidate | 产品级 ReviewTask |
| 信息结构 | 线性查看 | 分组 + 联动 + 风险优先 |
| 来源展示 | 当前字段单来源为主 | 多来源并排 |
| 裁决方式 | 单条编辑 | 产品级检查 + 字段级裁决 |

---

## 八、实施顺序

1. 先实现任务接口契约和 mock 数据结构
2. 再实现五区页面骨架
3. 再接入依赖组与冲突显示
4. 最后接实时裁决与入库动作

---

## 九、判断

V2 的关键不是把 V1 做得更精致，而是把“复核对象”从字段提升到产品。  
否则即使页面可用，仍无法支持真实业务审单。
