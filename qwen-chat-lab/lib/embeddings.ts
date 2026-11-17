import { OLLAMA_URL } from "./ollama.ts";
import { normalizeVector } from "./vector-math.ts";

export const EMBEDDING_MODEL = "qwen3-embedding:0.6b";
export const EMBEDDING_DIMENSIONS = 1024;
// Qwen recommends an instruction on queries, with unprefixed retrieval documents.
export const QUERY_INSTRUCTION = "Given a question about the documents, retrieve relevant passages that answer the question";

function localEndpoint(route: string) {
  const url = new URL(OLLAMA_URL);
  if (!["127.0.0.1", "localhost", "[::1]"].includes(url.hostname) || !["http:", "https:"].includes(url.protocol)) {
    throw new Error("本项目的向量检索只连接本机 Ollama，请将 OLLAMA_BASE_URL 设为 http://127.0.0.1:11434。");
  }
  return new URL(route, url).toString();
}

function boundedSignal(signal: AbortSignal | undefined, timeoutMs: number) {
  return signal ? AbortSignal.any([signal, AbortSignal.timeout(timeoutMs)]) : AbortSignal.timeout(timeoutMs);
}

export async function embeddingModelIdentity(signal?: AbortSignal): Promise<{ model: string; digest: string }> {
  const response = await fetch(localEndpoint("/api/tags"), { cache: "no-store", redirect: "error", signal: boundedSignal(signal, 5000) });
  if (!response.ok) throw new Error("无法读取本机 Ollama 模型列表。");
  const data = await response.json();
  const model = data.models?.find((item: { name: string }) => item.name === EMBEDDING_MODEL);
  if (!model || typeof model.digest !== "string") throw new Error(`本机缺少向量模型，请先运行 ollama pull ${EMBEDDING_MODEL}。`);
  return { model: EMBEDDING_MODEL, digest: model.digest };
}

export async function embedTexts(texts: string[], signal?: AbortSignal): Promise<number[][]> {
  if (!texts.length) return [];
  const response = await fetch(localEndpoint("/api/embed"), {
    method: "POST", redirect: "error", signal: boundedSignal(signal, 60_000),
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ model: EMBEDDING_MODEL, input: texts, dimensions: EMBEDDING_DIMENSIONS, truncate: false, keep_alive: "2m", options: { num_ctx: 8192 } }),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(`本地向量生成失败：${data.error || response.status}。请确认 Ollama 正在运行。`);
  if (!Array.isArray(data.embeddings) || data.embeddings.length !== texts.length) throw new Error("Embedding 返回的向量数量与输入数量不一致。");
  return data.embeddings.map((vector: unknown) => normalizeVector(vector, EMBEDDING_DIMENSIONS));
}

export async function embedQuery(query: string, signal?: AbortSignal): Promise<number[]> {
  return (await embedTexts([`Instruct: ${QUERY_INSTRUCTION}\nQuery:${query}`], signal))[0];
}
