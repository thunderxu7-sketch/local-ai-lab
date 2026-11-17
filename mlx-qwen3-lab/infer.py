"""Run Qwen3 locally on the Apple GPU; optionally load a LoRA adapter."""

import argparse
import importlib.metadata
import json
import os
import time
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import mlx.core as mx
from mlx_lm import load, stream_generate
from mlx_lm.sample_utils import make_sampler

ROOT = Path(__file__).resolve().parent


def local_path(value):
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompt", default="请用一句中文解释 LoRA 微调是什么。")
    parser.add_argument("--max-tokens", type=int, default=160)
    parser.add_argument("--adapter-path")
    parser.add_argument("--report", help="Save inference metrics as JSON.")
    args = parser.parse_args()
    if not mx.metal.is_available():
        raise RuntimeError("Apple Metal GPU is unavailable")
    mx.set_default_device(mx.gpu)
    mx.random.seed(42)
    model_path = ROOT / "models" / "Qwen3-4B-4bit"
    config = json.loads((model_path / "config.json").read_text())
    quantization = config.get("quantization", config.get("quantization_config", {}))
    if quantization.get("bits") != 4:
        raise RuntimeError(f"Expected a 4-bit model: {quantization}")
    adapter = str(local_path(args.adapter_path)) if args.adapter_path else None
    start = time.perf_counter()
    model, tokenizer = load(str(model_path), adapter_path=adapter)
    load_seconds = time.perf_counter() - start
    prompt = tokenizer.apply_chat_template(
        [{"role": "user", "content": args.prompt}],
        tokenize=False,
        add_generation_prompt=True,
        enable_thinking=False,
    )
    print(f"Device: {mx.device_info()['device_name']}; quantization: 4-bit", flush=True)
    print(f"Prompt: {args.prompt}", flush=True)
    output = []
    last = None
    for result in stream_generate(
        model, tokenizer, prompt, max_tokens=args.max_tokens, sampler=make_sampler(temp=0)
    ):
        print(result.text, end="", flush=True)
        output.append(result.text)
        last = result
    answer = "".join(output).strip()
    if last is None or not answer:
        raise RuntimeError("Model generated no text")
    report = {
        "model": str(model_path),
        "adapter": adapter,
        "device": mx.device_info()["device_name"],
        "quantization_bits": 4,
        "versions": {name: importlib.metadata.version(name) for name in ["mlx", "mlx-lm", "transformers"]},
        "prompt": args.prompt,
        "response": answer,
        "load_seconds": load_seconds,
        "prompt_tokens": last.prompt_tokens,
        "generation_tokens": last.generation_tokens,
        "prompt_tokens_per_second": last.prompt_tps,
        "generation_tokens_per_second": last.generation_tps,
        "mlx_peak_memory_gb": last.peak_memory,
        "finish_reason": last.finish_reason,
    }
    print("\n\n" + json.dumps(report, ensure_ascii=False, indent=2), flush=True)
    if args.report:
        dest = local_path(args.report)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
