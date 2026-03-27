# Codex 执行指令：原始费率表解析器 V1

## 目标

新建 `~/codex-openai/development/rate_standardization/parse_raw_rate.py`，
解析**原始**费率表 xlsx（双层列头结构），输出与 `parse_processed_rate.py` 相同的 DB-ready 行格式。

**一期范围：3款**（1578 结构特殊，本次不做）

| 产品代码 | product_id | 文件 |
|---|---|---|
| 1803 | 1170004238 | `~/Desktop/开发材料/10款重疾/1803-中意悦享安康（悠享版）重大疾病保险/1803-中意悦享安康（悠享版）重大疾病保险-费率表.xlsx` |
| 919A | 1010003919 | `~/Desktop/开发材料/10款重疾/919A-招商信诺爱享无忧重大疾病保险/919A-招商信诺爱享无忧重大疾病保险-费率表.xlsx` |
| 1568 | 1010004001 | `~/Desktop/开发材料/10款重疾/1568-招商信诺爱享未来少儿重大疾病保险A款/1568-招商信诺爱享未来少儿重大疾病保险A款-费率表.xlsx` |

---

## 硬约束：Sheet 选择规则

这是业务规则，必须固化在解析器中，不可跳过。

### 规则优先级（从高到低）

1. **用户显式指定 `--sheet`**：严格按指定名称读，找不到则报错退出
2. **未指定时，自动选择**：
   - 优先匹配名称为 `"费率表"` 的 sheet
   - 排除名称含以下关键词的 sheet（次标准体/优选体等非主表）：
     ```python
     EXCLUDED_SHEET_KEYWORDS = ["次标准", "次标准体", "优选体", "加费"]
     ```
   - 若只剩一个候选 → 选它
   - 若有多个候选 → 选第一个，并打印警告
   - 若全被排除 → 报错，提示用户显式指定 `--sheet`

### 实现函数

```python
EXCLUDED_SHEET_KEYWORDS = ["次标准", "次标准体", "优选体", "加费"]

def select_sheet(workbook, sheet_name: str | None) -> str:
    """
    返回最终要读取的 sheet 名称。
    """
    all_sheets = workbook.sheetnames

    if sheet_name is not None:
        if sheet_name not in all_sheets:
            raise ValueError(f"指定的 sheet '{sheet_name}' 不存在，可用: {all_sheets}")
        return sheet_name

    # 自动选择：优先 "费率表"
    if "费率表" in all_sheets:
        return "费率表"

    # 排除非主表
    candidates = [s for s in all_sheets
                  if not any(kw in s for kw in EXCLUDED_SHEET_KEYWORDS)]

    if len(candidates) == 0:
        raise ValueError(f"所有 sheet 均被排除，请用 --sheet 显式指定。sheets: {all_sheets}")
    if len(candidates) > 1:
        print(f"[警告] 多个候选 sheet，自动选择第一个: {candidates[0]}，其余: {candidates[1:]}")
    return candidates[0]
```

### 已知产品 sheet 行为

| 产品 | Sheets | 选择结果 | 原因 |
|---|---|---|---|
| 1803 | `['Sheet1']` | `Sheet1` | 唯一 sheet |
| 919A | `['费率表', '次标准体费率表']` | `费率表` | 命中优先规则 |
| 1568 | `['费率表', '次标准体加费费率表']` | `费率表` | 命中优先规则 |

---

## 两种模板结构

### 模板 A（1803）：性别外层，缴费期内层

```
Row5: [empty, 年龄(merged R5:R6), 男性(merged C5:I5), ..., 女性(merged J5:P5), ...]
Row6: [empty, empty,  趸交, 3年交, 5年交, 10年交, 15年交, 20年交, 30年交,  趸交, 3年交, ..., 20年交]
Row7+: [empty, age,  rate, rate, rate, ...]
```

解析方式：
1. 读 Row5 的 merged cell ranges，确定哪些列属于"男性"、哪些属于"女性"
2. 读 Row6 各列的缴费期文本
3. 组合 → 每列对应 `(gender, pay_period)`

注意：
- "一次性付清" = 趸交（使用 `PAYMENT_YEARS_NORMALIZATION_MAP` 归一）
- 某些年龄+性别+缴费期组合值为空/"-" → 跳过该行（不输出）

