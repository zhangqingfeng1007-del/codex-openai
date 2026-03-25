# AIX 保险智能体 — 完整开发规范 v4.1

> 本文档覆盖当前版本核心开发要求，是一期开发的主要参考文档。
> 个别基础设施细节（JWT/AES/会话管理）以现有工程实现为准，无需重新设计。
> 更新日期：2026-03-23
> 本次更新（v4.1）：增加目标分层（最终目标/一期范围/二期路线）、补全架构图、新增"一期实施顺序与后续开发任务"章节、
> 统一产品主数据口径（my_ensure.cmb_product）、修复推荐卡片数量（7张）与命名、修复章节编号乱序、
> 修复预算分配与险种边界冲突（by_coverage 标注一期/预留）、去除验收清单重复条目、
> 新增第八章对话过程可视化规范（7阶段+文案风格+一期最小实现）、章节重排（共 16 章）

---

## 第一章 项目背景与目标

### 1.0 目标分层（必读）

| 层级 | 说明 |
|------|------|
| **最终目标** | 全能力保险智能体：覆盖重疾险、医疗险、寿险、增额终身寿、分红险等全险种，服务个人用户和 B 端用户 |
| **一期范围** | 重疾险场景主链路跑通，验证核心对话架构、推荐链路、精算链路、卡片展示、移动端体验 |
| **一期定位** | 非目标收缩，而是实施顺序的第一步；一期架构必须支持后续险种扩展，不能建成重疾险专属系统 |

**一期明确不支持**（不代表系统不做，是后续阶段任务）：
- 非重疾险的产品推荐和保费测算
- 多次重疾险、增额终身寿、年金险
- B 端企业用户

**一期可以做到**：
- 对话中提到医疗险/寿险时，AI 可说明"属于后续保障优先级，当前仅支持重疾险精准推荐"
- 不得基于通用知识估算非重疾险保费，不得给出非重疾险产品推荐卡

---

### 1.5 智能体基础能力原则

AIX 的目标不是构建一个只能单次回答问题的保险问答工具，而是构建一个具备持续服务能力的保险智能体。为此，系统在架构设计上必须长期坚持以下三项基础能力原则：**记忆能力、规则能力、学习能力**。

#### 1.5.1 记忆能力

智能体必须具备持续记忆用户关键信息和对话结论的能力，而不是每一轮对话都从零开始。

**核心作用：**
- 记录用户基础画像（年龄、性别、家庭结构、预算、健康情况、已有保险）
- 记录阶段性对话摘要、历史推荐结论、重点风险提示
- 在后续对话中复用已知信息，减少重复追问，提高连续服务体验
- 为保障规划、保单分析、产品推荐提供跨会话上下文基础

**系统落点：**
- `memory_store.py` — 核心记忆和摘要记忆的读写
- `update_core_memory` 工具 — 对话过程中及时更新关键用户信息
- `save_recall_summary` 工具 — 对话阶段结束时保存总结

**原则要求：** 记忆能力是智能体长期服务能力的基础，不得退化为一次性会话工具；后续险种扩展、家庭保障规划、保单分析等能力，都应建立在统一记忆体系之上。

#### 1.5.2 规则能力

智能体必须在明确规则约束下行动，而不是依赖大模型自由发挥。

**核心作用：**
- 约束回答边界，避免超出数据库和系统能力范围编造答案
- 约束工具调用时机，确保需求分析、推荐、记忆写入、问题上报等动作可控
- 约束产品推荐逻辑，确保结果基于产品库、评分逻辑和精算能力，而非通用常识
- 约束风险披露口径，对当前不支持险种、数据不完整等状态如实说明

**系统落点：**
- `chat_engine.py` — 系统提示词、工具定义、行为约束规则
- `app/rules/` 目录 — 产品规则、数据规则、问题处理规则文件
- 需求分析、预算测算、产品检索、评分链路中的结构化约束逻辑

**原则要求：** 规则优先于模型自由生成；不得用通用知识替代数据库中的产品事实和精算结果；不得将预留能力描述为当前已支持能力。

#### 1.5.3 学习能力

智能体必须具备通过问题反馈持续改进能力边界的机制，而不是能力边界长期静止不变。

**核心作用：**
- 记录用户提问中当前无法回答的问题
- 记录数据库缺失的产品、险种、责任或规则缺口
- 将问题反馈转化为后续数据补录、规则修订、能力扩展任务
- 支撑系统从一期重疾险能力逐步演进为全能力保险智能体

**系统落点：**
- `report_issue` 工具 — 对超出能力范围、产品不在库中、当前版本暂不支持等情况静默记录
- 后续可结合问题台账、产品补录流程、规则更新流程形成闭环
- 二期及后续阶段应逐步将问题反馈与数据治理、规则维护、险种扩展排期打通

**原则要求：** 对无法覆盖的问题，系统必须诚实说明并进入反馈闭环；学习能力不是指模型自行训练，而是通过问题收集、规则更新、数据补录持续增强系统能力。

#### 1.5.4 三项能力与系统目标的关系

记忆能力、规则能力、学习能力共同构成 AIX 保险智能体区别于普通保险问答系统的核心基础设施：

| 能力 | 解决的问题 |
|------|----------|
| 记忆能力 | 是否能够持续理解同一个用户 |
| 规则能力 | 是否能够稳定、可信、可控地行动 |
| 学习能力 | 是否能够随着问题积累不断扩展能力边界 |

这三项能力应被视为系统长期有效演进的基础要求，而非可选优化项。无论后续扩展到医疗险、寿险、增额终身寿，还是开放 B 端能力，均应继续复用这一基础设计。

---

### 1.1 公司定位

保险科技公司，愿景"让普通人成为保险专家"。
核心资产：1万+款结构化保险产品数据库（责任/费率/现金价值/病种/核保规则）。

> **本项目不是从零构建保险数据，而是基于公司既有产品主数据、责任标准库和精算能力，分阶段建设保险智能体系统。**

### 1.2 产品定位（v4.0 收口）

**产品名称**：保险智能体
**产品定位**：以 AI 对话为核心的保险规划和推荐系统，而非流程式测算后台工具

