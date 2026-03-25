# AIX保险智能体开发文档

**版本：** V1.2  
**文档状态：** 研发实施版（正式商用版，非测试 PoC）  
**适用对象：** 前端、后端、AI、Java 精算、数据、测试、运维  
**目标：** 作为正式商用版的一体化开发规范，供开发团队与开发 AI 直接实施，无需再查阅其他文档  
**更新日期：** 2026-03-21

> 本次更新：基于《AIX智能体需求与开发文档-v3.4》完成开发文档升级，新增精算公允定价模块（M-精算），产品评分升级为 7 维度（含性价比），补充精算数据库表设计及导入方案。

---

## 第一章 项目背景与目标

### 1.1 公司定位

保险科技公司，愿景"让普通人成为保险专家"。
核心资产：1万+款结构化保险产品数据库（责任/费率/现金价值/病种/核保规则）。

### 1.2 用户类型

| 类型 | 典型场景 | 当前阶段优先级 |
|------|---------|-------------|
| **个人用户** | 咨询保险知识、分析保险需求、获取保险产品推荐 | P0，第一阶段主要对象 |
| **企业用户（B端）** | 产品开发人员查市场行情、生产保险产品、制定风控方案，销售人员查产品责任 | P2，第二阶段开发 |

### 1.3 开发目标与分阶段策略

本项目目标为**正式商用版**，不是测试 PoC。采用分阶段逐步上线策略：

**第一阶段（当前开发重点）：**
- 交互：文字 + 语音 + 图片识别三种输入
- 产品：重疾险（aix_category_id=6001）× 全量在售产品
- 端：桌面网页 + 手机网页（响应式）
- 具备完整的需求分析、产品评分、精算报告能力

**第二阶段（后续扩展）：**
- 险种：扩展至百万医疗险（7001）、寿险（1001-3002）、年金险（4001-4002）
- 用户：开放 B 端企业用户（产品研发、销售工具）
- 性能：高并发支持、CDN、分库分表

**整体技术原则：**
- 各模块独立开发、独立部署，单模块问题不影响整体
- 接口设计面向正式版，避免后期大规模重构
- 数据库设计一步到位，预留扩展字段

---

## 第二章 系统架构

### 2.0 智能体整体架构图

```
┌─────────────────────────────────────────────────────────────┐
│                     智能交互层                               │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────────────┐  │
│  │ 文字输入  │  │ 语音输入  │  │      图片识别输入          │  │
│  │ (textarea)│  │(Aliyun   │  │  (保险单/体检报告/证件)    │  │
│  │          │  │ NLS ASR) │  │                          │  │
│  └────┬─────┘  └────┬─────┘  └──────────┬───────────────┘  │
│       └─────────────┴──────────────────-┘                   │
│                         │ SSE 流式响应                        │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ 响应展示层：文字流 / 快捷选项卡片 / 需求报告卡 / 产品推荐卡 │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────┬───────────────────────────────────┘
                          │ HTTP / SSE
┌─────────────────────────▼───────────────────────────────────┐
│                      引擎层（BFF）                            │
│  ┌──────────────┐  ┌───────────┐  ┌────────────────────┐   │
│  │ 会话管理      │  │ JWT认证   │  │  ASR Token 代理     │   │
│  │ 客户档案(AES) │  │ AES加密  │  │  精算服务代理        │   │
│  └──────┬───────┘  └─────┬─────┘  └────────────────────┘   │
└─────────┼────────────────┼─────────────────────────────────┘
          │                │
┌─────────▼────────────────▼───────────────────────────────────┐
│                   大模型赋能模块（Python AI 服务）              │
│                                                               │
│  ┌─────────────┐   ┌──────────────┐   ┌──────────────────┐  │
│  │ 对话编排引擎  │   │  记忆系统     │   │   RAG 规则注入    │  │
│  │ (chat.py)   │   │ MemGPT L1/L2 │   │  (关键词意图匹配) │  │
│  └──────┬──────┘   └──────┬───────┘   └──────────────────┘  │
│         │                 │                                   │
│  ┌──────▼──────────────────▼────────────────────────────┐   │
│  │                  Kimi k2.5 API                        │   │
│  │     Function Calling × 6 工具 + Vision（图片理解）      │   │
│  └──────────────────────────────────────────────────────┘   │
│         │                                                     │
│  ┌──────▼──────┐   ┌──────────────┐   ┌──────────────────┐  │
│  │ 需求分析引擎  │   │  产品评分引擎  │   │   精算计算引擎    │  │
│  │(needs_      │   │(product_     │   │  (Java 服务代理) │  │
│  │ analysis.py)│   │ scorer.py)   │   │                  │  │
│  └─────────────┘   └──────────────┘   └──────────────────┘  │
└──────────────────────────────┬───────────────────────────────┘
                               │
┌──────────────────────────────▼───────────────────────────────┐
│                         数据库层                               │
│                                                               │
│  ┌──────────────────────┐    ┌─────────────────────────────┐ │
│  │     aix_engine       │    │        my_ensure            │ │
│  │  - chat_memories(L1) │    │  - cmb_product（产品基本信息）│ │
│  │  - chat_summaries(L2)│    │  - cmb_product_rate（费率表）│ │
│  │  - insurance_need_   │    │  - cmb_product_disease      │ │
│  │    reports（需求报告） │    │  - cmb_coverage（责任项树）  │ │
│  │  - profiles（客户档案）│    │  - cmb_product_coverage    │ │
│  │  - chat_issues       │    │                             │ │
│  └──────────────────────┘    └─────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘

外部服务：
  Aliyun NLS ← 实时语音识别（前端 WebSocket 直连）
  Kimi API   ← 大模型推理（SSE 流式）
```

### 2.1 服务拓扑

```
[浏览器 / 手机浏览器]
        ↓ HTTP / SSE / WebSocket
[Nginx :80]  ← 反向代理 + 静态文件 + SSE 缓冲关闭
        ↓
[Node.js BFF :3001]  ← API 聚合 / Session / JWT(可选) / SSE代理 / ASR Token
        ↓                          ↓
[Java 精算服务 :8080]    [Python AI 服务 :8000]
  养老/教育/保障精算       AI 对话 + 报告生成
        ↓                          ↓
              [MySQL 8 :3306]
          aix_engine（业务 + 对话记忆）
          my_ensure（重疾险产品库，10款样本）
              [RabbitMQ :5672]（预留，当前未用）

[Aliyun NLS]  ← 前端直连 WebSocket（BFF 只提供临时 Token）
```

### 2.2 技术栈

| 层 | 技术 | 版本 | 说明 |
|----|------|------|------|
| 前端 | React + TypeScript + Tailwind CSS + Vite | 18 / 5 / 3 | Zustand 状态管理，Framer Motion 动画 |
| BFF | Node.js + Express + TypeScript | 18 / 4 | 路由、SSE代理、JWT、AES加密 |
| AI服务 | Python + FastAPI + uvicorn | 3.11 / 0.115 | 对话引擎、报告生成、Kimi API |
| 精算服务 | Java 17 + Spring Boot 3 | 17 / 3.x | 养老/教育/保障精算计算 |
| 数据库 | MySQL 8.0 | 8.0 | 两个库：aix_engine + my_ensure |
| 大模型 | Kimi (moonshot-k2.5) | - | 对话 + Function Calling + Vision |
| 语音 | Aliyun NLS（智能语音交互） | - | 实时流式 ASR，中文优化 |
| 部署 | Docker + Docker Compose | - | 6个容器，单机部署 |

### 2.3 目录结构

```
aix-engine/
├── aix-bff/                        # Node.js BFF
│   └── src/
│       ├── routes/
│       │   ├── index.ts            # 路由注册
│       │   ├── chat.ts             # AI 对话代理（SSE）
│       │   ├── asr.ts              # ★新增：Aliyun NLS Token 接口
│       │   ├── admin.ts            # 管理后台 API
│       │   ├── session.ts          # 会话管理
│       │   ├── profiles.ts         # 客户档案（AES 加密）
│       │   ├── report.ts           # 报告生成代理
│       │   ├── pension.ts / education.ts / insurance.ts / financial.ts
│       │   └── config.ts
│       ├── proxy/
│       │   ├── python-client.ts    # SSE 字节流代理（proxySSE）
│       │   └── java-client.ts      # REST 代理
│       ├── db/mysql.ts             # MySQL 连接池
│       └── index.ts                # Express 入口（body-parser 10mb）
│
├── aix-ai-service/                 # Python FastAPI AI 服务
│   └── app/
│       ├── main.py
│       ├── routers/
│       │   ├── chat.py             # ★重写：对话路由（编排层）
│       │   └── report.py           # 报告生成（不动）
│       ├── services/
│       │   ├── kimi_client.py      # ★重写：LLM 客户端（M-A）
│       │   ├── chat_engine.py      # ★重写：工具集+提示词（M-H）
│       │   ├── product_search.py   # ★修复+扩展：产品查询（M-B）
│       │   ├── memory_store.py     # 记忆读写（M-C，已实现）
│       │   ├── needs_analysis.py   # ★新建：需求分析（M-D）
│       │   ├── product_scorer.py   # ★新建：产品评分（M-E）
│       │   ├── rules_loader.py     # RAG 规则注入（已实现）
│       │   ├── issue_reporter.py   # 问题上报（已实现）
│       │   └── prompt_builder.py / fallback_report.py
│       └── rules/
│           ├── question_rules.md   # 提问规则
│           ├── product_rules.md    # ★更新：加险种分类说明
│           └── data_rules.md       # 数据使用规则
│
├── aix-actuarial-service/          # Java 精算服务
│   └── src/main/java/
│       ├── controller/
│       │   └── PricingController.java      # ★新增：公允定价 REST API
│       ├── service/
│       │   ├── ActuarialPricingEngine.java  # ★新增：精算计算引擎（PVFB/GP公式）
│       │   └── ProductConfigService.java   # ★新增：读取产品精算配置
│       └── (原有精算模块不动)
│
├── db/migration/                  # 精算数据库迁移
│   └── 06-actuarial-tables.sql    # ★新增：精算配置+死亡率/重疾发病率表
├── frontend/
│   └── src/
│       ├── modules/
│       │   └── chat/
│       │       ├── ChatPage.tsx    # ★重写：主页面（M-O）
│       │       └── components/
│       │           ├── VoiceInput.tsx       # ★新建（M-J）
│       │           ├── ImageInput.tsx       # ★新建（M-K）
│       │           ├── ChatInputBar.tsx     # ★新建（M-L）
│       │           ├── NeedsReportCard.tsx  # ★新建（M-P）
│       │           └── ProductRecommendCard.tsx # ★新建（M-N）
│       ├── store/useStore.ts       # ★扩展：ChatMessage 类型
│       ├── layouts/MainLayout.tsx  # 不动（已有响应式布局）
│       └── App.tsx                 # 不动
│
├── db/
│   ├── init/                       # Docker 首次启动执行
│   │   ├── 00-charset.sql
│   │   ├── 01-schema.sql
│   │   ├── 02-seed-data.sql
│   │   ├── 03-seed-cities-products-policy.sql
│   │   └── 04-chat-memory-issues.sql
│   └── migration/                  # 手动执行迁移
│       └── 05-needs-analysis.sql   # ★新建
│
├── nginx/nginx.conf
├── docker-compose.yml
└── .env
```

### 2.4 Docker Compose 服务定义

