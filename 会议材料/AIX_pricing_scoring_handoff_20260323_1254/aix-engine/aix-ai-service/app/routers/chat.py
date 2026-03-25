"""AI 对话路由 v3.4 — 完整编排层

流程：
  1. 并行加载产品文本 + 用户记忆
  2. RAG 规则注入
  3. 处理图片（多模态消息转换）
  4. 构建系统提示词
  5. 注册 tool_handler（6个工具，SSE side-effects 经 Queue 传递）
  6. 调用 Kimi（SSE 流式 + Function Calling）
  7. 流出所有 SSE 事件
"""

import asyncio
import json
import logging
import os

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.services.chat_engine import build_chat_system_prompt, CHAT_TOOLS
from app.services.issue_reporter import record_issue
from app.services.kimi_client import call_kimi_with_tools
from app.services.memory_store import (
    format_memory_for_prompt,
    load_core_memory,
    load_recent_summaries,
    save_summary,
    update_core_memory,
)
from app.services.needs_analysis import (
    build_report_summary,
    save_needs_report,
    update_report_recommendations,
)
from app.services.product_scorer import score_products
from app.services.product_search import fetch_products_for_scoring, fetch_products_text
from app.services.rules_loader import get_relevant_rules

logger = logging.getLogger(__name__)
router = APIRouter()

_SENTINEL = object()  # Queue 结束哨兵


def sse_event(event: str, data: str) -> str:
    return f"event: {event}\ndata: {data}\n\n"


def _enrich_recommendations(top3: list[dict]) -> list[dict]:
    """基于 score_breakdown 阈值为每个产品推导亮点标签。"""
    TAG_MAP = [
        ("age_fit",       20, "年龄适配"),
        ("budget_match",  20, "预算友好"),
        ("coverage",      20, "保障完整"),
        ("value_score",   18, "性价比高"),
        ("waiting_period",15, "等待期短"),
        ("sale_status",   10, "现行在售"),
    ]
    result = []
    for p in top3:
        bd   = p.get("score_breakdown") or {}
        tags = [label for key, threshold, label in TAG_MAP if (bd.get(key) or 0) >= threshold]
        result.append({**p, "highlights": tags[:4]})
    return result


def _build_conclusion(top3: list[dict]) -> str:
    """根据 top3 排名生成选购建议摘要。"""
    if not top3:
        return ""
    top = top3[0]
    name1 = top.get("product_name", "首推产品")
    lines = [f"综合保障完整性、性价比和年龄适配度，推荐优先考虑 **{name1}**。"]
    if len(top3) >= 2:
        name2 = top3[1].get("product_name", "次选产品")
        lines.append(f"如预算有限或有特殊偏好，**{name2}** 也是不错的替代选择。")
    if len(top3) >= 3:
        lines.append("如需最大化病种覆盖或公司偏好不同，可参考第三款备选方案。")
    return "".join(lines)


def _build_risk_notes(top3: list[dict], args: dict) -> list[str]:
    """生成风险提示列表（静态通用 + 产品特定）。"""
    notes = [
        "以上产品均为重疾险，确诊首次重疾后一次性赔付保额，理赔后合同通常终止。",
        "保费与年龄正相关，投保越早保费越低，建议尽早配置。",
        "实际核保结果以保险公司审核为准，有基础疾病或特殊职业可能被拒保或加费。",
        "当前数据库覆盖主流重疾险产品，如需更全面对比建议咨询专业顾问。",
    ]
    # 若含已停售产品，补充说明
    has_offline = any(p.get("sale_status") == "N" for p in top3)
    if has_offline:
        notes.append("部分推荐产品已停止公开销售，可通过存量渠道购买，请与代理人确认可投保性。")
    return notes


