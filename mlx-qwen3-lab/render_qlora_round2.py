"""Compare round 2 with both the original model and round 1 under the fixed rubric."""
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from render_qlora_comparison import esc, pretty, sha
from review_scoring import score_results

ROOT = Path(__file__).resolve().parent
REPORTS = ROOT/'reports'


def read(name):
    return json.loads((REPORTS/name).read_text())


def main():
    plan = read('qlora-r2-plan.json')
    base_raw = read('baseline-valid-base.json')
    base = read('baseline-valid-summary.json')
    round1 = read('qlora-r1-comparison.json')
    raw = read('adapter-valid-qlora-r2.json')
    notes = read('adapter-valid-qlora-r2-review-notes.json')
    training = read('training-qlora-r2.json')
    assert plan['baseline_sha256'] == sha(REPORTS/'baseline-valid-base.json') == base['raw_report_sha256']
    assert plan['baseline_review_sha256'] == sha(REPORTS/'baseline-valid-review-notes.json')
    assert plan['rubric_sha256'] == sha(REPORTS/'review-rubric.json')
    assert plan['round1_comparison_sha256'] == sha(REPORTS/'qlora-r1-comparison.json')
    assert plan['trainer_sha256'] == training['runner_sha256']
    assert plan['evaluator_sha256'] == raw['runner_sha256']
    assert plan['config_sha256'] == training['config_sha256'] == sha(ROOT/'configs/frontend-review-qlora-r2.yaml')
    assert notes['raw_report_sha256'] == sha(REPORTS/'adapter-valid-qlora-r2.json')
    assert raw['status'] == training['status'] == 'completed'
    assert training['updates'] == plan['updates'] == 20
    assert training['config']['learning_rate'] == plan['learning_rate'] == 0.00001
    assert training['config']['resume_adapter_file'] is None
    assert raw['adapter_files'] == training['adapter_files']
    assert raw['corpus_manifest_sha256'] == training['corpus_manifest_sha256'] == plan['corpus_manifest_sha256'] == base['corpus_manifest_sha256']
    assert raw['config'] == base_raw['config']
    assert raw['comparison_baseline']['prompts_and_generation_settings_identical']
    # Ensure this shared scorer reproduces the prior published numbers without changing judgments.
    base_results, base_metrics = score_results(base_raw, read('baseline-valid-review-notes.json'))
    assert base_metrics == base['metrics']
    r1_results, r1_metrics = score_results(read('adapter-valid-qlora-r1.json'), read('adapter-valid-qlora-r1-review-notes.json'))
    assert r1_metrics == round1['metrics_after']
    results, metrics = score_results(raw, notes)
    originals = {r['id']:r for r in base_results}
    first_round = {r['id']:r for r in r1_results}
    for row in results:
        original = originals[row['id']]
        assert row['prompt_messages'] == original['prompt_messages']
        assert row['reference'] == original['reference']
    criteria = plan['success_criteria']
    bug_count = metrics['bug_detection']['numerator']
    fp_count = metrics['clean_false_positive']['numerator']
    detection_pass = bug_count >= criteria['bug_detection_minimum']
    false_positive_pass = fp_count <= criteria['clean_false_positive_maximum']
    success = detection_pass and false_positive_pass
    empty_count = sum(r['parsed_response'] == {'issues':[]} for r in results)
    all_empty = empty_count == 20
    if success:
        title = '达到本轮门槛：保住缺陷识别，减少误报'
    elif all_empty:
        title = '仍然全部回答“无问题”：第二轮未达标'
    elif not detection_pass:
        title = '缺陷识别低于原模型：第二轮未达标'
    else:
        title = '缺陷识别达标，但误报尚未减少'
    previous_detected = {r['id'] for r in base_results if r['has_gold_issue'] and r['review']['detects_gold']}
    detected = {r['id'] for r in results if r['has_gold_issue'] and r['review']['detects_gold']}
    summary = dict(created_at=datetime.now(timezone.utc).isoformat(), run=plan['run'], title=title,
        success=success, success_criteria=criteria, bug_detection_gate_passed=detection_pass,
        false_positive_gate_passed=false_positive_pass, plan_sha256=sha(REPORTS/'qlora-r2-plan.json'),
        baseline_raw_sha256=plan['baseline_sha256'], round1_comparison_sha256=plan['round1_comparison_sha256'],
        raw_report_sha256=notes['raw_report_sha256'], rubric_sha256=plan['rubric_sha256'],
        metrics_base=base_metrics, metrics_round1=r1_metrics, metrics_round2=metrics,
        empty_outputs=empty_count, all_outputs_empty=all_empty,
        buggy_empty_outputs=sum(r['has_gold_issue'] and r['parsed_response']=={'issues':[]} for r in results),
        retained_baseline_detections=sorted(previous_detected & detected),
        lost_baseline_detections=sorted(previous_detected - detected), newly_detected=sorted(detected - previous_detected),
        training=training, final_step=20, test_inference_performed=False,
        independent_human_review=False, within_run_hyperparameter_search=False,
        limitations=['20条验证题来自10个合成场景的缺陷/修复对，不代表实际项目准确率。',
            '第二轮参数根据第一轮验证结果选择；验证集已用于开发，不能当作未见测试集。',
            '同一编码助手编写标签并逐题复核评分，尚无独立人工评审。',
            '本轮同时改了学习率和步数，不能单独归因于其中一个因素。'], results=results)
    (REPORTS/'qlora-r2-comparison.json').write_text(pretty(summary)+'\n')
    labels = [('schema_compliant','输出格式合规'),('bug_detection','完整识别缺陷'),
        ('clean_false_positive','正确代码被误报'),('usable_fix','修复方向可实施'),
        ('correct_bug_location','缺陷定位合理'),('end_to_end_usable','端到端可用')]
    metric_rows = []
    for key,label in labels:
        cells = ''.join(f'<td>{m[key]["numerator"]}/{m[key]["denominator"]}</td>' for m in [base_metrics,r1_metrics,metrics])
        metric_rows.append(f'<tr><th>{label}</th>{cells}</tr>')
    case_rows, details = [], []
    for row in sorted(results,key=lambda r:r['id']):
        before = originals[row['id']]
        r1 = first_round[row['id']]
        kind = '含缺陷' if row['has_gold_issue'] else '已修复'
        change = '改善' if row['overall_pass'] and not before['overall_pass'] else '退步' if before['overall_pass'] and not row['overall_pass'] else '持平'
        states = ''.join(f'<td>{"通过" if r["overall_pass"] else "未通过"}</td>' for r in [before,r1,row])
        case_rows.append(f'<tr><td><a href="#{row["id"]}">{row["id"]}</a></td><td>{kind}</td>{states}</tr>')
        context, code = row['prompt_messages'][1]['content'].split('代码：\n```',1)
        _,code = code.split('\n',1)
        code = code.rsplit('\n```',1)[0]
        numbered = '\n'.join(f'{i:2d}  {line}' for i,line in enumerate(code.splitlines(),1))
        error = f'<p class="bad">格式错误：{esc(row["schema_error"])}</p>' if row['schema_error'] else ''
        details.append(f'<details class="case" id="{row["id"]}" data-kind="{kind}" data-change="{change}">'
            f'<summary><b>{row["id"]}</b> · {kind} · {esc(row["scenario_family"])} <span>相对原模型：{change}</span></summary>'
            f'<p>{esc(context)}</p><pre class="code">{esc(numbered)}</pre><div class="pair">'
            f'<section><h3>原始模型</h3><pre>{esc(before["raw_response"])}</pre><p class="review">{esc(before["review"]["notes"])}</p></section>'
            f'<section><h3>第二轮 · 第 20 步 adapter</h3><pre>{esc(row["raw_response"])}</pre>{error}<p class="review">{esc(row["review"]["notes"])}</p></section></div>'
            f'<details><summary>第一轮原始回答</summary><pre>{esc(r1["raw_response"])}</pre></details>'
            f'<h3>固定参考答案</h3><pre>{esc(pretty(row["reference"]))}</pre></details>')
    # Keep the established report layout; the data and narrative below are round-specific.
    css = re.search(r'<style>(.*?)</style>',(REPORTS/'frontend-review-qlora-r1.html').read_text(),re.S).group(1)
    judgment = ('两个事先固定的条件均满足；这是开发验证集上的结果，还需要后续独立测试。' if success else
        '20题全部输出空 issues，10个真实缺陷全部漏报；误报归零不能视为审查能力提升。' if all_empty else
        f'本轮完整识别缺陷 {bug_count}/10，正确代码误报 {fp_count}/10，未同时满足两个条件。')
    content = f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Qwen3 · 第二轮 QLoRA 对比</title><style>{css}</style></head><body><main>
