# Qwen3-4B MLX 本地训练环境

已在 Apple M4、24GB 统一内存、macOS 15.7.3 上验证推理与最小 QLoRA 训练流程。

## 当前阶段：第二轮已完成，仍未满足缺陷识别门槛

打开 [原模型、第一轮、第二轮对比页](reports/frontend-review-qlora-r2.html)。第二轮从原始 4bit 基座重新初始化 adapter，学习率从 0.0001 降为 0.00001，更新次数从 100 缩短到 20；batch=1、最后4层、rank=8 等其余训练设置不变。20步约相当于100条训练数据的0.2轮，没有遍历完整训练集。

评测前固定的成功条件为：完整识别缺陷至少 **5/10**，正常代码误报最多 **8/10**。同一组20题、同一提示和解码参数、同一评分标准的结果如下：

| 指标 | 原始模型 | 第一轮：1e-4 / 100步 | 第二轮：1e-5 / 20步 |
| --- | ---: | ---: | ---: |
| 格式合规 | 17/20 | 20/20 | 20/20 |
| 正常代码出现误报 | 9/10 | 0/10 | 0/10 |
| 完整识别真实缺陷 | 5/10 | 0/10 | 0/10 |
| 提供可实施修复 | 5/10 | 0/10 | 0/10 |
| 输出空 issues | 2/20 | 20/20 | 20/20 |

**第二轮仍对所有题输出 `{"issues":[]}`，10个真实缺陷全部漏报。误报条件满足，但缺陷识别条件失败，本轮未达标。** 第二轮训练程序耗时约74秒，MLX分配峰值3.10 GB，验证 loss 从4.892变为1.703；loss下降不能代替任务评测。

新 adapter 保存在 `adapters/frontend-review-qlora-r2/`，约7.35 MB，与第一轮权重指纹不同，确认没有误用第一轮结果。原始模型、数据、既有两组原始回答与评分标准均保留。只评测最终第20步，本轮没有追加第三次训练，测试集继续未使用。

```bash
uv run --frozen --offline python train_review_qlora.py --config configs/frontend-review-qlora-r2.yaml --report reports/training-qlora-r2.json
uv run --frozen --offline python evaluate_review_baseline.py --adapter-path adapters/frontend-review-qlora-r2 --output reports/adapter-valid-qlora-r2.json
uv run --frozen --offline python render_qlora_round2.py
```

以上是本轮实际使用的命令；已有训练和评测输出会拒绝覆盖。参数与门槛保存在 `reports/qlora-r2-plan.json`，训练过程、原始回答、逐题评语和汇总分别在 `reports/training-qlora-r2.json`、`reports/adapter-valid-qlora-r2.json`、`reports/adapter-valid-qlora-r2-review-notes.json`、`reports/qlora-r2-comparison.json`。共用评分函数 `review_scoring.py` 已核对能原样复算原模型和第一轮分数。

这组更温和的设置仍未避免空答案倾向。下一步应先诊断训练目标和数据表达，再设计新的实验。由于本轮同时改变学习率与步数，不能把结果单独归因于其中之一；同一验证集已用于参数选择，最终能力仍需独立测试确认。

## 第一轮记录：100步后出现退化

打开 [第一轮训练前后对比页](reports/frontend-review-qlora-r1.html)，可以逐题查看代码、两次原始回答和评分理由。2026-11-17 完成一次预定的 100 步 QLoRA：batch=1，100 条数据各遍历一次，最后 4 层，rank=8，学习率 0.0001，最大长度 512，开启梯度检查点与 prompt masking。该轮只评测最终第 100 步 adapter，没有挑选中间 checkpoint。

| 指标 | 原始模型 | 第一轮 adapter |
| --- | ---: | ---: |
| 格式合规 | 17/20 | 20/20 |
| 正常代码出现误报 | 9/10 | 0/10 |
| 完整识别真实缺陷 | 5/10 | 0/10 |
| 提供可实施修复 | 5/10 | 0/10 |
| 输出空 issues | 2/20 | 20/20 |

**误报数降低，但模型对所有题都回答 `{"issues":[]}`，10 个真实缺陷全部漏报。这是行为退化，没有取得有效的审查能力提升。** 在正负各半的集合中，一律回答空列表也能得到 10/20 的端到端可用分数，因此不能只看总分或 loss。

训练程序约 217 秒，MLX 分配峰值 3.15 GB，验证 loss 从 4.892 降至 1.379。约 7.35 MB 的 adapter 保存在 `adapters/frontend-review-qlora-r1/`，56 个张量全部有限、28 个 lora_b 均有非零更新。原始模型 11 个文件与数据指纹未变，测试集没有进入训练或模型评测。本轮 adapter 保留供分析，不作为实际审查模型使用。

