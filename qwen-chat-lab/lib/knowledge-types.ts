export type KnowledgeChunk = {
  id: string;
  file: string;
  title: string;
  heading: string;
  lineStart: number;
  lineEnd: number;
  content: string;
};

export type KnowledgeSource = KnowledgeChunk & { citation: number; score: number };
export type RetrievalTrace = {
  query: string;
  method: "keyword" | "vector";
  vector?: {
    model: string;
    dimensions: number;
    modelDigest: string;
    minimumScore: number;
    cacheHit: boolean;
    embeddedChunks: number;
    reusedChunks: number;
    indexUpdatedAt: string;
  };
  documentCount: number;
  chunkCount: number;
  durationMs: number;
  sources: KnowledgeSource[];
  citationWarning?: string;
  scope?: "agent";
  queries?: string[];
};

export type KnowledgeDocument = {
  file: string;
  title: string;
  content: string;
  chunkCount: number;
};

export type KnowledgeLibrary = {
  documents: KnowledgeDocument[];
  chunkCount: number;
  index?: VectorIndexStatus;
};

export type VectorIndexStatus = {
  model: string;
  dimensions: number;
  state: "ready" | "stale" | "missing" | "error";
  indexedChunks: number;
  updatedAt?: string;
  error?: string;
};
