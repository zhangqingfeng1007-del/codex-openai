# AIX 重疾险产品开发定价工具 — 开发文档 v1.2

> **文档版本：** v1.2（2026-03-21 结构收口）
> **编写日期：** 2026-03-21
> **上次更新：** 2026-03-21（P0 Bug 修复 + 自动重算补全 + 验收测试 + 假设版本标识 + 边界说明文档）
> **工具状态：** 主链路功能已收口，具备可复核的验收方式；多次赔付/现金价值等规划中
> **文件路径：** `aix-engine/docs/insurance-product-tool.html`

---

## 一、工具概述

### 1.1 定位与用途

本工具是一款**重疾险单次赔付产品的精算定价工具（增强版原型）**，面向保险精算师和产品开发人员，用于：

- **新产品定价参考**：组合病种保障，查看公允保费数量级
- **定价假设验证**：验证利率、费用率、退保率等假设对保费的敏感性
- **费率表生成**：多缴费方式 × 男/女 × 年龄，导出为 CSV

> ⚠️ **当前阶段说明**：当前版本已超出 PoC 阶段，但尚未达到正式精算生产工具标准。不支持多次赔付（Markov 模型）、现金价值、按年龄段分段退保率等正式产品开发所需能力。详见 `当前版本边界说明.md`。

### 1.2 技术架构

| 特性 | 说明 |
|------|------|
| 部署方式 | **纯前端单页工具**，无需服务器，直接浏览器打开 |
| 文件组成 | `insurance-product-tool.html`（主工具）+ `actuarial-data.js`（精算数据，195KB）|
| 依赖项 | 无外部依赖，全部用原生 HTML/CSS/JavaScript 实现 |
| 浏览器兼容 | Chrome / Safari / Firefox 现代版本 |
| 数据来源 | 中国标准生命表 CL1/CL2_1013、行业重疾发生率 2017 经验数据 |

### 1.3 与后端精算服务的区别

| 对比维度 | `PricingController.java`（后端服务） | 本工具（前端独立） |
|---------|--------------------------------------|-------------------|
| 部署 | Java Spring Boot，需 MySQL DB 配置 | 双文件，浏览器直接打开 |
| 病种 | 固定（读取 DB 中精算配置） | 完全可定制（每病种独立选择） |
| 保额 | 单一 sumAssured | 重疾/身故/轻中症独立配置 |
| 缴费方式 | 单一 premPayPeriod | 多缴费方式并行配置 |
| 用途 | AI 评分用公允定价（已上市产品） | 新产品开发 / 定价验证 |
| 数据来源 | MySQL `actuarial_qx_table` | 内嵌 JS 数组（直接从 Excel 提取）|
| 输出 | 单一公允保费值 | 完整精算过程 + 逐年明细 + 多方案费率表 |

---

## 二、数据来源与处理

### 2.1 原始数据文件

**源文件：** `/Desktop/保险产品定价20200923.xlsm`（44个工作表，专业精算定价模型）

数据提取使用 Python 脚本（`openpyxl`，`data_only=True`），读取 Excel 已缓存的公式计算结果。

### 2.2 精算数据结构（`actuarial-data.js`）

文件包含以下 JavaScript 常量，每个数组有 106 个值（对应年龄 0～105 岁）：

```
actuarial-data.js
├── MORTALITY               死亡率（CL1_1013_M / CL2_1013_F）
├── CI_AGG                  重疾合计发生率（CI_2017_M/F，标准25种聚合）
├── MINORCI_AGG             轻症合计发生率（MinorCI_2017_M/F，默认选中项合计）
├── MODERATECI_AGG          中症合计发生率（ModerateCI_2017_M/F）
├── SPECIALCI_AGG           特定疾病合计发生率（SpecialCI_2017_M/F）
├── CI_RATES                重疾逐病种发生率（20列 × 男/女 × 106年龄）
├── MINORCI_RATES           轻症逐病种发生率（19列 × 男/女 × 106年龄）
└── MODERATECI_RATES        中症逐病种发生率（21列 × 男/女 × 106年龄）
```

### 2.3 数据映射关系（Excel Sheet → JS）

#### 死亡率

| JS 常量 | Excel 来源 | Sheet.列 |
|---------|-----------|----------|
| `MORTALITY.male` | CL1_1013_M | Qtable 列12 |
| `MORTALITY.female` | CL2_1013_F | Qtable 列13 |

#### 重疾（CI）发生率

