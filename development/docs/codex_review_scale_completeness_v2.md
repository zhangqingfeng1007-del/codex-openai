# Codex 执行指令：字段规模 + 完整性机制 V2（含补录与扩展设计）

**版本：** V2（含用户 4 条修改意见）
**触发背景：**
- V2 mock 只有 7 个字段；真实产品 1010003851 在 DB 中有 37 条 coverage 记录
- 复核员无法发现"从未被抽取过的字段"——完整性存在结构性盲区
- 用户补充 4 条修改意见（见下文）

本轮输出两份设计文档，不写代码，只输出文档。

---

## 用户 4 条修改意见（必须体现在文档中）

### 意见 1：审查页可直接打开原始文件
复核员在审查页内（或在新窗口）可直接打开原始文件（PDF/xlsx）。
目的：通过自主浏览原始文档，主动发现抽取层遗漏的字段。
要求：
- 对 clause/product_brochure：支持 PDF 页面内嵌或新标签打开，默认跳转到引用该字段的页码（source.page）
- 对 processed_rate：支持以表格形式展示 xlsx 内容
- 每个字段的来源区（Source 卡片）有"查看原始文件"按钮，直接定位到对应页码/行

### 意见 2：发现遗漏后可手动补录
复核员在浏览原始文件时若发现遗漏项，可在页面内直接补录，包括：
- 补录内容：final_value（结果）、来源文件名+页码+引用原文、描述/备注
- 补录映射：从 coverage_catalog（下文定义）中选择匹配的字段 ID，确保补录项绑定到正式覆盖项目录
- 补录项的 item 状态：`manually_added`（新状态，见状态机扩展）
- 补录操作需记录操作日志（operator, operated_at, source_evidence）

### 意见 3：提供完整的 coverage catalog（阿里云全库结构）
设计中必须包含 ensure_recognize 库中 重疾险（aix_category_id=6001）产品的全量覆盖项目录，供：
- 复核员补录时查找匹配项（搜索 + 树形选择）
- task 创建时做模板差集（预期字段集 - 已提取字段集 = 待补充字段集）
- 支持标准值参考（帮助复核员选择 final_value）

**完整 coverage catalog（96 项，来自 ensure_recognize.cmb_product_coverage）：**

**基础规则类：**
| coverage_id | coverage_name | 典型标准值示例 |
|---|---|---|
| 504404104932884480 | 投保年龄 | 0-55周岁 / 0（28天）-55周岁 / 28天-55周岁 |
| 504404079033057280 | 保险期间 | 终身 / 10/15/20年 / 至60/70/80周岁 |
| 504404053238087680 | 交费期间 | 趸交 / 趸交，5/10/15/20/30年交 |
| 504404025597624320 | 交费频率 | 年交 / 年交，月交 / 趸交，年交，月交 |
| 504403966302748672 | 等待期 | 非意外180天，意外0天 / 非意外90天，意外0天 |
| 504588812006326272 | 等待期（简化） | 180天 / 90天 |
| 504403696281845760 | 宽限期 | 60天 / 30天 |
| 504403997487398912 | 犹豫期 | 15天 / 10天 |
| 504403883226169344 | 保费要求 | — |
| 504403843099262976 | 保额要求 | — |

**产品基本信息类：**
| coverage_id | coverage_name | 备注 |
|---|---|---|
| 504398548524466176 | 合同名称（条款名称） | 条款全称 |
| 522812374571679744 | 生效时间 | 产品生效日期 |
| 504400764916334592 | 报备年度 | 2021年 / 2023年 |
| 504400827860254720 | 条款编码 | — |
| 504399213468450816 | 长短险 | 长险 / 短险 |
| 615861059366289408 | 指定第二投保人 | — |
| 504404186914750464 | 停售是否可以续保 | 支持 / 不支持 |
| 504404276903542784 | 是否保证续保 | 是 / 否 |
| 504404249137250304 | 保证续保期限 | — |
| 504404213464694784 | 最大续保年龄 | — |
| 504762556708421632 | 产品说明 | — |
| 504400209506598912 | 标签 | — |

