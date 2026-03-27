# Codex 执行指令：Review Task 创建层 Step 1 — 设计文档 + 脚本

**本轮范围：输出两份文档 + 一个可运行脚本。**

---

## 背景信息（必须理解）

### 已有数据文件

1. **抽取层输出**：`~/codex-openai/development/data/extractions/tier_a_rule_candidates_v2.json`
   - 结构：`[{product_id, db_product_id, product_name, source_blocks, candidates[]}]`
   - 每个 candidate：`{coverage_name, value, confidence, note, block_id, page, evidence_text}`
   - **注意**：candidates 按 coverage_name 索引，没有 coverage_id，每个字段一条候选

2. **Coverage 白名单**：`~/codex-openai/development/data/manifests/coverage_whitelist_v1.json`
   - 结构：`[{coverage_id, coverage_name, tier, products_count, extract_method, required_in_phase_1, default_review_mode}]`
   - 共 29 项（Tier A/B/C 重疾险核心字段）
   - 用途：确定 is_tier_a、default_review_mode

3. **完整 coverage dump**：`~/codex-openai/development/data/manifests/full_coverage_dump.json`
   - 结构：`[{product_id, product_name, aix_category_id, coverage_id, coverage_name, standard_content}]`
   - 共 3689 条，106款重疾险产品
   - **关键**：这是 DB `cmb_product_coverage` 的本地镜像，可替代 DB 查询
   - 通过 `WHERE product_id='1010003851'` 可得到该产品预期字段全集

4. **当前 V2 mock**：`~/codex-openai/development/review-module/mock/review-task-v2.json`
   - 这是 V2 review task JSON 的参考样例，schema 以此为准并扩展

### V2 review task JSON 当前结构（参考 mock）

```
顶层字段：
  task: {task_id, task_status, rule_version}
  catalog_version_at_creation: str
  product: {product_id, product_name, company_name, aix_category_id}
  document_package: {document_package_id, files[{source_type, file_name, parse_quality, local_path}]}
  field_groups: [FieldGroup]
  dependency_groups: [DependencyGroup]
  conflict_count, missing_count, not_extracted_count, pending_review_count, total_items

FieldGroup（静态）：
  {group_type, group_name, items: [CoverageItem]}

FieldGroup（动态）：
  {group_type, group_name, is_dynamic: true, item_ids: [str]}

CoverageItem（含新字段）：
  item_id, coverage_id, coverage_name, status, candidate_summary, final_value
  is_tier_a, review_priority, source_count, is_tier_a, sources[], logic_trace
  （新增）group_level_1, group_level_2, risk_level, is_required

Source：
  source_id, source_type, file_name, page, block_id, title_path[]
  source_raw_value, md_text, block_text, raw_value, normalized_value
  confidence, extract_method, conflict
```

### DB 不可直连说明

当前本机 IP 不在阿里云白名单内，无法直接 pymysql 连接。
**替代方案**：使用 `full_coverage_dump.json` 作为本地 template 来源。

---

## 任务 A：输出 review_task_builder_design_v1.md

**路径**：`~/codex-openai/development/docs/review_task_builder_design_v1.md`

只写文档，不写代码实现。内容要求：

### 1. 输入规格

```python
product_id: str                     # DB product_id，如 "1010003851"
extracted_candidates: list[dict]    # 来自 tier_a_rule_candidates_v2.json 的 candidates 列表
document_package_info: dict         # 含 files[]，每个 file 有 local_path
catalog_version: str                # 默认 "v1.2"
task_id: str                        # 可选，不传则自动生成
```

### 2. 核心处理步骤

**Step A：加载 coverage template**
- 从 `full_coverage_dump.json` 过滤 `product_id == target_id`
- 得到 `template_fields[]`：`{coverage_id, coverage_name, standard_content}`
- 补充 is_tier_a / default_review_mode（从 `coverage_whitelist_v1.json` lookup 同名字段）
- 补充 group_level_1 / group_level_2（根据 coverage_name 做规则映射，见下文分组映射表）

**Step B：构建 extracted index**
- 将 `extracted_candidates` 按 `coverage_name` 建索引
- 注意：同一 coverage_name 可能有多条候选（多来源场景），需合并

**Step C：计算每个 template field 的状态**
```
IF coverage_name 在 extracted_index：
    IF confidence >= 0.90 AND conflict == False：
        status = "candidate_ready"
    ELSE：
        status = "review_required"
ELSE：
    status = "not_extracted"
```

**Step D：分配 review_priority**
```
conflict=true      → priority=1
not_extracted      → priority=2
Tier A + dependency_group 成员 → priority=4
review_required    → priority=5
candidate_ready    → priority=6
```

**Step E：构建 field_groups**
- 按 group_level_1 / group_level_2 分组
- 动态分组（dynamic_not_extracted / dynamic_missing）只存 item_ids，不存 items
- 动态分组置顶

**Step F：计算统计字段**
```python
total_items = len(all_static_items)
conflict_count = sum(1 for i in items if i.source_count > 1 and any conflict)
missing_count = sum(1 for i in items if i.status == "cannot_extract")
not_extracted_count = sum(1 for i in items if i.status == "not_extracted")
pending_review_count = sum(1 for i in items if i.status in {"review_required", "candidate_ready"})
```

### 3. 分组映射表（group_level_1 / group_level_2）

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
| 合同名称、生效时间、报备年度、条款编码、长短险 | 产品基本信息 | — | tier_info |
| 其他/未匹配 | 其他 | — | tier_other |