def _compute_budget_allocation(budget: int, args: dict) -> dict | None:
    """
    根据家庭结构和预算计算分配建议。

    返回 BudgetAllocation 结构：
      by_person  → 各成员年保费建议（元）
      by_coverage → 各险种年保费建议（元）
      rationale  → 分配说明

    一期当前只有重疾险，by_coverage 固定为 critical_illness=全额。
    by_person 按家庭结构比例分配。
    """
    if not budget or budget <= 0:
        return None

    family = str(args.get("family_structure") or "")
    has_spouse   = any(kw in family for kw in ["已婚", "配偶", "老婆", "老公", "伴侣", "丈夫", "妻子"])
    has_children = any(kw in family for kw in ["孩", "子女", "宝宝", "儿子", "女儿", "小孩"])

    # 按成员比例分配
    if has_spouse and has_children:
        by_person = {
            "self":     int(budget * 0.60),
            "spouse":   int(budget * 0.30),
            "children": int(budget * 0.10),
        }
        rationale = (
            f"本人重疾保障优先（60%，约{by_person['self']:,}元/年），"
            f"配偶次之（30%，约{by_person['spouse']:,}元/年），"
            f"剩余10%约{by_person['children']:,}元/年建议为子女配置医疗险。"
        )
    elif has_spouse:
        by_person = {
            "self":   int(budget * 0.60),
            "spouse": int(budget * 0.40),
        }
        rationale = (
            f"本人重疾优先（60%，约{by_person['self']:,}元/年），"
            f"配偶保障同等重要（40%，约{by_person['spouse']:,}元/年）。"
        )
    elif has_children:
        by_person = {
            "self":     int(budget * 0.75),
            "children": int(budget * 0.25),
        }
        rationale = (
            f"本人重疾优先（75%，约{by_person['self']:,}元/年），"
            f"建议为子女配置医疗险（约{by_person['children']:,}元/年）。"
        )
    else:
        by_person = {"self": budget}
        rationale = f"全额{budget:,}元/年集中配置本人重疾险，保障最大化。"

    # 一期只有重疾险
    by_coverage = {"critical_illness": budget}
    rationale += " 当前阶段优先完善重疾险，后续可增加百万医疗险形成双重保障。"

    return {
        "by_person":   by_person,
        "by_coverage": by_coverage,
        "rationale":   rationale,
    }


def _extract_last_user_text(messages: list[dict]) -> str:
    """从对话历史中提取最后一条用户消息的纯文本（兼容多模态格式）"""
    for m in reversed(messages):
        if m.get("role") == "user":
            content = m.get("content", "")
            if isinstance(content, list):
                return " ".join(
                    p.get("text", "") for p in content if p.get("type") == "text"
                )
            return str(content)
    return ""


def _build_multimodal_message(text: str, image_base64: str) -> dict:
    """将文字 + base64 图片合并为 Kimi Vision 多模态消息"""
    return {
        "role": "user",
        "content": [
            {"type": "image_url", "image_url": {"url": image_base64}},
            {"type": "text", "text": text or "请分析这张图片"},
        ],
    }