**重疾责任类：**
| coverage_id | coverage_name | 典型标准值示例 |
|---|---|---|
| 504414287641837568 | 重疾赔付次数 | 1次 / 2次 / 3次 / 5次 |
| 504414357279866880 | 重疾分组 | 不涉及 / 不分组 / 3组 / 5组 |
| 504414479724183552 | 重疾数量 | 100种 / 120种 / 150种 |
| 504414417531043840 | 重疾保障说明 | 等待期内重疾，退还已交保费；意外或等待期后重疾，给付基本保额 |
| 504414245455527936 | 重疾赔付时间间隔 | 1年 / 3年 |
| 504414538465411072 | 特定重疾保障说明 | — |
| 504414566722437120 | 特定重疾数量 | 3种 / 5种 / 12种 |
| 504414607226830848 | 恶性肿瘤多次给付保障说明 | — |
| 504414668425920512 | 恶性肿瘤多次给付次数 | 2次 / 3次 |
| 504414638398898176 | 恶性肿瘤多次给付间隔期 | 1年 / 3年 |
| 504414697978986496 | 恶性肿瘤状态 | — |
| 504414729142665216 | 恶性肿瘤具体病种 | — |

**轻症/中症责任类：**
| coverage_id | coverage_name | 典型标准值示例 |
|---|---|---|
| 504415315875463168 | 轻症赔付次数 | 1次 / 3次 / 6次 |
| 504415344233152512 | 轻症分组 | 不分组 / 不涉及 |
| 504415419973894144 | 轻症数量 | 50种 / 60种 |
| 504415370573381632 | 轻症保障说明 | — |
| 504415276587417600 | 轻症赔付时间间隔 | 1年 |
| 504415072798769152 | 中症赔付次数 | 1次 / 3次 |
| 504415100573450240 | 中症分组 | 不分组 |
| 504415162380713984 | 中症数量 | 10种 / 20种 |
| 504415131632271360 | 中症保障说明 | — |
| 504415041484095488 | 中症赔付时间间隔 | 1年 |

**豁免责任类：**
| coverage_id | coverage_name | 备注 |
|---|---|---|
| 504742441774350336 | 被保险人轻症豁免 | — |
| 504742512788111360 | 被保险人中症豁免 | — |
| 504742548670382080 | 被保险人重疾豁免 | — |
| 504740869933760512 | 投保人全残豁免 | — |
| 504740905061056512 | 投保人身故豁免 | — |
| 504742953533964288 | 豁免其他责任1_保障说明 | — |
| 504742990997487616 | 豁免其他责任1_原文标题 | — |
| 504761862450446336 | 豁免免责数量 | — |
| 504761819668545536 | 豁免具体免责条款 | — |

**身故责任类：**
| coverage_id | coverage_name | 备注 |
|---|---|---|
| 504404937305096192 | 身故责任保障说明 | 18周岁前身故，退还已交保费；18周岁及以后，给付基本保额 |
| 504762213845041152 | 身故免责数量 | — |
| 504762188666634240 | 身故具体免责条款 | — |

**全残责任类：**
| coverage_id | coverage_name | 备注 |
|---|---|---|
| 504408259453911040 | 全残责任保障说明 | — |
| 504762150854983680 | 全残免责数量 | — |
| 504762115425697792 | 全残具体免责条款 | — |

**疾病责任免除类：**
| coverage_id | coverage_name | 备注 |
|---|---|---|
| 504761972722892800 | 疾病免责数量 | 5条 / 7条 / 10条 |
| 504761940493860864 | 疾病具体免责条款 | 完整免责条款原文 |
| 505323632290299904 | 排他项说明 | — |

**疾病其他责任（扩展槽位）：**
| coverage_id | coverage_name | 备注 |
|---|---|---|
| 504416020036190208 | 疾病其他责任1_保障说明 | 扩展责任槽位 |
| 504416050532974592 | 疾病其他责任1_原文标题 | — |
| 504415918999601152 | 疾病其他责任2_保障说明 | — |
| 504415988960591872 | 疾病其他责任2_原文标题 | — |
| 504415833469353984 | 疾病其他责任3_保障说明 | — |
| 504415872124059648 | 疾病其他责任3_原文标题 | — |
| 504415766305964032 | 疾病其他责任4_保障说明 | — |
| 504415801777192960 | 疾病其他责任4_原文标题 | — |

**其他责任与免责类：**
| coverage_id | coverage_name | 备注 |
|---|---|---|
| 504761672716910592 | 其他免责1_免责数量 | — |
| 504761634909454336 | 其他免责1_具体免责条款 | — |
| 504761704409071616 | 其他免责1_原文标题 | — |

**保单权益类：**
| coverage_id | coverage_name | 典型标准值示例 |
|---|---|---|
| 504760761890242560 | 转换权 | 支持（交费期满后可转年金） / 不支持 |
| 504760734723735552 | 保单贷款 | 最高70%现金价值 / 不支持 |
| 504760707838246912 | 减保 | 支持 / 不支持 |
| 504760677517623296 | 减额交清 | 支持 / 不支持 |
| 504760621368475648 | 家庭费率优惠 | — |

