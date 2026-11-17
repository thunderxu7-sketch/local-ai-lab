import type { ToolTrace } from "@/lib/chat";
import type { RetrievalTrace } from "@/lib/knowledge-types";
import { RetrievalCard } from "./knowledge";

export function TaskSources({ trace, prefix }: { trace: RetrievalTrace; prefix: string }) {
  return <details className="agent-sources"><summary>查看本轮引用 · {trace.sources.length} 个片段 · {trace.queries?.length ?? 1} 次检索</summary><RetrievalCard trace={trace} prefix={prefix} /></details>;
}

export function ToolTraceCard({ trace }: { trace: ToolTrace }) {
  const search = trace.name === "search_knowledge";
  const label = search ? "检索本地知识库" : trace.name === "calculate" ? "调用本地计算器" : trace.name;
  return <section className={`tool-trace ${trace.status}`} aria-label="工具调用记录">
    <div className="tool-trace-heading">
      <span className="tool-symbol">{trace.step || (search ? "⌕" : "∑")}</span>
      <strong>{label}</strong>
      <span className={`tool-status ${trace.status}`}>{trace.status === "running" ? "执行中" : trace.status === "complete" ? "已完成" : trace.status === "cancelled" ? "已停止" : "出错"}</span>
    </div>
    <div className="tool-trace-args">{search ? `查询：${String(trace.args.query || "")}` : JSON.stringify(trace.args)}</div>
    {trace.status !== "running" && <div className={`tool-trace-result ${trace.status === "error" ? "text-error" : ""}`}>返回：{typeof trace.result === "string" ? trace.result : JSON.stringify(trace.result)}</div>}
    {trace.retrieval?.sources.map((source) => <div className="tool-source-label" key={source.citation}>[{source.citation}] {source.heading}</div>)}
    {(trace.round || trace.durationMs !== undefined) && <div className="tool-trace-meta">{trace.round ? `第 ${trace.round} 轮` : ""}{trace.durationMs !== undefined ? ` · 工具耗时 ${trace.durationMs} ms` : ""}</div>}
  </section>;
}
