# Codex 完整上下文同步 + 执行指令 V1

> 本文档用于向 Codex 同步项目最新状态、目标修订，以及基于盲测 V1 结果的代码修复任务。
> 请 Codex 完整阅读后执行，按节顺序，每节完成后汇报数字结果。

---

## 一、项目目标更新（必须理解，影响所有后续开发）

### 1.1 本项目的两个独立价值

**价值 A：条款智能拆解（独立项目）**
- 目标：替代人工将保险条款结构化入库，降低人工成本
- 要求：覆盖全量标准项，完整准确入库

**价值 B：AIX 智能体数据底座**
- 目标：向客户呈现完整的保险责任利益
- 字段缺失 = 误导客户 = 合规风险，不可接受

### 1.2 关键原则修订

**之前的错误认知（废弃）：**
> "一期只需覆盖结构类字段，责任类字段优先级低，用户不太关心"

**正确认知：**
- 由易到难是**开发节奏**，不是**目标边界**
- 结构类字段（当前 Tier A 10个）是起点，不是终点
- 责任类字段（重疾保险金比例/身故/轻中症/保费豁免等）是必须项

### 1.3 完整标准项分类（全量目标）

**第一类：产品结构类（当前阶段，Tier A）**
- 投保年龄、保险期间、交费期间、交费频率、等待期、宽限期、犹豫期
- 重疾赔付次数、重疾分组、重疾数量

**第二类：重疾责任类（下一阶段）**
- 重疾保险金比例、身故保险金、重疾间隔期、是否含身故

**第三类：轻症/中症类（下一阶段）**
- 轻症数量/赔付比例/次数/分组
- 中症数量/赔付比例/次数/分组

**第四类：特定责任类（三期）**
- 特定疾病额外赔付、少儿特定疾病、保费豁免条款

**第五类：现金价值/精算类（三期）**
- 现金价值表、保证续保、复效期限

---

## 二、盲测 V1 结果（背景）

### 2.1 测试概况

- 10款重疾险产品（3难度：简单/中等/复杂）
- 对比方式：blind_test_results_v1.json vs blind_test_v1_gold.json
- 评测脚本：`~/codex-openai/development/scripts/eval_blind_test_v1.py`

### 2.2 命中率矩阵

```
                投保年龄  保险期间  交费期间  交费频率  等待期  宽限期  犹豫期  重疾赔付  重疾分组  重疾数量
1010003676        MM    hit     MM      MM    hit    hit    hit    hit    hit    hit
1010003677        MM    hit     MM      MM    hit    hit    hit    hit    hit    hit
1010003722        MM     MM     MM     hit    hit    hit    hit    hit    hit    hit
1010003723        MM    hit     MM     hit    hit    hit    hit    hit    hit    hit
1010003758        MM    hit     MM      MM    hit    hit    hit    hit    hit    hit
1010003851        MM     MM     MM      MM    hit    hit    hit     MM     MM    hit
1310003720       hit    hit    miss     MM    hit    hit    hit    hit    hit     MM
1360003636        MM    hit     MM     hit     MM    hit    hit     MM     MM   miss
1360003728        MM    hit     MM      MM     MM    hit    hit     MM     MM   miss
1530003621       hit    hit     MM      MM    hit   miss    hit   miss   miss   miss
命中率            20%   80%     0%    30%    80%   90%   100%   60%   60%   60%
```

### 2.3 问题分类

**A. 格式问题（语义正确，格式不符）**
- 投保年龄：从费率表读取时丢失"（28天）"婴儿天数（8/10款）
- 交费期间：`趸交，5年，10年，30年` 应为 `趸交，5/10/30年交`（10/10款）

**B. 规则缺口（真正的提取错误）**
- 重疾赔付次数：多次赔付产品（真惠保2次、倍佑/守护一生5次）识别为"1次"
- 重疾分组：多次无分组产品输出"不涉及"（应为"不分组"），5次分组产品无组数
- 等待期：倍佑/守护一生输出"90天"（应为"非意外90天，意外0天"）

**C. Miss（结构特殊未处理）**
- 1530003621（臻享惠康）：双主险结构，多字段 miss（单独处理，本轮不修复）

---

## 三、代码修复任务