@router.post("")
async def chat_endpoint(request: Request):
    body = await request.json()
    messages: list[dict] = body.get("messages", [])
    profile_id: str | None = body.get("profile_id") or None
    image_data: dict | None = body.get("image")  # {"base64": "data:image/...;base64,..."}

    kimi_key = os.getenv("KIMI_API_KEY", "")
    if not kimi_key or kimi_key.startswith("your_"):
        async def _no_key():
            yield sse_event("error", json.dumps({"message": "未配置 KIMI_API_KEY"}, ensure_ascii=False))
        return StreamingResponse(_no_key(), media_type="text/event-stream")

    async def event_stream():
        # ── SSE side-effect queue（tool_handler 向此 Queue 推送 SSE 事件） ──
        sse_queue: asyncio.Queue = asyncio.Queue()

        try:
            # 1. 并行加载：产品文本 + 用户记忆
            if profile_id:
                products_text, core_memory, summaries = await asyncio.gather(
                    fetch_products_text(),
                    load_core_memory(profile_id),
                    load_recent_summaries(profile_id, limit=3),
                )
                memory_text = format_memory_for_prompt(core_memory, summaries)
            else:
                products_text = await fetch_products_text()
                memory_text = ""

            # 2. RAG 规则注入
            last_user_text = _extract_last_user_text(messages)
            rules_text = get_relevant_rules(last_user_text)

            # 3. 处理图片（修改最后一条 user 消息为多模态格式）
            has_image = bool(image_data and image_data.get("base64"))
            chat_messages = list(messages) if messages else [{"role": "user", "content": "你好"}]

            if has_image and chat_messages:
                last_text = last_user_text or "请分析这张图片"
                chat_messages = chat_messages[:-1] + [
                    _build_multimodal_message(last_text, image_data["base64"])
                ]

            # 4. 构建系统提示词
            system = build_chat_system_prompt(products_text, memory_text, rules_text, has_image)

            # 5. 注册 tool_handler
            async def tool_handler(name: str, args: dict) -> str:
                try:
                    return await _handle_tool(
                        name, args, profile_id, last_user_text, sse_queue
                    )
                except Exception as e:
                    logger.error(f"tool_handler error [{name}]: {e}")
                    return f"工具执行失败: {e}"

            # 6. 调用 Kimi 并流出事件
            async for event in call_kimi_with_tools(
                system=system,
                messages=chat_messages,
                tools=CHAT_TOOLS,
                tool_handler=tool_handler,
            ):
                # 每次迭代前先排空 SSE queue（tool_handler 产生的事件）
                while not sse_queue.empty():
                    yield sse_queue.get_nowait()

                if event["type"] == "chunk":
                    yield sse_event("chunk", json.dumps(
                        {"content": event["content"]}, ensure_ascii=False
                    ))
                elif event["type"] == "done":
                    # 最后再排空一次（最后一轮工具可能还有残留）
                    while not sse_queue.empty():
                        yield sse_queue.get_nowait()
                    yield sse_event("done", "{}")
                    return

        except Exception as e:
            logger.error(f"chat_endpoint error: {e}", exc_info=True)
            yield sse_event("error", json.dumps({"message": str(e)}, ensure_ascii=False))

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def _handle_tool(
    name: str,
    args: dict,
    profile_id: str | None,
    last_user_text: str,
    sse_queue: asyncio.Queue,
) -> str:
    """处理单个工具调用，返回工具结果字符串，SSE 事件推入 sse_queue。"""

    # ── 1. show_options ────────────────────────────────────────────────────────
    if name == "show_options":
        if "route_options" in args:
            # 路由卡片：触发 route_options SSE 事件，前端渲染 RouteCard
            await sse_queue.put(sse_event(
                "route_options",
                json.dumps({"route_options": args["route_options"]}, ensure_ascii=False)
            ))
        else:
            # 普通选项 chip：触发 options SSE 事件
            options = args.get("options", [])
            if options:
                await sse_queue.put(sse_event(
                    "options", json.dumps({"options": options}, ensure_ascii=False)
                ))
        return "选项已展示"

    # ── 2. update_core_memory ─────────────────────────────────────────────────
    if name == "update_core_memory":
        if profile_id:
            await update_core_memory(
                profile_id,
                field=args.get("field", ""),
                value=args.get("value", {}),
            )
            return "记忆已更新"
        return "无 profile_id，跳过记忆更新"

    # ── 3. save_recall_summary ────────────────────────────────────────────────
    if name == "save_recall_summary":
        if profile_id:
            await save_summary(
                profile_id,
                summary=args.get("summary", ""),
                recommendation=args.get("recommendation", ""),
            )
            return "摘要已保存"
        return "无 profile_id，跳过摘要保存"

    # ── 4. report_issue ───────────────────────────────────────────────────────
    if name == "report_issue":
        await record_issue(
            issue_type=args.get("issue_type", "unanswerable_question"),
            description=args.get("description", ""),
            user_query=args.get("user_query") or last_user_text,
            profile_id=profile_id,
        )
        return "问题已记录"

    # ── 5. start_needs_analysis ───────────────────────────────────────────────
    if name == "start_needs_analysis":
        mode = args.get("mode", "conversation")
        return f"已启动需求分析模式（{mode}），请继续收集用户信息"

    # ── 6. generate_needs_report ──────────────────────────────────────────────
    if name == "generate_needs_report":
        pid = profile_id or "anonymous"

        # 6a. 保存需求报告
        report_id = await save_needs_report(pid, args)

        # 6b. 获取评分用产品列表并计算 Top3
        age = int(args.get("age") or 35)
        gender = str(args.get("gender") or "male")
        products_raw = await fetch_products_for_scoring(
            age=age,
            gender=gender,
            budget_annual=int(args.get("budget_annual") or 0),
            preferred_company=str(args.get("preferred_company") or ""),
        )
        top3 = await score_products(products_raw, args)

        # 6c. 回写推荐结果到报告
        if report_id not in ("anonymous", "unknown"):
            await update_report_recommendations(report_id, top3)

        # 6d. 推送 SSE 事件（前端展示需求报告卡 + 产品推荐卡）
        summary = build_report_summary(args)
        await sse_queue.put(sse_event("needs_report", json.dumps({
            "report_id": report_id,
            "summary":   summary,
        }, ensure_ascii=False)))

        # 生成结构化 payload：highlights / conclusion / risk_notes / budget_allocation
        enriched_top3     = _enrich_recommendations(top3)
        conclusion        = _build_conclusion(top3)
        risk_notes        = _build_risk_notes(top3, args)
        effective_budget  = int(
            args.get("budget_annual")
            or args.get("budget_annual_recommended")
            or 0
        )
        budget_allocation = _compute_budget_allocation(effective_budget, args)

        rec_payload: dict = {
            "top3":       enriched_top3,
            "conclusion": conclusion,
            "risk_notes": risk_notes,
        }
        if budget_allocation:
            rec_payload["budget_allocation"] = budget_allocation

        await sse_queue.put(sse_event("product_recommendations", json.dumps(
            rec_payload, ensure_ascii=False
        )))

        # 6e. 返回摘要给 Kimi，供其生成解释文字
        top3_brief = [
            {
                "name":          p.get("product_name", ""),
                "company":       p.get("company_name", ""),
                "score":         p.get("total_score", 0),
                "annual_premium": p.get("annual_premium", 0),
                "fair_premium":   p.get("fair_premium", 0),
            }
            for p in top3
        ]
        return json.dumps({"top3": top3_brief}, ensure_ascii=False)

    # 未知工具
    logger.warning(f"未知工具调用: {name}")
    return "ok"
