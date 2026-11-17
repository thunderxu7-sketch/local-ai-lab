"""Combine immutable raw answers and explicit semantic reviews into local JSON/HTML."""
import hashlib
import html
import json
import statistics
from datetime import datetime, timezone
from pathlib import Path
from validate_review_data import parse_json

ROOT = Path(__file__).resolve().parent
REPORTS = ROOT / 'reports'


def esc(value):
    return html.escape(str(value))


def pretty(value):
    return json.dumps(value, ensure_ascii=False, indent=2)


def main():
    raw_path = REPORTS / 'baseline-valid-base.json'
    raw = json.loads(raw_path.read_text())
    notes = json.loads((REPORTS / 'baseline-valid-review-notes.json').read_text())
    rubric = json.loads((REPORTS / 'review-rubric.json').read_text())
    audit = json.loads((REPORTS / 'corpus-audit.json').read_text())
    data_check = json.loads((ROOT / 'logs/frontend-review-data-check.json').read_text())
    assert hashlib.sha256(raw_path.read_bytes()).hexdigest() == notes['raw_report_sha256'], '评语不属于这次原始输出'
    assert raw['status'] == 'completed' and len(raw['results']) == 20
    reviews = {row['id']: row for row in notes['results']}
    assert len(reviews) == len(notes['results']) == 20
    assert set(reviews) == {row['id'] for row in raw['results']}
    results = []
    for row in raw['results']:
        review = reviews[row['id']]
        bug = bool(row['reference']['issues'])
        try:
            parse_json(row['raw_response'])
            json_valid = True
        except (ValueError, TypeError):
            json_valid = False
        if bug:
            passed = row['schema_valid'] and all(review[k] for k in ['detects_gold','fix_usable','line_correct']) and review['extra_false_positives'] == 0
        else:
            passed = row['schema_valid'] and row['parsed_response'] == {'issues':[]} and review['extra_false_positives'] == 0
        results.append(dict(row, review=review, json_valid=json_valid, has_gold_issue=bug, overall_pass=passed))
    bugs = [r for r in results if r['has_gold_issue']]
    clean = [r for r in results if not r['has_gold_issue']]
    assert len(bugs) == len(clean) == 10
    def metric(numerator, denominator):
        return dict(numerator=numerator, denominator=denominator, rate=numerator/denominator)
    metrics = dict(
        parseable_json=metric(sum(r['json_valid'] for r in results),20),
        schema_compliant=metric(sum(r['schema_valid'] for r in results),20),
        bug_detection=metric(sum(r['review']['detects_gold'] for r in bugs),10),
        clean_false_positive=metric(sum(r['review']['extra_false_positives'] > 0 for r in clean),10),
        usable_fix=metric(sum(r['review']['fix_usable'] for r in bugs),10),
        correct_bug_location=metric(sum(r['review']['line_correct'] for r in bugs),10),
        end_to_end_usable=metric(sum(r['overall_pass'] for r in results),20))
    report = dict(created_at=datetime.now(timezone.utc).isoformat(), raw_report_sha256=notes['raw_report_sha256'],
        corpus_manifest_sha256=raw['corpus_manifest_sha256'], metrics=metrics,
        total_seconds=raw['total_seconds'], peak_mlx_memory_gb=max(r['mlx_peak_memory_gb'] for r in results),
        median_generation_tokens_per_second=statistics.median(r['generation_tokens_per_second'] for r in results),
        evaluation_split='valid', test_inference_performed=False, new_training_performed=False,
        reviewer=notes['reviewer'], independent_human_review=False, rubric=rubric, results=results)
    (REPORTS / 'baseline-valid-summary.json').write_text(pretty(report) + '\n')
    cards = []
    labels = [('schema_compliant','输出格式合规'),('bug_detection','完整识别缺陷'),
        ('clean_false_positive','正常代码被误报'),('usable_fix','修复方向可实施'),('end_to_end_usable','端到端可用')]
    for key, label in labels:
        m = metrics[key]
        cards.append(f'<div class="card"><span>{label}</span><strong>{m["numerator"]}<small> / {m["denominator"]}</small></strong><span>{m["rate"]:.0%}</span></div>')
    rows, details = [], []
    for row in sorted(results, key=lambda r:r['id']):
        review = row['review']
        badge = '通过' if row['overall_pass'] else '待改善'
        kind = '有缺陷' if row['has_gold_issue'] else '已修复'
        rows.append(f'<tr><td><a href="#{row["id"]}">{row["id"]}</a></td><td>{kind}</td>'
            f'<td>{"通过" if row["schema_valid"] else "失败"}</td>'
            f'<td>{"—" if not row["has_gold_issue"] else ("是" if review["detects_gold"] else "否")}</td>'
            f'<td>{review["extra_false_positives"]}</td><td>{badge}</td></tr>')
        prompt = row['prompt_messages'][1]['content']
        context, code = prompt.split('代码：\n```',1)
        _, code = code.split('\n',1)
        code = code.rsplit('\n```',1)[0]
        numbered = '\n'.join(f'{i:2d}  {line}' for i,line in enumerate(code.splitlines(),1))
        error = f'<p class="error">格式错误：{esc(row["schema_error"])}</p>' if row['schema_error'] else ''
        details.append(f'<details class="case" id="{row["id"]}" data-pass="{str(row["overall_pass"]).lower()}" data-kind="{kind}">'
            f'<summary><b>{row["id"]}</b> · {kind} · {esc(row["scenario_family"])} <span>{badge}</span></summary>'
            f'<p>{esc(context)}</p><pre class="code">{esc(numbered)}</pre>'
            f'<div class="answers"><section><h3>模型原始回答</h3><pre>{esc(row["raw_response"])}</pre>{error}</section>'
            f'<section><h3>参考答案</h3><pre>{esc(pretty(row["reference"]))}</pre></section></div>'
            f'<p class="review"><b>逐题复核：</b>{esc(review["notes"])}</p></details>')
    content = '''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Qwen3-4B · 前端审查训练前基线</title><style>
:root{color-scheme:light;--ink:#182c3e;--muted:#526579;--line:#d8e2e8;--blue:#145a77}*{box-sizing:border-box}body{margin:0;background:#f4f7f8;color:var(--ink);font:16px/1.7 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}main{max-width:1180px;margin:auto;padding:40px 24px 80px}h1{font-size:34px;line-height:1.3;margin:8px 0 16px}h2{font-size:23px;margin-top:40px}h3{font-size:16px;margin-top:0}p{max-width:1000px}.eyebrow{font-size:13px;letter-spacing:.1em;color:var(--blue);font-weight:700}.lead{font-size:19px}.muted{color:var(--muted)}.cards{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin:28px 0}.card{background:white;border:1px solid var(--line);border-radius:12px;padding:18px}.card span{display:block;font-size:14px;color:var(--muted)}.card strong{display:block;font-size:34px;margin:8px 0}.card small{font-size:20px;font-weight:400;color:var(--muted)}.notice{border-left:4px solid #b78424;background:#fff8e9;padding:18px 22px;border-radius:5px}a{color:var(--blue);text-underline-offset:3px}.table-wrap{overflow-x:auto}table{width:100%;border-collapse:collapse;background:#fff;font-size:14px}th,td{padding:10px 14px;text-align:left;border-bottom:1px solid var(--line)}th{background:#e8eff3}.case{margin:14px 0;background:white;border:1px solid var(--line);border-radius:10px;padding:16px 20px;scroll-margin-top:20px}summary{cursor:pointer;font-size:15px}summary span{float:right;color:#84571a}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f2f5f7;border:1px solid #e0e7eb;border-radius:6px;padding:16px;font:13px/1.7 ui-monospace,SFMono-Regular,Consolas,monospace}.code{background:#152b3d;color:#dfebf2;border:0}.answers{display:grid;grid-template-columns:1fr 1fr;gap:20px}.answers section{min-width:0}.review{background:#edf4f5;padding:14px;border-radius:6px}.error{color:#a02234;font-size:14px}.controls{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin:20px 0}select,button,input{font:inherit;border:1px solid #aabac5;background:white;color:var(--ink);border-radius:6px;padding:7px 12px}button{cursor:pointer}footer{font-size:13px;color:var(--muted);margin-top:36px}.case[hidden]{display:none}@media(max-width:800px){.cards{grid-template-columns:repeat(2,1fr)}.answers{grid-template-columns:1fr}h1{font-size:27px}summary span{float:none;display:block}main{padding:24px 16px}}
</style></head><body><main><div class="eyebrow">LOCAL AI LAB / VALIDATION BASELINE / 2026-11-17</div>
<h1>先记录原模型，再判断微调有没有帮助</h1>
<p class="lead">本地 Qwen3-4B 4bit 已完成 20 条验证题。当前最突出的问题是<strong>对正确代码的误报</strong>，其次是行号和修复说明的准确性。</p>
<p class="muted">原始权重 · 无 adapter · thinking 关闭 · temperature 0 · 每题最多 512 token · 全部本地离线运行</p>
''' + '<div class="cards">' + ''.join(cards) + '</div>' + f'''
<div class="notice"><b>如何读这些数字：</b>验证集由 10 个场景的缺陷/修复版本组成。20 条不是 20 个独立场景，不能代表真实项目准确率。标签与语义评分由同一编码助手编写、复核，尚无独立人工评审。正常代码误报率越低越好。<br>“端到端可用”同时要求格式合规、语义正确、定位合理、修复可实施、没有额外误报；当前通过 2 条。</div>
<h2>数据与运行记录</h2>
<p>训练 / 验证 / 测试：<b>100 / 20 / 20 条</b>，对应 50 / 10 / 10 个独立场景。每组缺陷与修复样本各半。最长 {data_check['longest_sample_tokens']} token；140 条格式/加载/长度检查和语法审查通过，16 个纯函数场景的 32 次行为探针通过。3 组近似候选已复核，未发现跨集合相同的归一化 token 序列。</p>
<p>本轮用时约 {report['total_seconds']:.1f} 秒，生成速度中位数 {report['median_generation_tokens_per_second']:.2f} token/秒，MLX 分配峰值 {report['peak_mlx_memory_gb']:.2f} GB（不是整机占用或训练峰值）。原始 JSON 可解析 19/20；加入字段与行号范围约束后，合规 17/20。完整发现缺陷 5/10，另 1 条仅部分命中；定位正确 1/10。</p>
<p><b>测试集尚未交给模型推理；本轮没有启动训练。</b>原始回答未修复、未重新生成，文件指纹把数据、模型和评分固定到本轮运行。</p>
<h2>逐题结果</h2><div class="table-wrap"><table><thead><tr><th>样例</th><th>代码状态</th><th>格式</th><th>完整识别缺陷</th><th>额外误报项</th><th>端到端</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>
<h2>检查代码与模型回答</h2><p>展开任一条，可直接对照代码、未修改的模型输出、参考答案和评分理由。</p>
<div class="controls"><label>筛选 <select id="filter"><option value="all">全部 20 条</option><option value="failed">待改善</option><option value="clean">已修复代码</option><option value="bug">含缺陷代码</option></select></label><button id="expand">展开可见样例</button><button id="collapse">收起全部</button><span id="count" aria-live="polite">20 条</span></div>
{''.join(details)}
<h2>接下来验证什么</h2><p>用当前训练集做一次短 QLoRA 实验，再以完全相同的验证题、system 和解码参数复测。优先观察正常代码的误报能否下降，同时保住真实缺陷的识别能力；检查行号和 JSON 合规性。验证方案固定后，再对未使用的测试集做最终比较。</p>
<p>这组数据适合学习训练与评测链路。它只有 70 个合成场景；如果要用于实际审查工具，应增加真实授权代码、独立复核和更广的未见场景。</p>
<footer>记录：<a href="baseline-valid-base.json">原始运行 JSON</a> · <a href="baseline-valid-summary.json">完整评分 JSON</a> · <a href="baseline-valid-review-notes.json">逐题评语</a> · <a href="review-rubric.json">评分标准</a> · <a href="corpus-audit.json">数据审查</a><br>
标签参考：<a href="https://react.dev/reference/react-dom/components/select">React select</a> · <a href="https://developer.mozilla.org/en-US/docs/Web/API/AbortSignal">MDN AbortSignal</a><br>原始报告 SHA-256：{esc(notes['raw_report_sha256'])}</footer>
</main><script>
const cases=[...document.querySelectorAll('.case')];
document.querySelector('#filter').addEventListener('change',e=>{{let n=0;for(const c of cases){{const v=e.target.value;c.hidden=!(v==='all'||v==='failed'&&c.dataset.pass==='false'||v==='clean'&&c.dataset.kind==='已修复'||v==='bug'&&c.dataset.kind==='有缺陷');if(!c.hidden)n++;}}document.querySelector('#count').textContent=n+' 条';}});
document.querySelector('#expand').addEventListener('click',()=>cases.filter(c=>!c.hidden).forEach(c=>c.open=true));
document.querySelector('#collapse').addEventListener('click',()=>cases.forEach(c=>c.open=false));
document.querySelectorAll('table a').forEach(a=>a.addEventListener('click',()=>{{const c=document.getElementById(a.hash.slice(1));document.querySelector('#filter').value='all';document.querySelector('#filter').dispatchEvent(new Event('change'));c.open=true;}}));
</script></body></html>'''
    dest = REPORTS / 'frontend-review-baseline.html'
    dest.write_text(content)
    print(pretty(dict(metrics=metrics, report=str(dest))))


if __name__ == '__main__':
    main()