| JS 常量 | Excel 来源 | 备注 |
|---------|-----------|------|
| `CI_AGG.male` | CI_2017_M | Qtable 列22，预计算聚合率 |
| `CI_AGG.female` | CI_2017_F | Qtable 列23 |
| `CI_RATES.male['25种重疾']` | CI_Male 列 H | VLOOKUP→CITable，`isAggregate:true`，聚合模式专用 |
| `CI_RATES.male['恶性肿瘤']` | CI_Male 列 I | 个别病种，自定义模式使用 |
| `CI_RATES.male['系统性红斑狼疮']` | CI_Male 列 J | |
| `CI_RATES.male['肌肉萎缩症']` | CI_Male 列 K | |
| `CI_RATES.male['终末期肺病']` | CI_Male 列 L | |
| `CI_RATES.male['多发性硬化']` | CI_Male 列 M | |
| `CI_RATES.male['心肌病']` | CI_Male 列 N | |
| `CI_RATES.male['细菌性脑膜炎']` | CI_Male 列 O | |
| `CI_RATES.male['肌萎缩侧索硬化']` | CI_Male 列 P | |
| `CI_RATES.male['植物人']` | CI_Male 列 Q | |
| `CI_RATES.male['血液传染HIV']` | CI_Male 列 R | |
| `CI_RATES.male['职业传染HIV']` | CI_Male 列 S | |
| `CI_RATES.male['肾髓质囊性病']` | CI_Male 列 T | |
| `CI_RATES.male['小儿麻痹症']` | CI_Male 列 U | |
| `CI_RATES.male['硬皮病']` | CI_Male 列 V | |
| `CI_RATES.male['慢性复发性胰腺炎']` | CI_Male 列 W | |
| `CI_RATES.male['严重类风湿性关节炎']` | CI_Male 列 X | |
| `CI_RATES.male['终末期疾病']` | CI_Male 列 Y | |
| `CI_RATES.male['其他CI']` | CI_Male 列 Z | |

（`CI_RATES.female` 对应 `CI_Female` sheet，结构完全相同）

#### 轻症（MinorCI）发生率

| JS 键名 | Excel 来源（MinorCI_Male） | 列索引 |
|---------|--------------------------|--------|
| `极早期恶性肿瘤` | MinorCI_Male | 列 H（索引7） |
| `9种主要轻症` | MinorCI_Male | 列 I（索引8），聚合率 |
| `30种非主要轻症` | MinorCI_Male | 列 J（索引9），聚合率 |
| `重大器官移植` | MinorCI_Male | 列 M（索引12） |
| `终末期肾病` | MinorCI_Male | 列 N（索引13） |
| `胃癌` ～ `脑癌` | MinorCI_Male | 列 O～Y（索引14～24） |
| `白血病` | MinorCI_Male | 列 Z（索引25） |
| `心梗mci` | MinorCI_Male | 列 AA（索引26） |
| `脑梗mci` | MinorCI_Male | 列 AB（索引27） |

#### 中症（ModerateCI）发生率

| JS 键名 | Excel 来源（ModerateCI_Male） | 列索引 |
|---------|------------------------------|--------|
| `中度帕金森氏病` | ModerateCI_Male | 列 H（索引7） |
| `中度瘫痪` | ModerateCI_Male | 列 I（索引8） |
| `中度脊髓灰质炎` | ModerateCI_Male | 列 J |
| `重症头部外伤` | ModerateCI_Male | 列 K |
| `中度脑炎脑膜炎后遗症` | ModerateCI_Male | 列 L |
| `早期运动神经性疾病` | ModerateCI_Male | 列 M |
| `中度类风湿性关节炎` | ModerateCI_Male | 列 N |
| `小面积III度烧伤` | ModerateCI_Male | 列 O（10%面积） |
| `中度脑中风后遗症` | ModerateCI_Male | 列 P |
| `系统性红斑狼疮MCI` | ModerateCI_Male | 列 Q |
| `慢性肾功能损害` | ModerateCI_Male | 列 R |
| `慢性肝功能衰竭` | ModerateCI_Male | 列 S |
| `视力严重受损` | ModerateCI_Male | 列 T（3岁始） |
| `一肢缺失` | ModerateCI_Male | 列 U |
| `人工耳蜗植入术` | ModerateCI_Male | 列 V |
| `单耳失聪` | ModerateCI_Male | 列 W |
| `角膜移植` | ModerateCI_Male | 列 X |
| `早期原发性心肌病` | ModerateCI_Male | 列 Y |
| `糖尿病单足截除` | ModerateCI_Male | 列 Z |
| `其余5种2ADL` | ModerateCI_Male | 列 AA |
| `其他8种MCI` | ModerateCI_Male | 列 AB |

> **注意：特定疾病（SpecialCI）复用 `MINORCI_RATES` 数据，不另建数组。**

---

## 三、精算数学模型

### 3.1 多脱退模型（Multi-Decrement）

本工具采用标准行业多脱退模型，模拟被保险人在保障期内的状态转移：

```
状态转移规则：
  死亡（qd_t）         → 终止合同，赔付身故保险金（deathSumAssured × deathBenefitPct）
  重疾（qCI_raw_t）    → 终止合同，赔付重疾保险金（ciSumAssured × qCI_t）
  轻症（qmCI_t）       → 合同继续，赔付轻症保险金（minorSABase × qmCI_t）
  中症（qMCI_t）       → 合同继续，赔付中症保险金（minorSABase × qMCI_t）
  特定疾病（qSCI_t）   → 合同继续，赔付特定疾病保险金（minorSABase × qSCI_t）
```

**生存概率递减（仅死亡 + 重疾原始发生率参与脱退，与 Benefit% 无关）：**

```
px_0 = 1.0
px_{t+1} = px_t × max(0, 1 − qd_t − qCI_raw_t)
```

其中 `qCI_raw_t` 规则：
- 聚合模式：`CI_AGG[gender][issueAge + t]`
- 自定义模式：Σ 选中病种的原始发生率（`isAggregate=true` 的聚合项**不参与**，且每个病种还须检查 `ToAge`）

