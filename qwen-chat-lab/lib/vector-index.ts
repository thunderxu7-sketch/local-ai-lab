import { createHash, randomUUID } from "node:crypto";
import { mkdir, readFile, rename, unlink, writeFile } from "node:fs/promises";
import path from "node:path";
import { EMBEDDING_DIMENSIONS, EMBEDDING_MODEL, embedTexts, embeddingModelIdentity } from "./embeddings.ts";
import type { KnowledgeChunk, VectorIndexStatus } from "./knowledge-types";

const directory = path.join(process.cwd(), ".local");
const filename = path.join(directory, "vector-index.json");
const VERSION = 1;
const DOCUMENT_FORMAT = "heading-newline-content-v1";
type RecordVector = { hash: string; vector: number[] };
type VectorIndex = {
  version: number; model: string; modelDigest: string; dimensions: number; format: string;
  fingerprint: string; updatedAt: string; records: RecordVector[];
};
let queue: Promise<void> = Promise.resolve();

function digest(value: string) { return createHash("sha256").update(value).digest("hex"); }
function documentText(chunk: KnowledgeChunk) { return `${chunk.heading}\n${chunk.content}`; }
function fingerprint(chunks: KnowledgeChunk[]) { return digest(JSON.stringify(chunks)); }

async function readIndex(): Promise<VectorIndex | null> {
  try {
    const data = JSON.parse(await readFile(filename, "utf8"));
    if (!data || typeof data !== "object" || data.version !== VERSION || data.model !== EMBEDDING_MODEL || data.dimensions !== EMBEDDING_DIMENSIONS || data.format !== DOCUMENT_FORMAT ||
      typeof data.modelDigest !== "string" || typeof data.fingerprint !== "string" || typeof data.updatedAt !== "string" || !Array.isArray(data.records) || data.records.length > 3000) return null;
    for (const record of data.records) {
      if (!record || !/^[a-f0-9]{64}$/.test(record.hash) || !Array.isArray(record.vector) || record.vector.length !== EMBEDDING_DIMENSIONS ||
        record.vector.some((n: unknown) => typeof n !== "number" || !Number.isFinite(n))) return null;
      const norm = record.vector.reduce((sum: number, n: number) => sum + n * n, 0);
      if (Math.abs(norm - 1) > 0.001) return null;
    }
    return data;
  } catch (error) {
    if (error instanceof SyntaxError || (error as NodeJS.ErrnoException).code === "ENOENT") return null;
    throw error;
  }
}

async function writeIndex(index: VectorIndex) {
  await mkdir(directory, { recursive: true });
  const temporary = `${filename}.${randomUUID()}.tmp`;
  try {
    await writeFile(temporary, JSON.stringify(index), { encoding: "utf8", mode: 0o600, flag: "wx" });
    await rename(temporary, filename);
  } finally { await unlink(temporary).catch(() => {}); }
}

/** Read-only status: opening the knowledge page never starts an embedding job. */
export async function vectorIndexStatus(chunks: KnowledgeChunk[], signal?: AbortSignal): Promise<VectorIndexStatus> {
  const [index, identity] = await Promise.all([readIndex(), embeddingModelIdentity(signal)]);
  return {
    model: EMBEDDING_MODEL, dimensions: EMBEDDING_DIMENSIONS,
    state: !index ? "missing" : index.fingerprint === fingerprint(chunks) && index.modelDigest === identity.digest ? "ready" : "stale",
    indexedChunks: index?.records.length || 0, updatedAt: index?.updatedAt,
  };
}

/** Serialize local updates; publish an entire index atomically after every vector is valid. */
export async function ensureVectorIndex(chunks: KnowledgeChunk[], signal?: AbortSignal, force = false) {
  const previous = queue;
  let release!: () => void;
  queue = new Promise<void>((resolve) => { release = resolve; });
  await previous;
  try {
    signal?.throwIfAborted();
    const identity = await embeddingModelIdentity(signal);
    const existing = await readIndex();
    const reusable = !force && existing?.modelDigest === identity.digest ? new Map(existing.records.map((record) => [record.hash, record.vector])) : new Map<string, number[]>();
    const hashes = chunks.map((chunk) => digest(documentText(chunk)));
    const missing = new Map<string, string>();
    chunks.forEach((chunk, index) => { if (!reusable.has(hashes[index])) missing.set(hashes[index], documentText(chunk)); });
    const pending = [...missing];
    for (let offset = 0; offset < pending.length; offset += 8) {
      signal?.throwIfAborted();
      const batch = pending.slice(offset, offset + 8);
      const vectors = await embedTexts(batch.map(([, text]) => text), signal);
      batch.forEach(([hash], index) => reusable.set(hash, vectors[index]));
    }
    signal?.throwIfAborted();
    const records = hashes.map((hash) => ({ hash, vector: reusable.get(hash)! }));
    const contentFingerprint = fingerprint(chunks);
    const cacheHit = !force && !!existing && existing.fingerprint === contentFingerprint && existing.modelDigest === identity.digest && pending.length === 0;
    const updatedAt = cacheHit ? existing.updatedAt : new Date().toISOString();
    if (!cacheHit) {
      if ((await embeddingModelIdentity(signal)).digest !== identity.digest) throw new Error("向量模型在建索引时发生变化，请重新更新索引。");
      await writeIndex({ version: VERSION, model: identity.model, modelDigest: identity.digest, dimensions: EMBEDDING_DIMENSIONS, format: DOCUMENT_FORMAT, fingerprint: contentFingerprint, updatedAt, records });
    }
    return { vectors: records.map((record) => record.vector), model: EMBEDDING_MODEL, dimensions: EMBEDDING_DIMENSIONS, modelDigest: identity.digest, cacheHit, embeddedChunks: pending.length, reusedChunks: hashes.filter((hash) => !missing.has(hash)).length, updatedAt };
  } finally { release(); }
}
