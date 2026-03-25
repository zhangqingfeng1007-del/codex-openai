import asyncio
import base64
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"


@dataclass
class ModelConfig:
    provider_name: str
    base_url: str
    api_key: str
    model: str
    enabled: bool


def load_model_configs() -> list[ModelConfig]:
    configs: list[ModelConfig] = []
    for suffix in ("A", "B", "C"):
        provider_name = os.getenv(f"MODEL_{suffix}_NAME", f"model_{suffix.lower()}")
        base_url = os.getenv(f"MODEL_{suffix}_BASE_URL", "https://api.openai.com/v1")
        api_key = os.getenv(f"MODEL_{suffix}_API_KEY", "")
        model = os.getenv(f"MODEL_{suffix}_MODEL", "gpt-4.1-mini")
        enabled = os.getenv(f"MODEL_{suffix}_ENABLED", "true").lower() == "true"
        configs.append(
            ModelConfig(
                provider_name=provider_name,
                base_url=base_url.rstrip("/"),
                api_key=api_key,
                model=model,
                enabled=enabled,
            )
        )
    return [config for config in configs if config.enabled]


class AnswerBankRepository:
    async def get_standard_answer(self, answer_key: str) -> dict[str, Any] | None:
        # 这里先返回模拟数据，后面可以替换成数据库、教辅题库或学校题库服务。
        demo_answers = {
            "math-grade3-unit2-001": {
                "question_summary": "三位数加减法口算与竖式计算",
                "standard_answer": "结果应为 245，验算步骤需完整。",
                "grading_points": [
                    "答案数值正确",
                    "列式过程完整",
                    "单位书写正确",
                ],
            }
        }
        return demo_answers.get(answer_key)


answer_bank_repository = AnswerBankRepository()


def build_prompt(
    subject: str,
    grade_level: str,
    answer_bank_payload: dict[str, Any] | None,
) -> str:
    prompt = f"""
你是一名认真、温和、适合给孩子讲解的作业批改老师。

请根据上传的作业图片完成这些任务：
1. 识别题目与学生答案。
2. 判断每道题是否正确。
3. 给出错误原因。
4. 给出更适合孩子理解的讲解。
5. 输出一个 0-100 的总体得分。

学科：{subject or '未指定'}
年级：{grade_level or '未指定'}
""".strip()

    if answer_bank_payload:
        prompt += "\n\n请结合以下标准答案信息进行核对：\n"
        prompt += json.dumps(answer_bank_payload, ensure_ascii=False, indent=2)

    prompt += """

请严格输出 JSON，格式如下：
{
  "score": 92,
  "summary": "整体表现良好，主要错误集中在...",
  "items": [
    {
      "question": "题目1",
      "student_answer": "学生答案",
      "is_correct": false,
      "feedback": "错误原因",
      "explanation": "给孩子的讲解"
    }
  ]
}
"""
    return prompt.strip()


async def call_openai_compatible_model(
    config: ModelConfig,
    image_bytes: bytes,
    mime_type: str,
    prompt: str,
) -> dict[str, Any]:
    if not config.api_key or os.getenv("MOCK_MODE", "true").lower() == "true":
        return {
            "provider": config.provider_name,
            "model": config.model,
            "raw_text": None,
            "parsed": {
                "score": 88,
                "summary": f"{config.provider_name} 认为整体基础不错，建议重点复习计算步骤。",
                "items": [
                    {
                        "question": "自动识别题目示例",
                        "student_answer": "示例答案",
                        "is_correct": False,
                        "feedback": "步骤有遗漏，结果可能受影响。",
                        "explanation": "先把已知条件写清楚，再一步一步计算会更稳。",
                    }
                ],
            },
        }

    image_base64 = base64.b64encode(image_bytes).decode("utf-8")
    payload = {
        "model": config.model,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime_type};base64,{image_base64}",
                        },
                    },
                ],
            }
        ],
        "temperature": 0.2,
    }

    async with httpx.AsyncClient(timeout=90.0) as client:
        response = await client.post(
            f"{config.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {config.api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        response.raise_for_status()
        data = response.json()

    raw_text = data["choices"][0]["message"]["content"]
    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        parsed = {
            "score": None,
            "summary": "模型返回了非 JSON 内容，请检查适配层。",
            "items": [],
        }

    return {
        "provider": config.provider_name,
        "model": config.model,
        "raw_text": raw_text,
        "parsed": parsed,
    }


def aggregate_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    valid_scores = [
        result["parsed"].get("score")
        for result in results
        if isinstance(result.get("parsed", {}).get("score"), (int, float))
    ]
    average_score = round(sum(valid_scores) / len(valid_scores), 1) if valid_scores else None

    return {
        "average_score": average_score,
        "consensus_summary": "；".join(
            result["parsed"].get("summary", "")
            for result in results
            if result.get("parsed", {}).get("summary")
        ),
        "model_results": results,
    }


app = FastAPI(title="Homework Grader")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
async def health() -> dict[str, Any]:
    return {
        "ok": True,
        "mock_mode": os.getenv("MOCK_MODE", "true").lower() == "true",
        "models": [config.provider_name for config in load_model_configs()],
    }


@app.get("/api/answer-bank/{answer_key}")
async def answer_bank_preview(answer_key: str) -> dict[str, Any]:
    payload = await answer_bank_repository.get_standard_answer(answer_key)
    if not payload:
        raise HTTPException(status_code=404, detail="未找到标准答案")
    return payload


@app.post("/api/grade")
async def grade_homework(
    image: UploadFile = File(...),
    subject: str = Form("数学"),
    grade_level: str = Form("三年级"),
    answer_key: str = Form(""),
) -> dict[str, Any]:
    if not image.content_type or not image.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="请上传图片文件")

    image_bytes = await image.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="图片内容为空")

    answer_bank_payload = None
    if answer_key:
        answer_bank_payload = await answer_bank_repository.get_standard_answer(answer_key)

    prompt = build_prompt(subject, grade_level, answer_bank_payload)
    model_configs = load_model_configs()
    if not model_configs:
        raise HTTPException(status_code=500, detail="没有启用任何模型配置")

    tasks = [
        call_openai_compatible_model(config, image_bytes, image.content_type, prompt)
        for config in model_configs
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    normalized_results: list[dict[str, Any]] = []
    for config, result in zip(model_configs, results, strict=True):
        if isinstance(result, Exception):
            normalized_results.append(
                {
                    "provider": config.provider_name,
                    "model": config.model,
                    "error": str(result),
                    "parsed": {
                        "score": None,
                        "summary": "模型调用失败",
                        "items": [],
                    },
                }
            )
        else:
            normalized_results.append(result)

    return {
        "request": {
            "filename": image.filename,
            "subject": subject,
            "grade_level": grade_level,
            "answer_key": answer_key or None,
            "answer_bank_used": bool(answer_bank_payload),
        },
        "aggregate": aggregate_results(normalized_results),
    }