### 模板 C/D（919A/1568）：缴费期外层，性别内层

```
Row6: [empty, 交费期/年龄(merged R6:R7), 趸交(merged C6:D6), ..., 20年交(merged K6:L6)]
Row7: [empty, empty, 男性, 女性, 男性, 女性, ...]
Row8+: [empty, age, rate, rate, ...]
```

解析方式：
1. 读 Row6 的 merged cell ranges，确定每对列的缴费期
2. 读 Row7 各列的性别文本
3. 组合 → 每列对应 `(pay_period, gender)`

---

## 输出行格式（与 parse_processed_rate.py 一致）

每个数据点输出一行 dict，关键字段：

```python
{
    "product_id": str,           # 传入参数
    "age": int,                  # 投保年龄
    "gender": int,               # 10=女, 11=男
    "pay_time": int,             # 趸交=0, N年交=N, 交至X周岁=X
    "pay_time_type": int,        # 趸交=12, N年交=10, 交至X周岁=11
    "insure_period": int,        # 终身=999（重疾险固定）
    "period_type": int,          # 终身=14（重疾险固定）
    "rate": float,               # 原始费率值（per 1000元）
    "pay_type": int,             # 趸交=0, 其他=12（年交）
    "amount": int,               # 默认 1000
    "company_id": str,           # 传入参数
    "company_name": str,         # 传入参数
    "product_name": str,         # 传入参数
    "rate_unit": str,            # "per_1000_amount"
    "source_type": str,          # "raw_rate"
    "source_file": str,          # 文件路径
}
```

**重要**：三款均为终身险，`insure_period=999, period_type=14` 固定写死。

---

## 关键实现细节

### 读 merged cell 范围

```python
from openpyxl import load_workbook

def get_merged_value_map(ws, row_num: int) -> dict[int, str]:
    """
    返回 {col_index: value}，已展开 merged cell（合并单元格内所有列都映射到同一值）。
    col_index 从 1 开始（openpyxl 规范）。
    """
    # 先读该行所有非None的值（只有合并区域左上角有值）
    raw = {cell.column: cell.value for cell in ws[row_num] if cell.value is not None}

    # 找出该行涉及的合并区域，展开到每一列
    result = {}
    for merged_range in ws.merged_cells.ranges:
        if merged_range.min_row <= row_num <= merged_range.max_row:
            # 取左上角值
            top_left_val = ws.cell(merged_range.min_row, merged_range.min_col).value
            if top_left_val is not None:
                for col in range(merged_range.min_col, merged_range.max_col + 1):
                    result[col] = top_left_val

    # 合并：优先使用展开的 merged 值，其次用原始值
    for col, val in raw.items():
        if col not in result:
            result[col] = val

    return result
```

### 检测模板类型

```python
def detect_template(ws) -> str:
    """
    A: Row5 中含 "男性"/"女性"（性别在外层）
    C: Row6 中含 "趸交"/"年交"（缴费期在外层，Row6 有 merged）
    """
    row5_vals = set(str(v).strip() for v in ws[5] if v.value)
    if "男性" in row5_vals or "女性" in row5_vals:
        return "A"
    return "C"
```

### 跳过无效行规则

- 年龄列（B列）值为 None、非数字、或是附注文本（如"月交保险费=..."）→ 跳过整行
- 费率值为 None、"-"、空字符串 → 跳过该单元格（不输出该行）
- 费率值无法转为 float → 跳过

### 同义词归一（直接调用已有 dict）

```python
from rate_standardization.rate_field_dicts import (
    PAYMENT_YEARS_NORMALIZATION_MAP,
    GENDER_NORMALIZATION_MAP,
    encode_payment_years,
)
```

- "一次性付清" → PAYMENT_YEARS_NORMALIZATION_MAP → "趸交" → encode_payment_years → (0, 12)
- "男性" → GENDER_NORMALIZATION_MAP → 11
- "女性" → GENDER_NORMALIZATION_MAP → 10

---

## 函数签名设计

```python
def parse_raw_rate(
    path: Path,
    product_id: str,
    company_id: str,
    company_name: str,
    product_name: str,
    sheet_name: str | None = None,   # None=第一个sheet（919A 需跳过次标准体）
) -> dict[str, Any]:
    """
    返回与 parse_processed_rate 相同结构：
    {
        "source_file": str,
        "row_count": int,
        "rows": [dict, ...],
        "preview_rows": [dict×5],
        "template_type": "A" | "C",
        "missing_note": str | None,  # 如有无法解析的情况
    }
    """
```