```yaml
# docker-compose.yml 关键部分（完整版见文件）
services:
  mysql:
    image: mysql:8.0
    ports: ["3306:3306"]
    environment:
      MYSQL_ROOT_PASSWORD: ${MYSQL_ROOT_PASSWORD:-root_secret}
      MYSQL_USER: aix
      MYSQL_PASSWORD: ${MYSQL_PASSWORD:-aix_secret}
      MYSQL_DATABASE: aix_engine

  ai:
    build: ./aix-ai-service
    ports: ["8000:8000"]
    environment:
      KIMI_API_KEY: ${KIMI_API_KEY}                    # 必须设置
      KIMI_API_BASE: https://api.moonshot.cn/v1
      MYSQL_HOST: mysql
      MYSQL_PORT: 3306
      MYSQL_USER: aix
      MYSQL_PASSWORD: ${MYSQL_PASSWORD:-aix_secret}
      MYSQL_DATABASE: aix_engine
      PRODUCT_DB_DATABASE: ${PRODUCT_DB_DATABASE:-my_ensure}

  bff:
    build: ./aix-bff
    ports: ["3001:3001"]
    environment:
      PYTHON_SERVICE_URL: http://ai:8000
      JAVA_SERVICE_URL: http://actuarial:8080
      MYSQL_HOST: mysql
      MYSQL_DATABASE: aix_engine
      MYSQL_USER: aix
      MYSQL_PASSWORD: ${MYSQL_PASSWORD:-aix_secret}
      JWT_ENABLED: ${JWT_ENABLED:-false}
      AES_SECRET_KEY: ${AES_SECRET_KEY:-}
      # ★新增：
      ALIYUN_ACCESS_KEY_ID: ${ALIYUN_ACCESS_KEY_ID}
      ALIYUN_ACCESS_KEY_SECRET: ${ALIYUN_ACCESS_KEY_SECRET}
      ALIYUN_NLS_APP_KEY: ${ALIYUN_NLS_APP_KEY}

  nginx:
    build: ./nginx
    ports: ["80:80"]
    depends_on: [bff]

  actuarial:
    build: ./aix-actuarial-service
    ports: ["8080:8080"]

  rabbitmq:
    image: rabbitmq:3-management
    ports: ["5672:5672", "15672:15672"]
```

### 2.5 .env 文件（完整）

```env
# 必填
KIMI_API_KEY=sk-xxxxxxxxxxxxxxxx

# Aliyun NLS（语音识别，必填）
ALIYUN_ACCESS_KEY_ID=LTAIxxxxxxxxxxxxxxxx
ALIYUN_ACCESS_KEY_SECRET=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
ALIYUN_NLS_APP_KEY=xxxxxxxxxxxxxxxx

# 数据库
MYSQL_ROOT_PASSWORD=root_secret
MYSQL_PASSWORD=aix_secret
PRODUCT_DB_DATABASE=my_ensure

# BFF 安全（可选）
JWT_ENABLED=false
JWT_SECRET=
AES_SECRET_KEY=
```

---

## 第三章 已实现内容（PoC 现状）

### 3.1 已实现功能

| 功能 | 状态 | 文件 |
|------|------|------|
| SSE 流式对话（Kimi API） | ✅ 已实现 | chat.py → kimi_client.py |
| MemGPT L1 核心记忆 | ✅ 已实现 | memory_store.py |
| MemGPT L2 对话摘要 | ✅ 已实现 | memory_store.py |
| RAG 规则注入（关键词匹配） | ✅ 已实现 | rules_loader.py |
| Function Calling（4个工具） | ✅ 已实现 | chat_engine.py + kimi_client.py |
| 卡片快捷选项（show_options） | ✅ 已实现 | chat.py + ChatPage.tsx |
| 管理后台（issues查看） | ✅ 已实现 | AdminPanel.tsx + admin.ts |
| 精算模块（7个业务模块） | ✅ 已实现，不动 | module1-7 |
| PDF 报告生成 | ✅ 已实现，不动 | report.py |

### 3.2 P0 Bug（必须在 Sprint 1 修复）

#### Bug 1：产品数据库 Collation 冲突

**症状：** `docker logs ai` 出现 `Illegal mix of collations (utf8mb4_general_ci,IMPLICIT) and (utf8mb4_unicode_ci,IMPLICIT)`，AI 因无产品数据而编造信息。

**根因：** `my_ensure.cmb_product.product_id` 列是 `utf8mb4_general_ci`，而 `cmb_product_coverage.product_id` 是 `utf8mb4_unicode_ci`，JOIN 时 MySQL 报排序规则冲突。

**修复位置：** `aix-ai-service/app/services/product_search.py` 第 67 行

```python
# 修复前（报错）
ON p.product_id = pc.product_id AND pc.is_deleted = 0

# 修复后
ON p.product_id COLLATE utf8mb4_unicode_ci = pc.product_id AND pc.is_deleted = 0
```

**同时修复缓存策略：**

```python
# 修复前：失败时锁死空字符串，容器重启才能恢复
_products_cache = ""   # ❌

# 修复后：失败时保持 None，允许下次请求重试
_products_cache = None  # ✅ 不赋值，下次仍会重试
_cache_fail_count += 1
if _cache_fail_count >= 3:
    _products_cache = ""  # 连续 3 次失败后才锁定
```

#### Bug 2：reasoning_content 缺失导致多轮对话卡死

**症状：** 第二轮对话（含 Function Call 后继续对话）报 `400 {"error":{"message":"reasoning_content is missing in assistant tool call message"}}`。

**根因：** Kimi k2.5 思考模式要求 assistant 的工具调用消息必须包含 `reasoning_content` 字段。

**修复位置：** `aix-ai-service/app/services/kimi_client.py`

```python
# 在流式收集阶段，同时收集 reasoning_content
reasoning_content_buf = ""

for chunk in stream:
    delta = chunk.choices[0].delta
    # 收集思考内容
    if hasattr(delta, 'reasoning_content') and delta.reasoning_content:
        reasoning_content_buf += delta.reasoning_content
    # 收集文字内容
    if delta.content:
        content_buf += delta.content
    # 收集工具调用 ...

# 构建 assistant 消息时，reasoning_content 与 content 平级
assistant_msg = {
    "role": "assistant",
    "content": content_buf or None,
    "reasoning_content": reasoning_content_buf,  # ★ 必须带上
    "tool_calls": [...]
}
```

#### Bug 3：会话历史离开页面后丢失

**根因分析：** Zustand `persist` 已配置 `chatMessages` 持久化到 `localStorage`（key: `aix-session-v4`）。需验证 `useEffect` 欢迎语逻辑：当 `messages.length > 0` 时应跳过欢迎初始化，不清除历史。

**修复验证：** 打开对话 → 发几条消息 → 刷新页面 → 历史消息应保留。若不保留，检查 `useEffect` 中的 `clearChatMessages()` 调用条件。

---

## 第四章 模块化开发计划

### 4.1 模块依赖图

```
后端模块（Python AI 服务 + BFF）
─────────────────────────────────────────────
Layer 0（无依赖，可并行）
  M-A  kimi_client.py      LLM 客户端
  M-B  product_search.py   产品查询（含评分接口）
  M-C  memory_store.py     记忆系统（已实现，仅验证）
  M-F  aix-bff/asr.ts      Aliyun NLS Token（新建）

Layer 1（依赖 Layer 0）
  M-H  chat_engine.py            对话引擎（依赖 M-C）
  M-D  needs_analysis.py         需求分析（依赖 M-C）
  M-E  product_scorer.py         产品评分（依赖 M-B + M-精算）
  M-精算 ActuarialPricingEngine   精算公允定价（Java，依赖精算DB表）

Layer 2（依赖所有 Layer 1）
  M-G  chat.py             对话路由（编排层）

前端模块（React）
─────────────────────────────────────────────
Layer 0（无依赖，可并行）
  M-I  useStore.ts                ChatMessage 类型扩展
  M-K  ImageInput.tsx             图片输入
  M-N  ProductRecommendCard.tsx   产品推荐卡片（纯展示）

Layer 1（依赖 Layer 0）
  M-J  VoiceInput.tsx       语音输入（依赖 M-F 的 token 接口）
  M-L  ChatInputBar.tsx     输入栏（依赖 M-J + M-K）
  M-P  NeedsReportCard.tsx  需求报告卡片（依赖 M-I）

Layer 2（最终集成）
  M-O  ChatPage.tsx         主页面（依赖全部前端模块）
```

### 4.2 Sprint 计划

#### Sprint 1 — 地基层（并行开发，预计 3 天）

**目标：** 修复所有 P0 Bug；所有 Layer 0 模块完成。

| 模块 ID | 文件 | 核心任务 | 完成验证 |
|---------|------|---------|---------|
| M-B | `product_search.py` | ① JOIN 加 `COLLATE utf8mb4_unicode_ci`；② 缓存从失败允许重试 | `docker restart ai` 后对话"推荐重疾险" → AI 给出真实产品名 |
| M-A | `kimi_client.py` | ① 流式收集 `reasoning_content`；② assistant 消息带 `reasoning_content`；③ 新增 `tool_handler` 回调参数 | 多轮对话含 Function Call 不报 400 |
| M-C | `memory_store.py` | 读写验证（无需改动，仅确认） | 对话告知年龄后 `SELECT * FROM chat_memories` 有记录 |
| M-F | `aix-bff/src/routes/asr.ts` | 新建：`GET /api/v1/asr/token`，用 AccessKey 换 Aliyun NLS 临时 Token，10 分钟缓存 | `curl localhost:3001/api/v1/asr/token` 返回 `{"token":"...","expires_at":"..."}` |
| M-I | `useStore.ts` | ① `ChatMessage` 接口加 `imageUrl?: string`；② 确认 `chatMessages` 在 `partialize` 中，持久化正常 | 刷新浏览器，历史消息不丢失 |
| M-K | `ImageInput.tsx` | ① `<input type="file" accept="image/*" capture="environment">`；② `FileReader` → base64；③ `URL.createObjectURL` → 缩略图预览 | 选图后显示缩略图；base64 字符串非空 |
| DB | `db/migration/05-needs-analysis.sql` | 建 `insurance_need_reports` 表 | `DESCRIBE insurance_need_reports` 成功 |

#### Sprint 2 — 引擎层（并行开发，预计 5 天）

**目标：** 完成所有 Layer 1 模块；完整对话引擎上线。

| 模块 ID | 文件 | 核心任务 | 完成验证 |
|---------|------|---------|---------|
| M-H | `chat_engine.py` | 重写：① 6个 Function Calling 工具定义；② 完整系统提示词（含险种分类+图片+需求分析规则） | 见第六章详细规范 |
| M-D | `needs_analysis.py` | 新建：`save_needs_report` / `load_latest_report` / `build_report_summary` | 调用后 SELECT 验证数据落库 |
| M-E | `product_scorer.py` | 新建：7维度评分算法（含精算性价比）+ `fetch_products_for_scoring` | 35岁男性8000预算 → Top3合理；精算得分≠0 |
| M-精算 | `ActuarialPricingEngine.java` | 新建：精算定价引擎，输入(product_id, age, gender)→输出公允年保费 | REST调用返回fair_premium；value_ratio有意义 |
| DB | `db/migration/06-actuarial-tables.sql` | 建 `product_actuarial_config` + `actuarial_qx_table` + `actuarial_ci_table` | DESCRIBE三表均成功；导入CL1_1013_M死亡率数据 |
| M-J | `VoiceInput.tsx` | ① `MediaRecorder` 采集 PCM；② BFF 获取 token；③ WebSocket 连 Aliyun NLS；④ 实时中间结果显示；⑤ 最终结果写入输入框 | 录音 → 识别结果出现在输入框 |
| M-P | `NeedsReportCard.tsx` | 需求报告卡片（桌面展开/手机折叠）| Mock 数据渲染正确；手机折叠正常 |
| M-N | `ProductRecommendCard.tsx` | Top3 对比卡片（桌面3列/手机 swipe）| Mock 数据渲染；手机可横向滑动 |