**终末期/护理/其他责任类：**
| coverage_id | coverage_name | 备注 |
|---|---|---|
| 504415626153295872 | 终末期疾病保障说明 | — |
| 504415660345262080 | 长期护理保障说明 | — |
| 504759588323983360 | 护理连续给付保障说明 | — |
| 504759629621100544 | 护理连续给付期限 | — |
| 504759659006394368 | 护理连续给付标准 | — |
| 552863274048552960 | 护理免责数量 | — |
| 552863326271832064 | 护理具体免责条款 | — |

**医疗类（部分重疾附加）：**
| coverage_id | coverage_name | 备注 |
|---|---|---|
| 504400934089392128 | 医院范围 | 二级及以上公立医院 |
| 504401100485820416 | 医院详情 | — |
| 504403250586714112 | 住院安排 | — |
| 504403275865784320 | 专家门诊 | — |
| 504403192554323968 | 国内二次诊疗 | — |
| 504403156760133632 | 就医陪诊 | — |
| 504403156760133632 | 就医绿通 | — |
| 504403116662587392 | 康复护理 | — |
| 504403329611595776 | 健康管理 | — |
| 504758586069876736 | 其他医疗责任1_保障说明 | — |
| 504758636779012096 | 其他医疗责任1_原文标题 | — |

### 意见 4：行业发展性——支持新责任项和标准值扩展
随着保险行业发展，会出现新的责任项和新的标准责任值，系统设计必须支持：
- **新 coverage 项扩展**：当复核员发现当前 coverage catalog 中没有匹配项时，可提请"新增 coverage 申请"，由管理员审批后写入 cmb_coverage 树
- **新标准值扩展**：coverage_standard 中新增标准值（不破坏已有值）
- **版本管理**：coverage catalog 应有版本号（catalog_version），与 rule_version 分开管理
- **review task 创建时记录 catalog_version**：便于历史任务回溯（任务创建时的字段集 vs 当前字段集差异）

---

## 任务一：coverage_template_minimal_design_v1.md

**文件路径：** `~/codex-openai/development/docs/coverage_template_minimal_design_v1.md`

### 核心前提

**coverage_template 的数据来源已存在，不需要新建：**
- `cmb_product_coverage`：每行是 `product_id → coverage_id → standard_content`
  - 对任意 product_id，`SELECT * FROM cmb_product_coverage WHERE product_id='X'` 即得该产品的预期字段全集
  - 1010003851 真惠保有 37 行
- `cmb_coverage`：3级嵌套集合树，重疾险相关 coverage 共 **96 个**（见上方完整目录）
- 任务创建时不需要另建 template 表，直接用 DB 查询做差集

### 文档应涵盖内容

#### 1. coverage_template 定义

说明 template 的来源（cmb_product_coverage + cmb_coverage JOIN 查询），以及输出结构：
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

#### 2. is_tier_a 定义规则

**强制 Tier A（无论置信度，逐项必须人工裁决）：**
- 所有投核保规则字段：投保年龄、保险期间、交费期间、交费频率、等待期、宽限期、犹豫期
- 核心责任字段：重疾赔付次数、重疾分组、重疾数量、轻症赔付次数、中症赔付次数
- 数量类字段：特定重疾数量、少儿重大疾病数量
- 动态升级为 Tier A：所有 `conflict=true`、所有 `source_count=0`、所有 `dependency_group` 成员、所有 `manually_added` 补录项

**可 Tier B 批量处理（同时满足所有条件）：**
- confidence ≥ 0.90 且 conflict=false 且 source_count=1
- 不在任何 dependency_group 中
- 字段类型属于说明性/权益类（保单贷款、减保、减额交清等）

#### 3. review_priority 分级

| priority | 适用字段 | 备注 |
|---|---|---|
| 1（最高）| conflict=true | 多来源矛盾 |
| 2 | not_extracted | 模板有，抽取层无 |
| 3 | manually_added | 复核员手动补录 |
| 4 | Tier A + dependency_group 成员 | 核心保障字段 |
| 5 | review_required | 一般字段 |
| 6 | candidate_ready | 高置信度候选 |

#### 4. 两层分组方案

```
group_level_1（一级，对应 cmb_coverage depth=1）
└── group_level_2（二级，对应 cmb_coverage depth=2）
    └── items[]
```

