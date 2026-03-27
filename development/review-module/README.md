# 人工复核模块 V1

这是独立于总系统的最小前端原型模块。

## 目录

1. `index.html`
   页面入口
2. `styles.css`
   页面样式
3. `app.js`
   本地交互逻辑
4. `mock/review-task-v1.json`
   本地 mock 数据

## 当前能力

1. 三栏结构展示资料与原文、候选结果、人工裁决
2. 展示来源字段、原始值、Markdown 值、Block 值
3. 展示判定链路、规范化链路、入库映射链路
4. 支持本地 Accept / Modify / Reject / Hold 交互
5. 使用 `localStorage` 保存当前浏览器内的裁决状态

## 本地运行

在目录 `/Users/zqf-openclaw/codex-openai/development/review-module` 下执行：

```bash
python3 -m http.server 8789
```

然后访问：

`http://127.0.0.1:8789`

## 后续接入方式

1. 用真实接口替换 `mock/review-task-v1.json`
2. 保持页面字段结构不变
3. 审核提交仍只进入复核模块，不直接写正式库