**目标文件：** `~/codex-openai/development/scripts/extract_tier_a_rules.py`

### 任务 1：重疾赔付次数 — 添加"以N次为限"模式

**根因：**
倍佑一生（1360003636）和守护一生（1360003728）条款原文：
```
"本合同约定的重大疾病保险金的累计给付次数以五次为限，当累计给付达到五次时，本合同终止。"
```
当前 `extract_ci_pay_times` 函数无法识别"以N次为限"句式。

**修改位置：** `extract_ci_pay_times` 函数，在现有的 `_CN_NUM` 搜索之后，`negative_markers` 之前

**新增代码：**
```python
# 新增：以N次为限模式（如"累计给付次数以五次为限"）
m = re.search(
    r"(?:累计给付次数|保险金的累计给付次数)以([一二三四五六七八九十\d]+)次为限",
    compact
)
if m:
    raw = m.group(1)
    num = _CN_NUM.get(raw, raw)
    return f"{num}次"
```

**验收：** 1360003636 和 1360003728 的 `重疾赔付次数` 输出 `"5次"`

---

### 任务 2：重疾赔付次数 — 添加跨块固定多次赔付检测

**根因：**
真惠保（1010003851）条款结构：
```
二、首次重大疾病保险金
"首次重大疾病保险金最多给付一次。"
"除第二次重大疾病保险金责任外，主合同其他责任自首次重大疾病确诊之时起终止。"

三、第二次重大疾病保险金
"第二次重大疾病保险金最多给付一次。"
"主合同自第二次重大疾病确诊之时起效力终止。"
```
这是**固定2次赔付**，没有"选择"语言。当前规则命中"首次...最多给付一次"返回"1次"，未检测到"第二次"独立责任条款。

**修改位置：** `extract_candidates` 跨块兜底区域，在 `cross_block_optional_multi` 规则之后

**新增代码：**
```python
# 跨块兜底：固定多次赔付（如真惠保"第二次重大疾病保险金最多给付一次"，非可选）
if "重疾赔付次数" not in results:
    _CI_ORD = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
               "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
    has_optional_lang = any(
        m in all_text for m in ["选择多次给付", "附加多次给付", "可选择多次"]
    )
    if not has_optional_lang:
        ord_hits = set()
        for cn, val in _CI_ORD.items():
            if (f"第{cn}次重大疾病保险金" in all_text
                    or f"第{cn}次重度疾病保险金" in all_text):
                ord_hits.add(val)
        for d in re.findall(r"第(\d+)次重大疾病保险金", all_text):
            ord_hits.add(int(d))
        firm_count = max(ord_hits) if ord_hits else 0
        if firm_count >= 2:
            evidence_block = next(
                (b for b in blocks
                 if "第二次重大疾病保险金" in b["text"]
                 or "第二次重度疾病保险金" in b["text"]),
                blocks[0]
            )
            add_candidate(
                results, "重疾赔付次数", f"{firm_count}次",
                evidence_block, 0.82, "rule: cross_block_firm_multi"
            )
```

**验收：** 1010003851 的 `重疾赔付次数` 输出 `"2次"`，同时原有产品（1次赔付）无 regression

---

### 任务 3：重疾分组 — 识别分组声明并推断组数

**根因：**
倍佑一生/守护一生条款原文：
```
"本合同约定的重大疾病保险金为分组重大疾病保险金，详细分组信息请见第三十一条"
"累计给付次数以五次为限"
```
当前 `extract_ci_grouping` 不识别"分组重大疾病保险金"；
当前分组推断逻辑中，5次赔付产品落入 `review_required`。

**修改 A：** `extract_ci_grouping` 函数

```python
def extract_ci_grouping(text: str) -> str | None:
    compact = normalize_spaces(text)
    if "分组" not in compact:
        return None
    if "不分组" in compact:
        return "不分组"
    if "分组重大疾病保险金" in compact:
        return "涉及分组"   # 确认涉及分组，组数后续从pay_times推断
    if "不同组" in compact or "分为" in compact:
        return "涉及分组"
    return None
```

**修改 B：** `extract_candidates` 末段分组推断，在现有逻辑**之前**插入优先处理：

