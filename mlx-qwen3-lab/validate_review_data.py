"""Check review JSONL, split isolation and the installed MLX-LM tokenization path."""
import argparse
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

from mlx_lm.tuner.datasets import load_local_dataset
from mlx_lm.utils import load_tokenizer

ROOT = Path(__file__).resolve().parent
DEFAULT_DATA = ROOT / "data/frontend-review"
PROMPT = re.compile(r"文件：([^\n]+)\n上下文：([^\n]+)\n代码：\n```(tsx|jsx|ts|js|html|css)\n(.+)\n```", re.DOTALL)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def unique_keys(pairs):
    obj = {}
    for key, value in pairs:
        require(key not in obj, f"JSON 包含重复字段：{key}")
        obj[key] = value
    return obj


def parse_json(text):
    return json.loads(text, object_pairs_hook=unique_keys)


def check_row(row, system):
    require(isinstance(row, dict) and set(row) == {"messages"}, "每行顶层只允许 messages")
    messages = row["messages"]
    require(isinstance(messages, list) and len(messages) == 3, "需要 system、user、assistant 三条消息")
    for message, role in zip(messages, ("system", "user", "assistant")):
        require(isinstance(message, dict) and set(message) == {"role", "content"}, "消息只允许 role 与 content")
        require(message["role"] == role and isinstance(message["content"], str) and message["content"].strip(), f"无效的 {role} 消息")
    require(messages[0]["content"] == system, "system 与 system.txt 不一致")
    match = PROMPT.fullmatch(messages[1]["content"])
    require(match is not None, "user 必须包含文件、单行上下文与带语言名的代码块")
    code = match.group(4)
    require("```" not in code, "代码内不能嵌套代码围栏")
    answer = parse_json(messages[2]["content"])
    require(isinstance(answer, dict) and set(answer) == {"issues"}, "assistant JSON 只允许 issues")
    issues = answer["issues"]
    require(isinstance(issues, list) and len(issues) <= 3, "issues 必须是最多 3 项的数组")
    seen_issues = set()
    for issue in issues:
        require(isinstance(issue, dict) and set(issue) == {"line", "problem", "reason", "suggestion"}, "问题字段必须为 line/problem/reason/suggestion")
        require(type(issue["line"]) is int and 1 <= issue["line"] <= len(code.splitlines()), "问题行号超出代码范围")
        for field in ("problem", "reason", "suggestion"):
            require(isinstance(issue[field], str) and issue[field].strip() and len(issue[field]) <= 300, f"{field} 需要 1–300 字符的非空文本")
        key = (issue["line"], issue["problem"])
        require(key not in seen_issues, "重复的问题标注")
        seen_issues.add(key)
    require(not any(tag in message["content"] for tag in ("<think>", "</think>", "<|im_start|>", "<|im_end|>") for message in messages), "不要在原始消息里手工写模型角色或思考标记")
    return code, answer


