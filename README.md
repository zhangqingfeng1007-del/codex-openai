# 作业批改工具原型

这是一个适合手机端使用的作业批改工具骨架，支持：

- 拍照或上传作业图片
- 后台并行调用 2-3 个大模型分别给出批改意见
- 聚合多个模型的总结与分数
- 预留标准答案库接口，后续可以接数据库、题库服务或教辅内容库

## 目录

- `homework_grader/main.py`：FastAPI 服务入口
- `homework_grader/static/`：手机端上传页面
- `requirements.txt`：依赖列表

## 本地启动

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn homework_grader.main:app --reload
```

浏览器打开 [http://127.0.0.1:8000](http://127.0.0.1:8000)。

## 环境变量

默认启用 `MOCK_MODE=true`，即使没有 API Key 也可以跑通页面与接口。

如果你要接真实模型，可以配置：

```bash
export MOCK_MODE=false

export MODEL_A_NAME=OpenAI
export MODEL_A_BASE_URL=https://api.openai.com/v1
export MODEL_A_API_KEY=your_key
export MODEL_A_MODEL=gpt-4.1-mini

export MODEL_B_NAME=ProviderB
export MODEL_B_BASE_URL=https://your-provider.example/v1
export MODEL_B_API_KEY=your_key
export MODEL_B_MODEL=some-vision-model

export MODEL_C_NAME=ProviderC
export MODEL_C_BASE_URL=https://your-provider.example/v1
export MODEL_C_API_KEY=your_key
export MODEL_C_MODEL=some-vision-model
```

## 关键接口

### 1. 批改接口

`POST /api/grade`

表单字段：

- `image`：作业图片
- `subject`：学科
- `grade_level`：年级
- `answer_key`：标准答案库编号，可选

### 2. 标准答案预览接口

`GET /api/answer-bank/{answer_key}`

目前是模拟数据，后续可替换为：

- MySQL / PostgreSQL 题库表
- 教辅解析库
- 学校自有标准答案服务
- OCR 后的题目检索服务

## 建议的下一步

1. 接入 OCR 预处理，让题目分割更稳定。
2. 给模型输出增加统一 schema 校验，减少返回格式漂移。
3. 将 `AnswerBankRepository` 改成数据库或外部服务实现。
4. 增加“家长视角”和“孩子视角”两种讲解风格。
