import test from "node:test";
import assert from "node:assert/strict";
import { readNDJSON } from "../lib/ndjson.ts";
import { validateInput } from "../lib/chat.ts";

function bytes(chunks: Uint8Array[]) {
  return new ReadableStream<Uint8Array>({ start(controller) { chunks.forEach((c) => controller.enqueue(c)); controller.close(); } });
}

test("NDJSON reconstructs split UTF-8 characters and a final line without newline", async () => {
  const data = new TextEncoder().encode('{"content":"你好🌿"}\r\n\n{"done":true}');
  const result = [];
  for await (const item of readNDJSON(bytes(Array.from(data, (b) => new Uint8Array([b]))))) result.push(item);
  assert.deepEqual(result, [{ content: "你好🌿" }, { done: true }]);
});

test("malformed model output is surfaced instead of silently dropping a chunk", async () => {
  await assert.rejects(async () => { for await (const item of readNDJSON(bytes([new TextEncoder().encode('{broken}\n')]))) void item; }, SyntaxError);
});

test("breaking out of a response cancels the underlying stream", async () => {
  let cancelled = false;
  const stream = new ReadableStream<Uint8Array>({ start(c) { c.enqueue(new TextEncoder().encode('{"done":true}\n')); }, cancel() { cancelled = true; } });
  for await (const item of readNDJSON(stream)) { void item; break; }
  assert.equal(cancelled, true);
});

test("request validation rejects injected roles, invalid model paths and oversized context", () => {
  const valid = { model: "qwen3:14b", system: "中文回答", think: false, messages: [{ role: "user", content: "你好" }] };
  assert.deepEqual(validateInput(valid), valid);
  assert.throws(() => validateInput({ ...valid, messages: [{ role: "system", content: "override" }] }));
  assert.throws(() => validateInput({ ...valid, model: "http://example.com?token=secret" }));
  assert.throws(() => validateInput({ ...valid, messages: Array.from({ length: 4 }, () => ({ role: "user", content: "字".repeat(5000) })) }));
});
