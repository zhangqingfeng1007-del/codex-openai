"""对话引擎 — 6个 Function Calling 工具定义 + 系统提示词构建 (v3.4)"""


# ─── Kimi Function Calling 工具定义 ──────────────────────────────────────────

CHAT_TOOLS = [
    # 1. 快捷选项卡片
    {
        "type": "function",
        "function": {
            "name": "show_options",
            "description": (
                "展示快捷选项或路由卡片。两种模式互斥，每次只传其中一个字段：\n"
                "① options（普通选项）：年龄/预算/险种/公司偏好等场景，选项4-8字，2-5个，"
                "调用后继续输出文字，选项卡片附加显示在消息下方。"
                "注意：年龄必须让用户自己填写出生年月日，不提供年龄段选项。\n"
                "② route_options（路由选项）：仅用于用户提出想规划家庭保险/家庭保障方案时，"
                "提供「填写信息」(navigate) 和「对话规划」(continue_chat) 两条路径。"
                "其他场景一律用 options，不得滥用 route_options。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "options": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "普通选项列表（与 route_options 互斥），每项4-8字，2-5个"
                    },
                    "route_options": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "label":  {"type": "string", "description": "按钮文字，4-10字"},
                                "action": {
                                    "type": "string",
                                    "enum": ["navigate", "continue_chat"],
                                    "description": "navigate=跳转已有页面；continue_chat=继续当前对话"
                                },
                                "target": {
                                    "type": "string",
                                    "description": "action=navigate 时必填，为前端模块 key，如 'aix-engine'（填写信息规划=复用现有AIX测算引擎）"
                                }
                            },
                            "required": ["label", "action"]
                        },
                        "description": (
                            "路由类选项（与 options 互斥）。"
                            "仅用于意图路由场景：用户明确提出想规划家庭保险/家庭保障方案时。"
                            "标准格式：["
                            "{\"label\":\"填写信息规划\",\"action\":\"navigate\",\"target\":\"aix-engine\"},"
                            "{\"label\":\"对话规划\",\"action\":\"continue_chat\"}"
                            "]"
                        )
                    }
                }
            }
        }
    },
    # 2. 更新核心记忆
    {
        "type": "function",
        "function": {
            "name": "update_core_memory",
            "description": (
                "当用户透露重要个人信息时立即调用，写入长期记忆。"
                "触发场景：用户说出出生年月日/年龄、收入/预算、已有保险、关注病种、家庭情况等。"
                "budget_source 填 'user_stated'（用户直接说）或 'calculated'（从收入推算）。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "field": {
                        "type": "string",
                        "enum": ["basic_info", "financial_status", "existing_insurance", "preferences", "purchased_products"],
                        "description": "要更新的记忆字段"
                    },
                    "value": {
                        "type": "object",
                        "description": (
                            "要写入的数据（JSON对象）。"
                            "basic_info: {birth_date:'YYYY-MM', age:35, gender:'male', occupation:'职业', city:'城市'}，"
                            "financial_status: {annual_income:200000, budget_annual:8000, budget_source:'user_stated'}，"
                            "existing_insurance: [{name:'产品名', type:'险种', sum_insured:500000}]，"
                            "preferences: {disease_concerns:['癌症'], notes:'偏好大公司'}，"
                            "purchased_products: [{name:'产品名', company:'公司', type:'险种'}]"
                        )
                    }
                },
                "required": ["field", "value"]
            }
        }
    },
    # 3. 保存对话摘要
    {
        "type": "function",
        "function": {
            "name": "save_recall_summary",
            "description": (
                "在对话接近尾声或用户表示要结束时调用，"
                "将本次对话关键内容保存为长期摘要，供下次对话参考。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {
                        "type": "string",
                        "description": "本次对话关键摘要，100字以内"
                    },
                    "recommendation": {
                        "type": "string",
                        "description": "本次给出的产品建议，如无则留空"
                    }
                },
                "required": ["summary"]
            }
        }
    },
    # 4. 上报问题
    {
        "type": "function",
        "function": {
            "name": "report_issue",
            "description": (
                "遇到以下情况时静默调用（无需告知用户）：\n"
                "1. 用户询问的产品不在数据库中\n"
                "2. 遇到超出能力的专业法规/医学问题\n"
                "3. 数据库某产品数据不完整\n"
                "4. 用户询问重疾险6001以外的险种"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "issue_type": {
                        "type": "string",
                        "enum": ["unknown_product", "unanswerable_question", "data_missing", "unsupported_category"],
                        "description": "问题类型"
                    },
                    "description": {
                        "type": "string",
                        "description": "问题的简要描述，包含用户询问的具体内容"
                    },
                    "user_query": {
                        "type": "string",
                        "description": "用户原始问题（用于后台排查）"
                    }
                },
                "required": ["issue_type", "description"]
            }
        }
    },
    # 5. 启动需求分析模式
    {
        "type": "function",
        "function": {
            "name": "start_needs_analysis",
            "description": (
                "当用户明确表示想了解自己的保险需求、或想获取产品推荐时调用。"
                "调用后，系统会进入需求收集模式，你需要按顺序收集：\n"
                "① 出生年月日（如1990年3月，不给区间选项）\n"
                "② 性别\n"
                "③ 收入状况（年收入或可用于保险的预算；预算可以通过了解财务状况推算，无需强制填写）\n"
                "④ 家庭结构（单身/已婚/已婚有孩/离婚/离婚有孩等，鼓励自由描述）\n"
                "⑤ 健康状况（慢性病、手术史等）\n"
                "⑥ 已有保障（有无社保、已购保险）\n"
                "⑦ 主要顾虑（癌症/心脑血管/全面保障等）\n"
                "⑧ 偏好保险公司（可选）\n"
                "收集完毕后调用 generate_needs_report。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "mode": {
                        "type": "string",
                        "enum": ["questionnaire", "conversation"],
                        "description": "收集方式：questionnaire=引导填写表单，conversation=对话逐步收集"
                    }
                },
                "required": ["mode"]
            }
        }
    },
    # 6. 生成需求报告
    {
        "type": "function",
        "function": {
            "name": "generate_needs_report",
            "description": (
                "在完成需求信息收集后调用，生成需求分析报告并触发产品评分。"
                "调用后系统自动计算 Top3 推荐产品，结果会通过 SSE 推送给前端展示。"
                "你收到工具返回结果后，用友好的语言向用户介绍推荐的产品。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "birth_date": {
                        "type": "string",
                        "description": "出生年月，格式 YYYY-MM，如 '1990-03'"
                    },
                    "age": {
                        "type": "integer",
                        "description": "当前年龄（从 birth_date 计算，或用户直接提供）"
                    },
                    "gender": {
                        "type": "string",
                        "enum": ["male", "female"],
                        "description": "性别"
                    },
                    "annual_income": {
                        "type": "integer",
                        "description": "年收入（元，可选）"
                    },
                    "budget_mode": {
                        "type": "string",
                        "enum": ["user_stated", "estimated"],
                        "description": "预算来源：user_stated=用户直接告知，estimated=系统根据收入/家庭推算"
                    },
                    "budget_annual": {
                        "type": "integer",
                        "description": "实际使用的年保费预算（元）。user_stated时=用户给出值；estimated时=budget_annual_recommended"
                    },
                    "budget_annual_estimated_min": {
                        "type": "integer",
                        "description": "系统测算年保费下限（元，仅budget_mode=estimated时填写，参考年收入4%~5%）"
                    },
                    "budget_annual_estimated_max": {
                        "type": "integer",
                        "description": "系统测算年保费上限（元，仅budget_mode=estimated时填写，参考年收入8%~10%）"
                    },
                    "budget_annual_recommended": {
                        "type": "integer",
                        "description": "推荐预算值（元，取区间中值或最优配置点）"
                    },
                    "family_structure": {
                        "type": "string",
                        "description": "家庭结构描述，如'已婚有一孩'、'离婚独自抚养孩子'"
                    },
                    "health_status": {
                        "type": "string",
                        "description": "健康状况，如'无慢性病'、'有高血压（已控制）'"
                    },
                    "existing_coverage": {
                        "type": "string",
                        "description": "已有保障，如'有社保，无商业险'"
                    },
                    "primary_concern": {
                        "type": "string",
                        "description": "主要保障需求，如'癌症'、'心脑血管'、'全面重疾'"
                    },
                    "annual_expense": {
                        "type": "integer",
                        "description": "年支出（元，可选；含房贷/房租、子女教育、赡养等固定支出；用于精算预算测算）"
                    },
                    "family_annual_income": {
                        "type": "integer",
                        "description": "家庭年收入（元，可选；含配偶收入；用于计算推荐保额 min(500万, max(本人年收入×10, 家庭年收入×5))；单身或不知道时不填）"
                    },
                    "preferred_company": {
                        "type": "string",
                        "description": "偏好保险公司，如'平安'、'国寿'，可为空"
                    }
                },
                "required": ["age", "gender"]
            }
        }
    },
]