#### Sprint 3 — 集成层（预计 4 天）

**目标：** 打通完整链路；ChatPage 重建。

| 模块 ID | 文件 | 核心任务 |
|---------|------|---------|
| M-G | `chat.py`（重写） | 见第六章：完整编排逻辑（记忆+规则+提示词+Kimi+6工具处理+图片+6种SSE事件） |
| M-L | `ChatInputBar.tsx` | 组合 VoiceInput + ImageInput + textarea；桌面/手机不同布局 |
| M-O | `ChatPage.tsx`（重写） | 接入所有 SSE 事件；渲染所有卡片组件；集成 ChatInputBar |
| BFF | `aix-bff/src/index.ts` | body-parser limit 改为 10mb |
| BFF | `aix-bff/src/routes/chat.ts` | 小调整（转发 image 字段） |

#### Sprint 4 — 打磨完善（预计 3 天）

- 图片前端压缩：超过 2MB 自动压缩至 ≤ 1024px
- 错误降级：ASR 失败提示手动输入；图片 API 失败给出说明；精算服务不可用时评分跳过（不影响其他维度）
- 管理后台新增：需求报告统计 Tab、精算参数配置 Tab（录入/批量导入产品精算配置）
- 产品推荐卡片新增性价比徽章：显示 `value_ratio`（如"比市场公允价格低12%"）
- 手机端细节：虚拟键盘弹出时自动滚动到最新消息

---

## 第五章 数据库设计

### 5.1 aix_engine 数据库（已有表，不动）

| 表名 | 用途 |
|------|------|
| `sessions` | 精算业务会话 |
| `profiles` | 客户档案（AES-256-GCM 加密 JSON） |
| `city_config` | 城市精算参数 |
| `admin_config` | 系统全局配置（精算参数、场景假设） |
| `products` | 简化产品库（规则引擎） |
| `chat_memories` | L1 核心记忆（每客户唯一） |
| `chat_summaries` | L2 对话摘要（最近3条） |
| `chat_issues` | AI 问题反馈记录 |

### 5.2 chat_memories 表结构