核心体验原则（参考 ChatGPT 首页交互哲学）：
- 首页唯一焦点是"开始对话"
- 欢迎态：居中欢迎语 + 居中大输入框 + 快捷建议（位于输入框下方）
- 对话态：消息流 + 底部固定输入栏
- 极简首页，不出现流程导航式结构
- 任何规划类需求先走"二选一路由"，不直接进入长问卷

### 1.3 用户类型

| 类型 | 典型场景 | 当前阶段优先级 |
|------|---------|-------------|
| **个人用户** | 咨询保险知识、分析保险需求、获取保险产品推荐 | P0，第一阶段主要对象 |
| **企业用户（B端）** | 产品研发人员、销售人员 | P2，第二阶段开发 |

### 1.4 开发目标与分阶段策略

**一期（当前版本）— 重疾险主链路**
- 交互：文字 + 语音 + 图片识别三种输入
- 险种：重疾险（aix_category_id=6001）全量在售产品
- 能力：需求分析 → 产品检索 → 7维度评分 → 精算定价 → Top3卡片展示
- 端：桌面网页 + 手机网页（响应式）
- 目标：验证核心架构可用，内部试运行

**二期 — 扩展险种与能力**（一期完成后启动）
- 险种扩展顺序（按复杂度从低到高）：寿险/身故险 → 增额终身寿/分红险 → 百万医疗险
- 跨险种组合规划建议
- 保单 OCR 与体检分析深化

**长期目标 — 全能力保险智能体**
- 全险种覆盖，基于产品库的精准推荐
- B 端开放（产品研发人员、销售人员）
- 高并发支持、CDN、分库分表

---

## 第二章 系统架构

### 2.1 完整系统架构图

```
╔══════════════════════════════════════════════════════════════════════╗
║                        用户（浏览器）                                 ║
║  文字输入 / 语音输入（ASR）/ 图片上传                                  ║
╚════════════════════════╤═════════════════════════════════════════════╝
                         │ HTTP / SSE / WebSocket
╔════════════════════════▼═════════════════════════════════════════════╗
║                     Nginx 反向代理（:80）                             ║
║  /api/*  →  BFF     /health  →  BFF     其余  →  前端静态资源         ║
╚═══════╤════════════════════════════════════════════════╤═════════════╝
        │                                                │
╔═══════▼═══════════════════════╗       ╔═══════════════▼═════════════╗
║   前端 React SPA（Vite）       ║       ║  BFF  Node.js Express :3001  ║
║                               ║       ║                              ║
║  ┌──────────────────────────┐ ║       ║  路由：                       ║
║  │  保险智能体首页 ChatPage  │ ║       ║  POST /api/chat/stream       ║
║  │  ┌─────────┐             │ ║       ║    → SSE 代理 AI :8000       ║
║  │  │ 欢迎态  │ 居中输入框   │ ║       ║  GET  /api/asr/token         ║
║  │  │ 对话态  │ 底部输入栏   │ ║       ║    → 阿里云 NLS Token        ║
║  │  └─────────┘             │ ║       ║  /api/actuarial/*            ║
║  │  NeedsReportCard         │ ║       ║    → 精算服务 :8080           ║
║  │  ProductRecommendCard    │ ║       ║  /api/admin/*                ║
║  │  RouteCard               │ ║       ║    → 管理后台 API             ║
║  └──────────────────────────┘ ║       ║                              ║
║  ┌──────────────────────────┐ ║       ║  JWT 鉴权 / AES 加密          ║
║  │  AIX 测算引擎（Module1~7)│ ║       ║  会话管理 / 客户档案           ║
║  │  基本信息→财务→需求→结果  │ ║       ╚══════════╤═══════════════════╝
║  └──────────────────────────┘ ║                  │
║  Zustand store（持久化）        ║       ╔══════════▼═══════════════════╗
╚═══════════════════════════════╝       ║   AI 服务 FastAPI :8000       ║
                                        ║                               ║
                                        ║  chat.py（SSE 对话编排）       ║
                                        ║    ↓ Function Calling × 6     ║
                                        ║  chat_engine.py               ║
                                        ║    Kimi k2.5 系统提示词        ║
                                        ║    工具：show_options          ║
                                        ║         update_core_memory    ║
                                        ║         start_needs_analysis  ║
                                        ║         generate_needs_report ║
                                        ║         save_recall_summary   ║
                                        ║         report_issue          ║
                                        ║    ↓                          ║
                                        ║  needs_analysis.py            ║
                                        ║    需求报告 + 预算测算          ║
                                        ║    ↓                          ║
                                        ║  product_scorer.py            ║
                                        ║    7维度评分 + 精算性价比       ║
                                        ║    ↓ 调用精算服务              ║
                                        ║  memory_store.py              ║
                                        ║    对话记忆（MySQL）            ║
                                        ╚══════════╤════════════════════╝
                         ┌─────────────────────────┘
          ╔══════════════▼══════════════╗     ╔══════════════════════════╗
          ║  精算服务 Java Spring :8080  ║     ║  MySQL 8.0                     ║
          ║                             ║     ║  my_ensure 库（产品主数据）：   ║
          ║  PricingController          ║     ║  ├─ cmb_product（1万+款）      ║
          ║  ActuarialPricingEngine     ║     ║  ├─ cmb_product_disease        ║
          ║  PVFB/GP 公式               ║     ║  └─ cmb_product_rate           ║
          ║  → fairPremium（元/年）      ║     ║  aix_engine 库（业务数据）：    ║
          ║                             ║     ║  ├─ chat_sessions              ║
          ║  GET /actuarial/fair-price  ║     ║  ├─ core_memory                ║
          ║    ?productId&age&gender    ║     ║  ├─ actuarial_qx_table         ║
          ╚═════════════════════════════╝     ║  ├─ actuarial_ci_table         ║
                                              ║  └─ product_actuarial_config   ║
                                              ╚════════════════════════════════╝
```

### 2.2 核心对话链路（SSE 全事件流）

