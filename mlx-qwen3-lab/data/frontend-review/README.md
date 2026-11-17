# 前端代码审查微调：数据约定 v2

任务：给定短代码与明确上下文，输出可确认的问题、原因和修改建议，并保持固定 JSON 格式。当前为 **140 条合成练习数据**，已完成格式与标签复核，其中100条训练数据用于第一轮100步QLoRA，以及从原基座重新开始的第二轮20步实验（第二轮未遍历完整训练集）；20条验证数据用于训练期间loss和前后生成对比。20条测试数据未用于模型评测。原12条格式样例归档在 `../frontend-review-format-samples/`。

## 1. 一条样例是什么

采用 MLX-LM 支持的 chat JSONL：UTF-8 编码，每一物理行是一个完整 JSON 对象，顶层只有 `messages`。代码中的换行在 JSON 文件中写作 `\n`，用 Python `json.dumps` 生成，不手工拼接转义。

每条固定三条消息：

| role | content |
| --- | --- |
| system | `system.txt` 的完整固定规则 |
| user | 文件名、上下文、带语言名的代码块 |
| assistant | 标准答案，必须是一个**字符串形式的 JSON 对象** |

下面是结构示意，便于阅读做了缩进；实际文件中每条占一行，system 使用完整内容：

```json
{
  "messages": [
    {"role": "system", "content": "此处使用 system.txt 的完整内容"},
    {"role": "user", "content": "文件：Tasks.tsx\n上下文：点击按钮应立即在列表中新增一个任务。\n代码：\n```tsx\n...\n```"},
    {"role": "assistant", "content": "{\"issues\":[{\"line\":5,\"problem\":\"直接修改了 React state 数组\",\"reason\":\"push 修改原数组，随后传给 setItems 的仍是同一引用，React 可能跳过更新。\",\"suggestion\":\"创建新数组，例如 setItems(previous => [...previous, '新任务'])。\"}]}"}
  ]
}
```

可直接使用的完整记录在 [train.jsonl](train.jsonl)。

## 2. 标准答案

```json
{
  "issues": [
    {
      "line": 5,
      "problem": "直接修改了 React state 数组",
      "reason": "push 修改原数组，随后传给 setItems 的仍是同一引用，React 可能跳过更新。",
      "suggestion": "创建新数组，例如 setItems(previous => [...previous, '新任务'])。"
    }
  ]
}
```

- `line`：代码块内从 1 开始的行号，不计文件名、上下文或围栏；指向导致问题的具体代码行。
- `problem`：是什么问题。
- `reason`：代码为何导致这个问题，写简短、可核验的因果说明。
- `suggestion`：具体、与上下文一致的修改方向，必要时给短代码。
- 最多 3 个明确问题；没有可确认的问题时用 `{"issues":[]}`。
- 不增加其他字段，不加 Markdown 围栏或 JSON 外的说明；不手工加入 `<think>` 或模型角色标记。

机器可读的输出约定在 [response.schema.json](response.schema.json)。行号是否位于代码范围、消息顺序和 split 隔离由校验脚本额外检查。

## 3. 当前数据与后续划分

| 文件 | 当前条数 | 独立场景 | 有缺陷 / 无缺陷 | 用途 |
| --- | ---: | ---: | ---: | --- |
| train.jsonl | 100 | 50 | 50 / 50 | 更新 adapter 参数 |
| valid.jsonl | 20 | 10 | 10 / 10 | 训练前基线、验证 loss、选择参数和步数 |
| test.jsonl | 20 | 10 | 10 / 10 | 参数确定后，比较原模型和 adapter 的任务表现 |

覆盖 React 状态、生命周期、异步请求、列表、JavaScript 边界、表单和可访问性。每个独立场景都有含缺陷和修复后两个版本，文件名与上下文相同，没有通过文件名或注释提示答案。50/50 平衡适合初步练习，但不代表真实代码中的缺陷比例。

已按代码场景家族固定 split：同一场景的缺陷与修复版本留在同一个集合，集合内部以 seed=42 打乱。三种集合共享基础 API 知识，但使用不同场景。测试集不能用于选训练步数或调整提示；如果根据测试失败修改了方案，应另外留出新的未见测试样例。当前测试集仅做文件完整性、标签和语法审查，未交给模型推理。

`manifest.json` 存放样例 ID、所属集合、行号、场景家族、来源、代码和文件指纹，**不作为模型输入**。这些示例由同一编码助手编写并复核，**没有独立人工标注**。验证集 20 条只有 10 个独立场景，不能当成真实项目准确率或统计显著性证据。原始规范保存在 `corpus_sources/review_corpus.py`，不是从用户私有生产代码抽取的数据。