def validate(data_dir, max_tokens=None):
    system = (data_dir / "system.txt").read_text().strip()
    manifest = parse_json((data_dir / "manifest.json").read_text())
    limit = manifest["max_seq_length"] if max_tokens is None else max_tokens
    require(type(limit) is int and limit > 0, "token 上限必须为正整数")
    index = {}
    sample_ids = set()
    for metadata in manifest["samples"]:
        key = (metadata["split"], metadata["row"])
        require(key not in index and metadata["id"] not in sample_ids, "manifest 的样例编号或位置重复")
        require(metadata["split"] in ("train", "valid", "test") and type(metadata["row"]) is int and metadata["row"] > 0, "manifest 的 split/row 无效")
        index[key] = metadata
        sample_ids.add(metadata["id"])
    rows = {}
    code_splits = {}
    family_splits = {}
    observed = set()
    for split in ("train", "valid", "test"):
        rows[split] = []
        lines = (data_dir / f"{split}.jsonl").read_text().splitlines()
        require(lines, f"{split} 不能为空")
        for number, text in enumerate(lines, 1):
            label = f"{split}:{number}"
            try:
                row = parse_json(text)
                code, answer = check_row(row, system)
                metadata = index.get((split, number))
                require(metadata is not None, "manifest 缺少这条样例")
                require(metadata["code_sha256"] == hashlib.sha256(code.encode()).hexdigest(), "代码指纹与 manifest 不一致")
                require(metadata["has_issue"] is bool(answer["issues"]), "manifest 的 has_issue 不一致")
                canonical = re.sub(r"\s+", "", code)
                code_key = hashlib.sha256(canonical.encode()).hexdigest()
                require(code_key not in code_splits, f"重复或跨集合重复代码，已出现在 {code_splits.get(code_key)}")
                code_splits[code_key] = label
                family = metadata["scenario_family"]
                require(isinstance(family, str) and family.strip(), "scenario_family 不能为空")
                require(family not in family_splits or family_splits[family] == split, f"同一场景家族跨集合泄漏：{family}")
                family_splits[family] = split
                observed.add((split, number))
                rows[split].append(row)
            except (ValueError, KeyError, TypeError) as error:
                raise ValueError(f"{label}: {error}") from error
    require(observed == set(index), "manifest 包含不存在的行")

    tokenizer = load_tokenizer(ROOT / "models/Qwen3-4B-4bit")
    datasets = load_local_dataset(data_dir, tokenizer, SimpleNamespace(mask_prompt=True))
    results = []
    for split, dataset in zip(("train", "valid", "test"), datasets):
        require(len(dataset) == len(rows[split]), f"MLX-LM 读取的 {split} 数量不一致")
        for i, row in enumerate(rows[split]):
            tokens, offset = dataset.process(dataset[i])
            messages = row["messages"]
            training_prefix = tokenizer.apply_chat_template(messages[:-1], add_generation_prompt=True, return_dict=False)
            inference_prefix = tokenizer.apply_chat_template(messages[:-1], add_generation_prompt=True, enable_thinking=False, return_dict=False)
            require(0 < offset < len(tokens) and offset == len(training_prefix), f"{split}:{i+1} 答案 masking 边界无效")
            require(tokens[:offset] == training_prefix, f"{split}:{i+1} 训练 prompt 不是完整序列的前缀")
            require(tokens[:len(inference_prefix)] == inference_prefix, f"{split}:{i+1} 训练与关闭思考的推理前缀不一致")
            target = tokenizer.decode(tokens[len(inference_prefix):])
            require(target == messages[-1]["content"] + "<|im_end|>\n", f"{split}:{i+1} 答案或结束标记发生变化")
            require(len(tokens) <= limit, f"{split}:{i+1} 共 {len(tokens)} token，超过 {limit}，会被训练器截断")
            results.append({"id": index[(split, i+1)]["id"], "split": split, "tokens": len(tokens), "masked_prompt_tokens": offset, "supervised_tokens": len(tokens)-offset, "inference_prefix_tokens": len(inference_prefix)})
    return {
        "checked_at": datetime.now(timezone.utc).isoformat(), "passed": True, "data": str(data_dir), "mask_prompt": True,
        "counts": {split: len(items) for split, items in rows.items()}, "max_seq_length": limit, "longest_sample_tokens": max(row["tokens"] for row in results),
        "mlx_lm_loader_compatible": True, "non_thinking_prefix_matches": True, "duplicate_code_found": False, "scenario_cross_split_found": False,
        "scope": "仅验证格式、明显重复、分词长度与边界；标签内容仍需复核，未训练模型，未评估测试集回答。",
        "samples": results,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--max-tokens", type=int)
    parser.add_argument("--report", type=Path, default=ROOT / "logs/frontend-review-data-check.json")
    args = parser.parse_args()
    try:
        report = validate(args.data.resolve(), args.max_tokens)
    except (ValueError, KeyError, OSError, TypeError) as error:
        raise SystemExit(f"数据检查失败：{error}") from error
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({key: value for key, value in report.items() if key != "samples"}, ensure_ascii=False, indent=2))
    print(f"报告：{args.report}")


if __name__ == "__main__":
    main()
