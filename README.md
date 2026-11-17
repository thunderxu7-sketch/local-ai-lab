# Local AI Lab

面向前端开发者的本地 AI 学习项目：从流式聊天、工具调用、向量 RAG 和 Agent，继续到 Apple Silicon 上的 MLX QLoRA 与效果评测。

仓库包含源码、依赖锁文件、虚构知识库、合成微调数据和实验记录的公开导出。模型权重、adapter、虚拟环境、个人聊天记录、缓存及本机原始日志不提交。

```text
local-ai-lab/
├── qwen-chat-lab/       # Next.js + Ollama：聊天、工具、RAG、Agent、评测
├── mlx-qwen3-lab/       # MLX：下载模型、推理、数据校验、QLoRA、前后对比
├── docs/               # 实验结论、评分标准、去除本机路径的逐题结果
└── scripts/            # 从本机记录导出可公开的实验结果
```

## 启动本地应用

需要 Node.js 22 和本机 Ollama。下面命令对应当前项目的默认模型：

```bash
git clone https://github.com/thunderxu7-sketch/local-ai-lab.git
cd local-ai-lab
ollama pull qwen3:14b
ollama pull qwen3-embedding:0.6b
cd qwen-chat-lab
npm ci
npm run dev
```

打开 <http://127.0.0.1:3010>。如果 Ollama 服务未启动，先在另一个终端运行 `ollama serve`。应用只监听本机地址。

界面支持普通对话、计算器工具、向量检索与带引用的 Agent 回答。`knowledge/` 中的“青竹笔记”为虚构产品；项目说明资料用于学习 RAG，不含真实业务文档。

详细说明：[网页项目 README](qwen-chat-lab/README.md)。

## 配置 MLX 环境

需要 Apple Silicon Mac、Python 3.12 和 uv；开发环境为 M4 / 24 GB。以下命令从仓库根目录开始执行：

```bash
cd mlx-qwen3-lab
uv sync --frozen
uv run --frozen python download_model.py
uv run --frozen --offline python infer.py --prompt '请用中文解释 LoRA。'
uv run --frozen --offline python validate_review_data.py
```

下载脚本固定 `mlx-community/Qwen3-4B-4bit` 的 revision，下载后生成本机 `model-manifest.json` 并校验文件。模型约 2.28 GB，不包含在 Git 仓库中；后续推理和训练使用本地文件。

数据为前端代码审查任务：100 条训练、20 条验证、20 条测试，输出固定为 `issues` JSON。每个场景包含缺陷版和修复版，同场景不跨集合。样例是编码助手编写的合成练习数据，尚无独立人工标注。

从干净环境运行一次训练与验证：

```bash
uv run --frozen --offline python evaluate_review_baseline.py --output reports/baseline-valid-base.json
uv run --frozen --offline python train_review_qlora.py --config configs/frontend-review-qlora-r2.yaml --report reports/training-qlora-r2.json
uv run --frozen --offline python evaluate_review_baseline.py --adapter-path adapters/frontend-review-qlora-r2 --output reports/adapter-valid-qlora-r2.json
```

已有输出会拒绝覆盖。第二轮配置只运行 20 次更新，约为训练集的 0.2 轮。它用于复现实验，**已经观察到能力退化，不应当作为可用的审查模型**。

详细说明：[MLX 项目 README](mlx-qwen3-lab/README.md)、[数据约定](mlx-qwen3-lab/data/frontend-review/README.md)。

## 实验结果

相同 20 条开发验证题，关闭 thinking、temperature=0。以下是一次本地运行记录，不是通用性能保证。

| 指标 | 原模型 | QLoRA 第一轮 | QLoRA 第二轮 |
| --- | ---: | ---: | ---: |
| 学习率 / 更新步数 | — | 1e-4 / 100 | 1e-5 / 20 |
| 正确代码被误报 | 9/10 | 0/10 | 0/10 |
| 完整识别真实缺陷 | 5/10 | 0/10 | 0/10 |
| 输出格式合规 | 17/20 | 20/20 | 20/20 |

两轮 adapter 都对所有题输出 `{"issues":[]}`。误报降低的同时，真实缺陷全部漏报，未达到“缺陷识别不低于原模型且减少误报”的条件。loss 下降不能单独证明任务能力提升。

验证题来自 10 个成对场景，且已用于选择后续实验参数；测试集尚未参与模型评测。标签和语义评分由同一编码助手复核，没有独立人工评审。

公开结果：[实验说明](docs/experiments.md)、[逐题输入、原始回答与评分](docs/evaluation-results.json)、[评分标准](docs/review-rubric.json)。回答文本保留原样，导出省略个人目录和运行环境元数据。

## 开发与复现

```bash
# 在 qwen-chat-lab 中
npm test
npm run build

# 在 mlx-qwen3-lab 中；语法审查复用兄弟项目的 TypeScript / PostCSS
uv run --frozen --offline python audit_review_corpus.py
```

`reports/`、`logs/` 和 `.local/` 中的文件在本机生成，不随仓库提交。子项目 README 中链接的历史本机报告因此可能不存在；公开快照统一放在 `docs/`。HTML 对比脚本还需要本机的实验计划和逐题复核文件，不会自动充当语义评分器。

本项目用于单机学习，没有账号、多用户隔离或公网部署配置。模型由原模型仓库单独提供，请遵循各自的使用条件。
