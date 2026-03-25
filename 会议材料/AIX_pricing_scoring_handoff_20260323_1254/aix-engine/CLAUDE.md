# AIX 保险智能体 — Claude Code 项目规范

> 本文件由项目 PM 维护，Claude Code 进入此项目目录后自动加载。
> 所有开发任务必须在此约束框架内执行，不得绕过。

---

## 一、项目概况

**项目名称：** AIX 保险智能体
**代码库：** `~/code/aix-engine/`
**当前阶段：** 一期 — 重疾险主链路跑通（内部试运行）
**最终目标：** 全险种、全能力保险智能体

**主文档（必读）：**
- 开发规范：`docs/AIX智能体需求与开发文档-v4.1.md`
- 一期范围：`/Users/zqf-openclaw/codex-openai/AIX一期正式开发范围与实施计划_V1.md`

**定价评分模块专项文档：**
- `docs/AIX产品定价工具开发文档-v1.2.md`
- `docs/精算移交说明.md`
- `docs/精算核对清单.md`

---

## 二、技术栈速览

| 服务 | 技术 | 端口 |
|------|------|------|
| 前端 | React 18 + TypeScript + Vite + Tailwind CSS v3 + Zustand | — |
| BFF | Node.js + Express | 3001 |
| AI 服务 | Python 3.11 + FastAPI + Kimi API（Function Calling × 6） | 8000 |
| 精算服务 | Java 17 + Spring Boot | 8080 |
| 数据库 | MySQL 8.0 | 3306 |
| 反向代理 | Nginx | 80 |
| 容器化 | Docker Compose | — |

**数据库口径（全文统一）：**
- 产品主数据：`my_ensure.cmb_product`（不是 `aix_engine.products`）
- 业务数据：`aix_engine.*`（需求分析、记忆、问题上报等）

---

## 三、定价评分模块核心文件

```
aix-ai-service/app/services/
  product_scorer.py     ← 7维度评分引擎（核心）
  product_search.py     ← 产品检索，连接 my_ensure.cmb_product
  needs_analysis.py     ← 需求报告 + 预算测算

aix-actuarial-service/src/main/java/com/aix/actuarial/service/
  ActuarialPricingEngine.java  ← PVFB/GP 精算定价公式

db/migration/
  06-actuarial-tables.sql  ← 精算表结构
  07-actuarial-data.sql    ← 死亡率表 + 重疾发生率表
```

**一期精算链路卡点：**
`actuarial_qx_table` / `actuarial_ci_table` / `product_actuarial_config` 三张表需要有数据，
数据来源：`docs/actuarial-data.js`（195KB），由精算同事负责生成 SQL 并导入。

**验收标准：**
```
GET /api/v1/actuarial/fair-price?productId=XX&age=35&gender=male
→ {"errorCode":"OK","fairPremium":7xxx}
偏差 < 5%（对照 docs/insurance-product-tool.html v1.2 工具）
```

---

## 四、研发治理原则（每次开发必须遵守）

### 核心约束

1. **模型不是业务真相来源。** 保险推荐、定价、评分必须基于真实产品数据、精算规则和明确配置，不能靠大模型自由生成。
2. **规则优先于模型自由生成。** 评分权重、产品筛选条件、精算公式均有明确实现，不得用通用知识替代。
3. **同一业务规则只能有一个主实现。** 禁止在多处重复实现评分逻辑、预算逻辑或产品检索逻辑。
4. **不允许把预留接口写成已实现能力。** 一期仅支持重疾险，非重疾险字段为后续预留，不能在推荐结果中输出。
5. **修复问题时必须同步删除废弃代码。** 不允许留下"临时但已接入主链路"的长期代码。

### 险种边界（一期硬约束）

| 险种 | 一期状态 |
|------|---------|
| 重疾险（aix_category_id=6001） | ✅ 当前支持 |
| 医疗险 / 寿险 / 增额终身寿 | 🔒 暂不支持，接口预留 |

**禁止对未收录险种估算保费或给出推荐，即使有通用知识也不能替代数据库数据。**

### 每次开发完成前的 8 项检查

1. 业务真相来源是否唯一（数据/规则/服务，不是模型猜测）
2. 数据模型是否支持真实业务，而不是只支持演示场景
3. 核心逻辑是否集中，而不是散落在 UI 事件中
4. 是否引入了重复口径或双轨逻辑
5. 修改后是否清理了无用代码
6. 文档、实现、测试是否同步更新
7. 主链路是否被真实测试覆盖
8. 结果是否可解释、可复核、可追溯

---

## 五、SSE 事件协议（AI 服务 → 前端）

| event | 触发时机 | payload 说明 |
|-------|---------|-------------|
| `chunk` | AI 流式文字输出 | `{text}` |
| `options` | 需要用户选择 | `{options:[]}` |
| `route_options` | 用户提规划类意图 | `{route_options:[{label,action,target}]}` |
| `needs_report` | 需求报告完成 | `NeedsReportSummary` |
| `product_recommendations` | 推荐结果 | `{top3,conclusion,risk_notes,budget_allocation}` |
| `done` | 对话结束 | — |
| `error` | 出错 | `{message}` |

---

## 六、前端推荐结果（7张卡片，顺序固定）

| # | 组件 | 内容 |
|---|------|------|
| 1 | `NeedsReportCard` | 用户画像摘要（折叠/展开） |
| 2 | `RecommendationCard`（首推） | 产品卡：排名 + 亮点标签 + 保费 + 性价比 + 评分条 |
| 3 | `RecommendationCard`（次选） | 同上 |
| 4 | `RecommendationCard`（备选） | 同上 |
| 5 | `ProductCompareCard` | 7维度横向对比（可滑动） |
| 6 | `RecommendationConclusionCard` | 选购建议 + 预算分配 |
| 7 | `RiskDisclosureCard` | 风险说明 |

---

## 七、注意事项

- **collation 问题：** `cmb_product.product_id` = `utf8mb4_general_ci`，其他表 = `utf8mb4_unicode_ci`，JOIN 必须加 `COLLATE utf8mb4_unicode_ci`
- **费率存储：** 费率值 × 10000 存储，使用时需除以 10000
- **Docker 重启后 nginx DNS 缓存失效：** 执行 `docker compose exec nginx nginx -s reload`
- **TypeScript 严格模式：** `noUnusedLocals: true`，`noUnusedParameters: true`，提交前运行 `npx tsc --noEmit`