```python
# === 分组推断（在现有四分支逻辑之前） ===
# 优先：分组重大疾病保险金 + 以N次为限 → N组
_all_compact_text = normalize_spaces(" ".join(b["text"] for b in text_blocks))
_has_grouped_ci = "分组重大疾病保险金" in _all_compact_text

if _has_grouped_ci and "重疾赔付次数" in results:
    _pay_val = results["重疾赔付次数"].get("value", "")
    _m_n = re.search(r"^(\d+)次$", _pay_val)
    if _m_n:
        _n_groups = int(_m_n.group(1))
        _evidence_block = next(
            (b for b in text_blocks
             if "分组重大疾病保险金" in normalize_spaces(b["text"])),
            text_blocks[0]
        )
        set_candidate(
            results, "重疾分组", f"{_n_groups}组",
            _evidence_block, 0.82,
            "rule: ci_grouping_from_分组保险金_and_pay_times"
        )
# 然后继续现有四分支逻辑（但需加一个新分支）
```

**修改 C：** 在现有四分支逻辑中，`elif grouping_match is not None:` 之前添加固定多次无分组分支：

```python
elif multi_pay is True and "若选择多次给付责任" not in (pay_times_value or "") \
        and not _has_grouped_ci and "重疾分组" not in results:
    # 固定多次赔付，条款中无分组声明 → 不分组
    pay_times_block = results.get("重疾赔付次数")
    set_candidate(
        results, "重疾分组", "不分组",
        pay_times_block, 0.78,
        "rule: ci_grouping_firm_multi_no_group"
    )
```

**验收：**
- 1360003636 → `重疾分组 = "5组"`
- 1360003728 → `重疾分组 = "5组"`
- 1010003851 → `重疾分组 = "不分组"`
- 原有单次赔付产品 → `重疾分组 = "不涉及"`（无 regression）

---

### 任务 4：等待期 — 加宽跨块升级模式

**根因：**
倍佑一生/守护一生等待期块文本为：
```
"在本合同保险期间内，若被保险人于本合同等待期（见释义）内因意外伤害事故
导致发生本合同所约定的疾病，不受等待期限制。"
```
当前跨块升级只匹配"无等待期"字样，未覆盖"不受等待期限制"表达。

**修改位置：** `extract_candidates` 末段等待期跨块升级（约第487-497行）

将：
```python
has_no_waiting_accident = (
    any("意外" in b["text"] and "无等待期" in b["text"] for b in blocks)
    or re.search(r"意外伤害.*无等待期|无等待期.*意外伤害", all_compact)
)
```
改为：
```python
has_no_waiting_accident = (
    any("意外" in b["text"] and "无等待期" in b["text"] for b in blocks)
    or re.search(
        r"意外伤害.*?无等待期"
        r"|无等待期.*?意外伤害"
        r"|因意外伤害.*?不受.*?等待期"
        r"|意外伤害事故.*?不受.*?等待期",
        all_compact
    )
)
```

**验收：** 1360003636 和 1360003728 的 `等待期` 输出 `"非意外90天，意外0天"`

---

### 任务 5：交费期间输出格式规范

**根因：**
盲测中从处理后费率表读取交费期间时，输出格式为：
`趸交，5年，10年，15年，20年，30年`
DB gold 要求格式为：
`趸交，5/10/15/20/30年交`

**修改位置：** 盲测脚本中读取费率表的部分（处理后费率表的列值解析）

在解析费率表缴费期间列时，将多个年数合并为 `X/Y/Z年交` 格式：

```python
def normalize_pay_period_from_rate(periods: list[str]) -> str:
    """将费率表的交费期间列表转为标准格式: 趸交，5/10/30年交"""
    dun = False
    years = []
    for p in periods:
        p = str(p).strip()
        if "趸" in p or "一次性" in p:
            dun = True
        else:
            m = re.match(r"(\d+)\s*年?交?$", p)
            if m:
                years.append(int(m.group(1)))
    result = []
    if dun:
        result.append("趸交")
    if years:
        result.append("/".join(str(y) for y in sorted(years)) + "年交")
    return "，".join(result)
```

**验收：** 重跑 `eval_blind_test_v1.py`，`交费期间` 命中率从 0% 提升至 ≥ 80%

---

## 四、执行顺序与汇报要求

### 执行顺序