```
用户消息
  │
  ▼
BFF POST /api/chat/stream
  │
  ▼
AI 服务 chat.py ──→ Kimi k2.5 API（Function Calling）
  │
  ├─ [chunk]              流式文字片段 → 前端逐字渲染
  ├─ [options]            多选项让用户选择
  ├─ [route_options]      规划路由卡（填写信息/对话规划）
  ├─ [needs_report]       需求报告摘要卡
  ├─ [product_recommendations]  推荐结果（Top3 + 预算分配）
  ├─ [done]               流结束
  └─ [error]              错误兜底

product_recommendations payload：
{
  top3: ProductRecommendation[]    // 最多3款产品 + 评分 + 性价比（符合条件产品不足3款时按实际数量返回）
  conclusion: string               // 选购建议
  risk_notes: string[]             // 风险说明
  budget_allocation: {             // 预算分配建议
    by_person: { self, spouse, children }
    by_coverage: { critical_illness, medical, life }
    rationale: string
  }
}
```

### 2.3 架构概览（文字版）

```
前端（React + Tailwind）
  ├── 保险智能体首页（ChatPage — 唯一入口，ChatGPT 风格）
  │     ├── 欢迎态：居中标题 + 居中输入框 + 快捷建议
  │     └── 对话态：消息流 + 底部输入栏
  └── AIX 保险智能测算引擎（结构化规划入口，由路由卡跳转）
        └── Module1~7（基本信息 → 推荐结果）

BFF（Node.js 3001）
  └── 会话管理、客户档案、ASR Token、精算代理

AI 服务（Python FastAPI 8000）
  ├── chat.py（SSE 对话编排）
  ├── chat_engine.py（Kimi 工具定义 + 系统提示词）
  ├── needs_analysis.py（需求报告 + 预算测算）
  ├── product_scorer.py（产品评分）
  └── memory_store.py（记忆系统）

精算服务（Java Spring Boot 8080）
  └── 费率计算、精算模型（PVFB/GP 公式）
```

### 2.4 两条规划路径

用户提出规划类需求时，AI 先弹出路由卡：

```
用户: "帮我规划家庭保险"
  ↓
路由卡（show_options route_options）
  ├── 填写信息规划 → navigate(aix-engine) → 跳转至 AIX 测算引擎 Module1
  └── 对话规划 → continue_chat → AI 继续对话收集信息
```

**关键约束（强制）：**
- `填写信息规划` = 复用现有 AIX 保险智能测算引擎，不是新建独立页面
- 路由 target key = `"aix-engine"`，前端 `TARGET_MODULE_MAP["aix-engine"] = 1`（Module1 基本信息）
- 两条路径共用同一套底层 schema（见第五章）
- 路由卡只做交互分流，不做业务逻辑分流

---

## 第三章 首页交互规范

### 3.1 品牌区设计规范

**左上角品牌标识：标准品牌 Logo 图片**
- 使用公司标准 Logo 图片：`frontend/public/aixlogo.png`（白底或透明底）
- 静态资源路径：`/aixlogo.png`，由 `Logo.tsx` 组件统一渲染
- 等比缩放，高度控制在 header 视觉协调范围内（默认 32px），不裁切、不拉伸
- 点击返回 Chat 首页，行为与旧版一致
- 不做额外滤镜、阴影、变色处理，保持品牌原始样式

> **旧版方案（已废弃）：** v4.0 阶段曾使用蓝色文字"AIx"（`#2B7FE0`）作为临时占位方案，
> 现已替换为标准品牌 Logo 图片，文字版不再作为当前事实描述。

**视觉层级（从重到轻）：**
1. 页面中心主标题：**保险智能体**（h1，加粗，黑色，最大字号）
2. 主标题下方副标：**人人都是保险专家**（蓝色中等字重）
3. 引导文案：**有任何保险问题，尽管问我**（小字灰色）
4. 左上角品牌标识：**标准 Logo 图片**（比页面主标题小，不抢焦点）
5. MainLayout header 中心：**chat 模式下隐藏**（由页面主体的 h1 承担）

**绝对禁止：**
- 把"人人都是保险专家"放进输入框 placeholder
- 把"人人都是保险专家"放成顶部导航主标题
- 把"人人都是保险专家"和"今天想了解什么？"并列成双主标题
- 口号堆叠（≤ 3 层文案，超出删减次要文案）

### 3.2 首页设计哲学

参考 ChatGPT 首页的核心原则：
- 首页是"开始对话"的起点，不是功能菜单
- 极简：顶部品牌区（仅 Logo 图片）+ 居中主区（标题 + 口号 + 输入框 + 快捷建议）+ 底部免责
- 快捷建议是"我可以这样问"的示范，不是模块菜单
- 顶部品牌区不抢占中心交互焦点

### 3.3 欢迎态布局

```
┌─────────────────────────────────────┐
│  [AIX Logo图片]            [⚙️]    │  ← MainLayout header：左 Logo，右操作
│  （标准品牌图片，点击返回首页）       │    chat 模式不显示中心标题
├─────────────────────────────────────┤
│                                     │
│                                     │
│          保险智能体                  │  ← 页面主标题 h1（最重要）
│      人人都是保险专家                │  ← 品牌口号，蓝色，副标
│      有任何保险问题，尽管问我         │  ← 引导文案，灰色小字
│                                     │
│  ┌─────────────────────────────┐    │
│  │  有问题，尽管问…           🎤│    │  ← 核心焦点：居中大输入框
│  │  ─────────────────────────  │    │
│  │  🖼️  🎤                  ↑  │    │
│  └─────────────────────────────┘    │
│                                     │
│  [帮我规划家庭保障]                  │  ← 快捷建议（输入框下方）
│  [帮我推荐适合的重疾险]              │    自然问题式，非功能菜单
│  [帮我看看现有保单]                  │
│  [保险一般怎么配置更合理]            │
│                                     │
└─────────────────────────────────────┘
│  AI建议仅供参考，不构成投保依据      │  ← 底部免责
```

### 3.4 对话态布局

```
┌─────────────────────────────────────┐
│  🛡 保险智能体              [新对话]│  ← 紧凑顶栏
├─────────────────────────────────────┤
│  用户消息                           │
│              AI 回复 + 卡片         │
│  用户消息                           │
│              AI 回复                │
│                              [滚动] │
├─────────────────────────────────────┤
│  [🖼️][🎤] 输入框              [↑]  │  ← 底部固定输入栏
└─────────────────────────────────────┘
```

