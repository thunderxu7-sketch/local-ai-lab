"""Render the first QLoRA comparison from immutable answers and explicit reviews."""
import hashlib
import html
import json
from datetime import datetime, timezone
from pathlib import Path
from validate_review_data import parse_json

ROOT = Path(__file__).resolve().parent
REPORTS = ROOT / 'reports'


def read(name):
    return json.loads((REPORTS / name).read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def esc(value):
    return html.escape(str(value))


def pretty(value):
    return json.dumps(value, ensure_ascii=False, indent=2)


def main():
    plan = read('qlora-r1-plan.json')
    base = read('baseline-valid-summary.json')
    raw = read('adapter-valid-qlora-r1.json')
    notes = read('adapter-valid-qlora-r1-review-notes.json')
    training = read('training-qlora-r1.json')
    assert plan['baseline_sha256'] == base['raw_report_sha256'] == sha(REPORTS/'baseline-valid-base.json')
    assert plan['rubric_sha256'] == sha(REPORTS/'review-rubric.json')
    assert plan['baseline_review_sha256'] == sha(REPORTS/'baseline-valid-review-notes.json')
    assert notes['raw_report_sha256'] == sha(REPORTS/'adapter-valid-qlora-r1.json')
    assert raw['status'] == training['status'] == 'completed'
    assert raw['adapter_files'] == training['adapter_files']
    assert raw['corpus_manifest_sha256'] == base['corpus_manifest_sha256'] == training['corpus_manifest_sha256']
    assert raw['comparison_baseline']['prompts_and_generation_settings_identical']
    originals = {r['id']:r for r in base['results']}
    reviews = {r['id']:r for r in notes['results']}
    assert len(raw['results']) == len(reviews) == len(notes['results']) == 20
    assert set(reviews) == set(originals) == {r['id'] for r in raw['results']}
    results = []
    for row in raw['results']:
        before = originals[row['id']]
        assert row['prompt_messages'] == before['prompt_messages'] and row['reference'] == before['reference']
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
        change = '改善' if passed and not before['overall_pass'] else '退步' if before['overall_pass'] and not passed else '持平'
        results.append(dict(row, review=review, json_valid=json_valid, has_gold_issue=bug,
            overall_pass=bool(passed), change=change, before=before))
    bugs = [r for r in results if r['has_gold_issue']]
    clean = [r for r in results if not r['has_gold_issue']]
    assert len(bugs) == len(clean) == 10
    def metric(n, d):
        return dict(numerator=n, denominator=d, rate=n/d)
    metrics = dict(
        parseable_json=metric(sum(r['json_valid'] for r in results),20),
        schema_compliant=metric(sum(r['schema_valid'] for r in results),20),
        bug_detection=metric(sum(r['review']['detects_gold'] for r in bugs),10),
        clean_false_positive=metric(sum(r['review']['extra_false_positives'] > 0 for r in clean),10),
        usable_fix=metric(sum(r['review']['fix_usable'] for r in bugs),10),
        correct_bug_location=metric(sum(r['review']['line_correct'] for r in bugs),10),
        end_to_end_usable=metric(sum(r['overall_pass'] for r in results),20))
    before_fp = base['metrics']['clean_false_positive']['numerator']
    after_fp = metrics['clean_false_positive']['numerator']
    before_detection = base['metrics']['bug_detection']['numerator']
    after_detection = metrics['bug_detection']['numerator']
    all_empty = all(r['parsed_response'] == {'issues':[]} for r in results)
    if all_empty:
        title = '全部回答“无问题”：本轮出现退化'
    elif after_fp < before_fp:
        title = '误报减少，缺陷识别未下降' if after_detection >= before_detection else '误报减少，但缺陷识别也下降了'
    else:
        title = '这一轮还没有降低误报'
    summary = dict(created_at=datetime.now(timezone.utc).isoformat(), title=title,
        run='frontend-review-qlora-r1', raw_report_sha256=notes['raw_report_sha256'],
        rubric_sha256=plan['rubric_sha256'], baseline_raw_sha256=plan['baseline_sha256'],
        metrics_before=base['metrics'], metrics_after=metrics,
        false_positive_reduction=before_fp-after_fp, bug_detection_change=after_detection-before_detection,
        empty_outputs_before=sum(r['parsed_response'] == {'issues':[]} for r in base['results']),
        empty_outputs_after=sum(r['parsed_response'] == {'issues':[]} for r in results),
        buggy_empty_outputs_after=sum(r['parsed_response'] == {'issues':[]} for r in bugs),
        improved_ids=[r['id'] for r in results if r['change']=='改善'],
        regressed_ids=[r['id'] for r in results if r['change']=='退步'],
        training=training, raw_adapter=str(raw['adapter']), final_step=100,
        test_inference_performed=False, human_review_independent=False, all_outputs_empty=all_empty,
        effective_improvement=False if all_empty else None,
        limitations=['仅10个成对合成验证场景；不能推断真实代码总体准确率。',
            '标签和语义评分均由编码助手复核，没有独立人工评审。',
            '同一验证集参与训练期间 loss 观察；这是开发集对比，测试集尚未使用。',
            '一次预定100步训练，仅评测最终adapter，没有挑选中间checkpoint。'], results=results)
    (REPORTS/'qlora-r1-comparison.json').write_text(pretty(summary)+'\n')
    labels = [('schema_compliant','输出格式合规','高'),('bug_detection','完整识别缺陷','高'),
        ('clean_false_positive','正常代码被误报','低'),('usable_fix','修复方向可实施','高'),
        ('correct_bug_location','缺陷定位合理','高'),('end_to_end_usable','端到端可用','高')]
    metric_rows = []
    for key,label,direction in labels:
        a,b = base['metrics'][key],metrics[key]
        delta = b['numerator']-a['numerator']
        better = delta > 0 if direction=='高' else delta < 0
        color = 'good' if better else 'bad' if delta else 'muted'
        metric_rows.append(f'<tr><th>{label}<small>越{direction}越好</small></th><td>{a["numerator"]}/{a["denominator"]}</td>'
            f'<td><b>{b["numerator"]}/{b["denominator"]}</b></td><td class="{color}">{delta:+d} 条</td></tr>')
    case_rows, cards = [], []
    for row in sorted(results, key=lambda r:r['id']):
        before = row['before']
        kind = '含缺陷' if row['has_gold_issue'] else '已修复'
        before_status = '通过' if before['overall_pass'] else '未通过'
        after_status = '通过' if row['overall_pass'] else '未通过'
        case_rows.append(f'<tr><td><a href="#{row["id"]}">{row["id"]}</a></td><td>{kind}</td>'
            f'<td>{before_status}</td><td>{after_status}</td><td>{row["change"]}</td></tr>')
        prompt = row['prompt_messages'][1]['content']
        context,code = prompt.split('代码：\n```',1)
        _,code = code.split('\n',1)
        code = code.rsplit('\n```',1)[0]
        numbered = '\n'.join(f'{i:2d}  {line}' for i,line in enumerate(code.splitlines(),1))
        error = f'<p class="bad">格式错误：{esc(row["schema_error"])}</p>' if row['schema_error'] else ''
        cards.append(f'<details class="case" id="{row["id"]}" data-kind="{kind}" data-change="{row["change"]}">'
            f'<summary><b>{row["id"]}</b> · {kind} · {esc(row["scenario_family"])} <span>{before_status} → {after_status} / {row["change"]}</span></summary>'
            f'<p>{esc(context)}</p><pre class="code">{esc(numbered)}</pre><div class="pair">'
            f'<section><h3>训练前 · 原始模型</h3><pre>{esc(before["raw_response"])}</pre><p class="review">{esc(before["review"]["notes"])}</p></section>'
            f'<section><h3>训练后 · 第 100 步 adapter</h3><pre>{esc(row["raw_response"])}</pre>{error}<p class="review">{esc(row["review"]["notes"])}</p></section></div>'
            f'<h3>固定参考答案</h3><pre>{esc(pretty(row["reference"]))}</pre></details>')
    content = '''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Qwen3 · 第一轮 QLoRA 前后对比</title><style>
:root{color-scheme:light;--ink:#1b3041;--muted:#586c7a;--line:#d6e1e7}*{box-sizing:border-box}body{margin:0;background:#f3f6f8;color:var(--ink);font:16px/1.75 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}main{max-width:1180px;padding:40px 24px 80px;margin:auto}h1{font-size:34px;line-height:1.35;margin:12px 0 20px}h2{font-size:23px;margin-top:38px}h3{font-size:16px;margin-top:0}.eyebrow{font-size:13px;color:#245b75;font-weight:700;letter-spacing:.1em}.lead{font-size:19px}.muted,small{color:var(--muted)}.good{color:#116b54}.bad{color:#a3293d}.cards{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin:28px 0}.metric{background:white;border:1px solid var(--line);border-radius:12px;padding:20px}.metric strong{font-size:35px;display:block;margin:8px 0}.metric span{color:var(--muted);font-size:14px}.notice{background:#fff7e7;border-left:4px solid #b68a37;padding:18px 22px;border-radius:5px}a{color:#145c7c;text-underline-offset:3px}.table-wrap{overflow-x:auto}table{border-collapse:collapse;width:100%;background:#fff}td,th{padding:12px 16px;text-align:left;border-bottom:1px solid var(--line);font-size:15px}thead{background:#e7eff3}th small{display:block;font-size:12px;font-weight:400}.controls{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin:20px 0}select,button{font:inherit;padding:6px 12px;border:1px solid #9fb4c0;border-radius:6px;background:white;color:var(--ink)}button{cursor:pointer}.case{background:white;padding:16px 20px;margin:14px 0;border:1px solid var(--line);border-radius:10px;scroll-margin-top:20px}summary{cursor:pointer;font-size:15px}summary span{float:right;font-size:13px;color:#466577}.pair{display:grid;grid-template-columns:1fr 1fr;gap:20px}.pair section{min-width:0}pre{background:#edf2f5;border:1px solid #dbe4e9;white-space:pre-wrap;overflow-wrap:anywhere;padding:16px;border-radius:6px;font:13px/1.7 ui-monospace,SFMono-Regular,Consolas,monospace}.code{background:#172d3f;color:#e4edf5;border:0}.review{background:#eaf3f1;padding:14px;border-radius:6px;font-size:14px}.case[hidden]{display:none}footer{font-size:13px;color:var(--muted);margin-top:36px}@media(max-width:800px){main{padding:24px 16px}.cards,.pair{grid-template-columns:1fr}h1{font-size:27px}summary span{float:none;display:block}}
</style></head><body><main><div class="eyebrow">LOCAL AI LAB / QLORA ROUND 1 / 2026-11-17</div>'''
    content += f'''<h1>{esc(title)}</h1><p class="lead">在完全相同的 20 条验证题上，正确代码的误报从 <b>{before_fp}/10</b> 变为 <b>{after_fp}/10</b>；完整识别缺陷从 <b>{before_detection}/10</b> 变为 <b>{after_detection}/10</b>。</p>
<p class="muted">本地 Qwen3-4B 4bit · 100 次更新 / 1 轮数据 · batch 1 · 最后 4 层 · LoRA rank 8 · 学习率 0.0001</p>
<div class="cards"><div class="metric"><span>正确代码被误报</span><strong>{before_fp} → {after_fp}<small> / 10</small></strong><span>越低越好；每条至少一项误报即计入</span></div>
<div class="metric"><span>完整识别真实缺陷</span><strong>{before_detection} → {after_detection}<small> / 10</small></strong><span>同时看识别，避免只学会不报错</span></div>
<div class="metric"><span>端到端可用回答</span><strong>{base['metrics']['end_to_end_usable']['numerator']} → {metrics['end_to_end_usable']['numerator']}<small> / 20</small></strong><span>格式、语义、定位、修复均符合要求</span></div></div>
<div class="notice"><b>本轮判定：{'没有取得有效改善。20 条原始回答全部为空 issues，10 个真实缺陷全部漏报。误报变少来自一律不报错；当前 adapter 不适合用于实际代码审查。' if all_empty else esc(title)} </b><br>这只是 10 个场景的缺陷/修复成对验证题。验证集用于开发过程中的 loss 观察，结果不代表真实项目总体准确率；测试集仍未使用。标签和语义评分由编码助手逐题复核，没有独立人工评审。</div>
<h2>同一标准下的前后表现</h2><div class="table-wrap"><table><thead><tr><th>指标</th><th>训练前</th><th>训练后</th><th>变化</th></tr></thead><tbody>{''.join(metric_rows)}</tbody></table></div>
<p>空 issues 回答：训练前 {summary['empty_outputs_before']}/20，训练后 {summary['empty_outputs_after']}/20；其中训练后有 {summary['buggy_empty_outputs_after']}/10 份缺陷代码被回答“没有问题”。这是观察是否过度保守的辅助指标，不单独作为成功标准。</p>
<p>{'这组验证题正负各半，固定返回空列表也能得到 10/20 的可用回答。因此总分从 2/20 到 10/20，并不能证明模型学会了审查。' if all_empty else ''}</p>
<h2>这轮训练实际做了什么</h2>
<p>冻结原始 4bit 权重，更新 {training['trainable_parameters']:,} 个 LoRA 参数。100 条训练样本各使用一次，最终第 100 步 adapter 单独保存，未挑选中间 checkpoint、未调整提示词、未重跑失败题。训练期间与最终 loss 计算只用验证集，测试数据没有进入训练或模型评测。</p>
<p>验证 loss 从 <b>{training['initial_validation_loss']:.3f}</b> 降至 <b>{training['final_validation_loss']:.3f}</b>，本轮训练程序耗时约 {training['total_seconds']/60:.1f} 分钟，MLX 分配峰值 {training['peak_mlx_memory_gb']:.2f} GB；adapter 约 {training['adapter_size_bytes']/1e6:.2f} MB。loss 是对参考答案的预测损失，任务效果以上面的实际生成评分为准。</p>
<p>前后推理均使用同一 system/user、相同顺序和模型版本，关闭 thinking、temperature=0、seed=42、最多生成 512 token；每题独立请求。原始模型文件与数据 SHA-256 校验未变，输出保留原文，没有修复 JSON。</p>
<h2>逐题可用性变化</h2><p>“通过”要求该题满足全部评分条件。改善 {len(summary['improved_ids'])} 条，退步 {len(summary['regressed_ids'])} 条，其余 {20-len(summary['improved_ids'])-len(summary['regressed_ids'])} 条持平；持平不表示两次回答文字相同。</p>
<div class="table-wrap"><table><thead><tr><th>样例</th><th>代码状态</th><th>训练前</th><th>训练后</th><th>变化</th></tr></thead><tbody>{''.join(case_rows)}</tbody></table></div>
<h2>展开看代码和两次原始回答</h2><div class="controls"><label for="case-filter">筛选</label><select id="case-filter"><option value="all">全部样例</option><option value="clean">已修复代码</option><option value="bug">含缺陷代码</option><option value="improved">改善</option><option value="regressed">退步</option></select><button id="expand">展开可见样例</button><button id="collapse">收起全部</button><span id="count" aria-live="polite">20 条</span></div>{''.join(cards)}
<h2>诊断与下一步</h2><p>已核对训练数据仍为 50 条缺陷 / 50 条正常样本，mask_prompt 开启，最长样例 327 token 未超过 512 上限，adapter 的 56 个张量均为有限值，28 个 lora_b 均有非零更新。评测输入与训练前一致，20 条空列表均来自模型的原始生成。现有检查支持这是本轮训练后的行为退化；具体诱因尚不能只凭一次运行确定。</p>
<p>本轮 adapter 与记录保留用于分析。下一轮可以先降低学习率、缩短更新步数，并提前设定“真实缺陷识别不低于原模型”的选择条件，验证能否避免一律输出无问题；这只是待验证方案，本轮没有自动启动第二次训练。方案确定后，再对未使用的测试集比较原模型与最终 adapter。</p>
<footer><a href="frontend-review-baseline.html">训练前完整基线</a> · <a href="qlora-r1-comparison.json">完整对比 JSON</a> · <a href="adapter-valid-qlora-r1.json">训练后原始回答</a> · <a href="adapter-valid-qlora-r1-review-notes.json">训练后逐题评语</a> · <a href="training-qlora-r1.json">训练过程记录</a> · <a href="review-rubric.json">固定评分标准</a><br>本地文件：adapters/frontend-review-qlora-r1/adapters.safetensors</footer>
</main><script>
const cases=[...document.querySelectorAll('.case')], filter=document.querySelector('#case-filter');
filter.addEventListener('change',()=>{{let n=0;for(const c of cases){{const v=filter.value;c.hidden=!(v==='all'||v==='clean'&&c.dataset.kind==='已修复'||v==='bug'&&c.dataset.kind==='含缺陷'||v==='improved'&&c.dataset.change==='改善'||v==='regressed'&&c.dataset.change==='退步');if(!c.hidden)n++;}}document.querySelector('#count').textContent=n+' 条';}});
document.querySelector('#expand').addEventListener('click',()=>cases.filter(c=>!c.hidden).forEach(c=>c.open=true));document.querySelector('#collapse').addEventListener('click',()=>cases.forEach(c=>c.open=false));
document.querySelectorAll('table a').forEach(a=>a.addEventListener('click',()=>{{filter.value='all';filter.dispatchEvent(new Event('change'));document.getElementById(a.hash.slice(1)).open=true;}}));
</script></body></html>'''
    dest = REPORTS/'frontend-review-qlora-r1.html'
    dest.write_text(content)
    print(pretty({k:v for k,v in summary.items() if k not in ['results','training']}))
    print(dest)


if __name__ == '__main__':
    main()
