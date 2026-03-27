# review task 创建补缺机制 V1

**版本：** V1.0  
**目标：** 解决“未被抽取的字段不会进入审核页”的结构性问题，并补充原始文件查看、手动补录、coverage catalog 扩展机制。

---

## 一、核心问题

当前 task 创建流程是：

```text
抽取层输出 candidates
-> 直接打包为 field_groups
-> 发给复核员
```

问题在于：
1. 抽取层只会产出“命中的候选”
2. 未命中的字段不会进审核任务
3. 复核员看到的是一个被截断的视图

所以，**遗漏问题不是页面渲染问题，而是 task 创建层没有做模板差集。**

---

## 二、状态区分：not_extracted vs cannot_extract

这两个状态必须分开，否则复核员无法判断是“抽取层没跑到”，还是“资料里确实没有”。

| 状态 | 含义 | 产生来源 | 后续动作 |
|---|---|---|---|
| `cannot_extract` | 系统尝试提取，但所有来源都未命中 | 抽取层已有记录，无结果 | 复核员标注是否阻断入库 |
| `not_extracted` | 系统从未产出该字段 | task 创建时模板差集发现 | 复核员判断是否产品无此项、是否需补录、是否需补资料 |

处理建议：
1. `cannot_extract`
   - 更偏“抽取失败”
2. `not_extracted`
   - 更偏“完整性缺口”

---

## 三、manually_added 新状态

### 3.1 定义

`manually_added` 表示该字段不是系统抽取出来的，而是复核员通过原始文件浏览或人工输入主动补录进任务。

它必须和 `not_extracted` 区分：

1. `not_extracted`
   - 系统识别缺口，但还没有补录内容
2. `manually_added`
   - 已由人工完成补录，并绑定正式 `coverage_id`

### 3.2 状态流转

`not_extracted` 不是单一路径，它至少有四种后续处理：

```text
not_extracted -> manually_added -> accepted
                            └-> rejected

not_extracted -> cannot_extract_from_clause
not_extracted -> pending_materials
not_extracted -> review_required
```

说明：
1. `not_extracted -> manually_added`
   - 复核员确认抽取层漏提，并已从原始资料中补录
2. `not_extracted -> cannot_extract_from_clause`
   - 复核员确认该产品确实无此项，不应强行补值
3. `not_extracted -> pending_materials`
   - 当前资料不足，需补充说明书、核保文件等后再判断
4. `not_extracted -> review_required`
   - 系统未抽取，但复核员已人工找到来源，准备进入正常裁决

### 3.3 补录后的默认确认规则

默认规则应明确为：

1. 同一复核员完成补录后，状态先进入 `manually_added`
2. `manually_added` 不直接等于可入库
3. 默认要求一次再次确认后，才能转为 `accepted`

当前阶段建议的最小执行口径：

1. mock / 原型阶段允许“补录人自己再次确认”后转 `accepted`
2. 正式系统阶段应支持“他人复审”开关，由管理员按任务类型配置

这样可以兼顾当前开发效率和后续审计要求。

### 3.4 最小日志要求

补录必须留痕：

```json
{
  "operator": "ops_user_01",
  "operated_at": "2026-03-26T10:30:00",
  "source_evidence": {
    "file_name": "招商信诺真惠保-条款.pdf",
    "page": 33,
    "quoted_text": "本合同保障120种重大疾病"
  }
}
```

---

## 四、原始文件浏览设计

### 4.1 设计目标

复核员不能只看候选结果，还必须能直接打开原始文件。

这一步有两个用途：
1. 复核当前候选值是否真的来自原始资料
2. 主动发现遗漏项并触发补录

### 4.2 文件访问机制

| 场景 | 交互 | 技术要求 |
|---|---|---|
| 从字段来源打开 | 点击 Source 卡片“查看原始文件” | PDF 定位到 `source.page` |
| 主动浏览 | 左栏顶部“原始文件”入口 | 可选文件、自由翻页 |
| 从原始文件补录 | 浏览原始文件后点击“补录为字段” | 打开补录表单 |

