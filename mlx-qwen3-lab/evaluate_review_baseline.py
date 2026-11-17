"""Offline Qwen3 validation, optionally with an adapter. Never evaluates the test set."""
import argparse
import hashlib
import importlib.metadata
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'
os.environ['TOKENIZERS_PARALLELISM'] = 'false'

import mlx.core as mx
from mlx_lm import load, stream_generate
from mlx_lm.sample_utils import make_sampler
from validate_review_data import check_row, parse_json

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data/frontend-review'


def fingerprint(path):
    digest = hashlib.sha256()
    with path.open('rb') as file:
        for block in iter(lambda: file.read(8 * 1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def save(path, obj):
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n')
    tmp.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'reports/baseline-valid-base.json')
    parser.add_argument('--adapter-path', type=Path)
    parser.add_argument('--compare-to', type=Path, default=ROOT / 'reports/baseline-valid-base.json')
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        raise SystemExit(f'保留既有基线，拒绝覆盖：{output}')
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest = parse_json((DATA / 'manifest.json').read_text())
    for filename, expected in manifest['file_sha256'].items():
        if fingerprint(DATA / filename) != expected:
            raise RuntimeError(f'数据指纹不匹配：{filename}')
    # Test file is fingerprinted above for integrity; its rows are never loaded as prompts.
    rows = [parse_json(line) for line in (DATA / 'valid.jsonl').read_text().splitlines()]
    system = (DATA / 'system.txt').read_text().strip()
    for row in rows:
        check_row(row, system)
    index = {s['row']: s for s in manifest['samples'] if s['split'] == 'valid'}
    assert len(rows) == 20 and len(index) == 20
    adapter, adapter_files, comparison = None, None, None
    generation_config = dict(seed=42, temperature=0, enable_thinking=False, max_tokens=512, independent_requests=True)
    if args.adapter_path:
        adapter = args.adapter_path.resolve()
        adapter_files = {name:fingerprint(adapter/name) for name in ['adapters.safetensors','adapter_config.json']}
        base = parse_json(args.compare_to.read_text())
        assert base['status'] == 'completed' and base['adapter'] is None
        assert base['corpus_manifest_sha256'] == fingerprint(DATA / 'manifest.json')
        assert base['data_sha256'] == manifest['file_sha256']
        assert base['config'] == generation_config
        assert base['versions'] == {name:importlib.metadata.version(name) for name in ['mlx','mlx-lm','transformers']}
        for number, (row, original) in enumerate(zip(rows, base['results']), 1):
            assert original['id'] == index[number]['id']
            assert original['prompt_messages'] == row['messages'][:-1]
        assert len(base['results']) == len(rows)
        comparison = dict(path=str(args.compare_to.resolve()), sha256=fingerprint(args.compare_to),
            prompts_and_generation_settings_identical=True)
    model_manifest = parse_json((ROOT / 'model-manifest.json').read_text())
    model_path = ROOT / 'models/Qwen3-4B-4bit'
    for file in model_manifest['files']:
        path = model_path / file['name']
        if path.stat().st_size != file['size'] or fingerprint(path) != file['sha256']:
            raise RuntimeError(f'原始模型文件改变：{path}')
    assert mx.metal.is_available()
    mx.set_default_device(mx.gpu)
    mx.random.seed(42)
    start = time.perf_counter()
    model, tokenizer = load(str(model_path), adapter_path=str(adapter) if adapter else None)
    report = dict(started_at=datetime.now(timezone.utc).isoformat(), status='running',
        split='valid', test_inference_performed=False, adapter=str(adapter) if adapter else None, model=str(model_path),
        adapter_files=adapter_files, comparison_baseline=comparison,
        repo=model_manifest['repo'], revision=model_manifest['revision'], all_model_hashes_verified=True,
        model_manifest_sha256=fingerprint(ROOT / 'model-manifest.json'),
        corpus_manifest_sha256=fingerprint(DATA / 'manifest.json'), data_sha256=manifest['file_sha256'],
        runner_sha256=fingerprint(Path(__file__)), device=mx.device_info()['device_name'],
        versions={name:importlib.metadata.version(name) for name in ['mlx','mlx-lm','transformers']},
        config=generation_config,
        load_seconds=time.perf_counter()-start, results=[])
    save(output, report)
    for number, row in enumerate(rows, 1):
        metadata = index[number]
        prompt_messages = row['messages'][:-1]
        assert [m['role'] for m in prompt_messages] == ['system','user']
        prompt = tokenizer.apply_chat_template(prompt_messages, tokenize=False,
            add_generation_prompt=True, enable_thinking=False)
        chunks, last = [], None
        began = time.perf_counter()
        # No shared conversation / KV cache; the reference answer is never passed to the model.
        for part in stream_generate(model, tokenizer, prompt, max_tokens=512, sampler=make_sampler(temp=0)):
            chunks.append(part.text)
            last = part
        if last is None:
            raise RuntimeError(f'没有模型输出：{metadata["id"]}')
        response = ''.join(chunks)
        predicted_row = {'messages': prompt_messages + [dict(role='assistant', content=response)]}
        parsed, schema_error = None, None
        try:
            _, parsed = check_row(predicted_row, system)
        except (ValueError, TypeError, KeyError) as error:
            schema_error = str(error)
        result = dict(id=metadata['id'], row=number, scenario_family=metadata['scenario_family'],
            prompt_messages=prompt_messages, reference=parse_json(row['messages'][-1]['content']),
            raw_response=response, parsed_response=parsed, schema_valid=schema_error is None,
            schema_error=schema_error, seconds=time.perf_counter()-began,
            prompt_tokens=last.prompt_tokens, generation_tokens=last.generation_tokens,
            generation_tokens_per_second=last.generation_tps, mlx_peak_memory_gb=last.peak_memory,
            finish_reason=last.finish_reason)
        report['results'].append(result)
        save(output, report)
        print(f"[{number:02d}/20] {metadata['id']} schema={result['schema_valid']} tokens={last.generation_tokens} finish={last.finish_reason}", flush=True)
        mx.clear_cache()
    report.update(status='completed', completed_at=datetime.now(timezone.utc).isoformat(),
        total_seconds=time.perf_counter()-start,
        schema_valid_count=sum(row['schema_valid'] for row in report['results']))
    save(output, report)
    print(f'基线原始记录：{output}', flush=True)


if __name__ == '__main__':
    main()