---

## main() CLI 入口

```bash
python -m development.rate_standardization.parse_raw_rate \
  --input ~/Desktop/.../1803-费率表.xlsx \
  --product-id 1170004238 \
  --company-id 155 \
  --company-name "中意人寿" \
  --product-name "中意悦享安康（悠享版）重大疾病保险" \
  --output /tmp/rate_1803_raw.json
```

---

## 验收标准

> **注意**：DB 中这 3 款产品的行数（1803=532, 919A=3010, 1568=2772）远超主险费率表行数，
> 因为 DB 包含次标准体加费数据。本脚本**只解析标准体主险费率表**，不与 DB 总行数对比。

### 1803

```bash
python -m development.rate_standardization.parse_raw_rate \
  --input "~/Desktop/开发材料/10款重疾/1803-中意悦享安康（悠享版）重大疾病保险/1803-中意悦享安康（悠享版）重大疾病保险-费率表.xlsx" \
  --product-id 1170004238 --company-id 155 --company-name "中意人寿" \
  --product-name "中意悦享安康（悠享版）重大疾病保险" --output /tmp/rate_1803.json
```

检查：
- [ ] `row_count` > 0，粗估范围 480–559（男43×7 + 女43×6，高龄部分缺档）
- [ ] 无 `payment_years`/`insurance_period` 字段
- [ ] `insure_period=999, period_type=14` 所有行
- [ ] 趸交行：`pay_time=0, pay_time_type=12, pay_type=0`
- [ ] 非趸交行：`pay_time_type=10, pay_type=12`
- [ ] age=18, 男性, 趸交 费率 ≈ 2786.0

### 919A

```bash
python -m development.rate_standardization.parse_raw_rate \
  --input "~/Desktop/开发材料/10款重疾/919A-招商信诺爱享无忧重大疾病保险/919A-招商信诺爱享无忧重大疾病保险-费率表.xlsx" \
  --product-id 1010003919 --company-id 161 --company-name "招商信诺" \
  --product-name "招商信诺爱享无忧重大疾病保险" --sheet "费率表" --output /tmp/rate_919A.json
```

检查：
- [ ] `row_count` = 51×5×2 = **510**（51个年龄 × 5缴费期 × 2性别，无缺档）
- [ ] 次标准体 sheet 未被解析
- [ ] `insure_period=999, period_type=14` 所有行
- [ ] age=0, 男性, 趸交 费率 ≈ 165.45

### 1568

```bash
python -m development.rate_standardization.parse_raw_rate \
  --input "~/Desktop/开发材料/10款重疾/1568-招商信诺爱享未来少儿重大疾病保险A款/1568-招商信诺爱享未来少儿重大疾病保险A款-费率表.xlsx" \
  --product-id 1010004001 --company-id 161 --company-name "招商信诺" \
  --product-name "招商信诺爱享未来少儿重大疾病保险A款" --sheet "费率表" --output /tmp/rate_1568.json
```

检查：
- [ ] `row_count` = 18×6×2 = **216**（18个年龄 × 6缴费期 × 2性别，无缺档）
- [ ] 次标准体加费费率表 sheet 未被解析
- [ ] age=0, 男性, 趸交 费率 ≈ 206.56

---

## 文件位置

- 新建文件：`~/codex-openai/development/rate_standardization/parse_raw_rate.py`
- 依赖（已存在）：`rate_standardization/rate_field_dicts.py`（包含 encode_payment_years, encode_insurance_period, GENDER_NORMALIZATION_MAP 等）
- 测试输出：`/tmp/rate_1803.json`, `/tmp/rate_919A.json`, `/tmp/rate_1568.json`

---

## 注意事项

1. **不要修改** `rate_field_dicts.py`，直接 import 使用
2. 919A 的 `sheet_name` 默认传 "费率表"（显式跳过"次标准体费率表"）
3. 1803 最后几个年龄段某些缴费期可能无费率（"-"或None） → 跳过，不报错
4. 1803 数据行从 Row7 开始；919A/1568 数据行从 Row8 开始
5. 不需要处理 1578（另立专项）
