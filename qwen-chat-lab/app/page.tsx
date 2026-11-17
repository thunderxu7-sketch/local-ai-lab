"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { readNDJSON } from "@/lib/ndjson";
import type { ChatEvent, Run, ToolTrace } from "@/lib/chat";
import type { RetrievalTrace } from "@/lib/knowledge-types";
import { CitedAnswer, KnowledgeView, RetrievalCard } from "@/components/knowledge";
import { TaskSources, ToolTraceCard } from "@/components/tool-trace";
import { EvaluationView } from "@/components/evaluations";

type Message = { id: string; role: "user" | "assistant"; content: string; status?: "complete" | "generating" | "cancelled" | "error"; detail?: string; tokens?: number; seconds?: number; tps?: number; tools?: ToolTrace[]; rag?: boolean; agent?: boolean; retrieval?: RetrievalTrace };
type Tab = "chat" | "runs" | "guide" | "knowledge" | "evaluations";
const DEFAULT_SYSTEM = "你是一位耐心、准确的中文技术助手。回答简洁清晰；不确定时明确说明，不编造事实。遇到算术问题时请调用计算器工具，依据工具结果回答，不要心算猜答案。";
const AGENT_EXAMPLE = "请先检索青竹笔记的导入规则，再调用计算器：一批文件都达到单文件上限时，总大小是多少？请给出计算式和来源。";
const examples = [
  { label: "查规则并计算", tag: "Agent · 连续调用", prompt: AGENT_EXAMPLE, rag: false, agent: true },
  { label: "换种说法查资料", tag: "RAG · 向量检索", prompt: "我把一篇笔记误删了，过十天再找还能救回来吗？", rag: true, agent: false },
  { label: "理解一个概念", tag: "普通对话", prompt: "请用一个前端开发者熟悉的例子，解释 Token 和上下文窗口。控制在 150 字以内。", rag: false, agent: false },
  { label: "调用计算器", tag: "工具调用", prompt: "请用计算器计算 1287 × 349，并告诉我结果。", rag: false, agent: false },
];

function Icon({ name, size = 19 }: { name: string; size?: number }) {
  const paths: Record<string, React.ReactNode> = {
    chat: <><path d="M21 11.5a8.4 8.4 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.4 8.4 0 0 1-3.8-.9L3 21l1.9-5.7a8.4 8.4 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.4 8.4 0 0 1 3.8-.9h.5a8.5 8.5 0 0 1 8 8v.5Z" /></>,
    chart: <><path d="M4 3v17h17M8 16v-4M13 16V7M18 16v-7" /></>,
    book: <><path d="M12 5v16M12 5C8 2 4 3 2 4v15c3-1 6-1 10 2 4-3 7-3 10-2V4c-3-1-7-1-10 1Z" /></>,
    plus: <path d="M12 5v14M5 12h14" />,
    arrow: <path d="m6 12 6-6 6 6M12 6v13" />,
    settings: <><path d="M4 7h16M4 17h16" /><circle cx="9" cy="7" r="3" /><circle cx="15" cy="17" r="3" /></>,
    download: <><path d="M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5" /></>,
    check: <path d="m5 12 4 4L19 6" />,
  };
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name] || paths.chat}</svg>;
}