### 3.5 旧 HomePage 的处理方式

**`HomePage` 降级为 AIX 测算引擎内部入口，不再作为总站默认首页。**

- `App.tsx` 的 `default` case 返回 `<ChatPage />`（原为 `<HomePage />`）
- ErrorBoundary onReset 跳转 `'chat'`（原为 `'home'`）
- `activeModule === 'home'` 仍可从测算引擎内部访问
- 任何"返回首页"操作 → `setActiveModule('chat')`

### 3.6 快捷建议内容（自然问题式）

快捷建议必须像用户会主动说出口的问题，不是功能模块入口。

| 标签 | 触发文字 | 说明 |
|------|---------|------|
| 帮我规划家庭保障 | 帮我规划家庭保险方案 | 触发路由卡（填写信息/对话规划） |
| 帮我推荐适合的重疾险 | 帮我推荐一款适合我的重疾险 | 进入需求收集对话 |
| 帮我看看现有保单 | 帮我做一个保单体检分析 | 保单分析流程 |
| 保险一般怎么配置更合理 | 保险一般怎么配置更合理 | 知识问答 |

---

## 第四章 规划路由逻辑

### 4.1 触发条件

当用户表达以下任一意图时，AI **必须**先弹出路由卡，不得直接进入对话收集：
- 帮我规划家庭保险
- 帮我做保险方案
- 帮我配家庭保障
- 帮我设计保障方案
- 想做一个保险规划
- 家庭保障规划

### 4.2 路由卡 SSE 事件

```json
{
  "event": "route_options",
  "data": {
    "route_options": [
      {"label": "填写信息规划", "action": "navigate", "target": "aix-engine"},
      {"label": "对话规划", "action": "continue_chat"}
    ]
  }
}
```

### 4.3 前端路由映射（ChatPage.tsx）

```typescript
// 模块 key → activeModule 值映射
const TARGET_MODULE_MAP = {
  'aix-engine':   1,   // 填写信息规划 → AIX 测算引擎 Module1（基本信息）
  'policy-check': 3,   // 保单体检 → Module3（保障需求）
}
```

### 4.4 填写信息规划说明

**填写信息规划 = 跳转至现有 AIX 保险智能测算引擎的 Module1（基本信息）入口**

- 不是新建 `/family-plan` 独立页面
- 不是未来待开发的新表单系统
- 就是现有 AIX 引擎的结构化信息采集流程
- 后续如需替换问卷 schema，在 AIX 引擎内部替换即可

**禁止**在代码、注释、文档中把 `aix-engine` 描述为 `/family-plan` 路由路径。

---

## 第五章 统一规划 Schema

### 5.1 核心原则

两条路径（填写信息规划 / 对话规划）必须共用同一套底层 schema：

| 字段 | 对话规划 | 填写信息规划 |
|------|---------|------------|
| age | AI 对话收集 | Module1 表单填写 |
| gender | AI 对话收集 | Module1 表单填写 |
| budget_annual | AI 推算/收集 | Module2 财务状况填写 |
| family_structure | AI 对话收集 | Module1 家庭情况填写 |
| primary_concern | AI 对话收集 | Module3 保障需求填写 |

不允许出现：一条路径支持某字段，另一条路径不支持的情况。

### 5.2 信息采集三个核心目的

每个字段必须能解释其用途，字段存在必须至少服务一个目的：

1. **了解客户，生成建议** — 用于 AI 生成保险购买建议
2. **结构化检索** — 将客户信息转为条件，在产品库中搜索符合要求的产品
3. **预算测算/分配** — 当客户不给预算时，根据信息推算预算和分配建议

| 字段 | 生成建议 | 产品检索 | 预算测算 |
|------|---------|---------|---------|
| age | ✅ | ✅（费率随年龄变化） | ✅（年龄影响保费基准） |
| gender | ✅ | ✅（男女费率不同） | ✅ |
| annual_income | ✅ | — | ✅（收入×5%~10%推算预算） |
| budget_annual | ✅ | ✅（价格筛选） | — |
| family_structure | ✅ | ✅（被保人数量） | ✅（家庭成员数影响总预算） |
| health_status | ✅ | ✅（核保规则过滤） | — |
| primary_concern | ✅ | ✅（病种覆盖过滤） | — |
| preferred_company | — | ✅（公司过滤） | — |

---

## 第六章 预算能力规范

### 6.1 设计原则

用户不愿或无法给出预算时，系统必须主动推算，而不是把"先告诉我预算"作为前提。

### 6.2 数据结构

```typescript
interface NeedsReportSummary {
  age: number
  gender: string
  primary_concern: string
  family_structure: string
  health_status?: string
  // 预算字段
  budget_annual?: number              // 实际使用的年保费（元）
  budget_mode?: 'user_stated' | 'estimated'
  budget_annual_estimated_min?: number  // 测算下限（estimated 模式）
  budget_annual_estimated_max?: number  // 测算上限（estimated 模式）
  budget_annual_recommended?: number    // 推荐预算
}
```

### 6.3 预算测算规则

| 情景 | budget_mode | 处理逻辑 |
|------|------------|---------|
| 用户明确给出预算 | user_stated | 直接使用用户值 |
| 用户给收入未给预算 | estimated | min=年收入×5%，max=年收入×10%，recommended=年收入×7% |
| 收入也不知道 | estimated | 根据职业/城市估算中等收入，同上逻辑；AI 说明"根据您的情况估算" |

### 6.4 预算分配能力（已全链路实现）

系统不仅测算总预算，还要回答：**预算优先给谁、优先配置什么保障**。

**当前完成状态（v4.1）：**
- ✅ `BudgetAllocation` 接口已入 `useStore.ts`
- ✅ Python `_compute_budget_allocation()` 已在 `aix-ai-service/app/routers/chat.py` 实现
- ✅ `product_recommendations` SSE payload 已包含 `budget_allocation` 字段
- ✅ 前端 `RecommendationConclusionCard` 已展示 by_person 人员分配格子

