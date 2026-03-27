# Codex 执行指令：1578 原始费率表解析（自然费率扩展）

## 背景

1578（金小葵·少儿长期重疾险）是自然费率产品，结构与 1803/919A/1568 不同：
- 无固定缴费期轴，而是"交至25周岁"
- 费率按"新保首年"和"续年"区分，对应 `premium_status` 字段
- 有两个计划（Sheet1=计划一，Sheet2=计划二），对应 `product_sub_name`
- Rate unit 为 **per 10,000元**，入库前需 ÷10 转换为 per 1,000

## 产品信息

| 字段 | 值 |
|---|---|
| product_id | `1010004022` |
| product_name | `招商信诺金小葵少儿重大疾病保险（互联网专属）` |
| company_id | `161` |
| company_name | `招商信诺` |
| 文件路径 | `~/Desktop/开发材料/10款重疾/1578-金小葵·少儿长期重疾险/1578-金小葵·少儿长期重疾险-费率表.xlsx` |

## 固定字段映射（来自条款确认）

| DB 字段 | 值 | 说明 |
|---|---|---|
| `insure_period` | **25** | 保至25周岁（条款截图确认） |
| `period_type` | **13** | 至X周岁编码 |
| `pay_time` | **25** | 交至25周岁 |
| `pay_time_type` | **11** | 交至X周岁编码 |
| `pay_type` | **12** | 年交 |
| `amount` | **1000** | 统一基准（rate ÷10 后为 per 1000） |

## xlsx 结构

```
Sheet1: 计划一（product_sub_name = "计划一"）
Sheet2: 计划二（product_sub_name = "计划二"）

每个 Sheet 结构（以 Sheet1 为例）：
Row1: 产品名称（忽略）
Row2: 计划名（merged）
Row3: 每10000元...（忽略）
Row4: 年龄(merged R4:R5) | 新保首年费率(merged B4:C4) | 其他保单年度费率(merged D4:E4)
Row5: -              | 男性 | 女性                  | 男性 | 女性
Row6+: 数据行
```

**列映射（固定）：**

| 列 | 含义 |
|---|---|
| A | 年龄（含 `*` 前缀，如 `*16`，需 strip `*`） |
| B | 新保首年费率_男（premium_status=10, gender=11） |
| C | 新保首年费率_女（premium_status=10, gender=10） |
| D | 续年费率_男（premium_status=11, gender=11） |
| E | 续年费率_女（premium_status=11, gender=10） |

**数据行范围：**
- Row 6–Row 30（共 25 行，年龄 0–24，最后是 `*24`）
- 跳过条件：年龄列为 None 或非数字（忽略 `*` 前缀后仍非数字）
- 值为 `-`、None 或空 → 跳过该格（不输出该行）

**年龄 0 的特殊处理：**
- B列（新保首年_男）= 13.34，C列（新保首年_女）= 11.21 → 有值
- D列（续年_男）= `-`，E列（续年_女）= `-` → 跳过（无续年费率）

**年龄 *16 以上：**
- B/C列（新保首年）= `-` → 跳过（16岁以上不接受新保）
- D/E列（续年）= 有值 → 正常输出

## 输出行示例

```python
# age=0, 新保首年, 男
{
    "product_id": "1010004022",
    "product_sub_name": "计划一",
    "age": 0,
    "gender": 11,
    "premium_status": 10,
    "pay_time": 25, "pay_time_type": 11,
    "insure_period": 25, "period_type": 13,
    "pay_type": 12,
    "rate": 1.334,        # 13.34 ÷ 10
    "amount": 1000,
    "source_type": "raw_rate",
}

# age=16, 续年, 女（*16 仅有续年）
{
    "product_id": "1010004022",
    "product_sub_name": "计划一",
    "age": 16,
    "gender": 10,
    "premium_status": 11,
    "pay_time": 25, "pay_time_type": 11,
    "insure_period": 25, "period_type": 13,
    "pay_type": 12,
    "rate": 1.026,        # 10.26 ÷ 10
    "amount": 1000,
    "source_type": "raw_rate",
}
```

## parse_raw_rate.py 扩展方案

在现有 `parse_raw_rate.py` 中新增 **模板 B** 的处理，检测逻辑：

```python
def detect_template(ws) -> str:
    # 检查 Row1/Row2 是否有"计划"字样 → 模板 B
    for row in ws.iter_rows(min_row=1, max_row=3, values_only=True):
        for cell in row:
            if cell and "计划" in str(cell):
                return "B"
    # Row5 含 "男性"/"女性" → 模板 A
    row5_vals = set(str(c.value).strip() for c in ws[5] if c.value)
    if "男性" in row5_vals or "女性" in row5_vals:
        return "A"
    return "C"
```

模板 B 解析函数：