一级示例（重疾险）：
- `基础规则`：投核保规则相关字段
- `疾病责任`：重疾/轻症/中症/特定重疾/恶性肿瘤多次
- `身故全残责任`：身故/全残
- `豁免责任`：被保险人豁免/投保人豁免
- `责任免除`：疾病免责/身故免责/全残免责
- `保单权益`：转换权/保单贷款/减保/减额交清
- `产品基本信息`：合同名称/条款编码/报备年度等

**动态分组（优先显示在左栏顶部）：**
- `冲突字段`（conflict=true）
- `未抽取字段`（not_extracted）
- `缺失字段`（cannot_extract）
- `依赖字段`（is_linked=true）
- `补录字段`（manually_added）

#### 5. Item 结构扩展

在现有字段基础上新增：
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

#### 6. catalog_version 管理

说明 catalog_version 的用途和维护机制：
- 记录字段在哪个版本的目录中定义
- review task 创建时记录当时的 catalog_version
- 历史任务查询时，可对比当时 catalog 版本与当前版本的差异

---

## 任务二：review_task_creation_gap_mechanism_v1.md

**文件路径：** `~/codex-openai/development/docs/review_task_creation_gap_mechanism_v1.md`

### 核心问题

当前 task 创建流程：抽取层输出 candidates → 直接打包为 field_groups → 发给复核员

遗漏问题：从未被抽取的字段永远不在复核页面出现。复核员看到的是"被截断的视图"。

### 文档应涵盖内容

#### 1. not_extracted vs cannot_extract 区分

| 状态 | 含义 | 产生来源 | 后续操作 |
|---|---|---|---|
| `cannot_extract` | 系统尝试提取，所有来源均未命中 | 抽取层有记录，无结果 | 标注 block_import=false/true |
| `not_extracted` | 系统从未尝试提取 | task 创建时模板差集发现 | 复核员判断：产品无此项→cannot_extract_from_clause / 抽取层漏提→review_required+手动填写 / 不确定→pending_materials |

#### 2. manually_added 新状态

补充状态机扩展：
- `manually_added`：复核员通过"原始文件浏览+补录"操作主动添加的字段
- 创建方式：复核员在原始文件浏览界面选中文本后，映射到 coverage catalog 中的某个 coverage_id，填写 final_value 和来源信息
- 后续状态：`manually_added` → `accepted`（复核员本人或上级确认）或 `rejected`（上级驳回）
- 日志记录：需完整记录 operator、source_evidence（file+page+quoted_text）

#### 3. 原始文件浏览设计（对应意见1）

**原始文件访问机制规格：**

| 场景 | 交互 | 技术要求 |
|---|---|---|
| 从字段来源打开 | 点击 Source 卡片上的"查看原始文件"按钮 | 打开 PDF，定位到 source.page 页 |
| 主动浏览 | 左栏顶部"原始文件"入口 | 可选择文件，自由翻页 |
| 从原始文件补录 | 在 PDF 视图中标注段落，点击"补录为新字段" | 触发补录流程 |

**PDF 显示方式（两种方案，设计中列出并说明取舍）：**
- 方案 A：页面内嵌 iframe（pdf.js）+ 右侧审核面板并排
- 方案 B：新标签页打开，URL 带页码锚点

**xlsx 显示方式：**
- 以只读表格视图渲染费率表
- 支持列/行搜索
- 不允许编辑

**文件访问数据结构：**
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

#### 4. 手动补录流程（对应意见2）

**触发入口：**
1. 在原始文件视图中标注文本段落后，点击"补录为字段"
2. 在左栏找不到某字段时，点击"手动补录"（直接输入，不依赖 PDF 标注）

**补录表单规格：**
```
coverage_name（从 catalog 搜索+选择）： [搜索框 + 下拉树]
final_value（手动输入）：              [文本框，可参考标准值列表]
来源文件：                             [下拉：条款/说明书/费率表]
来源页码：                             [数字输入]
引用原文：                             [文本框，从 PDF 标注自动填入 或 手动粘贴]
备注：                                 [文本框]

[提交补录]  [取消]
```

**coverage catalog 搜索器规格：**
- 支持中文模糊搜索（字段名）
- 显示所属分类（父节点路径）和标准值参考列表
- 如果搜索无结果，显示"申请新增 coverage 项"入口（见意见4扩展机制）

**补录后的 item 结构：**
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

#### 5. coverage catalog 扩展机制（对应意见4）

**新增 coverage 项申请流程：**