### 3.2 核心精算公式

```
GP（年缴毛保费）= PVFB / (AnnuityDue - PV_Loading)
```

**未来保险金精算现值（PVFB，v1.1 起支持责任级独立保额）：**

```
PVFB = Σ[t=1..T]  px_t × BenefitAmount_t × v^t

BenefitAmount_t =
    deathSumAssured × qd_t    × deathBenefitPct/100     （身故，终止脱退）
  + ciSumAssured   × qCI_t                              （重疾，终止脱退）
  + minorSABase    × (qmCI_t + qMCI_t + qSCI_t)         （轻/中/特疾，合同继续）
```

**缴费期年金精算现值（期初年金）：**

```
AnnuityDue = Σ[t=0..PPP-1]  px_t × v^t
```

其中 PPP = 缴费年期（趸交时 PPP = 1）

**附加费用精算现值：**

```
PV_Loading = loading_rate × AnnuityDue
```

**折现因子：**

```
v = 1 / (1 + pricing_rate)
T = 保障终止年龄 − 投保年龄
```

### 3.3 病种加权发生率计算（benefit-weighted）

用于 PVFB 中赔付贡献的发生率：每个病种乘 `Benefit%`，并受 `ToAge` 约束。

```javascript
// PVFB 用（benefit-weighted）：
qCI_t = Σ_i ( chosen_i && age < toAge_i ? rawRate_i[age] × benefitPct_i/100 : 0 )

// 生存概率用（raw，不乘 Benefit%，但同样受 ToAge 和 isAggregate 过滤）：
qCI_raw_t = Σ_i ( chosen_i && !isAggregate_i && age < toAge_i ? rawRate_i[age] : 0 )
```

### 3.4 聚合模式与自定义模式的口径规则

| | 聚合模式（📦） | 自定义模式（🔧） |
|--|------------|--------------|
| PVFB 中 qCI_t | `CI_AGG[gender][age] × ciBenefitPct/100` | Σ 选中个别病种（`isAggregate=false`）× 各自 Benefit% |
| 生存概率中 qCI_raw_t | `CI_AGG[gender][age]` | Σ 选中个别病种原始率（`isAggregate=false`，且 age < toAge） |
| 聚合项（`25种重疾`） | 参与计算 | **完全不参与**（`isAggregate=true`，自动过滤）|

> **关键约束（v1.0 修复）：** 自定义模式下，`CI_DISEASES` 数组中的 `{id:'25种重疾', isAggregate:true}` 项在 `computeCI()` 和 `rawCIRate` 两处均被过滤，确保不存在"聚合 + 逐病种"重复计入。

### 3.5 精算参数验证结果

**基准场景：35岁男性，终身保障（至105岁），20年缴，重疾/身故各50万保额，3.5% 预定利率，25% 附加费用率**

| 保障组合 | 年缴保费（元） |
|---------|-------------|
| 仅身故 | 11,535 |
| 仅重疾（25种聚合） | 9,538 |
| 身故 + 重疾 | 16,067 |
| 身故 + 重疾 + 轻症(30%) + 中症(60%) | 19,392 |
| 同上（35岁女性） | 16,605 |
| 男/女比（身故+重疾） | 1.168 |

---

## 四、功能详细说明

### 4.1 左侧：产品配置面板

#### 区块1：基本参数

| 字段 | 范围 | 默认值 | 说明 |
|------|------|-------|------|
| **产品名称** | 任意文本 | （空） | 用于导出文件命名，不影响计算 |
| 计算基准年龄 | 0～70岁 | 35岁 | 单点计算使用的年龄 |
| 性别 | 男/女 | 男 | 切换时自动重建病种列表（禁用不适用病种） |
| 保险期间 | 终身（至105岁）/ 定期 N 年 | 终身 | 终身时 T = 105 − issueAge |
| 重疾保额 | 任意正整数 | 500,000元 | 重疾赔付和生存概率基准 |
| 身故保额 | 任意正整数 | 500,000元 | 身故赔付金额 |
| 轻/中/特疾保额模式 | % × 重疾保额 / 固定金额 | % × 重疾保额 | 两种模式：百分比以重疾保额为基数，或填入固定金额 |
| 缴费方式 | 趸交/3/5/10/20/30年交（多选） | 20年交 | 每种方式独立计算保费 |

**承保规则（每种缴费方式独立配置）：**

| 字段 | 说明 |
|------|------|
| 男性投保年龄范围 | 超出范围的年龄组合不出费率 |
| 女性投保年龄范围 | 同上 |

#### 区块2：精算假设

| 字段 | 范围 | 默认值 | 说明 |
|------|------|-------|------|
| 预定利率 | 0.1%～20% | 3.50% | 监管规定传统险上限 3.5% |
| 附加费用率 | 0%～60% | 25% | 期缴产品监管上限约 25% |
| 死亡率表 | 固定（当前版本） | CL1/CL2_1013 | 中国精算师协会 2013 生命表 |
| **退保率（年）** | 0%～20% | 0% | 常数年退保率，实务中 2%～5%；退保后精算等效于 px 额外递减；0=不计退保 |
| **重疾赔付次数** | 1～6次 | 1次 | >1次为多次赔付，当前模型以单次为下限（Markov 模型预留）；计算结果自动显示警告 |

