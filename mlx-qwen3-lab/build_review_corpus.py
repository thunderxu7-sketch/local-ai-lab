"""Materialize the reviewed, deterministic synthetic frontend-review corpus."""
import hashlib
import json
import random
from pathlib import Path
from corpus_sources.review_corpus import SCENARIOS

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data/frontend-review'


def main():
    system = (DATA / 'system.txt').read_text().strip()
    manifest = dict(version=2, purpose='synthetic-learning-pilot', max_seq_length=1024,
        seed=42, target_counts_after_expansion=dict(train=100, valid=20, test=20),
        source='assistant-authored-and-reviewed-synthetic-fixtures',
        limitations='缺陷/修复成对；验证集20条只有10个独立场景；非真实项目分布、非独立人工标注。',
        samples=[])
    assert len(SCENARIOS) == 70
    assert len({s['scenario_family'] for s in SCENARIOS}) == 70
    for split, expected in [('train', 100), ('valid', 20), ('test', 20)]:
        examples = []
        for scenario in SCENARIOS:
            if scenario['split'] != split:
                continue
            for variant in ('buggy', 'fixed'):
                code = scenario[variant]
                issues = [scenario['issue']] if variant == 'buggy' else []
                lang = scenario['filename'].rsplit('.', 1)[1]
                user = f"文件：{scenario['filename']}\n上下文：{scenario['context']}\n代码：\n```{lang}\n{code}\n```"
                row = dict(messages=[dict(role='system', content=system), dict(role='user', content=user),
                    dict(role='assistant', content=json.dumps(dict(issues=issues), ensure_ascii=False, separators=(',', ':')))])
                meta = dict(id=scenario['id'] + ('-bug' if issues else '-ok'), split=split,
                    scenario_family=scenario['scenario_family'], source=manifest['source'],
                    code_sha256=hashlib.sha256(code.encode()).hexdigest(), has_issue=bool(issues))
                examples.append((row, meta))
        random.Random(42).shuffle(examples)
        assert len(examples) == expected
        output = []
        for i, (row, metadata) in enumerate(examples, 1):
            output.append(json.dumps(row, ensure_ascii=False))
            manifest['samples'].append(dict(metadata, row=i))
        (DATA / f'{split}.jsonl').write_text('\n'.join(output) + '\n')
    manifest['file_sha256'] = {name: hashlib.sha256((DATA / name).read_bytes()).hexdigest()
        for name in ['system.txt', 'response.schema.json', 'train.jsonl', 'valid.jsonl', 'test.jsonl']}
    (DATA / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(dict(counts=manifest['target_counts_after_expansion'], scenarios=len(SCENARIOS)), ensure_ascii=False))


if __name__ == '__main__':
    main()