```
任务1 → run eval → 确认1360003636/1360003728重疾赔付次数=5次
任务2 → run eval → 确认1010003851重疾赔付次数=2次，无regression
任务3 → run eval → 确认分组字段全部正确
任务4 → run eval → 确认等待期格式
任务5 → run eval → 确认交费期间命中率
最终 → 完整eval矩阵汇报
```

### 每步汇报格式

```
任务X完成
修改了：[具体函数名 + 修改描述]
eval结果：
  重疾赔付次数: hit=X mismatch=X miss=X hit_rate=X%
  重疾分组: hit=X mismatch=X miss=X hit_rate=X%
  [其他变化字段]
Regression检查：[无 / 有，描述]
```

### 禁止事项

- 不允许只汇报"代码已修改"，必须附 eval 数字
- 不允许为了提高命中率修改 eval 脚本或 gold 文件
- 不允许任何修复引入新的 mismatch（regression = 本次修改失败）
- 每个新规则必须有对应的条款原文 evidence

---

## 五、eval 命令参考

```bash
# 运行盲测对比评估
python3 ~/codex-openai/development/scripts/eval_blind_test_v1.py

# 输入文件（不可修改）：
#   ~/codex-openai/development/data/blind_test_v1/blind_test_results_v1.json
#   ~/codex-openai/development/data/gold/blind_test_v1_gold.json
# 输出：
#   ~/codex-openai/development/data/eval/blind_test_v1_eval.json
```

---

## 六、盲测完整 mismatch/miss 明细（供修复参考）

以下是 `eval_blind_test_v1.py` 的完整输出，包含每个非 hit 条目的候选值 vs gold：

