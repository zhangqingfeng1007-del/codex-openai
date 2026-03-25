# Codex 修复指令：盲测 V1 发现问题

**来源：** 10款产品盲测结果（blind_test_results_v1.json）与 DB gold 对比分析
**目标文件：** `~/codex-openai/development/scripts/extract_tier_a_rules.py`
**要求：** 每项修复必须附 evidence_text，不接受无来源修改

---

## 一、问题总览

| 优先级 | 问题 | 影响产品 | 类型 |
|---|---|---|---|
| P0 | 重疾赔付次数：多次赔付产品识别为1次 | 1010003851（2次）、1360003636、1360003728（5次）| 规则缺口 |
| P0 | 重疾分组：多次赔付无分组输出"不涉及" | 1010003851（不分组）| 逻辑错误 |
| P0 | 重疾分组：多次分组产品未输出组数 | 1360003636、1360003728（5组）| 规则缺口 |
| P1 | 等待期：未升级为完整"非意外X天，意外0天" | 1360003636、1360003728 | 跨块升级失效 |
| P1 | 投保年龄：从费率表读取时丢失婴儿天数 | 8/10 款 | 格式缺口 |
| P1 | 交费期间：输出格式不符合规范 | 10/10 款 | 格式规范 |

---

## 二、P0 修复：重疾赔付次数

### 2.1 问题根因（必须完整理解）

重大疾病多次赔付在条款中有三种表达模式，当前规则只覆盖了模式1：

**模式1（已覆盖）：可选多次赔付**
```
851A："若选择多次给付责任，可给付第二次..."
```
当前规则：`cross_block_optional_multi` → "1次（若选择多次给付责任，2次）"

**模式2（未覆盖）：固定N次分独立责任条款**
```
1010003851（真惠保）：
  "二、首次重大疾病保险金"
  "首次重大疾病保险金最多给付一次。"
  "除第二次重大疾病保险金责任外，主合同其他责任自首次重大疾病确诊之时起终止。"
  "三、第二次重大疾病保险金"
  "第二次重大疾病保险金最多给付一次。"
  "主合同自第二次重大疾病确诊之时起效力终止。"
```
特点：首次和第二次是**平级的独立责任条款**，没有"选择"语言
当前结果：错误输出"1次"（匹配了"首次...最多给付一次"）

**模式3（未覆盖）：以N次为限 + 分组结构**
```
1360003636（倍佑一生）/ 1360003728（守护一生）：
  "本合同约定的重大疾病保险金为分组重大疾病保险金，详细分组信息请见第三十一条"
  "本合同约定的重大疾病保险金的累计给付次数以五次为限，当累计给付达到五次时，本合同终止。"
  "7.2.2 第一次重大疾病保险金"
  "7.2.3 第二次重大疾病保险金"
  ...
  "7.2.6 第五次重大疾病保险金"
```
特点：有"以N次为限"明确限制 + "分组重大疾病保险金"声明 + 逐次责任条款

### 2.2 修复方案

#### 修复 A：在 `extract_ci_pay_times` 函数中添加"以N次为限"模式

位置：在现有的 `_CN_NUM` 搜索段落之后，`negative_markers` 检查之前

```python
# 新增：以N次为限模式（如"累计给付次数以五次为限"）
m = re.search(r"(?:累计给付次数|保险金的累计给付次数)以([一二三四五六七八九十\d]+)次为限", compact)
if m:
    raw = m.group(1)
    num = _CN_NUM.get(raw, raw)
    return f"{num}次"
```

#### 修复 B：在跨block兜底区域，添加固定多次赔付检测

位置：在 `cross_block_optional_multi` 规则之后（约第450行之后）

**前提条件检查（必须同时满足）：**
1. `all_text` 中存在 `"第二次重大疾病保险金"` 或 `"第二次重度疾病保险金"`
2. 不含 `"选择多次给付"`, `"附加多次给付"`, `"可选择多次"` 等可选语言
3. `"重疾赔付次数"` 尚未在 `results` 中

**计数逻辑：**
- 统计 `all_text` 中 `第X次重大疾病保险金` 的不同X值数量（X = 一/二/三/四/五/1/2/3/4/5）
- 该数量即为赔付次数