### 4. 关键设计决策

- **coverage_id 做主 key**，不用 coverage_name（避免扩展槽位碰撞）
- **动态分组引用式**：`{is_dynamic: true, item_ids: [...]}`，不复制 item 对象
- **DB 不可用时降级**：优先用 `full_coverage_dump.json` 本地文件，不需要实时 DB
- **多来源合并**：同一 coverage_name 有多条候选时，全部保留在 sources[]，设 conflict=true

---

## 任务 B：输出 review_task_json_schema_v2.md

**路径**：`~/codex-openai/development/docs/review_task_json_schema_v2.md`

只写文档。内容：完整 JSON Schema 定义，TypeScript interface 风格，包含：

1. 顶层 `ReviewTask` 结构（所有字段，必填/可选，类型，含义）
2. `FieldGroup` 两种类型（静态 / 动态，区分规格）
3. `CoverageItem` 完整字段（含新增的 coverage_id / is_tier_a / review_priority / group_level_1/2 / risk_level / is_required / source_count / catalog_version）
4. `Source` 完整字段
5. `DependencyGroup` 结构
6. `status` 所有枚举值及含义（9个状态，含 not_extracted / manually_added）
7. `source_type` 枚举（clause / product_brochure / processed_rate / raw_rate / underwriting_rule / manual）
8. 统计字段规则（如何计算 total_items / conflict_count / pending_review_count）

---

## 任务 C：build_review_task.py

**路径**：`~/codex-openai/development/scripts/build_review_task.py`

### 功能：生成单产品的 V2 review task JSON

```
python build_review_task.py --product_id 1010003851
```

**输入文件（全部本地，不需要 DB 连接）：**
- `tier_a_rule_candidates_v2.json`（抽取层候选）
- `full_coverage_dump.json`（coverage template）
- `coverage_whitelist_v1.json`（is_tier_a / default_review_mode）

**输出**：
```
~/codex-openai/development/data/review_tasks/{product_id}_review_task_v2.json
```

### 关键实现细节

1. **product_id 匹配逻辑**
   - `tier_a_rule_candidates_v2.json` 用 `db_product_id` 字段存 DB product_id
   - 命令行传入的 `--product_id` 应与 `db_product_id` 匹配

2. **Source 对象构建**
   - 从 candidate 的 `block_id`、`page`、`evidence_text`、`note` 构建 Source 对象
   - `source_type` 根据 `block_id` 前缀判断：
     - `brochure_` 开头 → product_brochure
     - 其他 → clause（默认）
   - `file_name` 从 document_package_info 中匹配对应 source_type 的文件
   - `confidence`：直接用 candidate.confidence
   - `extract_method`：用 candidate.note

3. **document_package_info 来源**
   - 默认从同目录的 `document_package_manifest.json` 读取（如果存在）
   - 或作为命令行参数 `--package_manifest path/to/file.json`
   - 暂时允许 local_path=null（不阻断脚本执行）

4. **dependency_groups 硬编码**
   - 重疾责任链固定：`["重疾赔付次数", "重疾分组", "重疾数量"]`

5. **item_id 生成规则**
   - 静态字段：`item_{coverage_id_short}_{coverage_name_pinyin_abbr}`（或直接 `item_{coverage_id}`）
   - Gap 字段（not_extracted）：`item_gap_{coverage_id}`

### 脚本结构

```python
def load_coverage_template(product_id: str) -> list[dict]:
    """从 full_coverage_dump.json 加载产品预期字段全集"""

def load_whitelist() -> dict:
    """加载 coverage_whitelist_v1.json，以 coverage_name 为 key"""

def load_extracted_candidates(product_id: str) -> list[dict]:
    """从 tier_a_rule_candidates_v2.json 提取指定产品的 candidates"""

def build_coverage_item(template_field: dict, candidates: list[dict], whitelist: dict) -> dict:
    """构建单个 CoverageItem"""

def build_field_groups(items: list[dict]) -> list[dict]:
    """按 group_level_1/2 构建 field_groups（含动态分组）"""

def compute_stats(items: list[dict]) -> dict:
    """计算统计字段"""

def build_review_task(product_id: str, package_manifest: dict, catalog_version: str) -> dict:
    """主函数，输出完整 review task dict"""

if __name__ == "__main__":
    # argparse: --product_id, --package_manifest, --catalog_version, --output
    # 输出到 ~/codex-openai/development/data/review_tasks/{product_id}_review_task_v2.json
```

### 验收标准

1. `python build_review_task.py --product_id 1010003851` 成功运行，无报错 ✓
2. 输出 JSON 包含 `full_coverage_dump.json` 中 1010003851 的所有字段（应 ≥ 30 项）✓
3. 静态分组总 item 数 = `total_items` ✓
4. 动态分组只有 `item_ids`，无 `items` 数组 ✓
5. 每个 CoverageItem 包含：`coverage_id / coverage_name / status / is_tier_a / review_priority / source_count` ✓
6. `not_extracted` 状态的字段：`sources=[]`，`candidate_summary="—"` ✓
7. 输出 JSON 可被前端 `app.js` 的 `loadTask()` 直接加载，页面正常渲染 ✓

---

## 输出目录检查

运行前请确保以下目录存在（如不存在则创建）：
```
~/codex-openai/development/data/review_tasks/
```