export default function Home() {
  const [tab, setTab] = useState<Tab>("chat");
  const [connected, setConnected] = useState<boolean | null>(null);
  const [models, setModels] = useState<{ name: string; size: number }[]>([]);
  const [model, setModel] = useState("qwen3:14b");
  const [system, setSystem] = useState(DEFAULT_SYSTEM);
  const [think, setThink] = useState(false);
  const [rag, setRag] = useState(false);
  const [agent, setAgent] = useState(false);
  const [settings, setSettings] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [phase, setPhase] = useState("");
  const [error, setError] = useState("");
  const [runs, setRuns] = useState<Run[]>([]);
  const [runsError, setRunsError] = useState("");
  const [hydrated, setHydrated] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const checkStatus = useCallback(async () => {
    try {
      const data = await (await fetch("/api/status")).json();
      setConnected(data.connected); setModels(data.models || []);
      if (data.connected && data.models.length) setModel((current) => data.models.some((m: { name: string }) => m.name === current) ? current : data.models[0].name);
    } catch { setConnected(false); }
  }, []);
  const refreshRuns = useCallback(async () => {
    try {
      const response = await fetch("/api/runs");
      if (!response.ok) throw new Error();
      const data = await response.json(); setRuns(data.runs); setRunsError("");
    } catch { setRunsError("读取记录失败，请稍后刷新。"); }
  }, []);

  useEffect(() => {
    void checkStatus();
    try {
      const saved = JSON.parse(localStorage.getItem("qwen-lab-session-v1") || "null");
      if (saved && Array.isArray(saved.messages)) {
        setMessages(saved.messages.filter((m: Message) => m && typeof m.content === "string" && ["user", "assistant"].includes(m.role)).map((m: Message) => ({
          ...m,
          status: m.status === "generating" ? "cancelled" : m.status,
          tools: m.tools?.map((tool) => tool.status === "running" ? { ...tool, status: "cancelled", result: "页面已重新打开，未完成的工具调用已停止显示。" } : tool),
        })));
        if (typeof saved.system === "string") setSystem(saved.system);
        if (typeof saved.think === "boolean") setThink(saved.think);
        if (typeof saved.rag === "boolean") setRag(saved.rag && saved.agent !== true);
        if (typeof saved.agent === "boolean") setAgent(saved.agent);
      }
    } catch { /* A malformed old draft should not prevent opening the lab. */ }
    setHydrated(true);
    return () => abortRef.current?.abort();
  }, [checkStatus]);
  useEffect(() => {
    if (!hydrated) return;
    try { localStorage.setItem("qwen-lab-session-v1", JSON.stringify({ messages, system, think, rag, agent })); } catch { /* Storage may be disabled. */ }
  }, [messages, system, think, rag, agent, hydrated]);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [messages]);
  useEffect(() => { if (tab === "runs") void refreshRuns(); }, [tab, refreshRuns]);

  async function sendPrompt(text: string) {
    const prompt = text.trim();
    if (!prompt || abortRef.current) return;
    setTab("chat"); setError(""); setInput(""); setBusy(true); setPhase(agent ? "模型正在判断需要哪些工具…" : rag ? "正在进行向量检索，文档变化时会自动更新索引…" : "正在连接模型，首次加载需要一点时间…");
    const controller = new AbortController(); abortRef.current = controller;
    const guard = setTimeout(() => controller.abort("timeout"), 195_000);
    const id = crypto.randomUUID();
    const history = rag || agent ? [] : messages.filter((m, i) => !m.rag && !m.agent && (m.role === "assistant" ? m.status === "complete" : messages[i + 1]?.status === "complete")).map(({ role, content }) => ({ role, content }));
    const user = { role: "user" as const, content: prompt };
    setMessages((prev) => [...prev, { ...user, id: crypto.randomUUID(), rag, agent }, { id, role: "assistant", content: "", status: "generating", rag, agent }]);
    const update = (patch: Partial<Message>) => setMessages((prev) => prev.map((m) => m.id === id ? { ...m, ...patch } : m));
    let textSoFar = "";
    let completed = false;
    try {
      const response = await fetch("/api/chat", { method: "POST", headers: { "Content-Type": "application/json" }, signal: controller.signal, body: JSON.stringify({ model, system, think, rag, agent, messages: [...history, user] }) });
      if (!response.ok) { const data = await response.json(); throw new Error(data.error || "请求失败。"); }
      if (!response.body) throw new Error("浏览器未收到响应流。");
      for await (const event of readNDJSON<ChatEvent>(response.body)) {
        if (event.error) throw new Error(event.error);
        if (event.resetResponse) { textSoFar = ""; update({ content: "" }); setPhase("模型正在继续处理任务…"); }
        if (event.notice) setPhase(event.notice);
        if (event.retrieval) {
          update({ retrieval: event.retrieval });
          setPhase(event.retrieval.sources.length ? "已找到原文，模型正在据此回答…" : "未找到相关资料");
        }
        if (event.tool) {
          setMessages((prev) => prev.map((message) => message.id === id
            ? { ...message, tools: [...(message.tools || []).filter((tool) => tool.id !== event.tool!.id), event.tool!] }
            : message));
          setPhase(event.tool.status === "running" ? `步骤 ${event.tool.step || 1}：${event.tool.name === "search_knowledge" ? "正在检索知识库" : "正在执行计算"}…` : event.tool.status === "error" ? "工具返回错误，模型正在处理…" : "工具执行完成，模型正在决定下一步…");
        }
        if (event.message?.thinking && !textSoFar) setPhase("模型正在思考…");
        if (event.message?.content) { textSoFar += event.message.content; update({ content: textSoFar }); setPhase("正在生成回答…"); }
        if (event.done) {
          completed = true;
          update({ status: "complete", tokens: event.eval_count, seconds: (event.lab?.durationMs || 0) / 1000, tps: event.eval_duration ? (event.eval_count || 0) / (event.eval_duration / 1e9) : undefined, detail: event.done_reason === "length" ? "已达到 512 token 上限，可继续追问。" : undefined });
        }
      }
      if (!completed) throw new Error("响应意外中断，请重试。");
    } catch (cause) {
      if (controller.signal.aborted && controller.signal.reason !== "timeout") update({ status: "cancelled", detail: "已停止生成；这轮未完成的对话不会加入后续上下文。" });
      else { const message = controller.signal.reason === "timeout" ? "请求超时，请稍后重试。" : cause instanceof Error ? cause.message : "发生未知错误。"; update({ status: "error", detail: message }); setError(message); }
    } finally {
      clearTimeout(guard); abortRef.current = null; setBusy(false); setPhase("");
      if (!completed) setMessages((prev) => prev.map((message) => message.id === id ? { ...message, tools: message.tools?.map((tool) => tool.status === "running" ? { ...tool, status: controller.signal.aborted ? "cancelled" : "error", result: "本次请求已结束，工具执行未完成。" } : tool) } : message));
      inputRef.current?.focus();
    }
  }

  function selectMode(mode: "chat" | "rag" | "agent") { if (busy) return; setRag(mode === "rag"); setAgent(mode === "agent"); }

  function newChat() { if (busy) return; setMessages([]); setInput(""); setError(""); setTab("chat"); inputRef.current?.focus(); }
  function exportRuns() {
    const url = URL.createObjectURL(new Blob([JSON.stringify(runs, null, 2)], { type: "application/json" }));
    const a = document.createElement("a"); a.href = url; a.download = "qwen-lab-runs.json"; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  return <div className="app-shell">
    <aside className="sidebar">
      <a className="brand" href="/" aria-label="Qwen Lab 首页"><span className="brand-mark">q<span>·</span></span><span>Qwen <b>Lab</b><small>本地 AI 实验室</small></span></a>
      <button className="new-chat" onClick={newChat} disabled={busy}><Icon name="plus" /> 新对话</button>
      <div className="nav-caption">工作台</div>
      <nav aria-label="主导航">{([{ id: "chat", name: "对话实验", icon: "chat" }, { id: "knowledge", name: "知识库", icon: "book" }, { id: "runs", name: "运行记录", icon: "chart" }, { id: "evaluations", name: "效果评测", icon: "check" }, { id: "guide", name: "操作指南", icon: "book" }] as const).map((item) => <button key={item.id} onClick={() => setTab(item.id)} className={tab === item.id ? "active" : ""}><Icon name={item.icon} />{item.name}{tab === item.id && <span className="nav-dot" />}</button>)}</nav>
      <div className="sidebar-note"><span className="eyebrow">你的第一步</span><h3>从调用模型，<br />到理解应用。</h3><p>提问、观察、记录。<br />让每次对话都成为实验。</p><span className="week-tag">WEEK 01 · API 工程</span></div>
      <div className="connection"><span className={`status-dot ${connected ? "online" : ""}`} /><div>{connected === null ? "正在检查连接" : connected ? "Ollama 已连接" : "Ollama 未连接"}<small>模型在这台 Mac 上运行</small></div><button aria-label="刷新连接状态" onClick={checkStatus}>↻</button></div>
    </aside>

    <main>
      <header className="topbar"><div><span className="breadcrumb">工作台</span><span className="slash">/</span><strong>{tab === "chat" ? "对话实验" : tab === "runs" ? "运行记录" : tab === "knowledge" ? "知识库" : tab === "evaluations" ? "效果评测" : "操作指南"}</strong></div><div className="header-right"><span className="local-badge"><span />LOCAL</span>{tab === "chat" && <button className={`icon-button ${settings ? "selected" : ""}`} aria-label="打开模型参数" aria-expanded={settings} onClick={() => setSettings(!settings)}><Icon name="settings" /></button>}</div></header>

      {tab === "chat" && <div className="chat-view">
        <div className="modelbar"><label><span className="mini-mark">Q</span><select aria-label="选择模型" value={model} onChange={(e) => setModel(e.target.value)} disabled={busy || !models.length}>{models.length ? models.map((m) => <option key={m.name} value={m.name}>{m.name}</option>) : <option value={model}>{model}</option>}</select></label><span>{agent ? "本地 Agent · 工具协作" : rag ? "本地文档 · 带来源回答" : "本地对话 · 多轮上下文"}</span></div>
        <div className="knowledge-mode"><div className="mode-switch" role="group" aria-label="对话模式"><button aria-pressed={!rag && !agent} disabled={busy} onClick={() => selectMode("chat")}>普通对话</button><button aria-pressed={rag} disabled={busy} onClick={() => selectMode("rag")}>知识库问答</button><button aria-pressed={agent} disabled={busy} onClick={() => selectMode("agent")}>Agent 模式</button></div><button className="knowledge-link" onClick={() => setTab("knowledge")}>查看知识库 ↗</button></div>
        {rag && <p className="knowledge-hint">每次根据当前问题检索。追问时请带上主题，点击引用编号可查看原文。</p>}
        {agent && <div className="agent-hint"><span>模型按当前任务决定调用顺序，可查资料、做计算。请完整描述任务。</span><button disabled={busy} onClick={() => { setInput(AGENT_EXAMPLE); inputRef.current?.focus(); }}>试试查规则并计算 ↗</button></div>}
        {settings && <section className="settings-panel"><label htmlFor="system-prompt">System Prompt <span>定义助手的角色与回答方式</span></label><textarea id="system-prompt" value={system} onChange={(e) => setSystem(e.target.value)} maxLength={2000} disabled={busy} rows={3} /><div className="settings-bottom"><label className="toggle-label"><input type="checkbox" checked={think} onChange={(e) => setThink(e.target.checked)} disabled={busy} />开启思考模式</label><span>上下文 8K · 输出上限 512 token · 超时 180 秒</span></div></section>}
        {!connected && connected !== null && <div className="notice">{models.length ? "连接暂时中断。" : "请先启动 Ollama："} <code>ollama serve</code>，然后点击左下角刷新。</div>}
        <div className="conversation">
          {messages.length === 0 ? <section className="welcome"><div className="welcome-symbol">✳</div><div className="eyebrow">HELLO, LOCAL INTELLIGENCE</div><h1>从一个好问题开始。</h1><p>模型就在你的 Mac 上。<br className="mobile-break" />选一个小实验，看看它如何回答。</p><div className="example-grid">{examples.map((example, i) => <button key={example.label} onClick={() => { selectMode(example.agent ? "agent" : example.rag ? "rag" : "chat"); setInput(example.prompt); inputRef.current?.focus(); }}><span className="example-number">0{i + 1}</span><strong>{example.label}</strong><small>{example.tag}<span>↗</span></small></button>)}</div><div className="welcome-foot"><span /> 开始前无需 API Key</div></section> : <div className="messages">{messages.map((message) => <article className={`message ${message.role}`} key={message.id}><div className="avatar">{message.role === "user" ? "你" : "Q"}</div><div className="message-main"><div className="message-heading">{message.role === "user" ? "你" : !message.agent && message.retrieval?.sources.length === 0 ? "知识库" : "Qwen"}{message.role === "assistant" && <span>{message.agent ? "Agent 模式" : message.rag ? "知识库问答" : "本地模型"}</span>}</div>{!message.agent && message.retrieval && <RetrievalCard trace={message.retrieval} prefix={message.id} />}{message.tools?.map((tool) => <ToolTraceCard key={tool.id} trace={tool} />)}<div className="message-content">{message.content ? <CitedAnswer text={message.content} trace={message.retrieval} prefix={message.id} /> : (message.status === "generating" ? <span className="generating"><i />{phase}</span> : "未生成回答")}</div>{message.agent && message.retrieval && <TaskSources trace={message.retrieval} prefix={message.id} />}{message.detail && <p className={`message-detail ${message.status === "error" ? "text-error" : ""}`}>{message.detail}</p>}{message.status === "complete" && <div className="message-metrics"><Icon name="check" size={12} />{message.seconds?.toFixed(1)} 秒<span>·</span>{message.tokens} token{message.tps !== undefined && <><span>·</span>{message.tps.toFixed(1)} token/s</>}</div>}</div></article>)}</div>}
          <div ref={endRef} />
        </div>
        <div className="composer-area">{error && <div className="error-banner" role="alert">{error}<button onClick={() => { const lastUser = messages.filter((m) => m.role === "user").at(-1); if (lastUser) setInput(lastUser.content); setError(""); inputRef.current?.focus(); }}>重新编辑</button></div>}<form className="composer" onSubmit={(e) => { e.preventDefault(); void sendPrompt(input); }}><textarea ref={inputRef} aria-label="输入消息" placeholder={agent ? "描述任务，例如：查导入规则，再计算一批文件的理论总大小" : rag ? "问问文档里的内容，例如：青竹笔记导入限制是什么？" : "向本地模型提问…"} value={input} onChange={(e) => setInput(e.target.value)} maxLength={rag || agent ? 2000 : 6000} rows={2} onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); if (!busy) void sendPrompt(input); } }} /><div className="composer-bottom"><span>{busy ? phase : "Enter 发送 · Shift + Enter 换行"}</span>{busy ? <button type="button" className="stop-button" onClick={() => abortRef.current?.abort()}><span /> 停止生成</button> : <button type="submit" className="send-button" aria-label="发送消息" disabled={!input.trim() || !connected || !models.length}><Icon name="arrow" /></button>}</div></form><p className="composer-note">回答可能有误，请验证关键信息。对话与实验记录仅保存在本机。</p></div>
      </div>}

      {tab === "runs" && <section className="content-page"><div className="page-title"><div className="eyebrow">OBSERVE & COMPARE</div><h1>每次运行，都有迹可循。</h1><p>最近 30 次请求。比较同一个问题在不同设置下的表现。</p></div><div className="toolbar"><span>{runs.length} 条记录</span><div><button className="secondary-button" onClick={refreshRuns}>刷新</button><button className="secondary-button" onClick={exportRuns} disabled={!runs.length}><Icon name="download" size={15} />导出 JSON</button></div></div>{runsError && <p role="alert" className="text-error">{runsError}</p>}{!runs.length && <div className="empty-state"><Icon name="chart" size={30} /><h3>第一条记录，来自第一次提问。</h3><p>发送消息后，会自动保存输入、回答、耗时与运行状态。</p><button className="secondary-button" onClick={() => setTab("chat")}>开始对话 ↗</button></div>}<div className="run-list">{runs.map((run) => <details className="run-card" key={run.id}><summary><span className={`run-state ${run.status}`}>{run.status === "complete" ? "完成" : run.status === "cancelled" ? "已停止" : "错误"}</span><strong>{run.prompt}</strong><span>{(run.durationMs / 1000).toFixed(1)}s</span><span className="run-chevron">⌄</span></summary><div className="run-body"><div className="run-meta">{new Date(run.createdAt).toLocaleString("zh-CN")} · {run.model} · {run.agent ? "Agent" : run.rag ? "知识库问答" : "普通对话"} · 思考{run.think ? "开启" : "关闭"}<br />{run.tokens} token · 首字 {run.firstTokenMs === null ? "—" : `${(run.firstTokenMs / 1000).toFixed(2)}s`} · {run.tokensPerSecond?.toFixed(1) || "—"} token/s</div>{run.tools?.map((tool) => <ToolTraceCard key={tool.id} trace={tool} />)}<div className="run-answer">{run.retrieval && (run.agent ? <TaskSources trace={run.retrieval} prefix={`run-${run.id}`} /> : <RetrievalCard trace={run.retrieval} prefix={`run-${run.id}`} />)}<div className="message-content"><CitedAnswer text={run.response || "无回答"} trace={run.retrieval} prefix={`run-${run.id}`} /></div></div>{run.error && <p className="text-error">{run.error}</p>}</div></details>)}</div></section>}

      {tab === "evaluations" && <EvaluationView busy={busy} onAsk={(result, report) => { if (busy) return; selectMode(result.mode); setModel(report.model); setSystem(report.system); setThink(report.think); setInput(result.prompt); setTab("chat"); }} />}

      {tab === "knowledge" && <KnowledgeView onAsk={(prompt) => { if (busy) return; selectMode("rag"); setInput(prompt); setTab("chat"); }} />}

      {tab === "guide" && <section className="content-page guide"><div className="page-title"><div className="eyebrow">LEARN BY BUILDING</div><h1>先跑通，再拆开理解。</h1><p>从普通对话、工具调用到知识库问答，沿着一次请求理解应用。</p></div><div className="flow"><span>浏览器<span>React 界面</span></span><b>→</b><span>Next.js API<span>转发与记录</span></span><b>→</b><span>Ollama<span>Qwen3 推理</span></span></div>{[{ title: "01 · 观察流式输出", text: "发送一个解释题，观察回答逐渐出现；生成中点击停止，再发送新问题。打开浏览器 Network，找到 /api/chat，查看逐行返回的 JSON。", file: "app/page.tsx → lib/ndjson.ts" }, { title: "02 · 验证多轮上下文", text: "先说“我的项目叫青竹”，再问“我的项目叫什么？”；开启新对话后再问同一个问题，比较答案。模型每次依赖请求中的 messages 历史。", file: "app/api/chat/route.ts" }, { title: "03 · 观察真实工具调用", text: "点“调用计算器”，观察 Qwen 发出 calculate 参数、服务端执行本地函数、计算结果回传给模型，最后查看模型生成的解释。", file: "lib/tools.ts → app/api/chat/route.ts → app/page.tsx" }, { title: "04 · 留下第一组对照", text: "固定一个问题，分别关闭、开启思考模式测试。在运行记录里比较回答、首字耗时和生成速度。记录正确答案与失败原因，不把模型自评当作通过。", file: "eval/cases.json → .local/runs.jsonl" }, { title: "05 · 根据文档回答", text: "进入知识库，先阅读青竹笔记示例资料。选择知识库问答，询问导入限制，点击回答里的 [1] 对照原文。再问资料中没有的内容，观察模型是否承认信息不足。每次只检索当前问题，追问请带主题。", file: "knowledge/*.md → lib/knowledge.ts → app/api/chat/route.ts" }, { title: "06 · 看懂 Agent 循环", text: "切换 Agent 模式，点击查规则并计算示例。观察模型先发出 search_knowledge，拿到导入规则后再发出 calculate，最后根据工具结果回答。普通算术可以直接使用计算器，是否查资料由模型决定。每次执行当前任务，工具记录和引用会一起保存。", file: "lib/agent.ts → lib/tools.ts → app/api/chat/route.ts" }].map((step) => <article className="guide-step" key={step.title}><h3>{step.title}</h3><p>{step.text}</p><code>{step.file}</code></article>)}<div className="guide-note"><strong>下一步：观察语义检索的边界。</strong><p>试着用“误删后怎么救回来”寻找回收站规则，比较检索到的片段与余弦相似度。文档变化后会自动更新本地向量；历史记录保留当时的检索方式与原文。</p></div></section>}
    </main>
  </div>;
}