## 4. 分词与训练目标

使用本地 `mlx-community/Qwen3-4B-4bit` 自带的聊天模板，不修改原模型文件。训练选择 `mask_prompt: true`，让 loss 只覆盖最后一条 assistant 对应的 token；本机 Qwen3 模板会自动在答案前加入空的思考标记，原始数据不要重复添加。

本机 MLX-LM 0.32.2 的 `ChatDataset` 已实测：训练序列包含的答案，与推理时 `enable_thinking=False` 的前缀一致。推理时传同一条 system 与 user 消息，**不要传标准 assistant 答案**，再由模型生成 JSON。

当前格式检查的序列上限设为 **1024 token**，包含角色模板、system、代码与标准答案。140 条样例最长 **327 token**，没有被截断。未来真实代码变长后必须重新检查；超过上限应缩小任务范围或重新评估训练内存，不能让训练器截掉标准答案。

## 5. 如何检查

在项目根目录运行：

```bash
cd mlx-qwen3-lab
HF_HUB_OFFLINE=1 uv run --frozen --offline python validate_review_data.py
uv run --frozen --offline python audit_review_corpus.py
```

脚本验证：JSON/角色/字段、空问题列表、行号、重复代码、场景跨 split、manifest 指纹、真实 MLX-LM 数据加载、prompt masking、关闭思考的推理前缀、token 长度与答案结束标记。仅加载 tokenizer，不执行模型训练或测试集生成。

报告写入 `logs/frontend-review-data-check.json` 和 `reports/corpus-audit.json`。后者调用兄弟网页项目已安装的 TypeScript / PostCSS 解析器检查语法，用 Node 执行 16 个纯函数场景的缺陷/修复探针，共 32 次；HTML 仅做片段标签平衡与属性去重检查。语法检查不等于类型检查或完整浏览器交互测试。

跨集合比较去变量名/字面量后的 AST token，未发现相同序列；相似度达到 0.88 的 3 个候选已逐项复核，均为短函数公共骨架，理由保存在审查报告。算法不能证明所有语义泄漏都不存在。

`prepare_review_samples.py` 保留旧格式样例的来源。新数据由 `build_review_corpus.py` 从 `corpus_sources/review_corpus.py` 确定性生成；**生成命令会覆盖当前三个 JSONL 和 manifest**。修改数据后，旧基线仍是原始快照，必须使用新报告路径重新评测，不能混用指纹不同的结果。

## 6. 训练前基线

`evaluate_review_baseline.py` 只读取验证集作为输入；仅传 system/user，不传标准答案。加载本地原始模型、验证 11 个权重/配置文件的 SHA-256，默认不加载 adapter；传 `--adapter-path` 时加载指定 adapter 并检查与原基线的输入和配置一致。关闭 thinking、temperature=0、seed=42、每题最多 512 个生成 token。每题独立请求，原始输出逐条保存，不修复 JSON、不补跑失败题。

```bash
uv run --frozen --offline python evaluate_review_baseline.py --output reports/baseline-valid-base-new-run.json
```

已有路径会拒绝覆盖。评分规则见 `reports/review-rubric.json`；格式自动检查，缺陷识别/误报/修改建议由编码助手结合代码语义复核。第一轮已经完成：误报从 9/10 变为 0/10，但 20 题全部输出空 issues，真实缺陷识别从 5/10 变为 0/10，属于行为退化。报告见 `reports/frontend-review-qlora-r1.html`。本轮未修改数据或评分标准，测试集继续留到方案固定后使用。

第二轮把学习率降为1e-5、更新缩短至20步，仍从原始基座训练；相同验证题再次全部输出空issues，未达到预先固定的“缺陷识别≥5/10且误报≤8/10”条件。三组结果见 `reports/frontend-review-qlora-r2.html`。两轮训练都没有修改本目录的数据、system、参考答案或评分标准；验证集已用于实验参数选择，不作为独立最终测试集。

标签依据包含 [React 的多选 select 约定](https://react.dev/reference/react-dom/components/select)、[MDN 的 AbortSignal 生命周期](https://developer.mozilla.org/en-US/docs/Web/API/AbortSignal)，以及各短代码在给定上下文下的实际行为。

官方依据：[MLX-LM 数据格式与 prompt masking](https://github.com/ml-explore/mlx-lm/blob/main/mlx_lm/LORA.md#data)。本机实际行为还通过已安装的 `mlx_lm/tuner/datasets.py` 验证。
