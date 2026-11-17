import test from "node:test";
import assert from "node:assert/strict";
import { cosineSimilarity, normalizeVector } from "../lib/vector-math.ts";

test("cosine ranking is independent of the magnitude of incoming embeddings", () => {
  const query = normalizeVector([3, 4], 2);
  const same = normalizeVector([300, 400], 2);
  const unrelated = normalizeVector([4, -3], 2);
  const opposite = normalizeVector([-3, -4], 2);
  assert.ok(Math.abs(cosineSimilarity(query, same) - 1) < 1e-10);
  assert.ok(Math.abs(cosineSimilarity(query, unrelated)) < 1e-10);
  assert.ok(Math.abs(cosineSimilarity(query, opposite) + 1) < 1e-10);
});

test("invalid or incompatible embeddings fail instead of producing plausible rankings", () => {
  for (const vector of [[0, 0], [NaN, 1], [Infinity, 1], ["1", 2], [1], null, [Number.MAX_VALUE, Number.MAX_VALUE]]) {
    assert.throws(() => normalizeVector(vector, 2));
  }
  assert.throws(() => cosineSimilarity([1, 0], [1, 0, 0]));
  assert.throws(() => cosineSimilarity([], []));
});
