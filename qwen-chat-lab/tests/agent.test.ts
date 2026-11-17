import test from "node:test";
import assert from "node:assert/strict";
import { needsCalculationCheck, registerAgentSources } from "../lib/agent.ts";
import { validateInput } from "../lib/chat.ts";
import { executeToolCall, validateSearchQuery } from "../lib/tools.ts";
import type { KnowledgeSource, RetrievalTrace } from "../lib/knowledge-types.ts";

function source(id: string, content = id): KnowledgeSource {
  return { id, file: `${id}.md`, title: id, heading: id, lineStart: 1, lineEnd: 2, content, score: 0.8, citation: 1 };
}
function retrieval(query: string, sources: KnowledgeSource[]): RetrievalTrace {
  return { query, method: "vector", documentCount: 3, chunkCount: 11, durationMs: 10, sources };
}

test("agent searches retain stable citations when results overlap or reorder", () => {
  const first = registerAgentSources(undefined, retrieval("first", [source("a"), source("b"), source("c")]), "task");
  assert.deepEqual(first.content.sources.map((s) => s.citation), [1, 2]);
  const next = registerAgentSources(first.aggregate, retrieval("next", [source("b"), source("c")]), "task");
  assert.deepEqual(next.content.sources.map((s) => s.citation), [2, 3]);
  assert.deepEqual(next.aggregate.sources.map((s) => [s.id, s.citation]), [["a", 1], ["b", 2], ["c", 3]]);
  assert.deepEqual(next.aggregate.queries, ["first", "next"]);
  assert.equal(next.aggregate.durationMs, 20);
  assert.equal(first.aggregate.sources.length, 2);
});

test("changed source content gets a fresh citation; empty search keeps prior evidence", () => {
  const first = registerAgentSources(undefined, retrieval("first", [source("a", "original")]), "task");
  const changed = registerAgentSources(first.aggregate, retrieval("changed", [source("a", "edited")]), "task");
  assert.deepEqual(changed.aggregate.sources.map((s) => [s.content, s.citation]), [["original", 1], ["edited", 2]]);
  const empty = registerAgentSources(first.aggregate, retrieval("missing", []), "task");
  assert.equal(empty.content.found, 0);
  assert.deepEqual(empty.aggregate.sources, first.aggregate.sources);
});

test("agent request validates mode and reserves room for tool context", () => {
  const input = { model: "qwen3:14b", system: "", think: false, agent: true, messages: [{ role: "user", content: "查规则再计算" }] };
  assert.deepEqual(validateInput(input), input);
  assert.throws(() => validateInput({ ...input, rag: true }), /不能同时开启/);
  assert.throws(() => validateInput({ ...input, agent: "true" }), /布尔值/);
  assert.throws(() => validateInput({ ...input, messages: [{ role: "user", content: "字".repeat(2001) }] }), /2000/);
  assert.throws(() => validateInput({ ...input, system: "字".repeat(2000), messages: [{ role: "user", content: "字".repeat(501) }] }), /2500/);
});

test("tools reject malformed arguments and unregistered actions", () => {
  assert.equal(validateSearchQuery({ query: " 导入规则 " }), "导入规则");
  for (const raw of [null, [], "query", { query: " " }, { query: "字".repeat(2001) }, { query: "规则", path: "/tmp/file" }]) {
    assert.throws(() => validateSearchQuery(raw));
  }
  assert.throws(() => executeToolCall({ function: { name: "shell", arguments: {} } }), /未注册/);
  assert.throws(() => executeToolCall({ function: { name: "calculate", arguments: { a: "8", b: 12, operation: "multiply" } } }), /必须是数字/);
  assert.throws(() => executeToolCall({ function: { name: "calculate", arguments: { a: 8, b: 0, operation: "divide" } } }), /不能为 0/);
});

test("numerical equations need a successful calculator result before completion", () => {
  assert.equal(needsCalculationCheck("计算式：12 MB × 8 个文件 = 96 MB", []), true);
  assert.equal(needsCalculationCheck("27*16=432", []), true);
  assert.equal(needsCalculationCheck("每个文件 12 MB，每批最多 8 个 [1]。", []), false);
  assert.equal(needsCalculationCheck("记录日期：2026-11-16。", []), false);
  const trace = { id: "calc", name: "calculate", args: {}, status: "error" as const };
  assert.equal(needsCalculationCheck("12×8=96", [trace]), true);
  assert.equal(needsCalculationCheck("12×8=96", [{ ...trace, status: "complete", result: 96 }]), false);
});