```python
# 跨block兜底：固定多次赔付（如真惠保"第二次重大疾病保险金最多给付一次"，非可选）
if "重疾赔付次数" not in results:
    _CI_ORD = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
               "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
    has_optional_lang = any(m in all_text for m in ["选择多次给付", "附加多次给付", "可选择多次"])
    if not has_optional_lang:
        # 找到所有"第X次重大疾病保险金"的X值
        ord_hits = set()
        for cn, val in _CI_ORD.items():
            if f"第{cn}次重大疾病保险金" in all_text or f"第{cn}次重度疾病保险金" in all_text:
                ord_hits.add(val)
        # 数字序数词
        for d in re.findall(r"第(\d+)次重大疾病保险金", all_text):
            ord_hits.add(int(d))
        firm_count = max(ord_hits) if ord_hits else 0
        if firm_count >= 2:
            evidence_block = next(
                (b for b in blocks if "第二次重大疾病保险金" in b["text"]
                 or "第二次重度疾病保险金" in b["text"]),
                blocks[0]
            )
            add_candidate(results, "重疾赔付次数", f"{firm_count}次",
                          evidence_block, 0.82, "rule: cross_block_firm_multi")
```

---

## 三、P0 修复：重疾分组

### 3.1 问题根因

当前分组推断逻辑（`extract_candidates` 末段）只有4个分支：

```
multi_pay=None  → review_required
multi_pay=False → "不涉及"（单次赔付）
"若选择多次给付责任" in pay_times → "不分组"（可选多次）
grouping_match → 使用文本中发现的分组值
else → review_required
```

缺失的情况：
- **固定多次但不分组**（真惠保2次）：multi_pay=True，无"若选择"，无grouping_match文本 → 当前落入`review_required`，正确应为"**不分组**"
- **分组多次**（倍佑/守护一生）：需要从"分组重大疾病保险金"+"以N次为限"推断"**N组**"

### 3.2 修改 `extract_ci_grouping` 函数

```python
def extract_ci_grouping(text: str) -> str | None:
    compact = normalize_spaces(text)
    if "分组" not in compact:
        return None
    if "不分组" in compact:
        return "不分组"
    # 新增：分组重大疾病保险金 → 确认涉及分组（组数后续从pay_times推断）
    if "分组重大疾病保险金" in compact:
        return "涉及分组"
    if "不同组" in compact or "分为" in compact:
        return "涉及分组"
    return None
```

### 3.3 修改 `extract_candidates` 末段分组推断

在现有分组推断逻辑之前，添加一个优先处理步骤：

```python
# 优先：分组重大疾病保险金 + 以N次为限 → N组
all_compact_text = normalize_spaces(" ".join(b["text"] for b in text_blocks))
has_grouped_ci_declaration = "分组重大疾病保险金" in all_compact_text
if has_grouped_ci_declaration and "重疾赔付次数" in results:
    pay_val = results["重疾赔付次数"].get("value", "")
    m_n = re.search(r"^(\d+)次$", pay_val)
    if m_n:
        n_groups = int(m_n.group(1))
        evidence_block = next(
            (b for b in text_blocks if "分组重大疾病保险金" in normalize_spaces(b["text"])),
            text_blocks[0]
        )
        set_candidate(results, "重疾分组", f"{n_groups}组",
                      evidence_block, 0.82,
                      "rule: ci_grouping_from_分组保险金_and_pay_times")
```

然后在现有逻辑中，补充固定多次无分组的情况：

```python
# 现有逻辑的 elif 链中，在 "elif grouping_match is not None:" 之前加：
elif multi_pay is True and "若选择多次给付责任" not in (pay_times_value or ""):
    # 固定多次赔付，无分组声明 → 不分组
    if not has_grouped_ci_declaration:  # 需要把 has_grouped_ci_declaration 传入此作用域
        pay_times_block = results.get("重疾赔付次数")
        set_candidate(results, "重疾分组", "不分组",
                      pay_times_block, 0.78,
                      "rule: ci_grouping_firm_multi_no_group")
    # 有分组声明时已在上面处理，此处不重复
```

> **注意：** 需要把 `has_grouped_ci_declaration` 的计算移到分组推断段落的开头，确保两处都能使用。

---

## 四、P1 修复：等待期跨块升级

### 4.1 问题

倍佑一生/守护一生等待期输出"90天"而非"非意外90天，意外0天"。

根因：这两款产品在等待期条文中，"意外无等待期"声明位于：
```
"在本合同保险期间内，若被保险人于本合同等待期（见释义）内因意外..."
```
该段在不同block，且使用的是"意外伤害事故...于等待期后"而非"无等待期"字样。