#### 区块3：保障责任配置（5个 Tab）

**Tab 1：重疾（CI）**

- **启用开关**：整体启用/禁用重疾保障
- **赔付比例**：默认 100%（相对重疾保额）
- **两种模式**：
  - `📦 25种重疾（标准聚合率）`：直接使用 `CI_AGG`，与监管备案数据一致
  - `🔧 自定义病种`：展示 17 个个别病种，**全部默认选中**（`chosen:true`），每个独立设置 `Benefit%`（默认 100%）和 `ToAge`（默认 105岁）；聚合项（`25种重疾`）**在切换到自定义模式时自动隐藏**（`setCIMode` + `onGenderChange` 均保持一致），不参与计算

**Tab 2：轻症（MinorCI）**

- 19种选项；默认选中：极早期恶性肿瘤、9种主要轻症聚合、30种非主要轻症聚合
- **默认赔付比例（注意不统一）：**
  - 极早期恶性肿瘤：30%，ToAge=75
  - 9种主要轻症（聚合）：30%，ToAge=75
  - 30种非主要轻症（聚合）：**25%**，ToAge=70  ← 非 30%
  - 其他癌症病种（胃/肝/肺等）：30%，ToAge=70
  - 心肌梗塞/脑梗塞（轻症级别）：**25%**，ToAge=70  ← 非 30%
- 批量修改按钮会将所有病种同步到输入值，再重建列表
- 每病种可独立配置 `Benefit%` 和 `ToAge`
- 性别专属病种（乳腺癌、宫颈癌、卵巢癌 = 女性专属；前列腺癌 = 男性专属）在对应性别下自动禁选

**Tab 3：中症（ModerateCI）**

- 21种中症病种，默认全部选中，默认赔付比例：60%，默认 ToAge=75（全部）
- 批量修改按钮可一键同步所有病种赔付比例

**Tab 4：特定疾病（SpecialCI）**

- 复用轻症发生率数据（`MINORCI_RATES`），共 14 种选项；默认仅选中"30种非主要轻症"
- 默认赔付比例：20%，默认 ToAge=60（全部）
- 同样支持性别专属病种（乳腺癌/宫颈癌 = 女性专属；前列腺癌 = 男性专属）
- 与轻症险同时使用时，注意两者病种不应重叠

**Tab 5：其他责任**

- 身故保障（默认启用，100% 身故保额）
- **保费豁免（WOP）**：在单次赔付模型中，重疾后合同终止，被保人自然不再缴费——即 WOP 效果已隐含于当前定价模型（px 递减导致 AnnuityDue 自然缩减）。若需为"重疾后合同继续+WOP"（多次赔付产品）定价，需单独建模 WOP 成本（约增加保费 1%～3%）。
- **多次重疾赔付**：需马尔可夫多状态模型（健康→第1次CI→第2次CI→死亡），保费通常比单次高 15%～35%。当前以单次下限计算，精算分解中自动显示红色警告。

### 4.2 右侧：计算结果面板

**结果卡1：核心保费（多缴费方式并列显示）**

每个选中的缴费方式独立显示一个保费方块：
- 年缴保费（趸交显示一次性保费）
- 超出承保年龄规则的组合显示"超承保范围"

**结果卡2：精算分解**（基于第一个**在承保范围内**的缴费方式）

- PVFB（未来保险金精算现值）
- AnnuityDue（缴费期年金现值）
- PV_Loading（附加费用现值）
- 分母 = AnnuityDue − PV_Loading
- 完整公式展示
- 若所有缴费方式均超出承保范围，该区块显示红色提示，不展示错误数据

**结果卡3：敏感性分析**（按需触发，点击"📊 敏感性分析"按钮）

- 表格1：GP（年保费）vs 预定利率（行）× 附加费用率（列），当前基准格以黄色标注，低于基准的格以蓝色标注，并显示相对偏差百分比
- 表格2：GP vs 退保率（固定利率/费用率），量化退保假设对保费的影响
- 帮助精算师快速评估假设敏感性，验证定价稳健性

**结果卡4：逐年精算明细**

| 列名 | 含义 |
|------|------|
| t | 保单年度（1, 2, 3...） |
| 年龄 | 被保险人年龄 |
| px_t | 当年初生存概率 |
| qd_t(‰) | 当年死亡率（千分之） |
| qCI_t(‰) | 当年加权重疾发生率（千分之） |
| qmCI_t(‱) | 当年加权轻症发生率（万分之） |
| qMCI_t(‱) | 当年加权中症发生率（万分之） |
| PVFB贡献 | 当年对 PVFB 的贡献值（元）；含死亡/重疾/轻中症/特定疾病四类责任合计 |
| 年金项 | 当年对 AnnuityDue 的贡献 |

> ⚠️ **精算核对注意**：逐年明细中 **特定疾病（qSCI_t）未单独输出**，其贡献合并在"PVFB贡献"列中。若需独立核对特定疾病责任成本，需在 `calculateCore()` 的 `detail2.push` 中手动添加 `qSCI` 字段输出。
> 显示策略：前30年 + 最后5年，中间省略标注。

**费率表（按需生成，v1.1 升级）**

