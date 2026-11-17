import type { RetrievalTrace } from "./knowledge-types";

export type ChatMessage = { role: "user" | "assistant"; content: string };
export type ChatInput = { model: string; messages: ChatMessage[]; system: string; think: boolean; rag?: boolean; agent?: boolean };
export type ToolTrace = {
  id: string;
  name: string;
  args: Record<string, unknown>;
  status: "running" | "complete" | "error" | "cancelled";
  result?: unknown;
  step?: number;
  round?: number;
  durationMs?: number;
  retrieval?: RetrievalTrace;
};
export type ChatEvent = {
  message?: { content?: string; thinking?: string };
  tool?: ToolTrace;
  retrieval?: RetrievalTrace;
  resetResponse?: boolean;
  notice?: string;
  done?: boolean;
  done_reason?: string;
  error?: string;
  eval_count?: number;
  eval_duration?: number;
  prompt_eval_count?: number;
  lab?: { id: string; durationMs: number; firstTokenMs: number | null };
};
export type Run = {
  id: string;
  createdAt: string;
  model: string;
  think: boolean;
  system: string;
  messages: ChatMessage[];
  prompt: string;
  response: string;
  status: "complete" | "cancelled" | "error";
  error?: string;
  durationMs: number;
  firstTokenMs: number | null;
  tokens: number;
  tokensPerSecond: number | null;
  promptTokens: number;
  finishReason?: string;
  tools?: ToolTrace[];
  rag?: boolean;
  agent?: boolean;
  agentCorrections?: number;
  retrieval?: RetrievalTrace;
};

export function validateInput(value: unknown): ChatInput {
  if (!value || typeof value !== "object") throw new Error("请求必须是 JSON 对象。");
  const v = value as Record<string, unknown>;
  if (typeof v.model !== "string" || !/^[a-zA-Z0-9._:/-]{1,160}$/.test(v.model)) throw new Error("请选择有效的本地模型。");
  if (typeof v.system !== "string" || v.system.length > 2000) throw new Error("System Prompt 最多 2000 字符。");
  if (typeof v.think !== "boolean") throw new Error("think 必须是布尔值。");
  if (v.rag !== undefined && typeof v.rag !== "boolean") throw new Error("rag 必须是布尔值。");
  if (v.agent !== undefined && typeof v.agent !== "boolean") throw new Error("agent 必须是布尔值。");
  if (v.rag && v.agent) throw new Error("知识库问答与 Agent 模式不能同时开启。");
  if (!Array.isArray(v.messages) || v.messages.length < 1 || v.messages.length > 40) throw new Error("对话最多 40 条消息，请开启新对话。");
  const messages: ChatMessage[] = v.messages.map((message: unknown) => {
    if (!message || typeof message !== "object") throw new Error("消息格式不正确。");
    const m = message as Record<string, unknown>;
    if ((m.role !== "user" && m.role !== "assistant") || typeof m.content !== "string" || !m.content.trim()) throw new Error("消息角色或内容不正确。");
    if (m.content.length > 6000) throw new Error("单条消息最多 6000 字符。");
    return { role: m.role, content: m.content };
  });
  if (messages.at(-1)?.role !== "user") throw new Error("最后一条消息必须来自用户。");
  if ((v.rag || v.agent) && messages.at(-1)!.content.length > 2000) throw new Error("知识库或 Agent 问题最多 2000 字符，请缩短问题。");
  if (v.agent && messages.at(-1)!.content.length + v.system.length > 2500) throw new Error("Agent 的问题与 System Prompt 合计最多 2500 字符，请缩短内容以留出工具上下文。");
  if (messages.reduce((sum, m) => sum + m.content.length, v.system.length) > 16000) throw new Error("本次上下文过长，请开启新对话。");
  return { model: v.model, messages, system: v.system, think: v.think, ...(typeof v.rag === "boolean" ? { rag: v.rag } : {}), ...(typeof v.agent === "boolean" ? { agent: v.agent } : {}) };
}
