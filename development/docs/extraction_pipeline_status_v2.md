# 抽取管道现状 V2（2026-03-28）

更新自：extraction_pipeline_status_v1.md（V12 基线，2026-03-27）

---

## 管道架构

```
原始 PDF（条款/说明书/费率表）
    ↓
blocks 解析（_blocks.json）
    ↓
extract_tier_a_rules.py（规则提取 + 费率表 XLSX/PDF 读取）
    ↓
tier_a_rule_candidates_v2.json
    ↓
merge_candidates.py（补充 rate_table_candidates 交费期间）
    ↓
tier_a_merged_candidates_v1.json
    ↓
eval_tier_a.py（对照 gold）
    ↓
tier_a_eval_v18.json
```

---

## 关键脚本清单

- `extract_tier_a_rules.py`：从条款/说明书 blocks + 原始费率表（XLSX/PDF）提取 Tier A 候选
- `merge_candidates.py`：透传规则候选（rate_table_candidates_v1.json 已于 2026-03-28 从主链移除）
- `eval_tier_a.py`：评估候选与 gold 的匹配，输出 hit/miss/mismatch
- `run_blind_test_v1.py`：blind test 主链路
- `eval_blind_test_v1.py`：blind test 评估

---

## 已生成说明书 blocks

- `1578_说明书_blocks.json`
- `851A_说明书_blocks.json`
- `864_说明书_blocks.json`
- `919A_说明书_blocks.json`

---

## V18 评测基线（2026-03-28，8产品含889，排除1548A，rate_table_candidates已清除）

| 字段 | hit | miss | mismatch | hit_rate |
|------|-----|------|----------|---------|
| 重疾数量 | 8 | 0 | 0 | **100%** |
| 等待期 | 8 | 0 | 0 | **100%** |
| 等待期（简化）| 8 | 0 | 0 | **100%** |
| 犹豫期 | 7 | 1 | 0 | 87.50% |
| 保险期间 | 7 | 1 | 0 | 87.50% |
| 交费期间 | 7 | 1 | 0 | 87.50% |
| 宽限期 | 7 | 1 | 0 | 87.50% |
| 重疾赔付次数 | 7 | 1 | 0 | 87.50% |
| 重疾分组 | 7 | 1 | 0 | 87.50% |
| 投保年龄 | 6 | 2 | 0 | 75.00% |
| 交费频率 | 6 | 0 | 2 | 75.00% |

已知 miss/mismatch 说明见：`eval_known_acceptable_misses_v1.md`

---

## 各字段当前状态

| 字段 | 来源 | 状态 |
|------|------|------|
| 等待期 | 条款 blocks | 稳定 |
| 等待期（简化）| 条款 blocks | 稳定 |
| 宽限期 | 条款 blocks | 稳定，889 miss（碎片化） |
| 犹豫期 | 条款 blocks | 稳定，1464 miss（条款无此内容） |
| 保险期间 | 条款 blocks | 稳定，889 miss（合同载明） |
| 重疾赔付次数 | 条款 blocks | 稳定，889 miss（碎片化） |
| 重疾分组 | 条款 blocks | 稳定，889 空字符串 |
| 重疾数量 | 条款 blocks / 附录序号计数 | 100%，889 碎片化兜底规则已生效 |
| 交费期间 | 条款/说明书/原始费率表XLSX/PDF | 稳定，889 miss（进行中：PDF 提取器开发）|
| 投保年龄 | 条款/说明书 blocks | 1568/889 miss（非标天数格式）|
| 交费频率 | 条款 blocks / 推断规则 / 原始XLSX | 1803/889 mismatch（核保规则本地无）|

---

## 当前进行中工作

1. **费率表 PDF 提取器**（`extract_rate_table_from_pdf.py`）
   - 替代手工 `rate_table_candidates_v1.json`
   - 覆盖格式 A（列式：851A/1134）和格式 B（行式：889）
   - 目标：交费期间、保险期间、交费频率从原始 PDF 自动提取

2. **889 剩余字段兜底**
   - 宽限期（跨 block）、重疾赔付次数（碎片化）、重疾分组（空字符串）

3. **1548A eval 接入**
   - 前提：交费期间/交费频率/重疾赔付次数 规则覆盖

---

## 技术债

| 项目 | 描述 | 优先级 |
|------|------|--------|
| `rate_table_candidates_v1.json` | 手工文件，需替换为 PDF 提取自动生成 | P1（费率表 PDF 提取器完成后） |
| `extraction_pipeline_status_v1.md` | 已过期（V12 基线），由本文件替代 | 已处理 |