```typescript
// useStore.ts — 已实现（全险种扩展结构）
interface BudgetAllocation {
  by_person?: {
    self?: number       // 本人（元/年）
    spouse?: number     // 配偶（元/年）
    children?: number   // 子女合计（元/年）
  }
  by_coverage?: {
    critical_illness?: number  // ✅ 一期填充
    medical?: number           // 🔜 二期预留，一期不填充
    life?: number              // 🔜 二期预留，一期不填充
    other?: number             // 🔜 后续预留
  }
  rationale?: string   // 分配说明文字
}
```

> **一期说明**：`by_coverage` 字段结构为全险种预留，一期仅填充 `critical_illness`，其他字段值为 `undefined`。前端展示时跳过空值，不会出现空格子。`by_coverage` 有数据后，二期可直接展示，无需改接口。

**一期分配逻辑（已实现）：**
- 有配偶+子女：本人 60% / 配偶 30% / 子女 10%
- 有配偶无子女：本人 60% / 配偶 40%
- 单亲+子女：本人 75% / 子女 25%
- 单身：本人 100%

---

## 第七章 推荐结果展示规范

### 7.1 推荐结果卡片结构（共 7 张展示）

推荐结果必须使用结构化卡片，禁止退回 Markdown 表格：

| # | 组件 | 数量 | 内容 |
|---|------|------|------|
| 1 | NeedsReportCard | 1 | 用户画像摘要（年龄/性别/预算/核心诉求/家庭） |
| 2~4 | RecommendationCard | 最多3（按实际返回数量）| 每产品：排名徽章 + 亮点标签 + 保费 + 性价比 + 评分条 |
| 5 | ProductCompareCard | 1 | 维度对比（横向可滑动，非表格墙） |
| 6 | RecommendationConclusionCard | 1 | 选购建议 + 预算分配格子 |
| 7 | RiskDisclosureCard | 1 | 风险说明（单次赔付/数据库边界/核保限制） |

> NeedsReportCard 由 `needs_report` SSE 事件触发，其余 6 张由 `product_recommendations` 事件触发，均在 ChatPage 消息流中渲染。

### 7.2 NeedsReportCard 展示规则

- 默认折叠，显示摘要 chips（年龄/性别/诉求/家庭）
- 点击展开 2 列字段详情
- 预算显示规则：
  - `user_stated`：直接显示值，如 `8,000元/年`
  - `estimated`：显示区间，如 `4,000~8,000元/年（测算）`

### 7.3 ProductCompareCard 要求

- 不得产生"表格墙"视觉感
- 横向可滑动（overflow-x-auto）
- 每个字段用进度条+数字展示，而非纯文字对比

---

## 第八章 对话过程可视化规范

### 8.1 展示目的

保险规划对用户而言是复杂且高决策成本的过程。系统必须在对话过程中向用户展示"当前在做什么、为什么进入这一步、这一步产出了什么"，而不是等待后在最终结果一次性呈现。

展示阶段性进度的核心目的：

- 让用户知道智能体不是黑箱：推荐结果来自需求分析、预算测算、产品筛选、评分排序等明确步骤
- 提升系统专业感和规划过程透明度
- 降低用户在等待过程中的不确定感和流失风险
- 为后续结果卡片的出现做好认知铺垫

### 8.2 展示边界（强制约束）

本规范展示的是**阶段性工作进度和判断依据摘要**，不是模型完整思维链或原始推理过程。

**禁止展示：**
- 模型的原始长推理文本（即使系统使用了 reasoning 模型）
- 尚未确认的草稿判断（如"我猜用户可能是……"）
- 自言自语式、跳跃式、可能引起用户误解的中间状态
- 把中间猜测当作最终结论输出给用户

**允许展示：**
- 当前所处阶段名称
- 该阶段的简短一句说明
- 阶段状态：进行中 / 已完成

### 8.3 规划链路各阶段定义

以下是推荐规划场景下的标准阶段序列，每个阶段对应现有系统模块：

| # | 阶段名称 | 触发时机 | 对应系统模块 | 参考展示文案 |
|---|---------|---------|------------|------------|
| 1 | 理解需求 | 用户发出规划意图后 | `chat_engine.py` 对话解析 | 正在理解你的家庭结构与核心保障诉求 |
| 2 | 补全关键信息 | `start_needs_analysis` 触发 | `needs_analysis.py` | 正在确认规划所需的关键信息 |
| 3 | 预算测算 | 信息收集完成，进入预算计算 | `needs_analysis.py` → `build_report_summary()` | 正在根据你的收入和家庭情况估算合理预算范围 |
| 4 | 产品筛选 | `generate_needs_report` 触发 | `product_search.py` | 正在从当前支持的产品库中筛选候选重疾险 |
| 5 | 评分排序 | 筛选结果返回后 | `product_scorer.py` | 正在结合保障责任、预算匹配和精算结果进行排序 |
| 6 | 生成建议 | 评分完成，构建 SSE payload | `chat.py` → `product_recommendations` | 已生成推荐建议，正在准备展示方案 |
| 7 | 风险提示 | 结果卡片生成完毕 | `RiskDisclosureCard` | 已补充当前版本的保障边界和注意事项 |

### 8.4 文案风格要求

- **简短**：每条说明不超过 20 字
- **专业但易懂**：避免技术词汇，面向普通用户
- **主动语态**：描述系统在做什么，不描述模型在想什么
- **不暴露技术实现**：不出现"调用工具""执行函数""API 请求"等表达

**正确示例：**
> 正在理解你的家庭结构与核心保障诉求
> 正在根据你的收入情况估算合理预算范围
> 正在从产品库中筛选符合条件的重疾险
> 正在对候选产品进行综合评分排序
> 已生成推荐建议，并补充需要注意的风险说明

**错误示例（禁止）：**
> 我在调用 generate_needs_report 工具……
> 我觉得用户可能需要定期寿险，但也可能需要……
> 正在思考最优解……（无具体内容）

### 8.5 一期最小实现要求

一期不需要实现复杂动画或细粒度思维链，最小可用实现为：

