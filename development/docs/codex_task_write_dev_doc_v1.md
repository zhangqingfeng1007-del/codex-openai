# Codex 任务：撰写原始文件解析器开发文档

任务类型：文档撰写（非代码实现）
交付物：`development/docs/raw_parser_dev_doc_v1.md`
参考材料：`development/docs/raw_parser_architecture_v1.md`（架构设计稿）
审查方：Claude

---

## 任务说明

请根据架构设计稿，撰写一份面向开发者的完整开发文档。

文档对象是：实际动手写代码的开发者（可以是 Codex 自己）。
文档目标是：让开发者无需再问"这个怎么做"，拿到文档就能开始写代码。

---

## 文档结构要求

文档必须包含以下章节，顺序如下：

---

### 第 1 章：模块总览

用一张表列出 Phase 1 的所有模块：

| 模块文件名 | 职责一句话 | 输入 | 输出 | 依赖的现有脚本 |
|-----------|-----------|------|------|--------------|

---

### 第 2 章：数据契约（最重要的章节）

定义所有模块之间传递的数据格式，不能有歧义。

#### 2.1 blocks.json（升级后）

给出完整的 JSON 示例（真实字段，不用省略号），包含：
- `_meta` 顶层字段：product_id, doc_category, source_file, parse_method, parse_quality, char_count, page_count, generated_at
- `blocks` 数组：每个 block 的完整字段

#### 2.2 structured_table.json

给出完整的 JSON 示例，包含：
- `_meta` 顶层字段
- `tables` 数组：schema + rows 完整示例（用真实的费率表字段名）
- `extracted_fields`：pay_periods, pay_frequencies 的完整示例值

#### 2.3 manifest.json（build_product_manifest 输出）

给出完整的 JSON 示例，一条产品条目的完整结构。

#### 2.4 向后兼容说明

明确说明：现有 blocks.json（纯数组格式）如何被下游脚本兼容读取。

---

### 第 3 章：各模块接口规范

对每个模块，写明：

#### 3.x `{module_name}.py`

**CLI 用法**（完整命令行示例，包含所有参数）

**核心函数签名**（Python 类型注解，不需要实现，只需要签名 + docstring）

**处理流程**（编号步骤，每步一句话，不超过 8 步）

**异常处理规则**（什么情况下 exit(1)，什么情况下写 warnings 继续）

---

### 第 4 章：路由规则完整表

写出完整的 (后缀, doc_category, parse_quality) → extractor 三维路由表，覆盖所有已知组合。

对 Phase 1 不支持的组合（如扫描件），明确标注"Phase 2"或"不支持，跳过"。

---

### 第 5 章：常量与关键词表

列出所有模块共用的常量，集中定义，避免各模块重复硬编码：

- `DOCUMENT_TYPE_RULES`：文件名关键词 → doc_category 映射
- `PROCESSED_FLAGS`：处理结果文件特征词列表
- `SUPPORTED_EXTENSIONS`：支持的文件后缀集合
- `PAY_PERIOD_ALIASES`：趸交别名表（一次性付清、一次交清 等 → 趸交）
- `PAY_FREQ_ORDER`：交费频率标准排序

这些常量建议放在一个公共文件 `constants.py` 或直接在文档中标注"建议每模块各自定义，保持一致"。

---

### 第 6 章：依赖说明

列出 Phase 1 各模块依赖的第三方库：

| 库名 | 版本要求 | 用途 | 若缺失的降级行为 |
|------|---------|------|--------------|

重点说明：pdfplumber、openpyxl、fitz（PyMuPDF）三个库的降级策略——任何一个缺失时脚本应该怎么跑（不能直接崩溃）。

---

### 第 7 章：验收测试清单

写出每个模块的验收命令和预期输出，格式：

```bash
# 模块名：验收命令
python scripts/xxx.py --input ... --output ...
# 预期：...
```

最终整合验收：
```bash
# 完整链路跑通，eval V19 = V18
```

---

## 写作要求

1. **必须使用真实值**：JSON 示例中用真实的产品 ID（如 889）、真实的文件名、真实的字段值，不用 `"..."` 占位
2. **必须完整**：不能有"详见其他文档"的引用跳转，本文档自包含
3. **不写废话**：不写"本文档旨在..."这类套话，直接进入内容
4. **格式**：Markdown，表格对齐，代码块标注语言类型

---

## 参考信息

现有脚本的关键入口（Codex 可直接读取验证）：

- `parse_md_blocks.py`：`main()` 接收 `--input`（Markdown 文件）+ `--output`（JSON）+ `--product-id`
- `extract_tier_a_rules.py`：`main()` 接收 manifest + output + 可选 `--blocks-dir`
- `locate_rate_xlsx(item)`：在 extract_tier_a_rules.py 第 337 行，从 item dict 查找 XLSX
- `extract_pay_info_from_rate_pdf(item)`：第 377 行，用 fitz 提取文本后 regex 匹配年数
- `extract_pay_frequency_from_rate_xlsx(item)`：第 422 行，用 openpyxl 读 tail 30 tokens

rate_table_extractor.py 需要覆盖并取代上述三个函数的功能。

现有 blocks.json 示例路径：`data/blocks/889_blocks.json`（纯数组格式，无 `_meta`）
现有 manifest 示例路径：`data/manifests/sample_manifest.json`
