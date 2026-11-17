# Qwen Lab · 运行限制与记录

本文依据项目 README 的运行边界和记录说明整理，并与 lib/chat.ts、lib/runs.ts、app/api/chat/route.ts 核对。

## 生成参数与超时

Qwen Lab 默认关闭思考，每轮模型生成最多 512 token，上下文配置为 8192 token，服务端一次请求超时为 180 秒。普通对话单条消息最多 6000 字符、最多 40 条历史、问题与历史及 System Prompt 总计最多 16000 字符。字符数不等于 token 数，这些限额只是粗略保护。长对话可以新开会话。

## RAG 与 Agent 输入限制

Qwen Lab 的知识库问答和 Agent 当前问题最多 2000 字符。Agent 的问题与 System Prompt 合计最多 2500 字符，累计工具上下文超过 9000 字符时会报错。模型输出长度达到上限不代表内容已完整。

## 本地记录的位置

Qwen Lab 的服务器运行记录位于 .local/runs.jsonl，包含输入、System Prompt、回答、工具步骤、检索原文、状态和耗时。网页“运行记录”展示最近 30 次请求并可导出 JSON。浏览器当前会话草稿保存在 localStorage；“新对话”清空草稿，但保留服务器记录。向量缓存另存于 .local/vector-index.json，它不是聊天记录。

## 部署范围

Qwen Lab 目前仅用于本机学习，没有账号、多用户隔离或联网搜索，推理和向量检索均调用本机 Ollama。网页不会直接加载 MLX 权重或启动 MLX 训练。为了给 24GB 统一内存留出余量，不同时进行 MLX 训练和 14B 推理。