```sql
CREATE TABLE chat_memories (
  id             VARCHAR(36)  NOT NULL DEFAULT (UUID()),
  profile_id     VARCHAR(36)  NOT NULL,
  basic_info     JSON         COMMENT '{"birth_date":"1990-05","age":35,"gender":"male","occupation":"office","city":"上海"}',
  financial_status JSON       COMMENT '{"annual_income":200000,"budget_annual":8000,"budget_source":"user_stated|calculated"}',
  existing_insurance JSON     COMMENT '[{"name":"平安寿险","type":"寿险","sum_insured":500000}]',
  preferences    JSON         COMMENT '{"disease_concerns":["癌症"],"notes":"偏好大公司"}',
  purchased_products JSON     COMMENT '[{"name":"招商信诺尊享e生","company":"招商信诺"}]',
  created_at     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_memory_profile (profile_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

### 5.3 insurance_need_reports 表（新增，Sprint 1）

```sql
-- 文件：db/migration/05-needs-analysis.sql
CREATE TABLE IF NOT EXISTS insurance_need_reports (
  id                   VARCHAR(36)  NOT NULL DEFAULT (UUID()),
  profile_id           VARCHAR(36)  NOT NULL,
  birth_date           VARCHAR(7)   COMMENT '出生年月，格式 YYYY-MM（精确日期，用于计算年龄）',
  age                  INT          COMMENT '生成报告时的实际年龄（从 birth_date 计算）',
  gender               VARCHAR(10)  COMMENT 'male/female',
  annual_income        INT          COMMENT '年收入（元，可选）',
  budget_annual        INT          COMMENT '年预算（元，可由年收入推算）',
  family_structure     VARCHAR(500) COMMENT '家庭结构（用户自由描述，含离婚/有孩等复杂情况）',
  health_status        VARCHAR(500) COMMENT '健康状况（用户自由描述）',
  existing_coverage    TEXT         COMMENT '已有保障描述',
  primary_concern      VARCHAR(200) COMMENT '主要顾虑/关注险种',
  preferred_company    VARCHAR(100) COMMENT '偏好保险公司（可空）',
  report_json          JSON         NOT NULL COMMENT '完整需求报告（generate_needs_report 工具参数）',
  recommended_products JSON         COMMENT 'Top3 产品评分结果',
  created_at           DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_needs_profile (profile_id),
  KEY idx_needs_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

### 5.4 精算定价数据库表（新增，Sprint 2，文件：06-actuarial-tables.sql）

#### product_actuarial_config（产品精算配置）

```sql
CREATE TABLE IF NOT EXISTS product_actuarial_config (
  product_id          VARCHAR(50)    NOT NULL COMMENT '对应 cmb_product.product_id',
  mortality_table_m   VARCHAR(50)    NOT NULL DEFAULT 'CL1_1013_M' COMMENT '男性死亡率表名',
  mortality_table_f   VARCHAR(50)    NOT NULL DEFAULT 'CL2_1013_F' COMMENT '女性死亡率表名',
  ci_table_m          VARCHAR(50)    NOT NULL DEFAULT 'CI25_Male'  COMMENT '男性重疾发病率表名',
  ci_table_f          VARCHAR(50)    NOT NULL DEFAULT 'CI25_Female' COMMENT '女性重疾发病率表名',
  pricing_rate        DECIMAL(6,4)   NOT NULL DEFAULT 0.0350 COMMENT '预定利率（如0.035=3.5%）',
  loading_rate        DECIMAL(6,4)   NOT NULL DEFAULT 0.2500 COMMENT '附加费用率（期交上限25%）',
  benefit_death       TINYINT        NOT NULL DEFAULT 1 COMMENT '是否含身故保障',
  benefit_ci          TINYINT        NOT NULL DEFAULT 1 COMMENT '是否含重疾保障',
  benefit_minor_ci    TINYINT        NOT NULL DEFAULT 0 COMMENT '是否含轻症保障',
  benefit_waiver      TINYINT        NOT NULL DEFAULT 0 COMMENT '是否含豁免保费',
  benefit_multiple_ci TINYINT        NOT NULL DEFAULT 0 COMMENT '是否支持多次重疾赔付',
  sum_assured         INT            NOT NULL DEFAULT 500000 COMMENT '定价基准保额（元）',
  updated_at          DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (product_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='每款产品的精算定价参数配置';
```

#### actuarial_qx_table（死亡率表）

```sql
CREATE TABLE IF NOT EXISTS actuarial_qx_table (
  table_name  VARCHAR(50)    NOT NULL COMMENT '如 CL1_1013_M、CL2_1013_F',
  age         SMALLINT       NOT NULL COMMENT '年龄（0~105）',
  qx          DECIMAL(12,10) NOT NULL COMMENT '当年死亡概率',
  PRIMARY KEY (table_name, age)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='精算死亡率表，数据来源：中国精算师协会标准生命表';
-- 初始数据：CL1_1013_M / CL2_1013_F（从 Excel Qtable 导入，见附录）
```

#### actuarial_ci_table（重疾发病率表）

```sql
CREATE TABLE IF NOT EXISTS actuarial_ci_table (
  table_name  VARCHAR(50)    NOT NULL COMMENT '如 CI25_Male、CI25_Female',
  age         SMALLINT       NOT NULL COMMENT '年龄',
  qx          DECIMAL(12,10) NOT NULL COMMENT '重疾发病率（当年）',
  PRIMARY KEY (table_name, age)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='重疾险发病率表，数据来源：同业经验数据';
-- 初始数据：CI25_Male / CI25_Female（从 Excel CI_MaleChoosen 导入）
```

### 5.5 my_ensure 数据库（重疾险产品库）

**注意：** `cmb_product.product_id` 列是 `utf8mb4_general_ci`，其余表是 `utf8mb4_unicode_ci`，所有跨表 JOIN 必须加 `COLLATE utf8mb4_unicode_ci`。

| 表名 | 用途 | 关键字段 |
|------|------|---------|
| `cmb_product` | 产品基本信息 | product_id(general_ci!), product_name, company_name, sale_status, long_short_term, waiting_period, tag |
| `cmb_coverage` | 责任项树（嵌套集合） | coverage_id, parent_id, depth, left_value, right_value, coverage_name |
| `cmb_product_coverage` | 产品↔责任 关联 | product_id(unicode_ci), coverage_id, standard_content, is_optional_coverage |
| `cmb_product_disease` | 病种定义 | product_id, disease_category, contract_disease_name, original_content |
| `cmb_product_rate` | 费率表（34字段） | product_id, age, gender, pay_time, insure_period, rate |

**关键 coverage_id 映射（来自 Excel 数据文件）：**

| coverage_id | coverage_name | 用途 |
|-------------|--------------|------|
| 3 | 投保年龄 | 判断用户年龄是否在范围内 |
| 4 | 保险期间 | 判断终身/定期 |
| 10 | 等待期 | 评分维度 |
| 9 | 投保规则 | 含保额限制等子项 |

**费率表枚举值（来自 Excel 数据文件）：**

```
gender:          0=不限, 10=女, 11=男
smoke:           0=不限, 10=不吸烟, 11=吸烟
social_security: 0=不限, 10=无社保, 11=有社保
pay_time_type:   10=年, 11=岁, 12=趸交
period_type:     10=年, 11=天, 12=月, 13=岁, 14=终身
insure_period:   999=终身
pay_type:        1=月交, 12=年交, 0=趸交
```

---

## 第六章 后端模块详细规范

### 6.1 M-A：LLM 客户端（kimi_client.py）

**职责：** 封装 Kimi API，处理流式输出和 Function Calling 多轮循环。

**对外接口：**

```python
async def call_kimi_with_tools(
    system: str,                                           # 系统提示词
    messages: list[dict],                                  # 对话历史
    tools: list[dict],                                     # 工具定义列表
    tool_handler: Callable[[str, dict], Awaitable[str]] = None,  # ★新增回调
    model: str = "kimi-k2.5",
    temperature: float = 1.0,                              # kimi-k2.5 只允许 1
    timeout: int = 300,
) -> AsyncGenerator[dict, None]:
    """
    流式输出，yields:
      {"type": "chunk", "content": "文字片段"}
      {"type": "tool_call", "name": "show_options", "arguments": {"options": [...]}}
      {"type": "done"}
    """
```

**实现要点：**

```python
# 1. 请求格式
payload = {
    "model": model,
    "stream": True,
    "temperature": temperature,
    "messages": [{"role": "system", "content": system}] + messages,
    "tools": tools,
    "tool_choice": "auto",
}

# 2. 流式收集（同时收集三类内容）
content_buf = ""
reasoning_content_buf = ""           # ★必须收集
collected_tools: dict[int, dict] = {}  # {index: {name, arguments_str}}

for chunk in stream:
    delta = chunk.choices[0].delta
    if hasattr(delta, 'reasoning_content') and delta.reasoning_content:
        reasoning_content_buf += delta.reasoning_content  # ★
    if delta.content:
        content_buf += delta.content
        yield {"type": "chunk", "content": delta.content}
    if delta.tool_calls:
        for tc in delta.tool_calls:
            idx = tc.index
            if idx not in collected_tools:
                collected_tools[idx] = {"name": tc.function.name, "arguments_str": ""}
            if tc.function.arguments:
                collected_tools[idx]["arguments_str"] += tc.function.arguments

# 3. 构建 assistant 消息（★ reasoning_content 必须平级）
assistant_msg = {
    "role": "assistant",
    "content": content_buf or None,
    "reasoning_content": reasoning_content_buf,  # ★
    "tool_calls": [
        {
            "id": f"call_{i}",
            "type": "function",
            "function": {
                "name": tool["name"],
                "arguments": tool["arguments_str"],
            }
        }
        for i, tool in collected_tools.items()
    ]
}

# 4. 工具回调（★ tool_handler 替代写死的 "ok"）
tool_results = []
for i, tool in collected_tools.items():
    args = json.loads(tool["arguments_str"])
    yield {"type": "tool_call", "name": tool["name"], "arguments": args}

    if tool_handler:
        result_str = await tool_handler(tool["name"], args)
    else:
        result_str = "ok"

    tool_results.append({
        "role": "tool",
        "tool_call_id": f"call_{i}",
        "content": result_str,
    })

# 5. 继续多轮（最多 5 轮）
messages = messages + [assistant_msg] + tool_results
# 重新请求 Kimi，继续流式输出...
```

### 6.2 M-B：产品查询（product_search.py）

**主要修复（Sprint 1）：**

```python
# 完整修复后的 SQL 查询（注意两处 COLLATE）
await cur.execute("""
    SELECT
        p.product_id, p.product_name, p.company_name,
        p.sale_status, p.long_short_term, p.tag, p.waiting_period,
        MAX(CASE WHEN c.coverage_name = '投保年龄'   THEN pc.standard_content END) AS age_range,
        MAX(CASE WHEN c.coverage_name = '保险期间'   THEN pc.standard_content END) AS insurance_period,
        MAX(CASE WHEN c.coverage_name = '交费期间'   THEN pc.standard_content END) AS payment_period,
        MAX(CASE WHEN c.coverage_name = '等待期'     THEN pc.standard_content END) AS waiting_period_detail,
        MAX(CASE WHEN c.coverage_name = '重疾赔付次数' THEN pc.standard_content END) AS critical_pay_times,
        MAX(CASE WHEN c.coverage_name = '轻症赔付次数' THEN pc.standard_content END) AS mild_pay_times
    FROM cmb_product p
    LEFT JOIN cmb_product_coverage pc
        ON p.product_id COLLATE utf8mb4_unicode_ci = pc.product_id  -- ★ COLLATE
        AND pc.is_deleted = 0
    LEFT JOIN cmb_coverage c
        ON pc.coverage_id = c.coverage_id
        AND c.coverage_name IN ('投保年龄','保险期间','交费期间','等待期','重疾赔付次数','轻症赔付次数')
        AND c.is_deleted = 0
    WHERE p.is_deleted = 0
    GROUP BY p.product_id, p.product_name, p.company_name,
             p.sale_status, p.long_short_term, p.tag, p.waiting_period
    ORDER BY p.product_id
    LIMIT 50
""")
```

**新增接口（Sprint 2，供 M-E 评分使用）：**

```python
async def fetch_products_for_scoring(
    age: int,
    gender: str,          # "male" 或 "female"
    budget_annual: int,
    preferred_company: str = None,
) -> list[dict]:
    """
    返回产品列表，每条含费率数据，供评分算法使用。
    费率查询固定参数：
      pay_time=20, pay_time_type=10(年), insure_period=999(终身),
      period_type=14(终身), pay_type=12(年交), smoke=10(不吸烟),
      social_security=0(不限), 保额=500000(50万)
    返回格式：[{
        "product_id": "...",
        "product_name": "...",
        "company_name": "...",
        "sale_status": "Y/N/P",
        "waiting_period": 90,       # 天
        "age_range": "0-17周岁",
        "annual_premium": 5600,     # 元（rate × 500000 计算）
        "disease_counts": {"重大疾病": 120, "轻症": 50},  # 来自 cmb_product_disease
        "preferred": False          # 是否匹配用户偏好公司
    }]
    """
    # gender 映射：male→11，female→10
    gender_code = 11 if gender == "male" else 10

    # 费率查询 SQL（同样需要 COLLATE）
    sql = """
        SELECT p.product_id, p.product_name, p.company_name,
               p.sale_status, p.waiting_period,
               MAX(CASE WHEN c.coverage_name='投保年龄' THEN pc.standard_content END) as age_range,
               pr.rate
        FROM cmb_product p
        LEFT JOIN cmb_product_coverage pc
            ON p.product_id COLLATE utf8mb4_unicode_ci = pc.product_id AND pc.is_deleted=0
        LEFT JOIN cmb_coverage c
            ON pc.coverage_id = c.coverage_id AND c.coverage_name = '投保年龄' AND c.is_deleted=0
        LEFT JOIN cmb_product_rate pr
            ON p.product_id COLLATE utf8mb4_unicode_ci = pr.product_id
            AND pr.age = %s AND pr.gender IN (0, %s)
            AND pr.pay_time = 20 AND pr.pay_time_type = 10
            AND pr.insure_period = 999 AND pr.period_type = 14
            AND pr.pay_type = 12 AND pr.smoke = 10 AND pr.social_security = 0
        WHERE p.is_deleted = 0
        GROUP BY p.product_id, p.product_name, p.company_name,
                 p.sale_status, p.waiting_period, pr.rate
    """
```

### 6.3 M-C：记忆系统（memory_store.py，已实现）

**接口（无需修改，仅参考）：**

```python
async def load_core_memory(profile_id: str) -> dict | None
async def update_core_memory(profile_id: str, field: str, value: Any) -> None
async def load_recent_summaries(profile_id: str, limit: int = 3) -> list[dict]
async def save_summary(profile_id: str, summary: str, recommendation: str = "") -> None
def format_memory_for_prompt(core: dict | None, summaries: list[dict]) -> str
```

**允许更新的字段（field 参数白名单）：**
`basic_info`, `financial_status`, `existing_insurance`, `preferences`, `purchased_products`

### 6.4 M-D：需求分析（needs_analysis.py，新建）

```python
import json, uuid
from datetime import datetime

async def save_needs_report(profile_id: str, report: dict) -> str:
    """保存结构化需求报告，返回 report_id"""
    report_id = str(uuid.uuid4())
    async with get_aix_conn() as conn:
        async with conn.cursor() as cur:
            await cur.execute("""
                INSERT INTO insurance_need_reports
                (id, profile_id, age, gender, budget_annual, family_structure,
                 health_status, existing_coverage, primary_concern, preferred_company, report_json)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                report_id, profile_id,
                report.get("age"), report.get("gender"), report.get("budget_annual"),
                report.get("family_structure"), report.get("health_status"),
                report.get("existing_coverage"), report.get("primary_concern"),
                report.get("preferred_company"), json.dumps(report, ensure_ascii=False)
            ))
    return report_id

async def update_report_recommendations(report_id: str, top3: list[dict]) -> None:
    """在报告中写入 Top3 推荐结果"""
    async with get_aix_conn() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "UPDATE insurance_need_reports SET recommended_products=%s WHERE id=%s",
                (json.dumps(top3, ensure_ascii=False), report_id)
            )

async def load_latest_report(profile_id: str) -> dict | None:
    """读取最新需求报告"""
    async with get_aix_conn() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT * FROM insurance_need_reports WHERE profile_id=%s ORDER BY created_at DESC LIMIT 1",
                (profile_id,)
            )
            return await cur.fetchone()

def build_report_summary(report: dict) -> dict:
    """构建前端展示用的摘要"""
    return {
        "age": report.get("age"),
        "gender": "男" if report.get("gender") == "male" else "女",
        "budget_annual": report.get("budget_annual"),
        "primary_concern": report.get("primary_concern", "重大疾病"),
        "family_structure": report.get("family_structure"),
    }
```

### 6.5 M-E：产品评分引擎（product_scorer.py，新建）

**评分维度（100分制）：**

| 维度 | 权重 | 计算逻辑 |
|------|------|---------|
| 年龄适配 | 20% | 用户年龄在 age_range 内=满分；范围外=0分（过滤） |
| 预算匹配 | 20% | `ratio = annual_premium / budget`：0.3-0.8=满分，>1.2=0分（买不起），<0.2=60分（保额可能不足） |
| 保障完整性 | 15% | `重疾病种数 / 120种 × 13`（最高13分）；有轻症+1分，有中症+1分 |
| **性价比（精算）** | **20%** | **`value_ratio = 实际保费 / 精算公允保费`；ratio≤0.90=20分；1.0=12分；>1.20=0分；服务不可用=跳过（该项权重转入保障完整性）** |
| 等待期 | 10% | ≤90天=10分；91-180天=6分；>180天=2分 |
| 在售状态 | 8% | Y=8分；P=5分；N=0分 |
| 公司偏好 | 7% | 用户指定公司=7分；无偏好：主流公司6分，其他5分 |

```python
async def score_products(products: list[dict], needs: dict) -> list[dict]:
    """
    products: fetch_products_for_scoring 的返回值
    needs: generate_needs_report 工具的参数
    返回：按分数降序排列的 Top3，含 score_breakdown
    """
    age = needs.get("age", 35)
    # 预算优先使用用户自述，否则从年收入推算（5%~10%）
    annual_income = needs.get("annual_income", 0)
    budget = needs.get("budget_annual") or (annual_income * 0.07 if annual_income else 8000)
    preferred = needs.get("preferred_company", "")

    scored = []
    for p in products:
        breakdown = {}

        # 1. 年龄适配（25分）
        age_range = p.get("age_range", "")
        breakdown["age_fit"] = _score_age(age, age_range) * 25

        # 2. 预算匹配（25分）
        premium = p.get("annual_premium", 0)
        ratio = (premium / budget) if budget > 0 else 1
        if 0.3 <= ratio <= 0.8:   breakdown["budget_match"] = 25
        elif 0.8 < ratio <= 1.0:  breakdown["budget_match"] = 18
        elif 1.0 < ratio <= 1.2:  breakdown["budget_match"] = 8
        elif ratio > 1.2:         breakdown["budget_match"] = 0
        else:                     breakdown["budget_match"] = 15  # 太便宜保额可能不足

        # 3. 保障完整性（20分）
        critical = p.get("disease_counts", {}).get("重大疾病", 0)
        mild     = p.get("disease_counts", {}).get("轻症", 0)
        breakdown["coverage"] = min(critical / 120 * 18, 18) + (2 if mild > 20 else 0)

        # 4. 等待期（10分）
        wp = p.get("waiting_period", 180)
        if wp <= 90:   breakdown["waiting_period"] = 10
        elif wp <= 180: breakdown["waiting_period"] = 6
        else:          breakdown["waiting_period"] = 2

        # 5. 在售状态（10分）
        status = p.get("sale_status", "N")
        breakdown["sale_status"] = {"Y": 10, "P": 6, "N": 0}.get(status, 0)

        # 5b. 性价比（精算，20分）——异步调用 Java 精算服务
        annual_premium = p.get("annual_premium", 0)
        fair_premium = await get_fair_premium(p["product_id"], age, "male" if needs.get("gender")=="male" else "female")
        if fair_premium > 0 and annual_premium > 0:
            vr = annual_premium / fair_premium
            if vr <= 0.90:    breakdown["value_score"] = 20
            elif vr <= 1.00:  breakdown["value_score"] = round(20 - (vr - 0.90) / 0.10 * 8, 1)
            elif vr <= 1.20:  breakdown["value_score"] = round(max(0, 12 - (vr - 1.00) / 0.20 * 12), 1)
            else:             breakdown["value_score"] = 0
            breakdown["value_ratio"] = round(vr, 3)
        else:
            # 精算服务不可用：跳过，将 20 分权重转移至保障完整性
            breakdown["value_score"] = 0
            breakdown["coverage"] = min(breakdown["coverage"] + 20, 35)

        # 6. 公司偏好（7分）
        MAJOR_COMPANIES = {"国寿", "平安", "太平洋", "新华", "泰康", "太平", "友邦",
                           "人保", "中信保诚", "招商信诺", "阳光"}
        company = p.get("company_name", "")
        if preferred and preferred in company:
            breakdown["preference"] = 7
        elif company in MAJOR_COMPANIES:
            breakdown["preference"] = 6
        else:
            breakdown["preference"] = 5

        total = sum(v for k, v in breakdown.items() if k != "value_ratio")
        scored.append({**p, "total_score": round(total, 1), "score_breakdown": breakdown})

    # 过滤掉不在年龄范围内（0分）的产品，按分数降序取 Top3
    valid = [s for s in scored if s["score_breakdown"]["age_fit"] > 0]
    return sorted(valid, key=lambda x: x["total_score"], reverse=True)[:3]
```

### 6.6 M-精算：精算公允定价引擎（Java Spring Boot）

**职责：** 基于标准精算公式，计算指定产品对特定年龄/性别客户的**市场公允年保费**，供产品评分模块计算性价比。

#### 核心精算公式

```
GP（年缴毛保费）= PVFB ÷ (AnnuityDue - PV_Loading)

PVFB       = Σ[t=1..T] px_t × (qd_t × CI_mult + qci_t) × SA × v^t
           （未来保险金现值：死亡赔付 + 重疾赔付）

AnnuityDue = Σ[t=1..PPP] px_t × v^(t-1)
           （缴费期内的生存年金现值，缴费年度初计）

PV_Loading = Σ[t=1..PPP] px_t × loading_rate × v^(t-1)
           （附加费用现值）

其中：
  px_t  = 生存到第 t 年初的概率 = ∏[i=0..t-1] (1 - qd_i - qci_i)
  qd_t  = 第 t 年死亡率（从 actuarial_qx_table 读取）
  qci_t = 第 t 年重疾发病率（从 actuarial_ci_table 读取）
  v     = 1 / (1 + pricing_rate)   折现因子
  T     = 保障期（终身取 IssueAge 到 105）
  PPP   = 缴费期（默认20年）
  SA    = 保额（默认 500,000 元）
  CI_mult = 重疾赔付倍数（通常=1，即一次性赔付保额）
  loading_rate = 附加费用率（从 product_actuarial_config 读取，默认 0.25）
```

#### 性价比评分规则

```
value_ratio = 产品实际年保费 / 精算公允年保费（GP）

value_ratio ≤ 0.90 → 性价比满分（20分），不再额外加分
value_ratio 0.90~1.00 → 线性插值：20 × (1 - (ratio-0.90)/0.10)
value_ratio = 1.00 → 基准（0加减）→ 12分
value_ratio 1.00~1.20 → 每超出1%扣1分，最低 0 分
value_ratio > 1.20 → 0分（明显高于市场公允价格）
注：实际年保费低于公允价格10%以上不再增加额外分数（封顶保护防数据错误）
```

#### Java 接口定义

```java
// controller/PricingController.java
@RestController
@RequestMapping("/api/v1/actuarial")
public class PricingController {

    @GetMapping("/fair-price")
    public ResponseEntity<FairPriceResponse> getFairPrice(
        @RequestParam String productId,
        @RequestParam int age,
        @RequestParam String gender   // "male" | "female"
    ) {
        double fairPremium = pricingEngine.calculate(productId, age, gender);
        return ResponseEntity.ok(new FairPriceResponse(productId, age, gender, fairPremium));
    }
}

// 返回结构
record FairPriceResponse(
    String productId,
    int age,
    String gender,
    double fairPremium,   // 公允年保费（元）
    double pricingRate,   // 使用的预定利率
    String mortalityTable // 使用的死亡率表
) {}
```

#### Python 调用方式（product_scorer.py 内）

```python
import httpx

async def get_fair_premium(product_id: str, age: int, gender: str) -> float:
    """调用 Java 精算服务获取公允年保费，失败时返回 0（跳过精算评分）"""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(
                f"{JAVA_SERVICE_URL}/api/v1/actuarial/fair-price",
                params={"productId": product_id, "age": age, "gender": gender}
            )
            return r.json().get("fairPremium", 0)
    except Exception:
        return 0  # 精算服务不可用时，该维度得分为 0，不影响其他评分
```

#### 后台配置入口

精算参数通过管理后台录入 `product_actuarial_config` 表，每款产品配置一行：
- 管理后台新增 **精算配置** Tab（Sprint 4）
- 支持批量导入：上传 CSV → 写入 `product_actuarial_config`
- 死亡率表初始数据：从 `保险产品定价20200923.xlsm` 的 Qtable sheet 导出 CSV 后导入

### 6.7 M-H：对话引擎（chat_engine.py，重写）

#### 6个 Function Calling 工具定义

```python
CHAT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "show_options",
            "description": "当你需要用户做选择时调用，展示快捷选项卡片。适用：年龄段/预算范围/险种选择/是否/公司偏好等。调用后继续输出文字，选项卡片显示在消息下方。选项4-8字，2-5个。",
            "parameters": {
                "type": "object",
                "properties": {
                    "options": {"type": "array", "items": {"type": "string"}, "description": "选项列表"}
                },
                "required": ["options"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_core_memory",
            "description": "获得用户新信息时调用，保存到长期记忆。不要重复保存已知信息。",
            "parameters": {
                "type": "object",
                "properties": {
                    "field": {
                        "type": "string",
                        "enum": ["basic_info", "financial_status", "existing_insurance", "preferences", "purchased_products"],
                        "description": "记忆字段名"
                    },
                    "value": {"description": "要保存的值（dict 或 list）"}
                },
                "required": ["field", "value"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "save_recall_summary",
            "description": "对话阶段性总结时调用，保存本次对话摘要和推荐方案到记忆。",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string", "description": "对话关键摘要（100字内）"},
                    "recommendation": {"type": "string", "description": "本次推荐的产品和理由"}
                },
                "required": ["summary"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "report_issue",
            "description": "遇到能力边界时调用：数据库没有的产品、无法回答的专业问题、数据缺失。",
            "parameters": {
                "type": "object",
                "properties": {
                    "issue_type": {
                        "type": "string",
                        "enum": ["unknown_product", "unanswerable_question", "data_missing"]
                    },
                    "description": {"type": "string", "description": "问题描述（50字内）"},
                    "user_query": {"type": "string", "description": "用户原始问题"}
                },
                "required": ["issue_type", "description", "user_query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "start_needs_analysis",
            "description": "用户明确表达购买意向时调用，启动结构化需求收集流程。触发词：'我想买'/'帮我推荐'/'做个规划'/'买什么保险好'。",
            "parameters": {
                "type": "object",
                "properties": {
                    "trigger_reason": {"type": "string", "description": "触发原因简述"}
                },
                "required": ["trigger_reason"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "generate_needs_report",
            "description": "收集完出生日期/家庭结构/健康状况等必要信息后调用，生成结构化保险需求报告并触发产品评分。",
            "parameters": {
                "type": "object",
                "properties": {
                    "birth_date":       {"type": "string", "description": "被保人出生年月，格式 YYYY-MM（如：1990-05），用于精确计算年龄"},
                    "age":              {"type": "integer", "description": "被保人当前年龄（从 birth_date 计算得出）"},
                    "gender":           {"type": "string", "enum": ["male", "female"], "description": "性别"},
                    "annual_income":    {"type": "integer", "description": "年收入（元，可选），用于计算建议保费预算"},
                    "budget_annual":    {"type": "integer", "description": "年缴保费预算（元，可选）；若未提供则由 annual_income × 5%~10% 自动推算"},
                    "family_structure": {"type": "string", "description": "家庭结构（用户自述，如：已婚有1个孩子/离婚带孩/单身等）"},
                    "health_status":    {"type": "string", "description": "健康状况（用户自述，如：良好，无基础疾病）"},
                    "existing_coverage":{"type": "string", "description": "已有保险（如：有社保，有平安寿险）"},
                    "primary_concern":  {"type": "string", "description": "主要顾虑/险种（如：重大疾病，癌症）"},
                    "preferred_company":{"type": "string", "description": "偏好保险公司（可空）"}
                },
                "required": ["birth_date", "age", "gender", "family_structure", "health_status"]
            }
        }
    }
]
```

#### 系统提示词结构

```python
def build_chat_system_prompt(
    products_text: str,
    memory_text: str,
    rules_text: str,
    has_image: bool = False,
) -> str:
    return f"""你是 AIX 保险智能顾问，专业、温暖、实用，用口语化中文交流。

## 角色定位
你的目标是帮用户理解保险需求，推荐最适合的产品，并提供专业解读。
重要原则：只推荐产品数据库中存在的产品，遇到数据库外的产品，诚实告知并调用 report_issue。

## 产品险种分类（当前只有重疾险可推荐）
当前数据库仅含重疾险（类型6001），其他险种暂无数据：
- 重疾长期型 6001 ← 当前可推荐
- 重疾消费型 6003 / 重疾返还型 6002（暂无数据）
- 百万医疗险 7001 / 寿险 1001-3002（暂无数据）
用户问其他险种时，诚实说明"当前版本暂未收录该险种"，并调用 report_issue。

## 工具使用规则
- `show_options`：提问或让用户选择时**优先调用**，选项简短（4-8字），2-5个
- `update_core_memory`：获得新的用户信息时调用（年龄/预算/健康/家庭/已有保险）
- `save_recall_summary`：对话完成一轮推荐后调用
- `report_issue`：遇到无法回答或数据库缺失时调用
- `start_needs_analysis`：用户表达购买意向时调用
- `generate_needs_report`：收集完4项必填信息后调用（触发自动评分推荐）

## 快捷选项卡片使用规则（show_options）
卡片主要用于**场景选择**，而非数据收集。典型场景：
- 用户说"我想买保险"→ show_options：["直接填问卷", "聊聊再推荐", "先看产品对比"]
- 用户说"我不确定买什么"→ show_options：["帮我分析需求", "直接推荐热门", "解释险种区别"]
- 选择采集方式后，卡片底部可提供参考示例（如"例：1990年5月出生"）
- 具体信息字段（年龄/金额/家庭情况）：优先让用户自由输入，AI 辅助解析；
  仅在用户明显迷茫时才用卡片给参考选项，选项作为"提示"而非"限制"

## 需求收集规则（start_needs_analysis 触发后）
按优先级收集，每次最多问2个问题，用户可自由输入，AI 解析并存入记忆：

**必填项（收集完即可生成报告）：**
1. 被保人出生年月日（必填，精确到月）
   - 引导语："请告诉我被保人的出生年月日，比如：1990年5月"
   - ⚠️ 不使用年龄区间选项，收集精确日期用于计算实际年龄
2. 健康状况（必填）
   - 引导语："请描述被保人的健康状况，比如是否有慢性病、手术史等"
   - show_options 参考底部提示：["健康，无病史", "有慢性病（高血压/糖尿病等）", "有手术或住院史"]
3. 家庭结构（必填）
   - 引导语："请描述您的家庭情况"
   - show_options 参考底部提示：["单身", "已婚无孩", "已婚有孩", "离婚", "离婚有孩子", "为孩子单独投保"]
   - 用户可补充具体情况（如孩子年龄、家庭责任等）

**重要项（尽量收集，影响推荐质量）：**
4. 年收入与财务状况（用于计算建议预算，非直接问预算金额）
   - 引导语："了解一下您的大致年收入范围，帮我计算适合您的保费预算"
   - show_options 参考：["10万以下", "10-30万", "30-80万", "80万以上"]
   - AI 根据年收入自动推算建议保费区间（通常为年收入5%-10%）
   - ⚠️ 不直接问"预算多少"，而是通过财务信息计算；用户也可直接告知预算
5. 已有保险（重要）
   - 引导语："目前有哪些保险？"
   - show_options 参考：["仅社保", "有商业保险", "无任何保险"]
6. 主要顾虑（重要）
   - show_options 参考：["重大疾病", "癌症专项", "轻症保障", "尽量保额高"]
7. 公司偏好（可选）
   - show_options 参考：["国寿/平安/太保", "招商信诺/中信保诚", "无偏好"]

收集完必填项（1+3）+ 任意2项重要项即可调用 generate_needs_report。

{f'''## 图片识别规则（本次对话包含图片）
按图片类型处理：
1. 保险单/合同：识别险种、保额、被保人、等待期、受益人 → update_core_memory 保存到 existing_insurance → 分析保障缺口
2. 体检报告/病历：识别关键异常指标 → 评估核保风险 → 建议适合险种（⚠️提醒：体检结果影响核保，如实告知）
3. 条款截图：用通俗语言解释含义，指出免责条款
4. 身份证/投保单：提取姓名/生日/性别 → update_core_memory（⚠️不存储身份证号，告知用户不保留原图）
5. 已购保险清单：汇总保障层次（医疗/重疾/寿险/意外）→ 识别缺口和重复覆盖
''' if has_image else ''}

## 用户记忆
{memory_text if memory_text else "（暂无记忆，这是首次对话）"}

## 行为规范
{rules_text}

## 可推荐的产品数据库
{products_text if products_text else "（产品数据暂时加载中，请稍后再问具体产品）"}

## 基本原则
- 不承诺投资收益或理赔结果
- 引用数据时注明"以合同为准"
- 不重复问已知信息（参考用户记忆）
- 语气专业但口语化，像朋友咨询而非推销
- 每次回复聚焦一个主题，不要一次给太多信息"""
```

### 6.7 M-G：对话路由（chat.py，重写）

**完整编排流程：**

```python
@router.post("/internal/chat")
async def chat_endpoint(request: Request):
    body = await request.json()
    messages = body.get("messages", [])
    profile_id = body.get("profile_id")
    image_data = body.get("image")        # {"base64": "data:image/jpeg;base64,..."}

    return StreamingResponse(event_stream(), media_type="text/event-stream")

async def event_stream():
    try:
        # 1. 并行加载：产品数据 + 用户记忆
        products_text, core_memory, summaries = await asyncio.gather(
            fetch_products_text(),
            load_core_memory(profile_id) if profile_id else None,
            load_recent_summaries(profile_id) if profile_id else [],
        )

        # 2. 格式化记忆
        memory_text = format_memory_for_prompt(core_memory, summaries)

        # 3. RAG 规则注入（基于最后一条用户消息的意图）
        last_user_msg = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        rules_text = get_relevant_rules(last_user_msg)

        # 4. 处理图片（若有，修改最后一条 user 消息为多模态格式）
        has_image = bool(image_data)
        if has_image and messages:
            last_text = last_user_msg or "请分析这张图片"
            messages = messages[:-1] + [{
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": image_data["base64"]}},
                    {"type": "text", "text": last_text}
                ]
            }]

        # 5. 构建系统提示词
        system = build_chat_system_prompt(products_text, memory_text, rules_text, has_image)

        # 6. 定义工具回调（★ 让 Kimi 基于真实数据解释）
        async def tool_handler(name: str, args: dict) -> str:
            if name == "show_options":
                options = args.get("options", [])
                yield sse_event("options", json.dumps({"options": options}, ensure_ascii=False))
                return "选项已展示"

            elif name == "update_core_memory" and profile_id:
                await update_core_memory(profile_id, args.get("field"), args.get("value"))
                return "记忆已更新"

            elif name == "save_recall_summary" and profile_id:
                await save_summary(profile_id, args.get("summary",""), args.get("recommendation",""))
                return "摘要已保存"

            elif name == "report_issue":
                await record_issue(args.get("issue_type"), args.get("description"),
                                   args.get("user_query"), profile_id)
                return "问题已记录"

            elif name == "start_needs_analysis":
                return "已启动需求分析模式，请继续收集用户信息"

            elif name == "generate_needs_report":
                # 保存需求报告
                report_id = await save_needs_report(profile_id or "anonymous", args)
                # 触发产品评分
                products_raw = await fetch_products_for_scoring(
                    age=args.get("age", 35),
                    gender=args.get("gender", "male"),
                    budget_annual=args.get("budget_annual", 8000),
                    preferred_company=args.get("preferred_company"),
                )
                top3 = score_products(products_raw, args)
                # 更新报告中的推荐产品
                if report_id != "anonymous":
                    await update_report_recommendations(report_id, top3)
                # 发送 SSE 事件给前端
                summary = build_report_summary(args)
                yield sse_event("needs_report", json.dumps({
                    "report_id": report_id,
                    "summary": summary,
                }, ensure_ascii=False))
                yield sse_event("product_recommendations", json.dumps({
                    "top3": top3
                }, ensure_ascii=False))
                # 返回评分结果供 Kimi 解释
                return json.dumps({"top3": [
                    {"name": p["product_name"], "company": p["company_name"],
                     "score": p["total_score"], "annual_premium": p.get("annual_premium", 0)}
                    for p in top3
                ]}, ensure_ascii=False)

            return "ok"

        # 7. 调用 Kimi，流式输出
        async for event in call_kimi_with_tools(
            system=system,
            messages=messages,
            tools=CHAT_TOOLS,
            tool_handler=tool_handler,
        ):
            if event["type"] == "chunk":
                yield sse_event("chunk", json.dumps({"content": event["content"]}, ensure_ascii=False))
            elif event["type"] == "done":
                yield sse_event("done", "{}")

    except Exception as e:
        logger.error(f"Chat error: {e}")
        yield sse_event("error", json.dumps({"message": str(e)}, ensure_ascii=False))
```

**注意：** `tool_handler` 既是 async 函数（有 `await`），又需要 `yield` SSE 事件。实现时需要用 `asyncio.Queue` 或将 SSE yield 和 return 分离：SSE yield 通过队列传出，return 返回工具结果字符串。

### 6.8 M-F：ASR Token 服务（aix-bff/src/routes/asr.ts，新建）

```typescript
// aix-bff/src/routes/asr.ts
import { Router, Request, Response } from 'express'

const router = Router()

// 简单内存缓存（生产用 Redis）
let tokenCache: { token: string; expiresAt: number } | null = null

router.get('/token', async (req: Request, res: Response) => {
  try {
    const now = Date.now()
    // 有效期内直接返回缓存
    if (tokenCache && tokenCache.expiresAt > now + 60_000) {
      return res.json({ token: tokenCache.token, expires_at: new Date(tokenCache.expiresAt).toISOString() })
    }

    // 向 Aliyun NLS 获取 Token
    // Aliyun NLS Token API：POST https://nls-meta.cn-shanghai.aliyuncs.com/
    // 使用阿里云 SDK：@alicloud/pop-core 或手写 HMAC 签名
    const token = await fetchAliyunNlsToken(
      process.env.ALIYUN_ACCESS_KEY_ID!,
      process.env.ALIYUN_ACCESS_KEY_SECRET!,
    )

    const expiresAt = now + 10 * 60 * 1000  // 10分钟
    tokenCache = { token, expiresAt }

    res.json({ token, expires_at: new Date(expiresAt).toISOString() })
  } catch (e: any) {
    res.status(500).json({ error: e.message })
  }
})

export default router

// 注册路由（在 index.ts 中）：
// import asrRouter from './routes/asr'
// app.use('/api/v1/asr', asrRouter)
```

---

## 第七章 前端模块详细规范

### 7.1 M-I：Store 扩展（useStore.ts）

**ChatMessage 接口扩展：**

```typescript
// 现有接口
interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  options?: string[]
}

// 扩展后
interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  options?: string[]
  imageUrl?: string               // 本地 blob URL，仅用于展示，不持久化
  needsReport?: {                 // 需求报告摘要
    report_id: string
    summary: {
      age: number
      gender: string
      budget_annual: number
      primary_concern: string
      family_structure: string
    }
  }
  productRecommendations?: Array<{  // Top3 产品推荐
    product_id: string
    product_name: string
    company_name: string
    total_score: number
    annual_premium: number
    score_breakdown: Record<string, number>
  }>
}
```

**重要：** `imageUrl`（blob:URL）是内存 URL，**不能**存入 localStorage（会失效）。在 Zustand `partialize` 中排除：

```typescript
partialize: (state) => ({
  ...state,
  chatMessages: state.chatMessages.map(m => ({
    ...m,
    imageUrl: undefined,  // 不持久化 blob URL
  })),
}),
```

### 7.2 M-K：图片输入（ImageInput.tsx）

```typescript
interface ImageInputProps {
  onImage: (base64: string, previewUrl: string, mimeType: string) => void
  disabled: boolean
}

export function ImageInput({ onImage, disabled }: ImageInputProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const isMobile = window.innerWidth < 768

  const handleFile = (file: File) => {
    if (!file.type.startsWith('image/')) return
    // 读取 base64
    const reader = new FileReader()
    reader.onload = (e) => {
      const base64 = e.target?.result as string    // "data:image/jpeg;base64,..."
      const previewUrl = URL.createObjectURL(file)  // blob: URL 用于展示
      onImage(base64, previewUrl, file.type)
    }
    reader.readAsDataURL(file)
  }

  return (
    <>
      {/* 手机端：弹出选择框（相机/相册） */}
      {isMobile ? (
        <input ref={inputRef} type="file" accept="image/*" capture="environment"
          className="hidden" onChange={e => e.target.files?.[0] && handleFile(e.target.files[0])} />
      ) : (
        /* 桌面端：支持拖拽 + 文件选择 */
        <input ref={inputRef} type="file" accept="image/*"
          className="hidden" onChange={e => e.target.files?.[0] && handleFile(e.target.files[0])} />
      )}
      <button onClick={() => !disabled && inputRef.current?.click()}
        disabled={disabled}
        className="p-2 rounded-lg text-gray-500 hover:text-accent hover:bg-accent/10 disabled:opacity-40 transition-colors"
        title="上传图片">
        <ImageIcon size={20} />
      </button>
    </>
  )
}
```

### 7.3 M-J：语音输入（VoiceInput.tsx）

```typescript
interface VoiceInputProps {
  onTranscript: (text: string) => void   // 最终识别结果
  onInterim: (text: string) => void      // 实时中间结果（显示在输入框内，灰色）
  disabled: boolean
}

// 核心状态机
type RecordState = 'idle' | 'connecting' | 'recording' | 'processing'

export function VoiceInput({ onTranscript, onInterim, disabled }: VoiceInputProps) {
  const [state, setState] = useState<RecordState>('idle')
  const isMobile = window.innerWidth < 768

  // 手机端：长按 PTT（Push-to-Talk）
  // 桌面端：点击开始/点击结束

  const startRecording = async () => {
    setState('connecting')
    // 1. 从 BFF 获取 Aliyun NLS token
    const { token } = await fetch('/api/v1/asr/token').then(r => r.json())

    // 2. 请求麦克风权限
    const stream = await navigator.mediaDevices.getUserMedia({ audio: {
      sampleRate: 16000, channelCount: 1, echoCancellation: true
    }})

    // 3. 连接 Aliyun NLS WebSocket
    const ws = new WebSocket(
      `wss://nls-gateway.cn-shanghai.aliyuncs.com/ws/v1?token=${token}`
    )

    ws.onopen = () => {
      // 发送开始识别指令
      ws.send(JSON.stringify({
        header: { name: "StartTranscription", appkey: ALIYUN_NLS_APP_KEY },
        payload: { format: "pcm", sample_rate: 16000, enable_intermediate_result: true }
      }))
      setState('recording')
    }

    ws.onmessage = (e) => {
      const msg = JSON.parse(e.data)
      if (msg.header.name === "TranscriptionResultChanged") {
        onInterim(msg.payload.result)  // 实时中间结果
      } else if (msg.header.name === "SentenceEnd") {
        onTranscript(msg.payload.result)  // 最终结果
        setState('idle')
      }
    }

    // 4. MediaRecorder → 发送 PCM 音频块
    const recorder = new MediaRecorder(stream)
    recorder.ondataavailable = (e) => {
      if (ws.readyState === WebSocket.OPEN) ws.send(e.data)
    }
    recorder.start(100)  // 每 100ms 发一次
  }

  // 手机端长按样式：按住=红色脉冲；松开=停止
  // 桌面端单击样式：点击开关

  return (
    <button
      onMouseDown={isMobile ? startRecording : undefined}
      onMouseUp={isMobile ? stopRecording : undefined}
      onTouchStart={isMobile ? startRecording : undefined}
      onTouchEnd={isMobile ? stopRecording : undefined}
      onClick={!isMobile ? toggleRecording : undefined}
      disabled={disabled}
      className={`p-2 rounded-lg transition-colors ${
        state === 'recording'
          ? 'text-red-500 bg-red-50 animate-pulse'
          : 'text-gray-500 hover:text-accent hover:bg-accent/10'
      } disabled:opacity-40`}
      title={isMobile ? "长按说话" : "点击说话"}>
      <MicIcon size={20} />
    </button>
  )
}
```

### 7.4 M-L：输入栏（ChatInputBar.tsx）

**桌面端布局：**

```
[🖼️] [🎤]   [文字输入框（自动增高，Enter发送）]   [↑发送]
```

**手机端布局：**

```
[文字输入框（单行）]   [↑发送]
[🖼️图片]  [🎤长按说话]
```

```typescript
interface ChatInputBarProps {
  onSend: (text: string, image?: { base64: string; mimeType: string }) => void
  disabled: boolean
}