- **展示载体**：在 AI 消息流中，以简短文本段落或轻量状态条形式展示阶段说明
- **必须覆盖的阶段**：阶段 2（补全信息）、阶段 3（预算测算）、阶段 4（产品筛选）、阶段 5（评分排序）、阶段 6（生成建议）
- **展示时机**：由 SSE `chunk` 事件中的阶段说明文本承载，或通过新增轻量 SSE 事件（如 `thinking_step`）推送
- **不需要实现**：动画进度条、可折叠的详细推理面板、实时逐字打印的推理流

后续版本可在一期基础上扩展：更细粒度的中间步骤、可交互的过程展示面板、与推荐卡片联动的步骤高亮等。

---

## 第九章 AI 工具规范

### 8.1 工具清单

| 工具 | 触发时机 |
|------|---------|
| show_options（普通） | 需要用户选择时（健康/家庭/收入/险种等） |
| show_options（route_options） | **仅在**用户提出规划类意图时 |
| update_core_memory | 用户透露重要个人信息时立即调用 |
| start_needs_analysis | 用户明确想要推荐产品时 |
| generate_needs_report | 收集足够信息后（至少：年龄+性别+家庭情况） |
| save_recall_summary | 对话将要结束时 |
| report_issue | 产品不在库中/超出能力范围时静默调用 |

### 8.2 generate_needs_report 必传字段

```python
# 必填
age: int
gender: "male" | "female"

# 预算字段（重要：必须填 budget_mode）
budget_mode: "user_stated" | "estimated"
budget_annual: int              # 实际使用的预算值
budget_annual_estimated_min: int  # estimated 模式填写
budget_annual_estimated_max: int  # estimated 模式填写
budget_annual_recommended: int    # estimated 模式填写

# 可选但建议填写
family_structure: str
health_status: str
primary_concern: str
preferred_company: str
```

### 8.3 route_options 标准格式

```json
[
  {"label": "填写信息规划", "action": "navigate", "target": "aix-engine"},
  {"label": "对话规划",     "action": "continue_chat"}
]
```

**target 说明：** `aix-engine` 是前端模块 key，映射到 AIX 测算引擎 Module1（基本信息），不是 URL 路径。

---

## 第十章 架构灵活性约束

### 10.1 问卷逻辑配置化

- 字段定义、显示顺序、必填规则尽量从配置读取
- AIX 测算引擎和对话规划共用同一份 schema 定义
- 后续替换问卷文件时，不需要同时修改 ChatPage 和 Module1~7

### 10.2 预算逻辑模块化

- 预算测算逻辑集中在 `needs_analysis.py` 的 `build_report_summary()` 中
- 不在 ChatPage、表单页、推荐页、Prompt 多处重复实现预算逻辑
- `budget_mode` / `budget_annual` / `budget_annual_recommended` 是唯一来源

### 10.3 推荐链路结构化

```
标准化 profile (NeedsReportSummary)
  → 检索条件 (fetch_products_for_scoring)
  → 评分 (score_products)
  → 丰富化 (enrich_recommendations)
  → 前端展示 (ProductRecommendCard)
```

- 每个环节输入输出明确，不靠大模型理解自然语言
- 评分参数来自 `score_breakdown`，不散落在 Prompt 中

### 10.4 前端展示与业务解耦

- UI 组件（ChatPage、卡片）可以独立更新样式
- `NeedsReportSummary`、`ProductRecommendationsPayload` 等接口尽量保持稳定
- UI 改版不应迫使后端接口重写

---

## 第十一章 一期实施顺序与后续开发任务

### 11.1 已完成（截止 v4.1）

| 模块 | 内容 |
|------|------|
| 前端入口 | ChatPage 欢迎态/对话态双布局，品牌区（标准 Logo 图片 `/aixlogo.png`），首页快捷建议（自然问题式） |
| 路由卡 | RouteCard 组件，填写信息规划 → aix-engine，对话规划 → continue_chat |
| 需求画像卡 | NeedsReportCard（由 `needs_report` SSE 事件触发，独立渲染，共 7 张中第 1 张，支持 user_stated / estimated 预算展示） |
| 推荐卡片组 | ProductRecommendCard（由 `product_recommendations` SSE 事件触发，第 2~7 张：RecommendationCard×最多3 + ProductCompareCard + RecommendationConclusionCard + RiskDisclosureCard）|
| 预算分配链路 | Python `_compute_budget_allocation()` → SSE payload → 前端人员分配格子 |
| SSE 全事件 | chunk / route_options / needs_report / product_recommendations / done / error 全部接线 |
| AI 工具 | 6 个工具定义完整（show_options / update_core_memory / start_needs_analysis / generate_needs_report / save_recall_summary / report_issue） |
| 精算服务 | Java PVFB/GP 定价公式、PricingController 接口就绪 |
| 语音输入 | VoiceInput.tsx，Aliyun NLS WebSocket 接线 |

### 11.2 一期剩余必须完成项

| 优先级 | 任务 | 负责人 | 说明 |
|--------|------|--------|------|
| 🔴 P0 | **精算数据导入** | 精算同事1 | 生成 `db/migration/07-actuarial-data.sql`（死亡率表+重疾发生率表+产品配置），导入后 value_score > 0 |
| 🔴 P0 | **全链路 E2E 验收** | PM | curl 冒烟测试（`test-e2e-chat.sh`）+ 浏览器人工验收 7 张卡片 |
| 🟡 P1 | 精算公允价偏差校验 | 精算同事1 | 对照 v1.2 HTML 工具，fairPremium 偏差 < 5% |
| 🟡 P1 | 语音/图片链路回归 | 程序员A | 确认 ASR Token + Kimi Vision 在生产环境可用 |
| 🟡 P1 | 移动端响应式验收 | 程序员A | 手机浏览器 7 张卡片可读，对话输入栏可用 |
| 🟢 P2 | 对话规划与填写信息规划 schema 一致性 | 程序员B | 确认两条路径收集字段完整对齐 |

**一期上线验收标准：**
- `curl /api/v1/actuarial/fair-price?productId=XX&age=35&gender=male` → `{"errorCode":"OK","fairPremium":7xxx}`
- 完整对话 → `product_recommendations` → `top3[0].total_score > 0`，`value_score > 0`
- 浏览器 7 张卡片全部渲染，无白屏无崩溃

### 11.3 二期准备项（一期期间不开发）