- 列结构：`缴费方式-性别` 为每列，支持多个缴费方式并列
- 超出承保规则的年龄组合显示"—"
- 示例表头：`投保年龄 | 20年交-男(元) | 20年交-女(元) | 趸交-男(元) | 趸交-女(元) | ...`
- 支持导出 CSV（7列：缴费方式/性别/投保年龄/保障期间/重疾保额/身故保额/年保费；不含假设版本、轻中症保额等）

**CSV 导出格式（v1.1 升级）**

```
缴费方式,性别,投保年龄,保障期间,重疾保额(元),身故保额(元),年保费(元)
20年交,男,35,终身,500000,500000,16067.00
20年交,女,35,终身,500000,500000,13768.00
...
```

---

## 五、核心函数说明

### 5.1 函数列表

```
insurance-product-tool.html
│
├── 数据与配置
│   ├── CI_DISEASES[...]          重疾病种配置（含 isAggregate 标志；17个个别病种全部默认 chosen:true）
│   ├── MINORCI_DISEASES[...]     轻症病种配置（含 genderNote；19种；各病种独立 benefitPct/toAge 默认值）
│   ├── MODERATECI_DISEASES[...]  中症病种配置（21种；默认 benefitPct=60, toAge=75）
│   ├── SPECIALCI_DISEASES[...]   特定疾病配置（14种，含 genderNote；默认 benefitPct=20, toAge=60）
│   └── UW_RULES{}                承保规则（缴费方式 → 男/女年龄范围）
│
├── 辅助工具
│   ├── getGender()               读取当前性别选择器值（'male'|'female'）
│   └── getRate(ratesObj, id, gender, age)  从发生率对象中取指定年龄的发生率值
│
├── 计算引擎
│   ├── computeAggregate(diseases, ratesObj, gender, issueAge, T)
│   │     通用病种加权合计（轻/中/特疾共用，含 ToAge 过滤）
│   ├── computeCI(ciMode, ciDiseases, ciBenefitPct, gender, issueAge, T)
│   │     重疾专用（聚合模式用 CI_AGG；自定义模式过滤 isAggregate）
│   └── calculateCore(issueAge, gender, T, premPayPeriod,
│                      ciSumAssured, deathSumAssured, minorSABase,
│                      pricingRate, loadingRate, ...)
│         核心精算引擎（PVFB / AnnuityDue / PV_Loading / GP）
│
├── UI 入口
│   ├── calculate()               单点计算，展示多缴费方式结果
│   ├── generateRateTable()       批量费率表（缴费方式 × 性别 × 年龄）
│   ├── calcForAgeGenderPay()     费率表单格计算（含承保规则判断）
│   └── exportCSV()               导出完整维度 CSV
│
└── UI 交互
    ├── buildDiseaseList(containerId, diseases)
    │     渲染病种列表（仅 addEventListener，无内联 onchange；
    │                    性别专属病种自动 disabled + d.chosen=false）
    ├── onGenderChange()           切换性别时重建所有4类病种列表，并重新调用 setCIMode 保持聚合行可见性一致
    ├── onBenefitTypeChange()      切换保险期间（终身/定期），控制 benefitYears/termUnit 显示
    ├── onParamChange()            ⚠️ 当前为空函数（auto-recalc 已删除，防止 checkbox 点击时卡顿）
    ├── onPayOptChange()           切换缴费方式时重建承保规则 UI
    ├── buildUWRulesUI()           渲染承保规则输入区
    ├── setUWRule(payYears,field,val)  更新 UW_RULES 中指定缴费方式的某个边界值
    ├── isUWEligible(age,gender,payYears)  承保规则判断（UW_RULES 为空时默认 true）
    ├── onMinorSAModeChange()      切换轻/中/特疾保额模式（fixed/pct_ci），更新提示文字
    ├── onMinorCIDefaultChange()   批量设置所有轻症病种默认赔付%，并重建轻症列表
    ├── onModerateCIDefaultChange() 同上（中症）
    ├── onSpecialCIDefaultChange()  同上（特定疾病）
    └── setCIMode(mode)            切换聚合/自定义模式，同步聚合行的 display 属性
```

### 5.2 calculateCore 参数说明

```javascript
calculateCore(
  issueAge,       // 投保年龄
  gender,         // 'male' | 'female'
  T,              // 保障期限（年）
  premPayPeriod,  // 缴费年期（趸交传 1）
  ciSumAssured,   // 重疾保额（元）
  deathSumAssured,// 身故保额（元）
  minorSABase,    // 轻/中/特疾赔付基准保额（由 minorSAMode 决定）
  pricingRate,    // 预定利率（小数，如 0.035）
  loadingRate,    // 附加费用率（小数，如 0.25）
  lapseRate,      // ★v1.2 年退保率（小数，如 0.03；0=不计退保）
  enableCI,       // 是否含重疾
  ciMode,         // 'aggregate' | 'custom'
  ciBenefitPct,   // 重疾赔付比例（聚合模式用，0～200）
  ciDiseases,     // CI_DISEASES 数组引用
  enableMinorCI,  // 是否含轻症
  minorCIDiseases,
  enableModerateCI,
  moderateCIDiseases,
  enableSpecialCI,
  specialCIDiseases,
  enableDeath,    // 是否含身故
  deathBenefitPct // 身故赔付比例（0～300）
)
// 返回：{ gp, pvfb, annuityDue, pvLoading, denom, detail }
// 注：lapseRate 在 px 递减时叠加：px *= max(0, 1 - qd - rawCI - lapseRate)
```