export function ChatInputBar({ onSend, disabled }: ChatInputBarProps) {
  const [input, setInput] = useState('')
  const [interimText, setInterimText] = useState('')  // 语音识别中间结果
  const [pendingImage, setPendingImage] = useState<{base64:string; previewUrl:string; mimeType:string} | null>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const isMobile = window.innerWidth < 768

  const handleSend = () => {
    const text = input.trim()
    if (!text && !pendingImage) return
    onSend(text, pendingImage ? { base64: pendingImage.base64, mimeType: pendingImage.mimeType } : undefined)
    setInput('')
    setPendingImage(null)
    if (textareaRef.current) textareaRef.current.style.height = 'auto'
  }

  const handleTranscript = (text: string) => {
    setInput(prev => prev + text)
    setInterimText('')
  }

  // 图片预览条（有 pendingImage 时显示在输入框上方）
  // ...
}
```

### 7.5 M-P：需求报告卡片（NeedsReportCard.tsx）

```typescript
interface NeedsReportCardProps {
  summary: {
    age: number; gender: string; budget_annual: number
    primary_concern: string; family_structure: string
  }
  onViewRecommendations: () => void
}

// 桌面展开版
// ┌────────────────────────────────────┐
// │ 📋 需求分析报告                     │
// │ 35岁男性 · 年预算 8,000元            │
// │ 家庭型(已婚有孩) · 健康状况良好        │
// │ 主要顾虑：重大疾病                    │
// │            [查看推荐产品 →]          │
// └────────────────────────────────────┘