```
复核员发现新字段（catalog 中没有）
        ↓
点击"申请新增 coverage 项"
        ↓
填写：拟议字段名 + 所属一级/二级分类 + 典型值示例 + 发现来源
        ↓
提交给管理员审批
        ↓
管理员审批通过 → 写入 cmb_coverage 树 + 分配 coverage_id + 更新 catalog_version
        ↓
复核员收到通知，用新 coverage_id 完成补录
```

**新增标准值机制：**
- 现有 coverage_id 下允许随时新增 standard_content 值（非破坏性）
- 新增标准值记录到 cmb_coverage_standard，带版本时间戳
- 复核员选 final_value 时：优先显示已有标准值，最下方提供"输入自定义值"

**catalog_version 版本管理规格：**

| 事件 | 版本变更 |
|---|---|
| 新增 coverage 项 | catalog_version MINOR +1（如 v1.2 → v1.3）|
| 新增标准值 | catalog_version PATCH +1（如 v1.2 → v1.2.1）|
| 重大重构（如分类调整）| catalog_version MAJOR +1（如 v1.x → v2.0）|

**review task 版本记录：**
- task 创建时记录 `catalog_version_at_creation`
- 未来重新审核时，可对比版本差异，提示"自任务创建以来，新增了 N 个字段"

#### 6. task 创建时的差集算法

```python
def build_review_task(product_id, extracted_candidates, catalog_version):
    # Step 1: 从 cmb_product_coverage 查询预期字段全集
    template_fields = query_db("""
        SELECT pc.coverage_id, c.name AS coverage_name, pc.standard_content,
               c.depth, cp.name AS parent_name,
               c.lft, c.rgt
        FROM cmb_product_coverage pc
        JOIN cmb_coverage c ON pc.coverage_id = c.id
        LEFT JOIN cmb_coverage cp ON c.parent_id = cp.id
        WHERE pc.product_id = %s
        ORDER BY c.lft
    """, [product_id])

    # Step 2: 构建已提取字段 index
    extracted_index = {c["coverage_name"]: c for c in extracted_candidates}

    # Step 3: 构建字段列表（含差集）
    items = []
    for tf in template_fields:
        if tf["coverage_name"] in extracted_index:
            item = build_item_from_candidate(extracted_index[tf["coverage_name"]], tf)
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

#### 7. 左栏过滤与搜索规格

**过滤器（多选）：**
- 状态：待复核 / 冲突 / 未抽取 / 缺失 / 已接受 / 已修改 / 已驳回 / 补录
- 分类：Tier A / Tier B
- 来源：clause-only / 多来源 / 无来源
- 依赖：在依赖组中 / 不在

**排序（默认优先级排序）：**
- 优先级（review_priority 升序）
- 字段名
- 状态

**搜索：**
- 字段名模糊匹配
- 候选值匹配
- 来源文件名匹配

#### 8. 批量操作规格

允许批量的条件（同时满足）：is_tier_a=false + conflict=false + is_linked=false + source_count=1 + confidence≥0.90

允许操作：批量接受（同组低风险字段）、批量标记 pending_materials（同组无来源字段）

禁止批量：Tier A / 有冲突 / dependency_group 成员 / manually_added

---

## 输出要求

1. 两份文档均为中文
2. 引用现有文档：`人工复核工作台_V2_产品级设计.md`、`人工复核信息架构_V2.md`、`人工复核模块状态机_V2.md`
3. **不修改现有三份 V2 设计文档**
4. 状态机扩展（not_extracted、manually_added）写入任务二文档，不直接改状态机文档
5. 所有 DB 查询均指向已有表 `cmb_product_coverage` 和 `cmb_coverage`，不提议新建 template 表
6. catalog_version 机制写入任务一文档

## 验收标准

1. `coverage_template_minimal_design_v1.md` 包含：is_tier_a 规则、review_priority 6级、两层分组方案、item 结构扩展、catalog_version 管理 ✓
2. `review_task_creation_gap_mechanism_v1.md` 包含：
   - not_extracted / manually_added 状态定义及区分 ✓
   - 差集算法伪代码（基于 cmb_product_coverage）✓
   - 原始文件浏览规格（PDF + xlsx，含定位到 source.page）✓
   - 手动补录表单规格（含 coverage catalog 搜索器）✓
   - coverage catalog 扩展机制（新增 coverage 项申请流程）✓
   - 标准值扩展机制 ✓
   - 左栏过滤/搜索规格 ✓
   - 批量操作规格 ✓
3. 96 个 coverage 项目录（意见3）体现在任务一文档中，作为 coverage catalog 参考 ✓
4. 不修改现有三份 V2 设计文档 ✓