---

## 六、文件结构

```
aix-engine/docs/
├── insurance-product-tool.html    ← 主工具
└── actuarial-data.js              ← 精算数据（195 KB）
    ├── const MORTALITY {...}      死亡率（男/女，106个值）
    ├── const CI_AGG {...}         重疾合计发生率（预计算）
    ├── const MINORCI_AGG {...}    轻症合计发生率（预计算）
    ├── const MODERATECI_AGG {...} 中症合计发生率（预计算）
    ├── const SPECIALCI_AGG {...}  特定疾病合计发生率（预计算）
    ├── const CI_RATES {...}       重疾逐病种发生率（男/女）
    ├── const MINORCI_RATES {...}  轻症逐病种发生率（男/女）
    └── const MODERATECI_RATES {...} 中症逐病种发生率（男/女）
```

---

## 七、数据提取脚本说明

精算数据由以下 Python 代码从 Excel 提取，可随时重新运行更新数据：

```python
import openpyxl

wb = openpyxl.load_workbook('保险产品定价20200923.xlsm', data_only=True, read_only=True)

def extract_rates(sheet_name, age_col, start_row_idx, disease_cols_with_idx):
    """
    sheet_name:          工作表名
    age_col:             年龄列的列索引（0-based）
    start_row_idx:       数据起始行索引（0-based，跳过表头）
    disease_cols_with_idx: [(键名, 列索引), ...]
    返回: {键名: [rate_age0...rate_age105]}
    """
    rows = list(wb[sheet_name].rows)
    result = {name: [0.0]*106 for name, _ in disease_cols_with_idx}
    for row in rows[start_row_idx:]:
        vals = [c.value for c in row]
        av = vals[age_col]
        if av is None or not isinstance(av, (int, float)): continue
        age = int(av)
        if 0 <= age <= 105:
            for name, cidx in disease_cols_with_idx:
                if cidx < len(vals) and vals[cidx] is not None:
                    result[name][age] = float(vals[cidx])
    return result
```

**各 Sheet 读取参数：**

| Sheet | age_col | start_row_idx | 备注 |
|-------|---------|---------------|------|
| Qtable | 2 | 4 | 死亡率 + 所有合计发生率 |
| CI_Male | 1 | 11 | 重疾逐病种（含25种聚合列） |
| CI_Female | 1 | 11 | 同上（女性） |
| MinorCI_Male | 1 | 11 | 轻症逐病种 |
| MinorCI_Female | 1 | 11 | 同上（女性） |
| ModerateCI_Male | 1 | 11 | 中症逐病种 |
| ModerateCI_Female | 1 | 11 | 同上（女性） |

---

## 八、使用方法

### 8.1 快速开始

1. 用浏览器打开 `insurance-product-tool.html`（需与 `actuarial-data.js` 在同一目录）
2. 配置左侧基本参数（年龄、性别、保险期间、重疾/身故保额）
3. 勾选所需缴费方式，配置承保年龄规则
4. 在"保障责任配置" Tab 中选择病种及赔付比例
5. 点击"🔢 计算公允保费"，右侧同时显示各缴费方式保费
6. 点击"📋 生成费率表"，生成多维度费率表
7. 点击"📥 导出费率表 CSV"导出

### 8.2 常见操作示例

**验证标准25种重疾产品定价（35岁男）：**
1. 年龄=35，男性，终身，重疾/身故各50万
2. 利率=3.5%，附加费用率=25%
3. CI Tab → "25种重疾（标准聚合率）"，100% 赔付
4. 身故保障=100%，勾选 20年交
5. 点击"计算" → 20年交显示约 16,067 元/年

**自定义病种（仅恶性肿瘤，50岁前保障）：**
1. CI Tab → 切换"自定义病种"
2. 仅勾选"恶性肿瘤"，ToAge=50
3. 聚合项"25种重疾"自动不参与计算（灰色标注）
4. 计算 → 恶性肿瘤仅在50岁前影响赔付和脱退

**多缴费方式对比：**
1. 勾选趸交 + 5年交 + 20年交
2. 配置各缴费方式承保年龄（如趸交 0-65岁，20年交 0-55岁）
3. 计算 → 结果区同时显示三种方式的保费
4. 生成费率表 → 六列（趸交男/女、5年交男/女、20年交男/女）

### 8.3 注意事项

- **两个文件必须在同一目录下**，浏览器才能加载精算数据
- 费率表生成耗时约 2～10 秒（取决于年龄范围 × 缴费方式数量 × PC 性能）
- 轻症、中症、特定疾病理赔后合同继续——不参与生存概率递减
- 自定义 CI 模式下，各病种发生率来自 CI_Male/Female 逐列，不等同于25种聚合率
- 切换性别后，对应不适用的性别专属病种自动变灰并强制取消勾选

---

## 九、版本变更记录

### v1.2（2026-03-21）

**新增精算参数：**