// 手机折叠版（默认折叠，点击展开）
// ┌────────────────────────────────┐
// │ 📋 需求报告 35岁·8000元·重疾  ▼  │
// └────────────────────────────────┘
```

### 7.6 M-N：产品推荐卡片（ProductRecommendCard.tsx）

```typescript
// 桌面3列
// ┌──────────┬──────────┬──────────┐
// │#1 招商信诺 │#2 中国人寿 │#3 平安人寿 │
// │尊享e生    │福禄长青   │平安福     │
// │评分 92分  │评分 88分  │评分 85分  │
// │~5,600/年  │~4,800/年  │~6,200/年  │
// │●●●●● 年龄│●●●●○ 年龄│●●●●○ 年龄│
// │●●●●● 预算│●●●●● 预算│●●●○○ 预算│
// │[查看详情] │[查看详情] │[查看详情] │
// └──────────┴──────────┴──────────┘

// 手机横向 swipe
// < [#1 招商信诺] [#2 中国人寿] [#3 平安] >
// overflow-x-scroll snap-x snap-mandatory
```

### 7.7 M-O：ChatPage 主页面（ChatPage.tsx，重写）

**SSE 事件处理：**

```typescript
// streamChat 函数接收的所有事件类型
async function streamChat(
  messages: ChatMessage[],
  callbacks: {
    onChunk: (content: string) => void
    onOptions: (options: string[]) => void
    onNeedsReport: (data: NeedsReportData) => void       // ★新增
    onProductRecommendations: (data: ProductRecData) => void  // ★新增
    onDone: () => void
    onError: (message: string) => void
  },
  signal: AbortSignal,
  profileId?: string,
  image?: { base64: string; mimeType: string },         // ★新增
) {
  const response = await fetch('/api/v1/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      messages: messages.map(m => ({ role: m.role, content: m.content })),
      profile_id: profileId,
      image,                                             // ★新增
    }),
    signal,
  })

  // SSE 解析（处理 6 种事件类型）
  const reader = response.body!.getReader()
  // ...解析逻辑，分发到对应 callback
}
```

---

## 第八章 API 文档

### 8.1 AI 对话接口

**BFF 入口：** `POST /api/v1/chat`

**请求体：**

```json
{
  "messages": [
    { "role": "user", "content": "我想买重疾险" },
    { "role": "assistant", "content": "好的，请问..." }
  ],
  "profile_id": "uuid-xxx",
  "image": {
    "base64": "data:image/jpeg;base64,/9j/4AAQ...",
    "mimeType": "image/jpeg"
  }
}
```

**响应（SSE 流）：**

```
event: chunk
data: {"content": "您好，我是AIX保险顾问"}