```
[MISMATCH] 1010003676 / 投保年龄
  候选: 0-59周岁  (source: processed_rate)
  gold: 0（28天）-59周岁

[MISMATCH] 1010003676 / 交费期间
  候选: 趸交，5年，10年，15年，20年，30年  (source: processed_rate)
  gold: 趸交，5/10/15/20/30年交

[MISMATCH] 1010003676 / 交费频率
  候选: 年交，半年交，季交，月交  (source: clause)
  gold: 趸交，年交

[MISMATCH] 1010003677 / 投保年龄
  候选: 0-59周岁  (source: processed_rate)
  gold: 0（28天）-60周岁

[MISMATCH] 1010003677 / 交费期间
  候选: 趸交，5年，10年，15年，20年，30年  (source: processed_rate)
  gold: 趸交，5/10/15/20/30年交

[MISMATCH] 1010003677 / 交费频率
  候选: 年交，半年交，季交，月交  (source: clause)
  gold: 趸交，年交

[MISMATCH] 1010003722 / 投保年龄
  候选: 0-17周岁  (source: processed_rate)
  gold: 0（28天）-17周岁

[MISMATCH] 1010003722 / 保险期间
  候选: 至25周岁  (source: clause)
  gold: 30年

[MISMATCH] 1010003722 / 交费期间
  候选: 10年，20年，30年  (source: processed_rate)
  gold: 10/20/30年交

[MISMATCH] 1010003723 / 投保年龄
  候选: 0-15周岁  (source: processed_rate)
  gold: 0（28天）-15周岁

[MISMATCH] 1010003723 / 交费期间
  候选: 至25周岁  (source: processed_rate)
  gold: 交至25周岁

[MISMATCH] 1010003758 / 投保年龄
  候选: 0-59周岁  (source: processed_rate)
  gold: 0（28天）-59周岁

[MISMATCH] 1010003758 / 交费期间
  候选: 趸交，5年，10年，15年，20年，30年  (source: processed_rate)
  gold: 趸交，5/10/15/20/30年交

[MISMATCH] 1010003758 / 交费频率
  候选: 趸交，年交  (source: processed_rate)
  gold: 趸交，年交，月交

[MISMATCH] 1010003851 / 投保年龄
  候选: 0-65周岁  (source: processed_rate)
  gold: 0（28天）-65周岁

[MISMATCH] 1010003851 / 保险期间
  候选: 10年，20年，30年  (source: processed_rate)
  gold: 10/20/30年

[MISMATCH] 1010003851 / 交费期间
  候选: 10年，20年，30年  (source: processed_rate)
  gold: 10/20/30年交

[MISMATCH] 1010003851 / 交费频率
  候选: 年交  (source: processed_rate)
  gold: 年交，月交

[MISMATCH] 1010003851 / 重疾赔付次数
  候选: 1次  (source: clause)
  gold: 2次

[MISMATCH] 1010003851 / 重疾分组
  候选: 不涉及  (source: clause)
  gold: 不分组

[MISS] 1310003720 / 交费期间
  候选: None
  gold: 趸交，5/10/15/20年交

[MISMATCH] 1310003720 / 交费频率
  候选: 年交，月交  (source: clause)
  gold: 趸交，年交，月交

[MISMATCH] 1310003720 / 重疾数量
  候选: 28种  (source: clause)
  gold: 120种

[MISMATCH] 1360003636 / 投保年龄
  候选: 0-55周岁  (source: processed_rate)
  gold: 0（30天）-55周岁

[MISMATCH] 1360003636 / 交费期间
  候选: 10年，20年，30年  (source: processed_rate)
  gold: 10/20/30年交

[MISMATCH] 1360003636 / 等待期
  候选: 90天  (source: clause)
  gold: 非意外90天，意外0天

[MISMATCH] 1360003636 / 重疾赔付次数
  候选: 1次  (source: clause)
  gold: 5次

[MISMATCH] 1360003636 / 重疾分组
  候选: 不涉及  (source: clause)
  gold: 5组

[MISS] 1360003636 / 重疾数量
  候选: None
  gold: 105种

[MISMATCH] 1360003728 / 投保年龄
  候选: 0-55周岁  (source: processed_rate)
  gold: 0（30天）-55周岁

[MISMATCH] 1360003728 / 交费期间
  候选: 10年，20年，30年  (source: processed_rate)
  gold: 10/20/30年交

[MISMATCH] 1360003728 / 交费频率
  候选: 年交  (source: processed_rate)
  gold: 年交，半年交，季交，月交

[MISMATCH] 1360003728 / 等待期
  候选: 90天  (source: clause)
  gold: 非意外90天，意外0天

[MISMATCH] 1360003728 / 重疾赔付次数
  候选: 1次  (source: clause)
  gold: 5次

[MISMATCH] 1360003728 / 重疾分组
  候选: 不涉及  (source: clause)
  gold: 5组

[MISS] 1360003728 / 重疾数量
  候选: None
  gold: 105种

[MISMATCH] 1530003621 / 交费期间
  候选: 趸交，5年，10年，14年，19年，24年，29年  (source: processed_rate)
  gold: 趸交，5/10/14/19/24/29年交

[MISMATCH] 1530003621 / 交费频率
  候选: 趸交，年交，月交  (source: processed_rate)
  gold: 趸交，年交，半年交，季交，月交

[MISS] 1530003621 / 宽限期
  候选: None
  gold: 60天

[MISS] 1530003621 / 重疾赔付次数
  候选: None
  gold: 重大疾病1次；少儿重大疾病1次

[MISS] 1530003621 / 重疾分组
  候选: None
  gold: 不涉及

[MISS] 1530003621 / 重疾数量
  候选: None
  gold: 120种重大疾病；20种少儿重大疾病
```

> **注：** 1530003621（臻享惠康）为双主险特殊结构，本轮修复任务不覆盖，标记为待处理。

---

## 七、背景文件索引

| 文件 | 用途 |
|---|---|
| `~/codex-openai/development/scripts/extract_tier_a_rules.py` | 主要修改目标 |
| `~/codex-openai/development/data/blind_test_v1/blind_test_results_v1.json` | 盲测原始结果 |
| `~/codex-openai/development/data/gold/blind_test_v1_gold.json` | DB gold 标准 |
| `~/codex-openai/development/data/blind_test_v1/md_cache/117-1360003636-倍佑一生（优享版）重大疾病保险-条款.md` | 倍佑一生条款 |
| `~/codex-openai/development/data/blind_test_v1/md_cache/394-守护一生重大疾病保险-条款.md` | 守护一生条款 |
| `~/codex-openai/development/data/blind_test_v1/md_cache/700-招商信诺真惠保重大疾病保险（互联网专属）-条款.md` | 真惠保条款 |
| `~/codex-openai/条款智能拆解项目规划_V1.md` | 项目规划全文 |