| 参数 | 实现方式 | 说明 |
|------|---------|------|
| 退保率（lapseRate） | 在 px 递减步骤叠加：`px *= (1 - qd - rawCI - lapseRate)` | 模拟提前退保对费率的影响；2%～5% 为行业常见值 |
| 重疾赔付次数（ciPayTimes） | UI 字段，计算时若 >1 则在精算分解中显示警告 | Markov 模型预留，当前以单次下限计算 |

**新增工具功能：**

| 功能 | 实现说明 |
|------|---------|
| 产品名称 | 顶部文本输入，用于导出文件命名 |
| 自动重算 | `onParamChange()` 改为带 500ms debounce 的真实实现；通过"自动重算"复选框开启/关闭 |
| 敏感性分析 | `sensitivityAnalysis()` 输出两个表：① GP vs 预定利率×附加费用率矩阵；② GP vs 退保率 |
| 保存配置 | `saveConfig()` 将全部参数（含病种选择、承保规则）导出为 JSON |
| 加载配置 | `loadConfigFile()` + `restoreConfig()` 从 JSON 文件恢复所有参数并自动重算 |
| 打印 | `window.print()` + `@media print` CSS（结果区无边框，操作按钮隐藏） |

**WOP/多次赔付说明（文档补充）：**

在当前单次赔付模型中，重疾后合同终止、WOP 效果已隐含（px 递减自然减少 AnnuityDue）。多次赔付需 Markov 模型，预计保费高于单次 15%～35%，已在"其他责任"Tab 中给出说明。

**新增/修改函数：**

| 函数 | 说明 |
|------|------|
| `saveConfig()` | 导出当前全部配置为 JSON 文件 |
| `loadConfigFile(input)` | 从文件选择控件读取 JSON 并调用 `restoreConfig` |
| `restoreConfig(cfg)` | 将 JSON 配置写回所有 DOM 输入，重建病种列表，触发 `calculate()` |
| `sensitivityAnalysis()` | 生成 GP 敏感性矩阵（利率×费用率）+ 退保率影响表 |

### v1.1（2026-03-21）

**P0 修复：**

| 问题 | 修复说明 |
|------|---------|
| CI 自定义模式重复计入 | `computeCI()` 和 `rawCIRate` 均加 `isAggregate` 过滤，聚合项在自定义模式下完全不参与 |
| ToAge 不影响脱退 | `rawCIRate` 自定义计算中同步加 `att >= toAge` 判断，赔付和脱退口径统一 |
| 内联 `onchange` 导致 ReferenceError | `buildDiseaseList()` 删除所有内联 `onchange`，统一改为 `addEventListener` |

**P1 新增功能：**

| 功能 | 说明 |
|------|------|
| 责任级独立保额 | 新增重疾保额、身故保额、轻/中/特疾保额模式三项配置；`calculateCore` 各责任分别乘对应保额 |
| 多缴费方式 | 缴费期改为多选（趸交/3/5/10/20/30年交），单点计算和费率表均支持并行输出 |
| 承保规则 | 每种缴费方式有独立的男/女投保年龄范围；超界组合不出费率 |
| 性别专属病种禁选 | 切换性别时重建病种列表，不适用病种 `disabled` + 强制取消勾选 |

**P2 升级：**

| 功能 | 说明 |
|------|------|
| 费率表结构升级 | 从"年龄+男+女+男女比"升级为"缴费方式×性别"多列，动态表头 |
| CSV 导出升级 | 包含缴费方式、性别、投保年龄、保障期间、重疾保额、身故保额、年保费 |

**代码审查修复（同日补丁）：**

| 问题 | 修复说明 |
|------|---------|
| `pct_base` 选项与 `pct_ci` 完全等价 | 删除无意义的"% × 基准保额"选项；`getParams()` 简化为 `fixed ? 固定值 : ciSumAssured`，消除死代码 |
| 精算分解使用第一个方案，不区分承保资格 | `calculate()` 改为取第一个 `isUWEligible` 为 true 的方案展示 breakdown；若全超承保范围则显示红色警告，提前 return，不展示无效数据 |
| 自定义 CI 模式下聚合行仍可见 | `buildDiseaseList()` 为聚合行写入 `data-aggregate="true"`；`setCIMode()` 切换时同步设置聚合行 `display`；`onGenderChange()` 重建列表后重新调用 `setCIMode()` 保持一致性 |

### v1.0（2026-03-21）

初版完成，基本精算计算引擎、病种选择、单一保额、单一缴费方式。

---

## 十、后续扩展规划

### 10.1 接入 AIX 智能体（AI 评分）

本工具的定价逻辑可直接增强 `PricingController.java`：

```
产品评分链路（规划）：
product_scorer.py
  → 调用 Java 精算服务（已支持多病种配置）
  → get_fair_premium(productId, age, gender)
  → value_ratio = 实际保费 / 公允保费
  → 性价比评分（0～20分）
```

### 10.2 功能增强（优先级排序）