已复核训练标签仍为 50 条缺陷 / 50 条正常、最长 327 token 没有截断、prompt masking 与聊天模板边界正确；两次评测的 system/user 和生成参数完全一致。随后进行了更低学习率、更少步数的第二轮实验，结果见上方；具体退化诱因仍未确定。

本轮执行的命令如下。已有 adapter 或报告时脚本会拒绝覆盖；新实验需用新的配置和输出路径。

```bash
uv run --frozen --offline python train_review_qlora.py
uv run --frozen --offline python evaluate_review_baseline.py --adapter-path adapters/frontend-review-qlora-r1 --output reports/adapter-valid-qlora-r1.json
uv run --frozen --offline python render_qlora_comparison.py
```

配置见 `configs/frontend-review-qlora-r1.yaml`，训练过程见 `reports/training-qlora-r1.json`，原始回答见 `reports/adapter-valid-qlora-r1.json`，逐题评分见 `reports/adapter-valid-qlora-r1-review-notes.json`，汇总见 `reports/qlora-r1-comparison.json`。原基线评测脚本按原指纹留存于 `reports/baseline-evaluator-source.py`。依赖仍为 46 个兼容包；全程使用本地权重，无依赖升级。

## 数据与训练前基线

新任务的数据约定见 [前端代码审查数据说明](data/frontend-review/README.md)。`data/frontend-review/` 已扩充为 **100 条训练、20 条验证、20 条测试**，对应 50/10/10 个独立场景，每个场景含缺陷和修复版各一条。输出统一为 `issues` 数组，包含 `line`、`problem`、`reason`、`suggestion`，允许无问题的空数组。原 12 条格式样例在 `data/frontend-review-format-samples/`；现有 smoke 数据与 adapter 保留在原目录。

```bash
uv run --frozen --offline python validate_review_data.py
uv run --frozen --offline python audit_review_corpus.py
```

真实 MLX-LM 数据加载、prompt masking 和关闭思考的推理前缀均检查通过，最长样例 327 token，低于本阶段 1024 token 限额。140 条语法审查、16 个纯函数场景的 32 次行为探针通过；3 组跨集合近似候选逐项复核为不同场景的公共短函数结构。详细检查见 `reports/corpus-audit.json`。语法检查不代替类型检查或完整浏览器交互；这些样例由同一编码助手编写并复核，没有独立人工标注。

打开 [训练前基线结果页](reports/frontend-review-baseline.html)，可逐题对照代码、模型原始回答、参考答案和评分理由。原始 Qwen3-4B 4bit 未加载 adapter，只对 20 条验证数据独立推理，关闭 thinking、temperature=0、seed=42、每题最多 512 token；未调整提示词或重新生成失败回答。

| 指标 | 训练前基线结果 |
| --- | ---: |
| JSON 可解析 | 19/20 |
| 格式合规（含字段和行号范围） | 17/20 |
| 完整识别预设缺陷 | 5/10（另 1 条部分命中） |
| 正常代码出现误报 | 9/10 |
| 提供可实施修复方向 | 5/10 |
| 缺陷定位合理 | 1/10 |
| 端到端可用 | 2/20 |

训练前离线推理约 141 秒，生成速度中位数 17.47 token/秒，MLX 分配峰值 2.75 GB。这些数字只适用于该次短输入。语义评分由编码助手逐题复核，标准见 `reports/review-rubric.json`；验证集只有 10 个独立场景，不能视为真实项目准确率。

原始记录 `reports/baseline-valid-base.json`、评分 `reports/baseline-valid-summary.json` 均保留模型/数据指纹。`evaluate_review_baseline.py` 只支持验证集；默认评测原模型，传 `--adapter-path` 时校验与基线的提示、数据、版本和解码参数一致。脚本拒绝覆盖已有结果；如需独立重跑，应指定新路径。

```bash
uv run --frozen --offline python evaluate_review_baseline.py --output reports/baseline-valid-base-new-run.json
```

结果页可直接用浏览器打开本地 HTML。重建现有结果页使用 `uv run --frozen --offline python render_review_report.py`，它只处理已保存的原始回答和评语，不调用模型。`audit_review_corpus.py` 的语法检查复用兄弟项目 `qwen-chat-lab/node_modules` 中的 TypeScript 与 PostCSS，不新增 Python 依赖。

检查记录：`logs/environment-recheck.json`、`logs/environment-recheck-inference.json`、`logs/frontend-review-data-check.json`。本机环境由 uv 管理，可用 `uv pip check --python .venv/bin/python` 检查依赖；独立环境没有 pip 模块不影响这些命令。

## 环境与模型