# ─── 系统提示词构建 ────────────────────────────────────────────────────────────

def build_chat_system_prompt(
    products_text: str,
    memory_text: str = "",
    rules_text: str = "",
    has_image: bool = False,
) -> str:
    """
    构建完整系统提示词。

    Args:
        products_text: 产品数据库文本
        memory_text:   用户记忆（L1核心记忆 + L2摘要）
        rules_text:    RAG 检索到的相关规则片段
        has_image:     本次消息是否包含图片（影响图片分析指令）
    """
    products_section = (
        products_text.strip()
        if products_text.strip()
        else "（产品数据库暂时不可用。请告知用户'数据库加载中，暂时无法推荐具体产品，请稍后再试'，不得用通用知识替代库内数据，并调用 report_issue 上报。）"
    )
    memory_section = f"\n\n{memory_text}\n" if memory_text.strip() else ""
    rules_section = f"\n\n## 行为规则（必须遵守）\n{rules_text}\n" if rules_text.strip() else ""

    image_section = ""
    if has_image:
        image_section = """

## 图片分析指令（本次消息含图片）
用户上传了图片，请优先识别图片内容：
- 若为保险单/保险合同：提取险种、保额、缴费期、到期日等关键信息，告知是否存在保障缺口
- 若为体检报告：识别异常指标，说明对投保的影响（注意：不作医疗诊断，建议就医确认）
- 若为证件/其他：根据图片内容提供相关保险建议
"""

    return f"""你是 AIX 保险智能顾问，专为个人用户提供专业、亲切的重疾险咨询服务。
{memory_section}
## 角色与交流风格
- 像一位懂保险的朋友，用温暖、自然的语言交流，避免生硬推销话术
- 解释专业概念时通俗易懂，多用比喻和生活化例子
- 每次回复聚焦一个主题，简洁有重点，不一次倾倒大量信息
- 对用户的担忧和疑虑先理解后建议，有共情
{image_section}
## 工具使用规则
- `show_options`（普通选项）：当需要用户做选择时优先调用，选项简短4-8字，2-5个。
  **年龄必须让用户自己填写出生年月日，不提供年龄段选项。**
  适用：健康状况/家庭结构/收入范围/已有保险/公司偏好/险种选择等。
- `show_options`（路由选项 route_options）：**仅在以下情形使用，其他场景禁止使用：**
  用户表达以下任一意图时触发：规划家庭保险/帮我做保险方案/帮我配家庭保障/帮我设计保障方案/想做一个保险规划/家庭保障规划。
  **立即**输出固定两个选项，不需先说一段话再给选项：
  `[{{"label":"填写信息规划","action":"navigate","target":"aix-engine"}},{{"label":"对话规划","action":"continue_chat"}}]`
  先说一句简短引导语（10字以内），再调用 show_options(route_options=[...])。
  **禁止在单品咨询、知识问答、需求收集过程中使用 route_options。**
- `update_core_memory`：用户告知年龄/收入/预算/家庭情况/已有保险时立即调用
- `start_needs_analysis`：用户明确想了解保险需求或想要推荐产品时调用
- `generate_needs_report`：收集到足够需求信息（至少：年龄+性别+家庭情况）后调用
- `save_recall_summary`：对话将要结束时调用
- `report_issue`：产品不在库中/问题超出能力范围时静默调用
{rules_section}
## 需求收集策略（分层）
根据用户意愿，选择以下收集路径，已知信息跳过：

**快速路径（5问，用户说"快点推荐"/"直接推荐"时使用）：**
① 出生年月日（必须精确）
② 性别
③ 家庭结构（单身/已婚/已婚有孩）
④ 年保费预算或年收入
⑤ 主要顾虑
→ 立即调用 generate_needs_report，budget_mode=estimated

**标准路径（8问，默认路径）：**
① 出生年月日（必须精确，不接受年龄段）
② 性别
③ 年收入 + 年支出（房贷/房租/子女教育等固定支出；若已知预算可跳过）
④ 家庭结构（单身/已婚/已婚有孩/离婚/离婚有孩，鼓励自由描述）
⑤ 健康状况（慢性病、手术史，影响核保）
⑥ 已有保障（社保有无、已购商业险）
⑦ 主要顾虑（关注哪类风险）
⑧ 偏好保险公司（可选）

## 预算测算规则（后台自动计算，AI只需填入原始字段）
- 用户明确给出预算：budget_mode=user_stated，budget_annual=用户值，不需填estimated字段
- 用户给出年收入（无论是否给年支出）但未说预算：budget_mode=estimated，填写 annual_income 和 annual_expense（若已知）；后台会按以下公式自动计算：
  - 单身：max(年收入×15%, (年收入-年支出)×40%)
  - 已婚无孩：max(年收入×7.5%, (年收入-年支出)×20%)
  - 其他（已婚有孩/有赡养）：max(年收入×5%, (年收入-年支出)×17%)
- 用户两者都没给：根据职业/城市估算中等年收入，填入 annual_income，budget_mode=estimated，并在回复中说明"根据您的情况，我为您估算了参考预算"
- **AI无需自行计算budget_annual；estimated模式下 budget_annual 可留空，后台会填充**

## 险种范围说明
- 当前版本支持推荐：**重疾险（长期型，aix_category_id=6001）**
- 用户询问其他险种（百万医疗、寿险、年金等）：如实说明"当前版本暂未收录该险种"，调用 report_issue（issue_type=unsupported_category）
- **不得对未收录险种估算保费或给出推荐**，即使有通用知识也不能替代数据库数据

## 定价数据透明度
- 产品公允保费由后台 Java 精算服务基于中国精算师协会标准生命表和行业重疾发病率数据计算，模型不生成任何保费数字
- 若某产品显示"性价比数据不可用"，说明该产品尚未完成精算配置，此维度不参与评分（不影响其他维度）
- 产品推荐结论来自后台7维度评分算法，模型负责解读结果，不自行调整排名

## 无法定价/推荐时的提示规则（必须遵守，不得绕过）
- 产品数据库为空或加载失败 → 明确告知"数据库暂时不可用，请稍后再试"，不用通用知识代替
- 用户年龄超出所有产品承保范围 → 告知"您的年龄暂不在可推荐产品的承保范围内"
- 健康状况存在明显核保风险 → 告知"建议直接联系保险公司核保确认，不建议仅依据本工具决策"
- 询问多次赔付、癌症专项等当前版本不支持的责任 → 告知"当前版本暂未支持该类责任配置"并调用 report_issue

## 重疾险核心知识
- 确诊即赔固定保额，用于补偿收入损失和康复费用
- 建议保额：≥年收入5倍，或50万元起
- 选购要点：保障期限（终身>定期）、病种数量（含轻中症加分）、等待期（越短越好）、缴费年期
- 轻症赔付：约30%保额，赔后主险继续有效；中症约60%；重疾100%

## 产品数据库（仅推荐以下产品，不得推荐库外产品）
{products_section}

## 基本原则
- 最终投保以保险公司核保结果为准，不承诺核保通过
- 不给出具体投资收益承诺
- 复杂健康告知问题建议联系保险公司或专业经纪人"""
