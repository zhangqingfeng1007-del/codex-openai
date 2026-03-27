# Codex 执行指令：费率解析器编码层修复 V1

## 背景

`parse_processed_rate.py` 已实现并完成最小验证（产品 1010003676 输出 618 行，与 DB 行数一致）。

但发现关键编码缺口：解析器输出**字符串**，DB 存储**整数编码**，需要修复才能真正入库。

---

## DB 实际字段结构（已通过 DESCRIBE + 枚举查询确认）

`cmb_product_rate` 表中的保险期间和缴费期间，**不是**字符串字段，而是双字段整数编码：

### 保险期间（insurance_period → 拆分为两个字段）

| period_type | insure_period | 含义 |
|---|---|---|
| 10 | N (1–100) | N年，如 30年 → (30, 10) |
| 11 | N (月数) | N月（较少见） |
| 13 | X (周岁) | 至X周岁，如 至70周岁 → (70, 13) |
| 14 | 999 | 终身（唯一组合）→ (999, 14) |

### 缴费期间（payment_years → 拆分为两个字段）

| pay_time_type | pay_time | 含义 |
|---|---|---|
| 10 | N (年数) | N年交，如 20年交 → (20, 10) |
| 11 | X (周岁) | 交至X周岁，如 交至60周岁 → (60, 11) |
| 12 | 0 | 趸交（唯一组合）→ (0, 12) |

---

## 当前问题（两处）

### 问题1：`rate_field_dicts.py` 中 `INTERNAL_TO_DB_FIELD` 映射错误

当前错误映射：
```python
"payment_years": "payment_years",      # ❌ DB 无此字段
"insurance_period": "insurance_period", # ❌ DB 无此字段
```

DB 实际字段名：`pay_time`, `pay_time_type`, `insure_period`, `period_type`

### 问题2：`parse_processed_rate.py` 输出字符串而非整数

当前输出（错误）：
```python
"payment_years": "趸交"      # ❌ 字符串
"insurance_period": "终身"   # ❌ 字符串
```

应输出：
```python
"pay_time": 0,        "pay_time_type": 12  # ✅ 趸交
"insure_period": 999, "period_type": 14    # ✅ 终身
```

---

## 修复任务

### 任务1：在 `rate_field_dicts.py` 中新增两个编码函数

在文件末尾追加以下内容：

```python
import re as _re


def encode_payment_years(value: str) -> dict[str, int]:
    """
    将标准化后的缴费期间字符串编码为 DB 整数字段对。

    返回 {"pay_time": int, "pay_time_type": int}

    规则：
    - "趸交" → (0, 12)
    - "交至X周岁" → (X, 11)
    - "N年交" → (N, 10)
    """
    if value == "趸交":
        return {"pay_time": 0, "pay_time_type": 12}
    if "交至" in value:
        m = _re.search(r"(\d+)", value)
        age = int(m.group(1)) if m else 0
        return {"pay_time": age, "pay_time_type": 11}
    m = _re.search(r"(\d+)", value)
    n = int(m.group(1)) if m else 0
    return {"pay_time": n, "pay_time_type": 10}


def encode_insurance_period(value: str) -> dict[str, int]:
    """
    将标准化后的保险期间字符串编码为 DB 整数字段对。

    返回 {"insure_period": int, "period_type": int}

    规则：
    - "终身" → (999, 14)
    - "至X周岁" → (X, 13)
    - "N年" → (N, 10)
    """
    if value == "终身":
        return {"insure_period": 999, "period_type": 14}
    if "周岁" in value:
        m = _re.search(r"(\d+)", value)
        age = int(m.group(1)) if m else 0
        return {"insure_period": age, "period_type": 13}
    m = _re.search(r"(\d+)", value)
    n = int(m.group(1)) if m else 0
    return {"insure_period": n, "period_type": 10}
```

同时，将 `INTERNAL_TO_DB_FIELD` 中的错误映射删除或注释：
```python
# 删除或注释以下两行（DB 无此字段，已拆分为 pay_time/pay_time_type/insure_period/period_type）
# "payment_years": "payment_years",
# "insurance_period": "insurance_period",
```

---

### 任务2：修改 `parse_processed_rate.py` 中的 `to_db_row` 函数

修改 import 部分，新增两个编码函数：
```python
from rate_standardization.rate_field_dicts import (
    ...
    encode_payment_years,       # 新增
    encode_insurance_period,    # 新增
    ...
)
```

修改 `to_db_row` 函数中的字段构建（替换两行）：

删除：
```python
"payment_years": normalize_payment_years(cell(row, header_index, "缴费期间")),
"insurance_period": normalize_insurance_period(cell(row, header_index, "保险期间")),
```

替换为：
```python
**encode_payment_years(normalize_payment_years(cell(row, header_index, "缴费期间"))),
**encode_insurance_period(normalize_insurance_period(cell(row, header_index, "保险期间"))),
```

即：先用现有 normalize 函数将原始字符串标准化为统一格式（如 "趸交", "30年交", "终身", "至70周岁"），再用新编码函数转为整数对。

---

## 验收标准

修复后，运行：
```bash
cd ~/codex-openai
python -m development.scripts.parse_processed_rate \
  --input ~/Desktop/开发材料/招行数据文件夹/（1010003676的结果费率表路径）.xlsx \
  --output /tmp/rate_1010003676_encoded.json
```

检查 `preview_rows[0]` 中应出现：

| 字段 | 预期值 | 说明 |
|---|---|---|
| `pay_time` | 整数，如 0 / 5 / 10 / 20 | 趸交=0，N年交=N |
| `pay_time_type` | 整数，如 10 / 12 | 年交=10，趸交=12 |
| `insure_period` | 整数，如 999 / 30 | 终身=999，N年=N |
| `period_type` | 整数，如 10 / 14 | 年=10，终身=14 |
| **不出现** | `payment_years` | 旧字符串字段已删除 |
| **不出现** | `insurance_period` | 旧字符串字段已删除 |

行数应仍为 618（不因编码变更而改变行数）。

---

## 文件位置

- 修改文件1：`~/codex-openai/development/rate_standardization/rate_field_dicts.py`
- 修改文件2：`~/codex-openai/development/rate_standardization/parse_processed_rate.py`
- 测试输入：`~/Desktop/开发材料/招行数据文件夹/` 下 1010003676 的结果费率表（Codex 自行确认路径）
- 测试输出：`/tmp/rate_1010003676_encoded.json`（临时验证用）

---

## 注意事项

1. 两个编码函数依赖**已经标准化**的字符串输入（即经过 PAYMENT_YEARS_NORMALIZATION_MAP / INSURANCE_PERIOD_NORMALIZATION_MAP 处理后的值），不要绕过 normalize 步骤直接接原始 Excel 值
2. `normalize_payment_years` 有两个中文变体兼容（缴费期间/交费期间），保持不变
3. 如果 normalize 后仍有未覆盖的字符串（如 "交至30周岁" 在 PAYMENT_YEARS_NORMALIZATION_MAP 中已有），`encode_payment_years` 的 "交至" 分支会正确处理
4. DATABASE_DEFAULTS 中的 `payment_years` / `insurance_period` 默认值也需要相应删除或不再使用（避免 setdefault 把旧字段写回去）