### 4.3 PDF 视图方案

推荐优先级：

1. **方案 A：页面内嵌 PDF 视图**
   - 优点：复核与浏览同屏
   - 缺点：实现较重
2. **方案 B：新标签页打开**
   - 优点：简单、稳定
   - 缺点：上下文跳转感更强

当前最小落地建议：
1. V1 先走 **方案 B**
2. 只要求能定位页码
3. 后续再升级为内嵌 pdf.js

### 4.4 xlsx 视图方案

对 `processed_rate` / `raw_rate`：
1. 不直接下载给复核员编辑
2. 以只读表格视图展示
3. 支持行列搜索
4. 不支持在线修改

### 4.5 文件访问上下文

```json
{
  "file_viewer_context": {
    "file_name": "招商信诺真惠保-条款.pdf",
    "source_type": "clause",
    "target_page": 12,
    "highlight_block_id": "1010003851_p12_b51"
  }
}
```

---

## 五、手动补录流程

### 5.1 触发入口

提供两类入口：

1. 从原始文件视图补录
   - 浏览文件
   - 发现遗漏
   - 点击“补录为字段”
2. 从左栏空位补录
   - 在 `not_extracted` 或“未找到字段”区域点击“手动补录”

### 5.2 补录表单规格

```text
coverage_name（搜索 coverage catalog）
final_value
来源文件
来源页码
引用原文
备注
```

要求：
1. 必须绑定正式 `coverage_id`
2. 必须填写来源信息
3. 必须填写 `quoted_text` 或等价原文引用

### 5.3 coverage catalog 搜索器

搜索器必须支持：
1. 中文模糊搜索
2. 展示父级路径
3. 展示典型标准值示例
4. 搜索无结果时提供“申请新增 coverage 项”入口

### 5.4 补录后的 item 结构

```json
{
  "item_id": "item_manual_xxxxx",
  "coverage_id": "504414479724183552",
  "coverage_name": "重疾数量",
  "status": "manually_added",
  "is_tier_a": true,
  "review_priority": 3,
  "sources": [
    {
      "source_id": "src_manual_001",
      "source_type": "clause",
      "file_name": "招商信诺真惠保-条款.pdf",
      "page": 33,
      "block_id": null,
      "source_raw_value": "本合同保障120种重大疾病",
      "normalized_value": "120种",
      "confidence": 1.0,
      "extract_method": "manual",
      "conflict": false
    }
  ],
  "final_value": "120种",
  "manually_added_by": "ops_user_01",
  "manually_added_at": "2026-03-26T10:30:00"
}
```

---

## 六、coverage catalog 扩展机制

### 6.1 为什么必须支持新增 coverage

保险责任会变化，现有 96 项目录不是终局。  
如果 catalog 不能扩展，复核页最终会卡死在“有新责任但没地方落”。

### 6.2 新增 coverage 项流程

```text
复核员发现 catalog 中没有匹配项
-> 提交新增申请
-> 管理员审批
-> 写入 cmb_coverage 树
-> 分配 coverage_id
-> 更新 catalog_version
-> 复核员重新完成补录
```

### 6.3 新增标准值

标准值扩展采用非破坏式策略：
1. 已有值不改
2. 新值只增不删
3. 新值写入标准值目录表，带时间戳和版本记录

### 6.4 catalog_version 规则

| 事件 | 版本变更 |
|---|---|
| 新增 coverage 项 | `MINOR +1` |
| 新增标准值 | `PATCH +1` |
| 目录结构重构 | `MAJOR +1` |

review task 创建时必须记录：

```json
{
  "catalog_version_at_creation": "v1.2"
}
```

---

## 七、task 创建时的差集算法

### 7.1 目标

构建 review task 时，不只要打包抽取结果，还要把“模板存在但未抽到”的字段补进来。

### 7.2 算法步骤

1. 查询 `cmb_product_coverage`
   - 得到该产品预期字段全集