event: options
data: {"options": ["0-10岁", "11-17岁", "18-35岁"]}

event: needs_report
data: {"report_id": "uuid-xxx", "summary": {"age": 35, "gender": "男", "budget_annual": 8000, "primary_concern": "重大疾病", "family_structure": "已婚有孩"}}

event: product_recommendations
data: {"top3": [{"product_name": "招商信诺尊享e生", "company_name": "招商信诺", "total_score": 92.5, "annual_premium": 5600, "score_breakdown": {...}}]}

event: done
data: {}

event: error
data: {"message": "错误描述"}
```

### 8.2 精算公允定价接口（Java 精算服务）

```
GET http://actuarial:8080/api/v1/actuarial/fair-price
  ?productId=1010003919&age=35&gender=male

Response 200:
{
  "productId": "1010003919",
  "age": 35,
  "gender": "male",
  "fairPremium": 5240.80,       // 精算公允年保费（元，50万保额基准）
  "pricingRate": 0.035,
  "mortalityTable": "CL1_1013_M",
  "ciTable": "CI25_Male"
}

Response 404: { "error": "product_actuarial_config not found for productId" }
Response 500: { "error": "计算失败，请检查精算表数据" }
```

**调用链路：** `product_scorer.py` → BFF（可选透传）→ Java 精算服务 `:8080`
**降级策略：** 若 5 秒内无响应，`get_fair_premium()` 返回 0，评分跳过精算维度

### 8.3 ASR Token 接口

```
GET /api/v1/asr/token

