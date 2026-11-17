"""Export synthetic experiment evidence without machine-local metadata or weights."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / 'mlx-qwen3-lab/reports'
DOCS = ROOT / 'docs'


def read(name):
    return json.loads((REPORTS / name).read_text())


def main():
    baseline = read('baseline-valid-base.json')
    runs = [('base', baseline, read('baseline-valid-review-notes.json'))]
    for number in [1, 2]:
        runs.append((f'round{number}', read(f'adapter-valid-qlora-r{number}.json'),
            read(f'adapter-valid-qlora-r{number}-review-notes.json')))
    all_answers = {}
    for label, raw, notes in runs:
        assert raw['status'] == 'completed' and len(raw['results']) == 20
        assert raw['config'] == baseline['config']
        review = {row['id']:row for row in notes['results']}
        all_answers[label] = {row['id']:dict(raw_response=row['raw_response'],
            schema_valid=row['schema_valid'], schema_error=row['schema_error'],
            review=review[row['id']]) for row in raw['results']}
        assert all(a['prompt_messages'] == b['prompt_messages'] for a,b in zip(raw['results'],baseline['results']))
    exported = dict(model=baseline['repo'], revision=baseline['revision'],
        generation_config=baseline['config'], split='valid', test_inference_performed=False,
        provenance='Synthetic fixtures; assistant-authored labels and semantic review, not independent human evaluation. Responses unchanged; machine-local metadata omitted.',
        results=[dict(id=row['id'], scenario_family=row['scenario_family'],
            prompt_messages=row['prompt_messages'], reference=row['reference'],
            runs={label:answers[row['id']] for label,answers in all_answers.items()})
            for row in sorted(baseline['results'],key=lambda row:row['id'])])
    content = json.dumps(exported,ensure_ascii=False,indent=2)+'\n'
    assert '/Users/' not in content and '/home/' not in content
    DOCS.mkdir(exist_ok=True)
    (DOCS/'evaluation-results.json').write_text(content)
    (DOCS/'review-rubric.json').write_text(json.dumps(read('review-rubric.json'),ensure_ascii=False,indent=2)+'\n')
    print('Exported 20 synthetic cases with original-model and two-adapter answers.')


if __name__ == '__main__':
    main()