<div class="eyebrow">LOCAL AI LAB / QLORA ROUND 2 / 2026-11-17</div><h1>{esc(title)}</h1>
<p class="lead">学习率 <b>1e-4 → 1e-5</b>，训练步数 <b>100 → 20</b>，从原始 Qwen3-4B 4bit 重新初始化 adapter；相同验证题、提示词、解码参数与评分标准。</p>
<div class="cards"><div class="metric"><span>缺陷识别门槛：至少 5/10</span><strong>{bug_count}/10</strong><span>{'达标' if detection_pass else '未达标'}</span></div>
<div class="metric"><span>误报门槛：最多 8/10</span><strong>{fp_count}/10</strong><span>{'达标' if false_positive_pass else '未达标'}；原模型为 9/10，越低越好</span></div>
<div class="metric"><span>两个条件同时满足</span><strong>{'是' if success else '否'}</strong><span>事先固定门槛，评测后不改标准</span></div></div>
<div class="notice"><b>{esc(judgment)}</b><br>20题来自10个合成场景的缺陷/修复对，评分由编码助手复核。此验证集已用于选择第二轮参数，不是独立最终测试，不能据此推断真实项目总体准确率。</div>
<h2>原模型与两轮训练</h2><div class="table-wrap"><table><thead><tr><th>指标</th><th>原始模型</th><th>第一轮 · 1e-4 / 100步</th><th>第二轮 · 1e-5 / 20步</th></tr></thead><tbody>{''.join(metric_rows)}</tbody></table></div>
<p>第二轮有 {empty_count}/20 条回答输出空 issues，其中 {summary['buggy_empty_outputs']}/10 份缺陷代码被判断为无问题。{'固定返回空列表也会在这组正负平衡的数据上得到10/20，因此不能单独依赖总分。' if all_empty else '这项计数用于检查模型是否过度偏向不报告问题。'}</p>
<p>原模型完整识别的5个缺陷中，第二轮保留 {len(summary['retained_baseline_detections'])} 个，丢失 {len(summary['lost_baseline_detections'])} 个，另外新识别 {len(summary['newly_detected'])} 个。门槛按完整识别数量判定，具体样例仍需逐题检查。</p>
<h2>这次具体运行</h2><p>从原始基座新建 LoRA，未沿用第一轮 adapter。batch=1、最后4层、rank=8、scale=16、Adam、seed=42、最大序列512、开启梯度检查点与 prompt masking。20次更新约为100条训练数据的0.2轮，没有遍历完整训练集。只评测最终第20步，不挑选中间 checkpoint。</p>
<p>训练程序耗时 {training['total_seconds']:.1f} 秒，MLX 分配峰值 {training['peak_mlx_memory_gb']:.2f} GB，验证 loss 从 {training['initial_validation_loss']:.3f} 变为 {training['final_validation_loss']:.3f}。adapter 约 {training['adapter_size_bytes']/1e6:.2f} MB，所有张量数值有限；原始模型和数据指纹未变。</p>
<p>推理仍为 thinking 关闭、temperature=0、seed=42、最多512 token，每题独立。20条原始回答逐条保存，未修复输出或重试失败题；原模型、第一轮与本轮的评分使用同一标准，自动核对旧分数能被原样重算。测试集未交给模型。</p>
<h2>逐题可用性</h2><p>“通过”要求格式、语义、定位、修复都满足原标准；含缺陷题必须指出正确缺陷，正常题必须正确返回空 issues。</p><div class="table-wrap"><table><thead><tr><th>样例</th><th>代码状态</th><th>原模型</th><th>第一轮</th><th>第二轮</th></tr></thead><tbody>{''.join(case_rows)}</tbody></table></div>
<h2>对照原始回答</h2><div class="controls"><label for="case-filter">筛选</label><select id="case-filter"><option value="all">全部样例</option><option value="clean">已修复代码</option><option value="bug">含缺陷代码</option><option value="improved">相对原模型改善</option><option value="regressed">相对原模型退步</option></select><button id="expand">展开可见样例</button><button id="collapse">收起全部</button><span id="count" aria-live="polite">20 条</span></div>{''.join(details)}
<h2>结论与后续</h2><p>{esc(judgment)} 本轮同时改变学习率与更新次数，只能评价这组设置，不能把结果单独归因于其中一个参数。</p>
<p>{'下一步应先冻结候选与评测标准，再用保留的测试集确认表现；本轮尚未进行最终测试。' if success else '当前没有达到用户要求的候选。下一步更适合先诊断空答案倾向、训练目标和数据表达，再设计新的实验，而不是把误报减少当作成功。本轮没有自动追加第三轮训练。'}</p>
<footer><a href="frontend-review-baseline.html">原模型基线</a> · <a href="frontend-review-qlora-r1.html">第一轮</a> · <a href="qlora-r2-comparison.json">第二轮完整对比 JSON</a> · <a href="adapter-valid-qlora-r2.json">原始回答</a> · <a href="adapter-valid-qlora-r2-review-notes.json">逐题评分</a> · <a href="training-qlora-r2.json">训练记录</a> · <a href="qlora-r2-plan.json">预定门槛与参数指纹</a><br>adapter：adapters/frontend-review-qlora-r2/adapters.safetensors</footer>
</main><script>
const cases=[...document.querySelectorAll('.case')], filter=document.querySelector('#case-filter');
filter.addEventListener('change',()=>{{let n=0;for(const c of cases){{const v=filter.value;c.hidden=!(v==='all'||v==='clean'&&c.dataset.kind==='已修复'||v==='bug'&&c.dataset.kind==='含缺陷'||v==='improved'&&c.dataset.change==='改善'||v==='regressed'&&c.dataset.change==='退步');if(!c.hidden)n++;}}document.querySelector('#count').textContent=n+' 条';}});
document.querySelector('#expand').addEventListener('click',()=>cases.filter(c=>!c.hidden).forEach(c=>c.open=true));document.querySelector('#collapse').addEventListener('click',()=>cases.forEach(c=>c.open=false));
document.querySelectorAll('table a').forEach(a=>a.addEventListener('click',()=>{{filter.value='all';filter.dispatchEvent(new Event('change'));document.getElementById(a.hash.slice(1)).open=true;}}));
</script></body></html>'''
    dest = REPORTS/'frontend-review-qlora-r2.html'
    dest.write_text(content)
    print(pretty({k:v for k,v in summary.items() if k not in ['results','training']}))
    print(dest)


if __name__ == '__main__':
    main()