Response 200:
{
  "token": "aliyun-nls-token-string",
  "expires_at": "2026-03-20T11:00:00.000Z"
}
```

### 8.3 管理后台接口（已实现）

```
GET  /api/v1/admin/issues?type=unknown_product&resolved=false&page=1
PATCH /api/v1/admin/issues/:id  { "resolved": true }
GET  /api/v1/admin/config
PUT  /api/v1/admin/config
```

---

## 第九章 双端响应式设计

### 9.1 断点策略

| 断点 | 设备 | 布局 |
|------|------|------|
| `< 768px` (default) | 手机 | 全屏对话，底部导航，单列 |
| `≥ 768px` (md:) | 平板/桌面 | 侧边导航，三栏布局 |

复用现有 MainLayout 的 `mobileView` 状态判断端类型。

### 9.2 ChatPage 布局线框图

**桌面端：**

```
┌─────────────────────────────────────────────────────┐
│ [AIX 保险顾问]    [🧠记忆已激活]         [新对话⊕]  │ header（固定）
├─────────────────────────────────────────────────────┤
│                                                     │
│  ┌──────────────────────────────────────────┐       │
│  │ 助手消息（左，max-w-[60%]，markdown渲染）  │       │ 消息区域
│  └──────────────────────────────────────────┘       │ flex-1
│                                                     │ overflow-y-auto
│            ┌──────────────────────────────────────┐ │
│            │ 用户消息（右，max-w-[60%]，含缩略图）  │ │
│            └──────────────────────────────────────┘ │
│                                                     │
│  ┌──────────────────────────────────────────────────┐│
│  │  📋 需求分析报告（宽卡片，展开4行）                ││ 报告卡
│  └──────────────────────────────────────────────────┘│
│                                                     │
│  ┌────────┬────────┬────────┐                        │
│  │ #1产品 │ #2产品 │ #3产品 │                        │ 3列产品卡
│  └────────┴────────┴────────┘                        │
│                                                     │
├─────────────────────────────────────────────────────┤
│ [🖼️][🎤]  [输入框（Enter发送，Shift+Enter换行）] [↑]│ 输入栏（固定底部）
└─────────────────────────────────────────────────────┘
```

**手机端：**

```
┌─────────────────────────┐
│ ←  AIX 保险顾问  🧠  ⊕  │ header（简化）
├─────────────────────────┤
│                         │
│ 助手消息（max-w-[88%]）  │ 消息区域
│                         │
│    用户消息（右对齐）    │
│                         │
│ ┌─────────────────────┐ │
│ │ 📋需求报告（折叠）  ▼│ │ 折叠卡（点击展开）
│ └─────────────────────┘ │
│                         │
│ ←[#1产品][#2产品][#3]→  │ 横向swipe
│                         │
├─────────────────────────┤
│ [输入框...............] ↑│ 主输入行
│ [🖼️图片]  [🎤长按说话]  │ 工具行
└─────────────────────────┘
  底部导航（MainLayout）
```

### 9.3 各组件双端差异

| 组件 | 桌面 | 手机 |
|------|------|------|
| 消息气泡宽度 | max-w-[60%] | max-w-[88%] |
| 输入栏布局 | 图标在左，输入框在右，一行 | 输入框在上，图标在下，两行 |
| 语音触发 | 单击开始/单击结束 | 长按说话（PTT），44px+触摸区 |
| 图片上传 | 拖拽+文件选择 | 弹出相机/相册选择器 |
| 需求报告卡 | 展开4行 | 折叠为1行，点击展开 |
| 产品推荐卡 | 3列横排 | 横向 swipe（snap-x） |
| 快捷选项 | flex-wrap 换行 | 横向 scroll，按钮更大 |
| Enter 行为 | 发送消息 | 换行（手机键盘Enter=换行） |

### 9.4 手机端特殊处理

```typescript
// 虚拟键盘弹出时滚动到最新消息
useEffect(() => {
  const handler = () => scrollToBottom()
  window.visualViewport?.addEventListener('resize', handler)
  return () => window.visualViewport?.removeEventListener('resize', handler)
}, [])

// 手机端 Enter 键行为（不发送）
const handleKeyDown = (e: KeyboardEvent) => {
  const isMobile = window.innerWidth < 768
  if (e.key === 'Enter' && !e.shiftKey && !isMobile) {
    e.preventDefault()
    handleSend()
  }
}
```

---

## 第十章 产品数据库规划

### 10.1 两套数据格式（不混用）

| 维度 | 测试版（当前）my_ensure | 正式版（规划）aix_product |
|------|------------------------|--------------------------|
| 表命名 | `cmb_product`, `cmb_coverage`... | `product`, `coverage`... |
| 产品ID | 招行格式 `1010003919` | 爱选格式 `10001` |
| 数据量 | 10款重疾险（6001类） | 1万+款全险种 |
| Collation | 混合（general_ci + unicode_ci）| 统一 utf8mb4_unicode_ci |

### 10.2 产品分类体系（aix_category_id）

```
寿险：1001(终身普通) 1002(增额寿) 2001(两全) 3001(定期普通) 3002(定期消费)
年金：4001(储蓄年金) 4002(养老年金) 5001(储蓄投资复合)
重疾：6001(长期) 6002(返还) 6003(消费) 6004(特定疾病) 6005(防癌给付)
医疗：7001(百万医疗) 7002(中端) 7003(高端) 7004(防癌) 7005(惠民保) 7006(特药) 7007(门诊)
设计类型：DT001(传统) DT002(分红) DT003(万能) DT004(投连)
```

**当前测试版只有 6001（重疾长期型）可推荐。** 其他类型用户问到时，AI 告知"当前版本暂未收录该险种"并调用 `report_issue`。

### 10.3 精算公允定价数据准备

**死亡率表数据来源：** `保险产品定价20200923.xlsm` Qtable sheet
包含：`CL1_1013_M`（男，2013年经验表）、`CL2_1013_F`（女，2013年经验表）等多版本

**重疾发病率表：** 同文件 `CI_MaleChoosen` / `CI_FemaleChoosen` sheet，含25种重疾合计发病率

**导入脚本：**
```bash
# 从 Excel 导出 CSV 后执行（初始化精算数据）
python3 scripts/import_actuarial_tables.py \
  --file 保险产品定价20200923.xlsm \
  --db mysql://aix_engine
```

**产品精算配置录入顺序：**
1. 死亡率/重疾表先导入（一次性）
2. 对每款产品在管理后台填写：使用哪张表、预定利率、附加费用率、含哪些责任
3. 第一批：现有10款重疾险全部配置（使用 CL1_1013_M + 3.5% + 25% 做默认值）

### 10.4 费率查询固定参数

重疾险费率表查询时固定以下参数（34维度简化为用户相关的2个）：

```python
RATE_DEFAULTS = {
    "pay_time": 20, "pay_time_type": 10,      # 20年缴
    "insure_period": 999, "period_type": 14,  # 终身
    "pay_type": 12,                            # 年交
    "smoke": 10,                               # 不吸烟
    "social_security": 0,                      # 不限
}
# 变量：age（用户年龄）、gender（11=男, 10=女）
# 保额：500000（50万），年保费 = rate × 500000
```

### 10.5 险种扩展路线图

| 阶段 | 险种 | 数据 |
|------|------|------|
| 测试版 | 重疾险(6001) × 10款 | cmb_* 表 |
| Alpha | 重疾险全量 + 百万医疗(7001) | 爱选标准格式批量导入 |
| Beta | + 寿险(1001-3002) + 年金(4001) | 同上 |
| 正式版 | 全险种(1001-7007) | 日更管道（0x1c 格式文件） |

---

## 第十一章 部署与运维

### 11.1 首次部署

```bash
# 1. 克隆代码，配置环境变量
cp .env.example .env
# 编辑 .env，填入 KIMI_API_KEY / ALIYUN_* / 数据库密码

# 2. 启动所有服务
cd ~/code/aix-engine
docker compose up -d

# 3. 导入重疾险产品数据（my_ensure 库）
docker compose exec -T mysql mysql -u root -proot_secret < 重疾险产品数据.sql
docker compose exec mysql mysql -u root -proot_secret -e \
  "GRANT ALL PRIVILEGES ON \`my_ensure\`.* TO 'aix'@'%'; FLUSH PRIVILEGES;"

# 4. 执行迁移
docker compose exec -T mysql mysql -u root -proot_secret aix_engine < db/migration/05-needs-analysis.sql

# 5. 重启 AI 服务（清除产品缓存）
docker compose restart ai
```

### 11.2 修改代码后重新构建

```bash
# 修改 Python AI 服务后
docker compose build ai && docker compose up -d ai

# 修改前端或 BFF 后
docker compose build nginx && docker compose up -d nginx
docker compose build bff && docker compose up -d bff

# 查看日志
docker logs aix-engine-ai-1 -f
docker logs aix-engine-bff-1 -f
```

### 11.3 访问地址

| 服务 | 地址 |
|------|------|
| 前端主界面 | http://localhost |
| AIX 保险顾问 | http://localhost/chat |
| 管理后台 | http://localhost/admin |

---

## 第十二章 测试验收清单

### Sprint 1 验收

- [ ] `docker logs aix-engine-ai-1` 无 `Collation` 报错
- [ ] 对话"推荐一款重疾险"→ AI 给出真实产品名（非幻觉）
- [ ] 多轮对话含 Function Call 不报 400 错误
- [ ] 刷新浏览器，对话历史保留
- [ ] `curl localhost:3001/api/v1/asr/token` 返回有效 token
- [ ] 图片选择后显示缩略图，base64 非空
- [ ] `DESCRIBE insurance_need_reports` 表存在

### Sprint 2 验收

- [ ] 对话"我想给孩子买保险"→ AI 进入收集模式，逐步问信息
- [ ] 完成4项信息 → AI 调用 `generate_needs_report`
- [ ] `SELECT * FROM insurance_need_reports` 有数据
- [ ] 语音录音 → Aliyun NLS 识别结果出现在输入框
- [ ] 产品推荐卡片 Mock 数据渲染正确（桌面3列、手机swipe）
- [ ] `GET /api/v1/actuarial/fair-price?productId=xxx&age=35&gender=male` 返回合理保费数值
- [ ] `product_scorer.py` 返回的 Top3 含 `value_score` 和 `value_ratio` 字段
- [ ] `DESCRIBE actuarial_qx_table` 成功；`SELECT COUNT(*) FROM actuarial_qx_table WHERE table_name='CL1_1013_M'` > 100 条

### Sprint 3 验收

- [ ] 完整链路：说话输入需求 → 收集信息 → 生成报告卡 → 显示 Top3 卡片
- [ ] 上传保险单图片 → AI 识别文档类型并提取信息
- [ ] 手机浏览器：长按录音 → 识别结果发送
- [ ] 手机浏览器：产品卡片可横向滑动
- [ ] 需求报告卡手机端折叠/展开正常

---

## 第十三章 文件变更清单

### Sprint 1（修复 + 地基）

| 操作 | 文件 | 说明 |
|------|------|------|
| 修改 | `aix-ai-service/app/services/product_search.py` | COLLATE 修复 + 缓存重试策略 |
| 修改 | `aix-ai-service/app/services/kimi_client.py` | reasoning_content 收集 + tool_handler 回调 |
| 新建 | `aix-bff/src/routes/asr.ts` | Aliyun NLS Token 接口 |
| 修改 | `aix-bff/src/routes/index.ts` | 注册 asr 路由 |
| 修改 | `aix-bff/src/index.ts` | body-parser limit 改为 10mb |
| 修改 | `frontend/src/store/useStore.ts` | ChatMessage 扩展 |
| 新建 | `frontend/src/modules/chat/components/ImageInput.tsx` | 图片输入组件 |
| 新建 | `db/migration/05-needs-analysis.sql` | 需求报告表 |

### Sprint 2（引擎层）

| 操作 | 文件 | 说明 |
|------|------|------|
| 重写 | `aix-ai-service/app/services/chat_engine.py` | 6工具 + 完整系统提示词 |
| 新建 | `aix-ai-service/app/services/needs_analysis.py` | 需求分析存取服务 |
| 新建 | `aix-ai-service/app/services/product_scorer.py` | 7维度评分（含精算性价比） |
| 修改 | `aix-ai-service/app/services/product_search.py` | 新增 fetch_products_for_scoring |
| 修改 | `aix-ai-service/app/rules/product_rules.md` | 加险种分类说明 |
| 新建 | `aix-actuarial-service/.../PricingController.java` | 精算定价 REST API |
| 新建 | `aix-actuarial-service/.../ActuarialPricingEngine.java` | PVFB/GP 精算计算引擎 |
| 新建 | `aix-actuarial-service/.../ProductConfigService.java` | 读取产品精算配置 |
| 新建 | `db/migration/06-actuarial-tables.sql` | 精算配置表 + 死亡率/重疾发病率表 |
| 新建 | `scripts/import_actuarial_tables.py` | 从 Excel 导入精算数据到 DB |
| 新建 | `frontend/src/modules/chat/components/VoiceInput.tsx` | 语音输入组件 |
| 新建 | `frontend/src/modules/chat/components/NeedsReportCard.tsx` | 需求报告卡片 |
| 新建 | `frontend/src/modules/chat/components/ProductRecommendCard.tsx` | 产品推荐卡片（含性价比评分展示） |

### Sprint 3（集成层）

| 操作 | 文件 | 说明 |
|------|------|------|
| 重写 | `aix-ai-service/app/routers/chat.py` | 完整编排：6工具+图片+所有SSE事件 |
| 新建 | `frontend/src/modules/chat/components/ChatInputBar.tsx` | 组合输入栏 |
| 重写 | `frontend/src/modules/chat/ChatPage.tsx` | 集成所有模块 |

### Sprint 4（打磨）

| 操作 | 文件 | 说明 |
|------|------|------|
| 修改 | `frontend/src/modules/chat/` | 图片压缩、手机端优化、错误降级 |
| 修改 | `frontend/src/admin/AdminPanel.tsx` | 新增需求报告统计 Tab |
| 修改 | `aix-bff/src/routes/admin.ts` | 新增报告统计接口 |

---

*文档结束。本文档覆盖所有开发信息，可直接用于指导开发实施。*
