# 人工复核页面字段清单与接口 JSON V1

生成时间：2026-03-25

## 一、模块定位

人工复核页按独立模块建设。

模块职责：

1. 读取智能拆解候选结果
2. 展示来源、证据、判定链路
3. 支持人工接受、修改、驳回
4. 输出标准入库前的最终确认结果

不负责：

1. 直接写正式库
2. 执行拆解规则
3. 修改标准项定义

## 二、页面字段清单

### 2.1 任务级字段

1. `task_id`
2. `product_id`
3. `product_name`
4. `document_package_id`
5. `task_status`
6. `rule_version`
7. `model_version`
8. `created_at`
9. `updated_at`

### 2.2 候选字段级字段

1. `candidate_id`
2. `coverage_id`
3. `coverage_name`
4. `raw_value`
5. `normalized_value`
6. `final_value`
7. `confidence`
8. `status`
9. `extract_method`
10. `reason_code`
11. `review_comment`

### 2.3 来源字段

1. `source_type`
   - `clause`
   - `raw_rate`
   - `processed_rate`
   - `product_brochure`
   - `uw_rule`
   - `multi_source`
2. `source_file`
3. `source_document_id`
4. `source_page`
5. `source_raw_value`

### 2.4 判定链路字段

1. `md_text`
2. `block_id`
3. `block_type`
4. `title_path`
5. `logic_trace`
6. `normalization_trace`
7. `priority_trace`

### 2.5 审核动作字段

1. `action`
   - `accept`
   - `modify`
   - `reject`
   - `hold`
2. `reviewer`
3. `review_time`
4. `review_comment`
5. `reason_code`

## 三、候选结果查询接口

### 3.1 `GET /api/v1/review/tasks/{task_id}`

作用：

1. 加载单个拆解任务
2. 返回页面展示所需全部信息

返回 JSON：

```json
{
  "task_id": "task_20260325_001",
  "product_id": "1010003851",
  "product_name": "招商信诺真惠保重大疾病保险（互联网专属）",
  "document_package_id": "pkg_1010003851_001",
  "task_status": "review_required",
  "rule_version": "rule_v1",
  "model_version": "llm_v1",
  "created_at": "2026-03-25T10:00:00+08:00",
  "updated_at": "2026-03-25T10:30:00+08:00",
  "items": [
    {
      "candidate_id": "cand_001",
      "coverage_id": 1001,
      "coverage_name": "投保年龄",
      "raw_value": "0-65周岁",
      "normalized_value": "0-65周岁",
      "final_value": "",
      "confidence": 0.98,
      "status": "review_required",
      "extract_method": "processed_rate:distinct_age_range",
      "source": {
        "source_type": "processed_rate",
        "source_file": "700-1-招商信诺真惠保重大疾病保险（互联网专属）-费率解析结果表.xlsx",
        "source_document_id": "doc_rate_700_1",
        "source_page": null,
        "source_raw_value": "0-65周岁"
      },
      "evidence": {
        "md_text": "投保年龄列最小=0，最大=65",
        "block_id": null,
        "block_type": null,
        "title_path": []
      },
      "logic_trace": {
        "priority_trace": [
          "processed_rate 命中",
          "条款未提供可用婴儿起保天数",
          "进入人工复核"
        ],
        "normalization_trace": [
          "年龄列去重",
          "生成区间 0-65周岁"
        ]
      }
    }
  ]
}
```

## 四、来源文件预览接口

### 4.1 `GET /api/v1/review/source`

请求参数：

1. `document_id`
2. `page`
3. `block_id` 可选

作用：

1. 页面左栏预览原始文件定位
2. 支持原文证据查看

返回 JSON：

```json
{
  "document_id": "doc_clause_700",
  "document_type": "clause_pdf",
  "file_name": "700-招商信诺真惠保重大疾病保险（互联网专属）-条款.pdf",
  "page": 3,
  "block_id": "1010003851_p3_b69",
  "raw_text": "首次重大疾病保险金最多给付一次。",
  "md_text": "首次重大疾病保险金最多给付一次。",
  "title_path": ["第一部分", "特别条款", "重大疾病保险金"]
}
```

## 五、提交复核结果接口

### 5.1 `POST /api/v1/review/submit`

作用：

1. 提交单条或多条人工复核结果
2. 只写入复核模块自己的结果表
3. 不直接写正式库

请求 JSON：

```json
{
  "task_id": "task_20260325_001",
  "reviewer": "user_001",
  "items": [
    {
      "candidate_id": "cand_001",
      "action": "modify",
      "final_value": "0（28天）-65周岁",
      "reason_code": "source_missing_need_manual_fix",
      "review_comment": "依据产品说明书补齐婴儿起保天数"
    },
    {
      "candidate_id": "cand_002",
      "action": "accept",
      "final_value": "2次",
      "reason_code": "",
      "review_comment": "与条款原文一致"
    }
  ]
}
```

返回 JSON：

```json
{
  "task_id": "task_20260325_001",
  "submitted_count": 2,
  "task_status": "review_completed"
}
```

## 六、查询复核结果接口

### 6.1 `GET /api/v1/review/results/{task_id}`

作用：

1. 返回人工裁决后的最终候选结果
2. 供统一入库模块读取

返回 JSON：

```json
{
  "task_id": "task_20260325_001",
  "product_id": "1010003851",
  "task_status": "review_completed",
  "items": [
    {
      "candidate_id": "cand_001",
      "coverage_id": 1001,
      "coverage_name": "投保年龄",
      "raw_value": "0-65周岁",
      "normalized_value": "0-65周岁",
      "final_value": "0（28天）-65周岁",
      "action": "modify",
      "reason_code": "source_missing_need_manual_fix",
      "review_comment": "依据产品说明书补齐婴儿起保天数",
      "reviewer": "user_001",
      "review_time": "2026-03-25T11:00:00+08:00"
    }
  ]
}
```

## 七、错因编码建议

建议统一维护 `reason_code`：

1. `source_file_wrong`
2. `source_missing_need_manual_fix`
3. `md_parse_wrong`
4. `block_split_wrong`
5. `rule_extract_wrong`
6. `llm_mapping_wrong`
7. `normalization_wrong`
8. `multi_source_priority_wrong`
9. `coverage_schema_missing`
10. `cannot_determine`

## 八、前端展示最小清单

V1 页面最小展示字段：

1. `coverage_name`
2. `raw_value`
3. `normalized_value`
4. `final_value`
5. `status`
6. `confidence`
7. `source_type`
8. `source_file`
9. `source_raw_value`
10. `md_text`
11. `block_id`
12. `logic_trace`
13. `action`
14. `reason_code`
15. `review_comment`

## 九、与总系统的接口边界

人工复核模块对总系统只输出两类结果：

1. 复核后的最终候选结果
2. 审核日志与错因记录

总系统不应直接依赖：

1. 页面内部状态
2. 前端组件结构
3. 临时展示字段

这样可保证人工复核页先独立开发，后续再平滑接入总系统。