```python
def parse_template_b(ws, product_id, product_sub_name, company_id, company_name, product_name, source_file):
    """
    解析 1578 格式：固定4列（新保首年男/女，续年男/女），列位置固定。
    """
    RATE_SCALE = 10.0   # per10000 → per1000

    # 确定数据起始行（找到年龄列第一个数字的行）
    data_start = None
    for i, row in enumerate(ws.iter_rows(min_row=1, values_only=True), start=1):
        age_raw = str(row[0]).strip() if row[0] is not None else ""
        age_clean = age_raw.lstrip("*").strip()
        if age_clean.isdigit():
            data_start = i
            break

    rows = []
    for row in ws.iter_rows(min_row=data_start, values_only=True):
        age_raw = str(row[0]).strip() if row[0] is not None else ""
        age_clean = age_raw.lstrip("*").strip()
        if not age_clean.isdigit():
            break
        age = int(age_clean)

        # (col_idx, premium_status, gender)
        combos = [
            (1, 10, 11),   # 新保首年_男
            (2, 10, 10),   # 新保首年_女
            (3, 11, 11),   # 续年_男
            (4, 11, 10),   # 续年_女
        ]
        for col_idx, prem_status, gender in combos:
            val = row[col_idx] if col_idx < len(row) else None
            if val is None or str(val).strip() in ("-", ""):
                continue
            try:
                rate = float(val) / RATE_SCALE
            except (ValueError, TypeError):
                continue

            rows.append({
                "product_id": product_id,
                "product_sub_name": product_sub_name,
                "age": age,
                "gender": gender,
                "premium_status": prem_status,
                "pay_time": 25,
                "pay_time_type": 11,
                "insure_period": 25,
                "period_type": 13,
                "pay_type": 12,
                "rate": rate,
                "amount": 1000,
                "company_id": company_id,
                "company_name": company_name,
                "product_name": product_name,
                "product_sub_name": product_sub_name,
                "rate_unit": "per_1000_amount",
                "source_type": "raw_rate",
                "source_file": source_file,
            })
    return rows
```

**调用方式**（在 `parse_raw_rate` 主函数中按模板分发）：

```python
template = detect_template(ws)
if template == "B":
    # 每个 sheet 作为一个计划
    all_rows = []
    for sheet_name in ["Sheet1", "Sheet2"]:
        ws_plan = wb[sheet_name]
        # 从 Row2 读取计划名
        plan_name = None
        for row in ws_plan.iter_rows(min_row=1, max_row=3, values_only=True):
            for cell in row:
                if cell and "计划" in str(cell):
                    plan_name = str(cell).strip()
                    break
        plan_rows = parse_template_b(ws_plan, product_id, plan_name, ...)
        all_rows.extend(plan_rows)
```

## 验收标准

```bash
python -m development.rate_standardization.parse_raw_rate \
  --input "~/Desktop/开发材料/10款重疾/1578-金小葵·少儿长期重疾险/1578-金小葵·少儿长期重疾险-费率表.xlsx" \
  --product-id 1010004022 --company-id 161 --company-name "招商信诺" \
  --product-name "招商信诺金小葵少儿重大疾病保险（互联网专属）" \
  --output /tmp/rate_1578.json
```

| 检查项 | 预期值 |
|---|---|
| `template_type` | `"B"` |
| `row_count` | **176**（计划一+计划二各88行，见计算） |
| age=0，计划一，新保首年，男 | rate ≈ 1.334 |
| age=0，计划一，新保首年，女 | rate ≈ 1.121 |
| age=16，计划一，续年，男 | rate ≈ 1.136 |
| age=0 无续年行 | D/E列为"-"，不输出 |
| `pay_time=25, pay_time_type=11` | 所有行 |
| `insure_period=25, period_type=13` | 所有行 |
| 无 `payment_years`/`insurance_period` 字符串字段 | 是 |

**row_count 计算：**
- 计划一：年龄 0–15（16个年龄）× 首年4格（男/女各1格，跳"-"后实际）+ 年龄 1–24（24个年龄）× 续年2格
  - 首年：年龄 0–15 = 16×2 = 32行
  - 续年：年龄 1–24 = 24×2 = 48行（年龄 0 的续年为"-"，跳过）
  - 合计：80行（如 Sheet1 中有部分空格则略少）
- 计划二：相同结构，但部分值可能略有差异，预期同 ~80 行
- 两个计划合计：**约 160–176 行**（以实际运行结果为准，不强制要求精确值）

## 注意事项

1. `product_sub_name` 从每个 sheet 的 Row2 动态读取（不硬编码"计划一"）
2. `*` 前缀年龄（如 `*16`）strip 后正常处理，不做特殊标记
3. 月交费率（年交×0.09）不入库，忽略附注行
4. `select_sheet()` 规则不适用于 1578（需遍历全部 sheet），模板 B 检测时直接遍历所有 sheet
