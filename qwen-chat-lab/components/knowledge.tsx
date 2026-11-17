"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { KnowledgeLibrary, RetrievalTrace } from "@/lib/knowledge-types";

export function CitedAnswer({ text, trace, prefix }: { text: string; trace?: RetrievalTrace; prefix: string }) {
  if (!trace) return <>{text}</>;
  const citations = new Set(trace.sources.map((source) => source.citation));
  return <>{text.split(/(\[\d+\])/g).map((part, index) => {
    const match = part.match(/^\[(\d+)\]$/);
    if (!match || !citations.has(Number(match[1]))) return <span key={index}>{part}</span>;
    return <button key={index} className="citation-link" aria-label={`查看引用 ${match[1]}`} onClick={() => {
      const source = document.getElementById(`${prefix}-source-${match[1]}`) as HTMLDetailsElement | null;
      if (source) {
        let parent: HTMLElement | null = source;
        while (parent) { if (parent instanceof HTMLDetailsElement) parent.open = true; parent = parent.parentElement; }
        source.scrollIntoView({ block: "nearest", behavior: "smooth" }); source.focus({ preventScroll: true });
      }
    }}>{part}</button>;
  })}</>;
}

export function RetrievalCard({ trace, prefix }: { trace: RetrievalTrace; prefix: string }) {
  return <section className="retrieval-card" aria-label="检索来源">
    <div className="retrieval-heading"><strong>{trace.scope === "agent" ? "本轮任务引用" : "知识库检索"} · {trace.sources.length ? `${trace.sources.length} 个候选片段` : "未找到相关段落"}</strong><span>{trace.durationMs} ms</span></div>
    <p className="retrieval-meta">{trace.documentCount} 份文档 · {trace.chunkCount} 个片段 · {trace.method === "vector" ? "本地向量检索" : "中文关键词检索"}</p>
    {trace.vector && <p className="retrieval-meta">{trace.scope === "agent" ? "最近一次检索：" : ""}{trace.vector.model} · {trace.vector.dimensions} 维 · {trace.vector.cacheHit ? "已复用本地索引" : `本次生成 ${trace.vector.embeddedChunks} 个片段向量`} · 相似度门槛 {trace.vector.minimumScore}</p>}
    {trace.sources.map((source) => <details key={source.citation} id={`${prefix}-source-${source.citation}`} className="source-card" tabIndex={-1}>
      <summary><span className="source-number">[{source.citation}]</span><span>{source.heading}<small>{source.file} · 第 {source.lineStart}–{source.lineEnd} 行</small></span><span className="source-expand">展开</span></summary>
      <pre>{source.content}</pre>
      <small className="source-score">{trace.method === "vector" ? "余弦相似度" : "关键词得分"} {source.score.toFixed(3)} · 用于排序，不代表答案正确率</small>
    </details>)}
    {!trace.sources.length && <p className="retrieval-empty">{trace.scope === "agent" ? "检索未找到相关原文，Agent 会根据这一结果决定下一步。" : "未调用聊天模型生成答案。可以更具体地描述问题，或补充资料。"}</p>}
    {trace.citationWarning && <p className="retrieval-warning">{trace.citationWarning}</p>}
  </section>;
}

export function KnowledgeView({ onAsk }: { onAsk: (prompt: string) => void }) {
  const [library, setLibrary] = useState<KnowledgeLibrary | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [building, setBuilding] = useState(false);
  const [indexMessage, setIndexMessage] = useState("");
  const indexAbort = useRef<AbortController | null>(null);
  const refresh = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const response = await fetch("/api/knowledge", { cache: "no-store" });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "读取知识库失败。");
      setLibrary(data);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "读取知识库失败。"); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void refresh(); }, [refresh]);
  useEffect(() => () => indexAbort.current?.abort(), []);

  async function updateIndex() {
    if (indexAbort.current) return;
    const controller = new AbortController(); indexAbort.current = controller;
    setBuilding(true); setIndexMessage(""); setError("");
    try {
      const response = await fetch("/api/knowledge", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}", signal: AbortSignal.any([controller.signal, AbortSignal.timeout(185_000)]) });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "更新向量索引失败。");
      setIndexMessage(`索引已更新：${data.indexedChunks} 个片段，生成 ${data.embeddedChunks} 个向量，复用 ${data.reusedChunks} 个。`);
      await refresh();
    } catch (cause) {
      if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : "更新索引失败。");
    } finally { indexAbort.current = null; setBuilding(false); }
  }

  return <section className="content-page knowledge-page">
    <div className="page-title"><div className="eyebrow">EMBED · RETRIEVE · ANSWER</div><h1>换一种说法，也能找到资料。</h1><p>本机模型把问题和文档转成向量，按语义相似度找到原文，再由 Qwen 回答。</p></div>
    <div className="knowledge-intro"><strong>先问项目，再对照资料</strong><p>这里有 Qwen Lab 的真实使用说明，以及虚构产品“青竹笔记”的演示资料。试问“改了 Qwen Lab 的资料，需要重启吗？”，点击回答中的 [1] 核对原文。左侧“效果评测”可查看固定 10 题的回答与工具记录。</p><button className="secondary-button" onClick={() => onAsk("我把 Qwen Lab 的资料改了几句，还删了一篇旧文档。要关掉服务再开一次，它才能用到新内容吗？")}>试试项目问答 ↗</button></div>
    <section className="vector-index-panel" aria-label="本地向量索引"><div><strong>本地向量索引</strong><p>{library?.index ? `${library.index.model} · ${library.index.dimensions} 维` : "正在检查索引…"}</p><span>{library?.index?.state === "ready" ? `已就绪 · ${library.index.indexedChunks} 个片段` : library?.index?.state === "stale" ? "文档或模型已变化，下次提问会自动更新" : library?.index?.state === "missing" ? "尚未建立，首次提问会自动生成" : library?.index?.error || "正在读取状态"}</span></div><button className="secondary-button" disabled={building || loading} onClick={updateIndex}>{building ? "正在生成向量…" : "更新向量索引"}</button></section>
    {indexMessage && <p className="index-message" role="status">{indexMessage}</p>}
    <div className="toolbar"><span>{library ? `${library.documents.length} 份文档 · ${library.chunkCount} 个片段` : "正在读取文档…"}</span><button className="secondary-button" disabled={loading} onClick={refresh}>{loading ? "读取中…" : "刷新文档"}</button></div>
    {error && <p className="text-error" role="alert">{error}</p>}
    {library?.documents.length === 0 && <div className="empty-state">知识库还是空的。将 UTF-8 Markdown 文件放入项目的 knowledge 文件夹后刷新。</div>}
    <div className="knowledge-documents">{library?.documents.map((doc) => <details className="knowledge-document" key={doc.file}><summary><span><strong>{doc.title}</strong><small>{doc.file} · {doc.chunkCount} 个片段</small></span><span>查看原文 ↗</span></summary><pre>{doc.content}</pre></details>)}</div>
    <div className="guide-note"><strong>换成自己的资料</strong><p>把 UTF-8 编码的 .md 文件放入项目 <code>knowledge/</code> 文件夹；用 # 和 ## 划分主题。下次提问会自动为新增或变化的片段生成向量，删除的文档也会从检索中移除，无需重启。最多 40 份文件，单份 128 KB，总计 1 MB；暂不读取子文件夹。</p><p>模型和向量都保存在本机。语义相近的段落仍可能缺少所需答案；相似度不是正确率。每次只检索当前问题，追问请带上主题，回答需对照引用原文核对。</p></div>
  </section>;
}
