export function normalizeVector(value: unknown, dimensions: number): number[] {
  if (!Array.isArray(value) || value.length !== dimensions || value.some((n) => typeof n !== "number" || !Number.isFinite(n))) {
    throw new Error(`Embedding 返回的向量无效，预期 ${dimensions} 个有限数字。`);
  }
  const norm = Math.sqrt(value.reduce((sum, n) => sum + n * n, 0));
  if (!Number.isFinite(norm) || norm < 1e-12) throw new Error("Embedding 返回了零向量或无效向量。");
  return value.map((n) => n / norm);
}

/** Inputs are normalized on ingestion; their dot product is cosine similarity. */
export function cosineSimilarity(a: number[], b: number[]): number {
  if (!a.length || a.length !== b.length) throw new Error("查询向量与文档向量维度不一致，请重建索引。");
  return Math.max(-1, Math.min(1, a.reduce((sum, n, index) => sum + n * b[index], 0)));
}