| 任务 | 说明 |
|------|------|
| 百万医疗险险种扩展方案 | 费率结构与重疾险不同，需独立精算模型 |
| 保单 OCR 深化 | 当前图片输入以 Vision 描述为主，二期考虑结构化提取 |
| 动态精算假设管理 | 支持精算假设（i / q_x / ci_rate）在管理后台调整 |
| B 端接口设计 | 产品研发/销售用户的权限和数据隔离方案 |
| `budget_allocation.by_coverage` 填充 | 医疗险/寿险数据就绪后，补充非重疾险预算分配建议 |

---

## 第十二章 文件变更清单（v4.1 实施）

| 文件 | 改动 |
|------|------|
| `frontend/src/components/Logo.tsx` | 使用标准品牌 Logo 图片（`/aixlogo.png`），等比缩放，点击返回首页 |
| `frontend/src/layouts/MainLayout.tsx` | chat 模式下隐藏 header 中心标题（由 ChatPage body h1 承担） |
| `frontend/src/modules/chat/ChatPage.tsx` | 欢迎态：移除内部顶栏、品牌层级（主标题+副标+引导语）、居中输入框 |
| `frontend/src/modules/chat/components/HomeQuickEntry.tsx` | 快捷建议改为自然问题式（帮我规划家庭保障等） |
| `frontend/src/App.tsx` | default case → `<ChatPage />`，ErrorBoundary onReset → `'chat'` |
| `frontend/src/store/useStore.ts` | 新增 `BudgetAllocation` 接口，`ProductRecommendationsPayload` 加 `budget_allocation?` |
| `frontend/src/modules/chat/components/ChatInputBar.tsx` | 新增 `variant='centered'` 模式 |
| `frontend/src/modules/chat/components/NeedsReportCard.tsx` | 支持 estimated 预算区间显示 |
| `aix-ai-service/app/services/chat_engine.py` | 路由 target=`aix-engine`，`generate_needs_report` 增预算字段，系统提示词增预算测算规则 |
| `aix-ai-service/app/services/needs_analysis.py` | `build_report_summary()` 传递预算字段到 SSE payload |

---

## 第十三章 验收清单（v4.1）

**品牌与视觉层级**
- [ ] 左上角品牌标识是标准品牌 Logo 图片（`/aixlogo.png`），欢迎态与对话态一致
- [ ] 欢迎态页面主标题是**保险智能体**（居中，最大最重）
- [ ] 主标题下方是**人人都是保险专家**（蓝色，副标，不抢主标题）
- [ ] 引导语轻量，与口号不并列重复
- [ ] MainLayout header 在 chat 模式下不显示中心"保险智能体"文字（由 body h1 承担）

**首页布局**
- [ ] 欢迎态：居中主标题 + 副标 + **居中输入框**（不在底部） + 输入框下方快捷建议
- [ ] 对话态：消息流 + **底部固定输入栏**
- [ ] chat 模式下左侧边栏隐藏，全宽布局
- [ ] 首页不出现流程导航式结构
- [ ] 顶部品牌区克制，不抢中心焦点

**快捷建议**
- [ ] 快捷建议像自然问题（帮我规划家庭保障 / 帮我推荐适合的重疾险 / 帮我看看现有保单 / 保险一般怎么配置更合理）
- [ ] 不像功能模块菜单或业务入口

**路由逻辑**
- [ ] 规划类意图触发二选一路由卡（填写信息规划 / 对话规划）
- [ ] 路由卡 `target='aix-engine'`，点击跳转至 Module1 基本信息
- [ ] 代码/注释/文档/AI 示例中无 `/family-plan` 路由路径残留
- [ ] `TARGET_MODULE_MAP['aix-engine'] = 1` 且注释说明"复用 AIX 测算引擎"

**旧 HomePage**
- [ ] `App.tsx` default case 返回 `<ChatPage />`（不再是 `<HomePage />`）
- [ ] ErrorBoundary onReset 跳转 `'chat'`（不是 `'home'`）
- [ ] "返回首页"操作统一跳转 `'chat'`

**预算能力**
- [ ] `useStore.ts` 有 `BudgetAllocation` 接口定义
- [ ] `ProductRecommendationsPayload` 包含 `budget_allocation?` 字段
- [ ] `budget_mode=estimated` 时，NeedsReportCard 显示预算区间（如 `4,000~8,000元/年（测算）`）
- [ ] AI 系统提示词包含预算测算规则（年收入 5%~10%）

**推荐结果**
- [ ] 推荐结果使用结构化卡片（无 Markdown 表格）
- [ ] 7 张展示卡片全部渲染：NeedsReportCard + RecommendationCard×最多3（按实际返回数量）+ ProductCompareCard + RecommendationConclusionCard + RiskDisclosureCard
- [ ] 代码/注释/文档无 `/family-plan` 作为路由路径的引用
- [ ] 用户不给预算时，AI 自动推算并说明来源
- [ ] 架构支持后续替换问卷 schema

**精算链路**
- [ ] `GET /api/v1/actuarial/fair-price?productId=XX&age=35&gender=male` 返回 `{"errorCode":"OK","fairPremium":7xxx}`
- [ ] `product_recommendations` 中 `top3[0].total_score > 0`，`value_score > 0`（需精算数据已导入）
- [ ] 精算公允价与 v1.2 HTML 工具偏差 < 5%

---

## 第十四章 技术栈

| 层 | 技术 |
|----|------|
| 前端 | React 18 + TypeScript + Vite + Tailwind CSS v3 + Zustand |
| BFF | Node.js + Express + MySQL2 |
| AI 服务 | Python 3.11 + FastAPI + Kimi API（Function Calling + Vision） |
| 精算服务 | Java 17 + Spring Boot |
| 数据库 | MySQL 8.0 |
| 消息队列 | RabbitMQ |
| 反向代理 | Nginx |
| 容器化 | Docker Compose |

---

## 第十五章 一期险种边界

| 险种 | 当前支持状态 | 规划阶段 |
|------|------------|---------|
| 重疾险（aix_category_id=6001） | ✅ 当前支持 — 完整推荐+精算定价+卡片展示 | 一期 |
| 寿险/身故险 | 🔜 规划支持 | 二期第一批 |
| 增额终身寿/分红险 | 🔜 规划支持 | 二期第二批 |
| 百万医疗险 | 🔜 规划支持（最复杂，二期末） | 二期第三批 |
| 多次重疾险、年金险 | 暂不支持 | 待定 |

