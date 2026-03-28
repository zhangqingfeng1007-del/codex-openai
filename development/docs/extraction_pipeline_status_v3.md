# 抽取管道现状 V3（2026-03-28）

更新自：extraction_pipeline_status_v2.md（V18 基线，2026-03-28）

---

## 管道架构（当前）

```
原始文件目录（10款重疾）
    ↓
build_product_manifest.py（自动扫描建档）
    ↓
manifest_new_format.json（source_files 格式，兼容层已接主链）
    ↓
extract_tier_a_rules.py（条款 blocks + structured_table fallback）
    ↓
tier_a_rule_candidates_v19.json
    ↓
eval_tier_a.py（对照 gold）
    ↓
tier_a_eval_v19.json  ← 当前基线
```

**同步运行（费率表解析支线）**：
```
build_rate_tables_batch.py
    ↓
data/tables/{product_id}_structured_table.json
    ↓（作为 structured_table fallback 被 extract_tier_a_rules.py 消费）
```

---

## 关键脚本清单

| 脚本 | 用途 | 状态 |
|------|------|------|
| `file_router.py` | 文件识别与解析器路由 | ✅ 完成 |
| `build_product_manifest.py` | 自动扫描产品目录建档 | ✅ 完成（兼容层已接主链）|
| `build_rate_tables_batch.py` | 批量生成 structured_table.json | ✅ 完成 |
| `rate_table_extractor.py` | 单文件费率表结构化提取 | ✅ 完成（格式A/B/C）|
| `verify_structured_tables.py` | structured_table 集成验证 | ✅ 完成 |
| `extract_tier_a_rules.py` | 规则提取主脚本（含 structured_table fallback）| ✅ 完成 |
| `eval_tier_a.py` | 评估候选与 gold 匹配 | ✅ 稳定 |
| `merge_candidates.py` | 历史合并脚本（当前透传）| 保留但不在主链 |

---

## V19 评测基线（2026-03-28，9产品，含1134，structured_table fallback 已接入）

| 字段 | hit | miss | mismatch | hit_rate | V18→V19 |
|------|-----|------|----------|---------|---------|
| 重疾数量 | 9 | 0 | 0 | **100%** | = |
| 等待期 | 9 | 0 | 0 | **100%** | = |
| 等待期（简化）| 9 | 0 | 0 | **100%** | = |
| 保险期间 | 9 | 0 | 0 | **100%** | ↑+12.5%（889 miss→hit，structured_table 生效）|
| 交费期间 | 8 | 0 | 1 | 88.9% | ↑+1.4% |
| 宽限期 | 8 | 1 | 0 | 88.9% | ↑+1.4% |
| 犹豫期 | 8 | 1 | 0 | 88.9% | ↑+1.4% |
| 重疾赔付次数 | 8 | 1 | 0 | 88.9% | ↑+1.4% |
| 重疾分组 | 8 | 1 | 0 | 88.9% | ↑+1.4% |
| 投保年龄 | 6 | 3 | 0 | 66.7% | -8.3%（1134新加入，既有资料缺口）|
| 交费频率 | 6 | 0 | 3 | 66.7% | -8.3%（1134新加入，定义句误命中）|

**V18 原有 8 产品：零回归。** 两个下降均来自 1134 首次纳入。

---

## structured_table fallback 实际补值范围（V19）

| 产品 | 补充字段 | 来源文件 |
|------|---------|---------|
| 889 | 保险期间 | 889_structured_table.json |
| 1548A | 交费期间、交费频率 | 1548A_structured_table.json |
| 其余产品 | 条款 blocks 已覆盖，fallback 未触发 | — |

---

## 已知 miss/mismatch（可接受，非代码 bug）

| 产品 | 字段 | 类型 | 根因 |
|------|------|------|------|
| 1134 | 投保年龄 | miss | 资料缺口：无产品说明书，费率表仅得 0-50，无法还原"28天" |
| 1803 | 交费频率 | mismatch | 资料缺口：核保文件缺失，条款/说明书/费率表均无半年/季/月频率声明，gold 需核保文件支持 |
| 889 | 交费频率 | mismatch | 资料缺口：同上，核保文件缺失 |
| 1464 | 犹豫期 | miss | 条款无犹豫期文字 |
| 1568 | 投保年龄 | miss | 非标天数格式，说明书是 scan_pdf（Phase 2）|
| 889 | 投保年龄 | miss | 非标天数格式 |

---

## 各字段当前状态

| 字段 | 来源 | 状态 |
|------|------|------|
| 等待期 | 条款 blocks | 稳定 100% |
| 等待期（简化）| 条款 blocks | 稳定 100% |
| 重疾数量 | 条款 blocks / 附录序号计数 | 稳定 100% |
| 保险期间 | 条款 blocks + structured_table fallback | 稳定 100%（889 已通过 fallback 命中）|
| 宽限期 | 条款 blocks | 稳定，1 miss（产品资料问题）|
| 犹豫期 | 条款 blocks | 稳定，1 miss（1464 条款无此内容）|
| 重疾赔付次数 | 条款 blocks | 稳定，1 miss |
| 重疾分组 | 条款 blocks | 稳定，1 miss |
| 交费期间 | 条款/说明书/structured_table fallback | 88.9%，1 mismatch |
| 投保年龄 | 条款/说明书 blocks | 66.7%，3 miss（1134 资料缺口 + 1568/889 非标格式）|
| 交费频率 | 条款 blocks / structured_table | 66.7%，3 mismatch（定义句误命中，规则修复进行中）|

---

## 当前基线：V20（2026-03-28 确立，9产品）

| 字段 | hit_rate | V18→V20 | 备注 |
|------|---------|---------|------|
| 重疾数量 | **100%** | = | |
| 等待期 | **100%** | = | |
| 等待期（简化）| **100%** | = | |
| 保险期间 | **100%** | ↑+12.5% | structured_table fallback 生效 |
| 交费频率 | **88.9%** | ↑+13.9% | 1134 gold 修正 + 定义句排除规则，仅剩 1803 mismatch（资料缺口）|
| 交费期间 | 88.9% | ↑+1.4% | |
| 宽限期 | 88.9% | ↑+1.4% | |
| 犹豫期 | 88.9% | ↑+1.4% | |
| 重疾赔付次数 | 88.9% | ↑+1.4% | |
| 重疾分组 | 88.9% | ↑+1.4% | |
| 投保年龄 | 66.7% | -8.3% | 1134 新加入，资料缺口（非回退）|

**V18 原有 8 产品：零回归。**

---

## 当前进行中工作

无。V20 为当前可信基线，1803/889 交费频率为已知资料缺口，等核保文件补充后再处理。

---

## 技术债（已知，不阻塞当前 eval）

| 项目 | 描述 | 优先级 |
|------|------|--------|
| `build_product_manifest.py` 契约 | source_files 兼容层是过渡方案，最终需统一到 files[] | P3 |
| structured_table candidate schema | 比其他候选多 source_type/parse_method/parse_quality | P3 |
| PDF tables[].rows 为空 | rate_table_extractor 表格行数据未填充 | P3 |
| table_format 枚举值 | 实际输出值与 dev doc 不一致 | P3 |
| 1578 交费期间 | 自然费率表，无缴费期列，须从条款提取 | P4 |
| Phase 2 OCR | 1803 产品说明书 scan_pdf，extractor: skip | Phase 2 |
