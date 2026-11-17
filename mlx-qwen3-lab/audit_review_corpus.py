"""Audit fingerprints, syntax, authored executable labels and cross-split clones."""
import hashlib
import json
import subprocess
from collections import Counter
from datetime import datetime, timezone
from difflib import SequenceMatcher
from html.parser import HTMLParser
from pathlib import Path
from corpus_sources.review_corpus import SCENARIOS

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data/frontend-review'
NEAR_REVIEWS = {
    frozenset(['T26-ok', 'E04-ok']): '短函数骨架相似；一个对查询参数编码，一个解析小数。名称归一化隐藏了 encodeURIComponent 与 parseFloat 的区别，缺陷机制、上下文及代码均不同。',
    frozenset(['T40-bug', 'E05-bug']): '短 return 表达式的公共骨架；一个错误使用逻辑或默认值，另一个错误使用 typeof 判断数组；关键运算符及缺陷机制不同。',
    frozenset(['T40-ok', 'E05-bug']): '空值合并表达式与 typeof 比较仅共享短函数骨架；不存在同场景的改名副本。',
}


class FragmentParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
    def handle_starttag(self, tag, attrs):
        assert len(dict(attrs)) == len(attrs), 'duplicate HTML attributes'
        if tag not in {'input', 'img', 'br', 'hr', 'meta', 'link'}:
            self.stack.append(tag)
    def handle_endtag(self, tag):
        assert self.stack and self.stack.pop() == tag, f'unbalanced tag: {tag}'


def main():
    manifest = json.loads((DATA / 'manifest.json').read_text())
    for name, expected in manifest['file_sha256'].items():
        assert hashlib.sha256((DATA / name).read_bytes()).hexdigest() == expected, name
    result = subprocess.run(['node', str(ROOT / 'corpus_sources/audit_fixtures.cjs')],
        input=json.dumps(SCENARIOS), capture_output=True, text=True, check=True)
    checks = json.loads(result.stdout)
    for scenario in SCENARIOS:
        if scenario['filename'].endswith('.html'):
            for variant in ['buggy', 'fixed']:
                parser = FragmentParser()
                parser.feed(scenario[variant])
                parser.close()
                assert not parser.stack, scenario['id']
                checks['syntax'].append(dict(id=scenario['id'] + ('-bug' if variant == 'buggy' else '-ok'),
                    method='html-fragment-balanced-tags-and-unique-attributes', errors=[]))
    assert len(checks['syntax']) == 140
    assert all(not row['errors'] for row in checks['syntax']), checks['syntax']
    assert all(row['passed'] for row in checks['probes']), checks['probes']
    samples = {s['id']: s for s in manifest['samples']}
    tokens = checks.pop('tokens')
    duplicates, near = [], []
    ids = list(tokens)
    pairs = 0
    for i, a in enumerate(ids):
        for b in ids[i+1:]:
            if samples[a]['split'] == samples[b]['split']:
                continue
            pairs += 1
            ratio = SequenceMatcher(None, tokens[a], tokens[b], autojunk=False).ratio()
            if tokens[a] == tokens[b]:
                duplicates.append([a, b])
            if ratio >= 0.88:
                review = NEAR_REVIEWS.get(frozenset([a, b]))
                assert review, f'需要复核新的近似候选：{a}, {b}'
                near.append(dict(a=a, b=b, normalized_token_similarity=round(ratio, 4),
                    reviewed_by='coding-assistant', disposition='distinct-scenarios-common-short-syntax', rationale=review))
    assert not duplicates, duplicates
    report = dict(checked_at=datetime.now(timezone.utc).isoformat(), passed=True, fingerprints_match=True,
        syntax_count=len(checks['syntax']), runtime_probe_count=len(checks['probes']),
        runtime_probe_scenarios=len(checks['probes']) // 2,
        cross_split_pairs_compared=pairs, normalized_cross_split_clones=duplicates,
        near_clone_threshold=0.88, near_clone_candidates=sorted(near, key=lambda x:-x['normalized_token_similarity']),
        balance={split:dict(Counter('bug' if s['has_issue'] else 'clean' for s in samples.values() if s['split'] == split))
            for split in ['train','valid','test']},
        independent_scenarios=dict(Counter(s['split'] for s in SCENARIOS)),
        label_review=dict(reviewer='same-coding-assistant-as-author', independent_human_review=False,
            scenarios_reviewed=70, criteria=['缺陷在给定上下文下可确认', '修复仅针对指定缺陷', '修复版无其他可确认问题',
                '不把未使用导入等风格项当功能缺陷', '缺陷/修复版本共享文件名和上下文，答案提示不进入模型输入']),
        limitations=['语法解析不等于类型检查；HTML 检查仅限这些片段的基本结构。',
            '执行探针仅验证带 probe 的纯函数标签；其余标签由编写助手逐项复核，未运行完整浏览器交互。',
            '词法/AST token 相似度不能证明语义无泄漏；成对样本相关，多个场景共享语言/API 基础知识。',
            '测试集只接受数据完整性和标签检查，未交给模型推理。'], **checks)
    dest = ROOT / 'reports/corpus-audit.json'
    dest.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ['syntax','probes']}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