**AI 在一期中能说什么 / 不能说什么：**

| 场景 | 可以 | 不可以 |
|------|------|--------|
| 用户问重疾险 | 完整推荐+精算定价+卡片展示 | — |
| 用户问医疗险 | 说明"医疗险是重要保障，后续版本将支持，目前先完善重疾险配置" | 给医疗险产品推荐卡，估算医疗险保费 |
| 用户问寿险 | 说明"寿险后续版本支持，当前重点优先重疾险" | 给寿险产品卡，计算身故保额 |
| 家庭保障规划 | 指出完整保障包含重疾+医疗+寿险，当前仅输出重疾险推荐结果 | 输出跨险种组合推荐卡 |

**核心原则：禁止基于通用知识估算非重疾险保费或给出产品推荐，即使有通用知识也不能替代数据库数据。**

---

## 第十六章 数据库主数据

**产品主数据（my_ensure 库）：**
- 产品主数据表：`my_ensure.cmb_product`（1万+款，在售产品 `product_status='RELEASED'`）
  - 历史别名：部分旧文档曾写作 `aix_engine.products`，统一以 `my_ensure.cmb_product` 为准
- `my_ensure.cmb_product_disease` — 产品病种覆盖表
- `my_ensure.cmb_product_rate` — 费率表

**业务数据（aix_engine 库）：**
- `aix_engine.chat_sessions` — 对话会话记录
- `aix_engine.core_memory` — 用户核心记忆
- `aix_engine.actuarial_qx_table` — 死亡率表（table_name: CL1_1013_M / CL2_1013_F）
- `aix_engine.actuarial_ci_table` — 重疾发生率表（table_name: CI25_Male / CI25_Female）
- `aix_engine.product_actuarial_config` — 产品精算配置

**费率计算：** 通过精算服务（Java :8080）代理计算

**注意：** `my_ensure.cmb_product.product_id` collation = `utf8mb4_general_ci`，aix_engine 表 = `utf8mb4_unicode_ci`，跨库 JOIN 必须加 `COLLATE utf8mb4_unicode_ci`

---

---

## 第十七章 数据库安全边界

### 17.1 三条强制约束

| # | 约束 | 执行位置 |
|---|------|---------|
| 1 | **大模型不得直接持有数据库连接信息**。所有数据库访问必须由后端服务完成，凭证通过环境变量注入容器，不得出现在代码、日志或 prompt 中 | Docker Compose env、`_get_product_db_params()` |
| 2 | **产品库必须走 `PRODUCT_DB_*` 只读连接**，与业务写库 `MYSQL_*`（aix_engine）完全隔离。阿里云侧账号须配置 `GRANT SELECT ON my_ensure.* TO '只读账号'`，不授予 INSERT/UPDATE/DELETE/DROP | `product_search.py` 唯一入口 |
| 3 | **进入 LLM 的数据必须经过后端裁剪**，只允许白名单字段注入 prompt。禁止注入：`product_id`（内部标识）、`rate`（原始费率数字）、原始病名列表及其他非结构化字段 | `_PROMPT_ALLOWED_FIELDS`（`product_search.py`） |

### 17.2 双库隔离说明

```
aix_engine（业务写库）           my_ensure（产品只读库）
  MYSQL_HOST                       PRODUCT_DB_HOST
  MYSQL_PORT                       PRODUCT_DB_PORT
  MYSQL_USER   → 读写权限           PRODUCT_DB_USER   → 仅 SELECT
  MYSQL_PASSWORD                   PRODUCT_DB_PASSWORD
  MYSQL_DATABASE=aix_engine        PRODUCT_DB_DATABASE=my_ensure
```

- 仅 `aix-ai-service` 中的 `product_search.py` 允许连接产品库，连接参数由 `_get_product_db_params()` 统一管理
- `needs_analysis.py`、`memory_store.py`、`issue_reporter.py` 等写操作模块只能使用 `MYSQL_*` 变量
- Java 精算服务（`aix-actuarial-service`）通过 `SPRING_DATASOURCE_URL` 连接 `aix_engine`，不连接产品库

### 17.3 进入 LLM 的数据通道

```
my_ensure DB
    │
    ├─ fetch_products_text()          → 结构化文本 → 系统提示词（允许字段见 _PROMPT_ALLOWED_FIELDS）
    │    允许字段：product_name, company_name, sale_status, tag,
    │             age_range, insurance_period, payment_period,
    │             waiting_period_detail, critical_pay_times,
    │             mild_pay_times, disease_counts（聚合数量，非原始列表）
    │    禁止字段：product_id, rate（原始费率）, 原始病名列表
    │
    └─ fetch_products_for_scoring()   → 结构化 dict → 后端评分引擎（不经过 LLM）
         含 product_id, rate → 仅用于调用精算服务和排序，不进入任何 prompt
```

### 17.4 阿里云只读账号授权规范

部署至阿里云 RDS 时，须按以下语句创建只读账号：

```sql
-- 在阿里云 RDS 控制台或 DMS 中执行
CREATE USER 'aix_readonly'@'%' IDENTIFIED BY '<strong_password>';
GRANT SELECT ON my_ensure.* TO 'aix_readonly'@'%';
FLUSH PRIVILEGES;

-- 验收：应只看到 SELECT 权限，无 INSERT/UPDATE/DELETE/DROP
SHOW GRANTS FOR 'aix_readonly'@'%';
-- 期望输出：
-- GRANT USAGE ON *.* TO `aix_readonly`@`%`
-- GRANT SELECT ON `my_ensure`.* TO `aix_readonly`@`%`
```

`.env` 对应填写：
```
PRODUCT_DB_HOST=rm-xxxx.mysql.rds.aliyuncs.com
PRODUCT_DB_USER=aix_readonly
PRODUCT_DB_PASSWORD=<strong_password>
PRODUCT_DB_DATABASE=my_ensure
```

---

*历史版本：v3.0~v3.6 → 见 docs/ 历史文档*
