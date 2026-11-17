import { loadKnowledge } from "@/lib/knowledge";
import { ensureVectorIndex, vectorIndexStatus } from "@/lib/vector-index";
import { EMBEDDING_DIMENSIONS, EMBEDDING_MODEL } from "@/lib/embeddings";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  try {
    const { documents, chunks } = await loadKnowledge();
    const index = await vectorIndexStatus(chunks, request.signal).catch((error) => ({ model: EMBEDDING_MODEL, dimensions: EMBEDDING_DIMENSIONS, state: "error", indexedChunks: 0, error: error instanceof Error ? error.message : "无法读取向量索引状态。" }));
    return Response.json({ documents, chunkCount: chunks.length, index }, { headers: { "Cache-Control": "no-store" } });
  } catch (error) {
    return Response.json({ error: error instanceof Error ? error.message : "读取知识库失败。" }, { status: 500 });
  }
}

export async function POST(request: Request) {
  const origin = request.headers.get("origin");
  if (origin) {
    try { if (new URL(origin).host !== request.headers.get("host")) return Response.json({ error: "只接受同源请求。" }, { status: 403 }); }
    catch { return Response.json({ error: "无效的请求来源。" }, { status: 403 }); }
  }
  let force = false;
  try {
    const raw = await request.text();
    if (raw.length > 1000) throw new Error("请求过大。");
    const data = raw ? JSON.parse(raw) : {};
    if (!data || typeof data !== "object" || Array.isArray(data) || (data.force !== undefined && typeof data.force !== "boolean")) throw new Error("force 必须是布尔值。");
    force = data.force === true;
  } catch (error) { return Response.json({ error: error instanceof Error ? error.message : "请求格式错误。" }, { status: 400 }); }
  try {
    const { chunks } = await loadKnowledge();
    const index = await ensureVectorIndex(chunks, AbortSignal.any([request.signal, AbortSignal.timeout(180_000)]), force);
    const { vectors, ...metadata } = index;
    return Response.json({ ...metadata, indexedChunks: vectors.length }, { headers: { "Cache-Control": "no-store" } });
  } catch (error) {
    return Response.json({ error: error instanceof Error ? error.message : "建立本地向量索引失败。" }, { status: 500 });
  }
}