| 状态 | 功能 | 说明 |
|------|------|------|
| ✅ 已完成 | 退保率假设 | `lapseRate` 参数，叠加到 px 递减 |
| ✅ 已完成 | 重疾赔付次数 UI | ciPayTimes 字段 + 警告说明 |
| ✅ 已完成 | 产品配置保存/加载 | JSON 导出/导入，含全部病种 |
| ✅ 已完成 | 敏感性分析 | GP vs 利率×费用率矩阵 + 退保率影响表 |
| ✅ 已完成 | 打印支持 | `@media print` CSS，按钮隐藏 |
| P0 | 更新率表数据 | 支持切换不同年份发生率表（当前固定 2017） |
| P1 | 多次重疾赔付（Markov） | Excel `MultipleCI_Markov` sheet 的完整实现 |
| P2 | 按年龄段退保率 | 当前简化为常数率，实务中按保单年度分段 |
| P2 | 佣金率/管理费分离 | 将附加费用率拆为一次性费用+每年费用 |
| P2 | 现金价值计算 | 责任准备金 + 现金价值表，支持储蓄型产品 |
| P3 | 年金/储蓄产品 | 当前仅支持消费型/保障型，年金需 Annuity_Table |

---

## 十一、已知限制与注意事项

| 限制 | 说明 |
|------|------|
| 险种范围 | 当前仅支持重疾险（含轻/中症），不支持医疗险、年金险 |
| 多次重疾赔付 | 当前为单次下限，实际多次赔付需 Markov 模型（高 15%～35%）；计算时自动显示警告 |
| 退保率 | 使用常数年退保率；实务中应按保单年度分段（第 1-3 年高、后期低），简化版本会低估早期退保影响 |
| 附加费用 | 当前使用单一 loadingRate，未区分一次性获客费用和逐年管理费，影响长期产品定价精度 |
| 再保 | 不含再保险费用，实际出单保费还需叠加再保附加费 |
| 准备金/现金价值 | 不计算责任准备金和现金价值，仅输出公允毛保费 |
| 营业税 | 不含增值税附加，实际销售价需在毛保费基础上调整 |
| SpecialCI 数据来源 | 与 MinorCI 共用 `MINORCI_RATES`，产品设计时需确认两类病种不重叠 |

---

**代码实现对齐补丁（同日）：**

| 差异项 | 修正说明 |
|--------|---------|
| MinorCI 默认 benefitPct 不统一 | 补充说明 30种非主要轻症=25%、心梗/脑梗=25%（非统一30%）；其余病种=30% |
| 各类责任默认 ToAge 未记录 | 补充：MinorCI=70/75、ModerateCI=75、SpecialCI=60 |
| CI 自定义模式默认选中状态 | 明确说明 17个个别病种**全部**默认 chosen:true |
| SpecialCI 缺少性别专属说明 | 补充乳腺癌/宫颈癌=女性专属、前列腺癌=男性专属 |
| SpecialCI 病种数量 | 补充共 14 种（MinorCI 为 19 种）|
| `onParamChange()` 行为 | 明确标注为**空函数**（auto-recalc 已删除，防卡顿）|
| §5.1 函数列表不完整 | 补充：`getGender()`、`getRate()`、`onBenefitTypeChange()`、`onMinorCIDefaultChange()`、`onModerateCIDefaultChange()`、`onSpecialCIDefaultChange()`、`setUWRule()` |

---

---

## 版本变更记录

### v1.2 补丁（2026-03-21，结构收口）

依据《AIX 产品定价工具下一阶段开发优先级清单 V1》执行。

**P0 Bug 修复：**

| 问题 | 修复方案 |
|------|---------|
| 敏感性分析"只选趸交"时 `payYears = -Infinity` 导致结果失真 | 抽出 `resolvePayPeriod(payYears, T)` helper，统一三处调用；敏感性分析正确识别趸交并显示 `趸交` 标签 |
| 自动重算未覆盖多数关键输入 | 补充 `oninput` 到 issueAge、ciSumAssured、deathSumAssured、minorSAValue、pricingRate、loadingRate；在 `onGenderChange()`（via `setCIMode`）、`onPayOptChange()`、`onMinorSAModeChange()` 末尾补调 `onParamChange()` |
| CSV 导出文件名硬编码为"重疾险费率表.csv" | 使用产品名称命名，空名时用默认值"重疾险"，去除文件名非法字符 |
| `saveConfig()` 二次读取 DOM | 统一基于 `getParams()` 构建配置快照，减少重复读 DOM |

**P1 新增：**

| 变更 | 说明 |
|------|------|
| `resolvePayPeriod()` helper | 统一趸交→PPP=1的映射逻辑，消除三处各自实现 |
| `getParams()` 补全 | 新增 `minorSAMode`、`assumptionVersion`、`mortalityTableId`、`ciTableId`、`minorCiTableId`、`moderateCiTableId` 字段 |
| `saveConfig()` 配置版本升至 1.2 | 包含全部假设版本字段 |
| 精算假设区 | 新增假设版本只读展示行 |
| 精算分解展示 | 末尾新增假设版本标注 |
| `insurance-product-tool-test.html` | 新建主页面验收测试（10个场景，自动化 PASS/FAIL 判断） |
| `当前版本边界说明.md` | 新建，明确区分已实现/部分实现/未实现功能 |

**不触发自动重算的控件（主动设计决策）：**
- 病种勾选 / 逐项 Benefit% / ToAge：计算量大，防卡顿
- 承保年龄规则：影响展示但不影响单点 GP

*文档结束。v1.2 完成主链路收口，具备可验收的测试方式，文档与代码一致。*
