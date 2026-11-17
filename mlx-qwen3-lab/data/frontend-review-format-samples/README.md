# 前端代码审查微调：数据约定 v1

任务：给定短代码与明确上下文，输出可确认的问题、原因和修改建议，并保持固定 JSON 格式。只做这项任务的监督微调；当前 12 条手写样例用于把格式和读取链路定好，不能证明模型能力提升。

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

| 文件 | 当前格式样例 | 扩充时的第一轮目标 | 用途 |
| --- | ---: | ---: | --- |
| train.jsonl | 8 | 100 | 更新 adapter 参数 |
| valid.jsonl | 2 | 20 | 查看验证 loss、选择参数和训练步数 |
| test.jsonl | 2 | 20 | 参数确定后，比较原模型和 adapter 的任务表现 |

当前训练样例包括 state 数组修改、定时器清理、effect 依赖、props 排序、图片替代文本，以及 3 条没有明确问题的代码。验证和测试各含 1 条问题代码与 1 条无问题代码。这只是格式试样，不把 2 条测试样例称为可靠评测集。

扩充前先按代码场景家族确定 split：同一组件的改名、修复版、轻微改写都放同一集合，避免只换变量名就同时出现在训练和评测中。三种集合应覆盖可比的任务类型，但使用不同代码场景。测试集不能用于选训练步数或反复调整提示；如果根据测试失败修改了方案，应另外留出新的未见测试样例。

`manifest.json` 存放样例 ID、所属集合、行号、场景家族、来源和代码指纹，**不作为模型输入**。当前样例为手写构造数据；内容已按代码逐条检查，后续扩充还需复核标签，尤其是误报和上下文不足的样例。真实项目代码只选自己有权使用的内容，并移除凭据和个人信息。

## 4. 分词与训练目标

使用本地 `mlx-community/Qwen3-4B-4bit` 自带的聊天模板，不修改原模型文件。训练选择 `mask_prompt: true`，让 loss 只覆盖最后一条 assistant 对应的 token；本机 Qwen3 模板会自动在答案前加入空的思考标记，原始数据不要重复添加。

本机 MLX-LM 0.32.2 的 `ChatDataset` 已实测：训练序列包含的答案，与推理时 `enable_thinking=False` 的前缀一致。推理时传同一条 system 与 user 消息，**不要传标准 assistant 答案**，再由模型生成 JSON。

当前格式检查的序列上限设为 **1024 token**，包含角色模板、system、代码与标准答案。12 条样例最长 **315 token**，没有被截断。未来真实代码变长后必须重新检查；超过上限应缩小任务范围或重新评估训练内存，不能让训练器截掉标准答案。

## 5. 如何检查

在项目根目录运行：

```bash
cd mlx-qwen3-lab
HF_HUB_OFFLINE=1 uv run --frozen --offline python validate_review_data.py
```

脚本验证：JSON/角色/字段、空问题列表、行号、重复代码、场景跨 split、manifest 指纹、真实 MLX-LM 数据加载、prompt masking、关闭思考的推理前缀、token 长度与答案结束标记。仅加载 tokenizer，不执行模型训练或测试集生成。

报告写入 `logs/frontend-review-data-check.json`。格式通过不代表标签必然正确，也不能识别所有语义相近的重复样例，仍需内容审查。

`prepare_review_samples.py` 保存这批样例的构造来源，已有 JSONL 时拒绝覆盖。继续扩充时编辑 JSONL 和 manifest，维护一致的 `system.txt`；先检查，再进入训练。

官方依据：[MLX-LM 数据格式与 prompt masking](https://github.com/ml-explore/mlx-lm/blob/main/mlx_lm/LORA.md#data)。本机实际行为还通过已安装的 `mlx_lm/tuner/datasets.py` 验证。