2. 读取抽取层候选
   - 得到已命中字段集
3. 做差集
   - `template - extracted = not_extracted`
4. 合并成统一 `items`
5. 再做分组、优先级、动态分组构建

### 7.3 伪代码

```python
def build_review_task(product_id, extracted_candidates, catalog_version):
    template_fields = query_product_template(product_id)
    # 优先使用 coverage_id 对齐，避免“其他责任槽位”类同名字段碰撞
    extracted_index = {}
    for candidate in extracted_candidates:
        key = candidate.get("coverage_id") or candidate.get("coverage_name")
        extracted_index[key] = candidate

    items = []
    for tf in template_fields:
        template_key = tf["coverage_id"]
        fallback_key = tf["coverage_name"]
        candidate = extracted_index.get(template_key) or extracted_index.get(fallback_key)

        if candidate:
            item = build_item_from_candidate(candidate, tf)
        else:
            item = {
                "item_id": f"item_{tf['coverage_id']}_gap",
                "coverage_id": tf["coverage_id"],
                "coverage_name": tf["coverage_name"],
                "status": "not_extracted",
                "review_priority": 2,
                "sources": [],
                "candidate_summary": "—",
                "final_value": "",
                "gap_reason": "not_in_extraction_pipeline"
            }
        items.append(item)

    return {
        "items": items,
        "catalog_version_at_creation": catalog_version,
        "field_groups": build_field_groups(items)
    }
```

### 7.4 为什么不能只用 coverage_name 做 key

当前目录里存在扩展槽位字段，例如：
1. 疾病其他责任1_保障说明
2. 疾病其他责任2_保障说明
3. 疾病其他责任3_保障说明

这类字段在人类视角上很像“同类字段”，但在系统里是不同的 `coverage_id`。  
如果 task 创建阶段只按 `coverage_name` 做 index，会发生覆盖和误匹配。

因此规则必须是：
1. **优先按 `coverage_id` 对齐**
2. 只有候选结果暂时缺失 `coverage_id` 时，才退回 `coverage_name` 兜底

### 7.5 结果

这样 review task 中会同时出现三类字段：
1. `已抽取字段`
2. `cannot_extract`
3. `not_extracted`

复核员第一次真正看到的是“应审字段全集”，而不是抽取层的残缺结果。

---

## 八、左栏过滤、排序、搜索

### 8.1 过滤器

必须支持多选过滤：
1. 状态
   - 待复核
   - 冲突
   - 未抽取
   - 缺失
   - 已接受
   - 已修改
   - 已驳回
   - 补录
2. 分类
   - Tier A
   - Tier B
3. 来源
   - clause-only
   - 多来源
   - 无来源
4. 依赖关系
   - 在依赖组中
   - 不在依赖组中

### 8.2 排序

默认按：
1. `review_priority`
2. `coverage_name`

### 8.3 搜索

搜索范围至少包括：
1. 字段名
2. 候选值
3. 来源文件名

---

## 九、批量操作边界

允许批量的字段必须同时满足：
1. `is_tier_a=false`
2. `conflict=false`
3. `is_linked=false`
4. `source_count=1`
5. `confidence>=0.90`

允许操作：
1. 批量接受
2. 批量标记 `pending_materials`

禁止批量：
1. Tier A
2. 冲突字段
3. dependency_group 成员
4. manually_added

---

## 十、最小落地建议

当前项目边界下，最可落地的顺序是：

1. 先把 `not_extracted` 差集机制做进 task 创建层
2. 再做 `manually_added` 状态和补录表单
3. 再加“查看原始文件”入口
4. 最后再做 coverage catalog 新增申请流程

原因：
1. 差集机制不做，复核页天然看不见遗漏
2. 补录入口不做，复核员发现遗漏后无处落
3. 原始文件入口不做，复核员很难自己验证遗漏
4. catalog 扩展流程属于治理层，重要但可晚一拍

结论：
**review task 创建补缺机制是人工复核工作台从“候选审阅页”升级为“完整性审阅页”的关键。**