当前跨块升级条件（第487-497行）：
```python
has_no_waiting_accident = (
    any("意外" in b["text"] and "无等待期" in b["text"] for b in blocks)
    or re.search(r"意外伤害.*无等待期|无等待期.*意外伤害", all_compact)
)
```

**问题：** 条款里写的是"被保险人因意外伤害事故导致...的，无等待期"，all_compact 里能找到但当前正则要求二者在同一 block（第一个条件）或用 all_compact 全文搜索（第二个条件有效）。

### 4.2 修复

加宽全文搜索模式，覆盖更多意外无等待期表达：

```python
has_no_waiting_accident = (
    any("意外" in b["text"] and "无等待期" in b["text"] for b in blocks)
    or re.search(
        r"意外伤害.*?无等待期|无等待期.*?意外伤害"
        r"|因意外伤害.*?不受.*?限制"
        r"|因意外伤害.*?不设.*?等待期"
        r"|意外伤害事故.*?无等待期|无等待期.*?意外伤害事故",
        all_compact
    )
)
```

---

## 五、P1 修复：输出格式规范

### 5.1 投保年龄：费率表来源时补充婴儿天数

**问题：** 当投保年龄从处理后费率表读取时，只有整数年龄（0周岁），丢失"（28天）"或"（30天）"婴儿最低投保天数信息。

**方案：** 在条款中查找投保年龄声明，若费率表提供了 min_age=0，从条款补充天数：

在 `extract_age` 函数中，优先匹配含天数的模式（当前已有）。
**在 `extract_candidates` 主流程中，当费率表来源的投保年龄为"0-X周岁"时**，用条款中 `extract_age` 的结果覆盖，因条款结果优先级更高且包含天数。

具体实现：调用方（Codex盲测脚本）在合并费率表与条款结果时，若条款提取到含"天"的投保年龄，以条款结果为准。

### 5.2 交费期间：统一输出格式

**规范：** `趸交，5/10/15/20/30年交`（用 `/` 分隔年数，末尾加"年交"）
**当前错误：** `趸交，5年，10年，15年，20年，30年`（每个单独写"年"，无"交"）

修改 `extract_pay_period` 函数，已有逻辑：
```python
years = sorted({int(x) for x in re.findall(r"(\d+)年交", compact)})
if years:
    parts = [str(y) for y in years]
    freqs.append("/".join(parts) + "年交")
```
这已是正确格式。**问题在于盲测脚本从处理后费率表读取时未遵循此格式。**

在盲测脚本中，从费率表读取的 `pay_periods` 列表如 `['趸交', '5年', '10年', '15年']`，需要做格式转换：
```python
def normalize_pay_period_from_rate(periods: list[str]) -> str:
    """将费率表的交费期间列表转为标准格式"""
    dunhan = []
    years = []
    for p in periods:
        p = p.strip()
        if "趸" in p or "一次性" in p:
            dunhan.append("趸交")
        else:
            m = re.match(r"(\d+)年?$", p)
            if m:
                years.append(int(m.group(1)))
    result = []
    if dunhan:
        result.append("趸交")
    if years:
        result.append("/".join(str(y) for y in sorted(years)) + "年交")
    return "，".join(result)
```

---

## 六、验收标准

修复完成后，重新运行 `eval_blind_test_v1.py`，验收标准：

| 字段 | 修复前命中率 | 目标命中率 | 关键验收点 |
|---|---|---|---|
| 重疾赔付次数 | 60% | ≥ 80% | 1010003851=2次；1360003636/1360003728=5次 |
| 重疾分组 | 60% | ≥ 80% | 1010003851=不分组；1360003636/1360003728=5组 |
| 等待期 | 80% | ≥ 90% | 1360003636/1360003728=非意外90天，意外0天 |
| 交费期间 | 0%（格式问题） | ≥ 90% | 格式统一后全部命中 |

**不允许：** 修复多次赔付后，之前命中的单次赔付产品出现 regression（新 mismatch）

---

## 七、执行顺序

1. 先做 Fix A（`extract_ci_pay_times` 添加"以N次为限"）
2. 再做 Fix B（跨块固定多次检测）
3. 运行 eval，确认 1360003636/1360003728 输出"5次"
4. 做 Fix 3.2（`extract_ci_grouping` + 分组推断）
5. 运行 eval，确认分组字段
6. 做等待期和格式修复
7. 最终 eval 全量验收

每一步完成后运行 eval，报告数字，不接受只说"代码已修改"。
