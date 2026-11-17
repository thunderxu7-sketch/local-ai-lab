"""Train one local pilot with installed MLX-LM, structured logs and a frozen corpus."""
import argparse
import hashlib
import importlib.metadata
import json
import math
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'
os.environ['TOKENIZERS_PARALLELISM'] = 'false'

import mlx.core as mx
import numpy as np
import yaml
from mlx_lm import load
from mlx_lm.lora import CONFIG_DEFAULTS, train_model
from mlx_lm.tuner.callbacks import TrainingCallback
from mlx_lm.tuner.datasets import CacheDataset, create_dataset
from mlx_lm.tuner.trainer import evaluate
from evaluate_review_baseline import fingerprint, save
from validate_review_data import validate

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=ROOT / 'configs/frontend-review-qlora-r1.yaml')
    parser.add_argument('--report', type=Path, default=ROOT / 'reports/training-qlora-r1.json')
    cli = parser.parse_args()
    os.chdir(ROOT)
    configuration = yaml.safe_load(cli.config.read_text())
    args = SimpleNamespace(**(CONFIG_DEFAULTS | configuration))
    adapter_path = ROOT / args.adapter_path
    report_path = cli.report.resolve()
    if adapter_path.exists() or report_path.exists():
        raise SystemExit('拒绝覆盖已有训练；新实验必须使用独立 adapter 和报告路径。')
    assert args.train and not args.test and args.resume_adapter_file is None
    assert args.fine_tune_type == 'lora' and args.report_to is None
    model_path = ROOT / args.model
    assert json.loads((model_path / 'config.json').read_text())['quantization']['bits'] == 4
    data_path = ROOT / args.data
    baseline_path = ROOT / 'reports/baseline-valid-base.json'
    baseline = json.loads(baseline_path.read_text())
    assert baseline['status'] == 'completed' and baseline['adapter'] is None
    assert fingerprint(data_path / 'manifest.json') == baseline['corpus_manifest_sha256']
    for name, digest in baseline['data_sha256'].items():
        assert fingerprint(data_path / name) == digest, name
    validation = validate(data_path, args.max_seq_length)
    model_manifest = json.loads((ROOT / 'model-manifest.json').read_text())
    for item in model_manifest['files']:
        assert fingerprint(model_path / item['name']) == item['sha256'], item['name']
    mx.set_default_device(mx.gpu)
    mx.random.seed(args.seed)
    np.random.seed(args.seed)
    started = time.perf_counter()
    report = dict(status='running', started_at=datetime.now(timezone.utc).isoformat(),
        config=vars(args), config_sha256=fingerprint(cli.config),
        runner_sha256=fingerprint(Path(__file__)), baseline_sha256=fingerprint(baseline_path),
        corpus_manifest_sha256=baseline['corpus_manifest_sha256'], data_sha256=baseline['data_sha256'],
        counts=validation['counts'], longest_sample_tokens=validation['longest_sample_tokens'],
        model_revision=model_manifest['revision'], all_model_hashes_verified_before=True,
        adapter_selection=f'final-after-{args.iters}-updates; no checkpoint selection or within-run hyperparameter search',
        test_used_for_training_or_evaluation=False, device=mx.device_info()['device_name'],
        versions={name:importlib.metadata.version(name) for name in ['mlx','mlx-lm','transformers']},
        events=[])
    save(report_path, report)

    class Recorder(TrainingCallback):
        def record(self, kind, info):
            for value in info.values():
                if isinstance(value, (float, int)) and not math.isfinite(value):
                    raise RuntimeError(f'Nonfinite training metric: {info}')
            event = dict(kind=kind, elapsed_seconds=time.perf_counter()-started, **info)
            report['events'].append(event)
            save(report_path, report)
            print('METRIC ' + json.dumps(event), flush=True)
        def on_train_loss_report(self, info):
            self.record('train', info)
        def on_val_loss_report(self, info):
            # Installed MLX-LM reports the number of updates completed before validation.
            self.record('valid', info)

    try:
        model, tokenizer = load(str(model_path))
        # Only these two splits become training/validation datasets; never load test rows here.
        train_rows = [json.loads(s) for s in (data_path / 'train.jsonl').read_text().splitlines()]
        valid_rows = [json.loads(s) for s in (data_path / 'valid.jsonl').read_text().splitlines()]
        assert len(train_rows) == 100 and len(valid_rows) == 20
        train_set = create_dataset(train_rows, tokenizer, args)
        valid_set = create_dataset(valid_rows, tokenizer, args)
        callback = Recorder()
        train_model(args, model, train_set, valid_set, callback)
        # MLX-LM's final in-loop validation precedes the last update; measure final weights explicitly.
        final_loss = evaluate(model, CacheDataset(valid_set), batch_size=1, num_batches=-1,
            max_seq_length=args.max_seq_length)
        callback.record('valid-final', dict(iteration=args.iters, val_loss=final_loss))
        adapter_file = adapter_path / 'adapters.safetensors'
        tensors = mx.load(str(adapter_file))
        finite = all(mx.all(mx.isfinite(value)).item() for value in tensors.values())
        updated = sum(bool(mx.any(value != 0).item()) for name,value in tensors.items() if name.endswith('lora_b'))
        assert finite and updated > 0
        for item in model_manifest['files']:
            assert fingerprint(model_path / item['name']) == item['sha256'], item['name']
        for name,digest in baseline['data_sha256'].items():
            assert fingerprint(data_path / name) == digest, name
        report.update(status='completed', completed_at=datetime.now(timezone.utc).isoformat(),
            total_seconds=time.perf_counter()-started, updates=args.iters,
            initial_validation_loss=report['events'][0]['val_loss'], final_validation_loss=final_loss,
            peak_mlx_memory_gb=mx.get_peak_memory()/1e9, adapter_tensors=len(tensors),
            trainable_parameters=sum(value.size for value in tensors.values()),
            all_adapter_values_finite=finite, updated_lora_b_tensors=updated,
            base_model_unchanged=True, corpus_unchanged=True,
            adapter_files={name:fingerprint(adapter_path/name) for name in ['adapters.safetensors','adapter_config.json']},
            adapter_size_bytes=adapter_file.stat().st_size)
        save(report_path, report)
        print('COMPLETED ' + str(report_path), flush=True)
    except BaseException as error:
        report.update(status='failed', error=f'{type(error).__name__}: {error}', elapsed_seconds=time.perf_counter()-started)
        save(report_path, report)
        raise


if __name__ == '__main__':
    main()