| 项目 | 已安装版本／位置 |
| --- | --- |
| 项目目录 | `mlx-qwen3-lab` |
| 独立 Python | `.venv`，Python 3.12.13 |
| MLX / Metal | 0.32.4 / 0.32.4 |
| MLX-LM | 0.32.2，含 `train` 依赖 |
| Transformers | 5.23.0 |
| Hugging Face Hub | 2.4.0 |
| Datasets | 5.2.0 |
| 模型 | `mlx-community/Qwen3-4B-4bit` |
| 模型目录 | `models/Qwen3-4B-4bit` |
| 固定模型 revision | `4dcb3d101c2a062e5c1d4bb173588c54ea6c4d25` |
| 量化 | 4 bit，group size 64 |
| 模型文件总大小 | 2,278,972,183 字节，约 2.28 GB |

依赖版本保存在 `uv.lock`；模型文件大小与 SHA-256 保存在 `model-manifest.json`。所有 11 个模型文件均已下载；大权重文件 SHA-256 与仓库的 LFS 元数据一致。推理与训练验证均在离线模式运行，确认没有依赖临时在线下载。

## 运行推理

在终端执行：

```bash
cd mlx-qwen3-lab
uv run --frozen --offline python infer.py --prompt '请用中文解释什么是过拟合。'
```

`infer.py` 默认关闭 Qwen3 的 thinking，使用确定性生成，最多生成 160 个 token；可通过 `--max-tokens` 调整。输出包含模型回答、速度和 MLX 峰值内存。脚本只加载本地权重，自动使用 Apple GPU。

如需进入环境后手动使用 MLX 命令：

```bash
cd mlx-qwen3-lab
source .venv/bin/activate
mlx_lm.lora --help
```

## 复现最小 QLoRA 训练

```bash
cd mlx-qwen3-lab
HF_HUB_OFFLINE=1 uv run --frozen --offline mlx_lm.lora --config configs/smoke.yaml
uv run --frozen --offline python infer.py --adapter-path adapters/smoke
```

此配置使用 8 条手写示例训练数据、2 条验证数据，训练 3 步；batch size 为 1，rank 为 8，只训练最后 4 层的 LoRA 参数，开启梯度检查点与 prompt masking。序列上限为 256，当前样例实际最长只有 42 token。

这是环境连通性测试，不能用来证明训练效果或长序列训练的内存余量。`adapters/smoke` 仅供验证，重复执行上述训练会覆盖这里的测试 adapter。正式训练请使用自己的训练／验证／测试数据和独立的 adapter 输出目录。

## 已完成的验证

- `uv pip check` 通过，46 个依赖包兼容。
- Metal 可用，默认设备为 Apple M4 GPU，矩阵运算检查通过。
- 原模型离线中文推理正常结束：36 个生成 token，约 41.14 token/秒，MLX 峰值内存 2.43 GB。该内存值仅是这次短输入推理的 MLX 分配峰值，不是整机占用或训练峰值。
- 3 步 QLoRA 训练与验证执行完成；可训练参数 1,835,008，约占模型参数的 0.046%。
- 成功保存约 7.35 MB 的 adapter：56 个张量全部为有限值，28 个初始为零的 `lora_b` 张量已发生非零更新。
- 保存的 adapter 可以重新加载，并完成离线中文生成。
- 训练后重新校验原始大权重文件，SHA-256 未改变。

输出质量的已知观察：在关闭 thinking、确定性解码时，原模型和测试 adapter 都把“17 + 25”回答成了“52”（正确答案是 42）。这项抽查没有通过，不能把上述运行检查解释为能力评测通过，也不能据此声称微调提升了模型。正式项目需单独建立评测集。

可查看的记录：

- `logs/download.log`：模型下载日志。
- `logs/inference-base.json`：原模型中文回答与速度、内存。
- `logs/train-smoke.log`：训练过程与 loss。
- `logs/training-check.json`：adapter 数值与原始权重校验结果。
- `logs/inference-adapter-chinese.json`：重新加载 adapter 的中文推理结果。
- `logs/inference-base-arithmetic.json`、`logs/inference-adapter.json`：算术抽查原始结果。

## 恢复环境与模型

```bash
cd mlx-qwen3-lab
uv sync --frozen
uv run --frozen python download_model.py
```

下载脚本固定模型 revision，支持复用已有下载，并在完成后校验大小与权重 SHA-256。恢复过程需要联网；日常运行上述本地推理和测试训练命令不需要联网。

来源：[模型仓库](https://huggingface.co/mlx-community/Qwen3-4B-4bit)、[MLX-LM 微调文档](https://github.com/ml-explore/mlx-lm/blob/main/mlx_lm/LORA.md)。
