"use client";

import { useCallback, useEffect, useState } from "react";
import type { EvaluationReport, EvaluationResult } from "@/lib/evaluation";
import { CitedAnswer } from "./knowledge";
import { TaskSources, ToolTraceCard } from "./tool-trace";

function label(result: EvaluationResult) {
  return result.error ? "运行错误" : result.review ? result.review.passed ? "复核通过" : "需改进" : "待复核";
}

export function EvaluationView({ onAsk, busy }: { onAsk: (result: EvaluationResult, report: EvaluationReport) => void; busy: boolean }) {
  const [reports, setReports] = useState<EvaluationReport[]>([]);
  const [selected, setSelected] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const refresh = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const response = await fetch("/api/evaluations", { cache: "no-store" });
      const data = await response.json();
      if (!response.ok) throw Error(data.error);
      setReports(data.reports); setError((data.warnings || []).join("；"));
      setSelected((id) => data.reports.some((r: EvaluationReport) => r.id === id) ? id : data.reports[0]?.id || "");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "读取报告失败。"); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void refresh(); }, [refresh]);
  const report = reports.find((r) => r.id === selected);
  const results = report?.results || [];
  const reviewed = results.filter((r) => r.review);
  const successes = reviewed.filter((r) => r.review?.passed && !r.error);
  const grounded = results.filter((r) => r.sources.length);
  const hits = grounded.filter((r) => r.checks.find((c) => c.name === "检索依据")?.passed);
  const completed = results.filter((r) => r.completed);
  const seconds = completed.length ? completed.reduce((total, r) => total + r.durationMs, 0) / completed.length / 1000 : null;

  function download() {
    if (!report) return;
    const url = URL.createObjectURL(new Blob([JSON.stringify(report, null, 2)], { type: "application/json" }));
    const link = document.createElement("a"); link.href = url; link.download = `qwen-project-eval-${report.id}.json`; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  return <section className="content-page evaluation-page">
    <div className="page-title"><div className="eyebrow">ASK · CHECK · IMPROVE</div><h1>用真实问题，检验回答。</h1><p>对照项目原文，分别检查检索、工具和最终答案。</p></div>
    <div className="eval-intro"><strong>固定 10 题 · 四类任务</strong><p>直接问答、换一种说法、检索后计算、资料缺失。参考答案和检查规则只供评测使用，不发送给回答模型。</p></div>
    <div className="toolbar eval-toolbar"><label>评测轮次 <select aria-label="选择评测轮次" value={selected} onChange={(e) => setSelected(e.target.value)} disabled={!reports.length}>{reports.map((r) => <option key={r.id} value={r.id}>{r.label} · {new Date(r.createdAt).toLocaleString("zh-CN")}</option>)}</select></label><div><button className="secondary-button" disabled={loading} onClick={refresh}>{loading ? "读取中…" : "刷新报告"}</button><button className="secondary-button" disabled={!report} onClick={download}>导出 JSON</button></div></div>
    {error && <p className="text-error" role="alert">{error}</p>}
    {!report && !loading && <div className="empty-state">还没有报告。在项目目录运行 <code>npm run eval:project</code>，然后刷新此页。</div>}
    {report && <>
      <div className="eval-stats">
        <div><span>内容复核通过</span><strong>{successes.length}<small> / {report.total}</small></strong><p>已复核 {reviewed.length} 题，待复核 {results.length - reviewed.length} 题</p></div>
        <div><span>预期依据命中</span><strong>{hits.length}<small> / {grounded.length}</small></strong><p>仅统计已运行且有预期依据的题</p></div>
        <div><span>平均请求耗时</span><strong>{seconds === null ? "—" : seconds.toFixed(1)}<small> 秒</small></strong><p>已完成题目，含检索和工具时间</p></div>
      </div>
      <p className="eval-meta">{report.model} · 思考{report.think ? "开启" : "关闭"} · 已运行 {results.length}/{report.total} · {report.status === "running" ? "评测进行中，请刷新查看进度" : report.status === "interrupted" ? "本轮已停止" : "本轮运行结束"}</p>
      {report.notes?.map((note, i) => <p className="eval-note" key={i}>{note}</p>)}
      <div className="run-list">{results.map((result) => <details key={`${report.id}-${result.id}`} className="run-card eval-case">
        <summary><span className={`eval-verdict ${result.error || result.review?.passed === false ? "fail" : result.review?.passed ? "pass" : "pending"}`}>{label(result)}</span><strong>{result.id} · {result.prompt}</strong><span>{(result.durationMs / 1000).toFixed(1)}s</span><span className="run-chevron">⌄</span></summary>
        <div className="run-body">
          <div className="eval-case-top"><span>{result.category} · {result.mode === "agent" ? "Agent 模式" : "知识库问答"} · {result.tokens} token</span><button disabled={busy} className="secondary-button" onClick={() => onAsk(result, report)}>用本轮设置再问一次 ↗</button></div>
          <div className="eval-expected"><strong>预期要点</strong><p>{result.expected}</p></div>
          {result.toolsUsed.map((tool) => <ToolTraceCard key={tool.id} trace={tool} />)}
          <strong className="eval-answer-label">实际回答</strong><div className="message-content"><CitedAnswer text={result.answer || "未生成回答"} trace={result.retrieval} prefix={`eval-${report.id}-${result.id}`} /></div>
          {result.retrieval && <TaskSources trace={result.retrieval} prefix={`eval-${report.id}-${result.id}`} />}
          {result.error && <p className="text-error">{result.error}</p>}
          <div className="eval-checks">{result.checks.map((check) => <div key={check.name}><span className={check.passed === false ? "text-error" : ""}>{check.passed === null ? "—" : check.passed ? "✓" : "!"} {check.name}</span><small>{check.detail}</small></div>)}</div>
          <div className="eval-review"><strong>内容复核{result.review ? ` · ${result.review.stage}` : " · 待完成"}</strong><p>{result.review?.note || "规则只检查关键线索和执行记录。还需对照返回原文，检查事实、引用支持关系和是否编造。"}</p></div>
        </div>
      </details>)}</div>
      <details className="eval-repro"><summary>查看复现信息</summary><p>题集、知识库和实现均保留指纹；切换轮次时应先核对变化，再比较结果。重跑使用 <code>npm run eval:project -- --label 新一轮</code>，报告保存在本机。</p><dl><dt>题集</dt><dd>{report.caseSetHash}</dd><dt>知识库</dt><dd>{report.knowledgeHash}</dd><dt>实现</dt><dd>{report.codeHash}</dd><dt>聊天模型</dt><dd>{report.modelDigest || "未记录"}</dd><dt>向量模型</dt><dd>{report.embeddingDigest || "未记录"}</dd></dl><p>本轮资料：{report.knowledgeFiles.map((f) => f.file).join("、")}</p><p>System Prompt：{report.system}</p></details>
    </>}
  </section>;
}
