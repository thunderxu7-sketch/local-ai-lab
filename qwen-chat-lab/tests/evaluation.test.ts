import test from "node:test";
import assert from "node:assert/strict";
import { checkProjectResult, type ProjectCase, type EvaluationResult } from "../lib/evaluation.ts";

const item: ProjectCase = { id: "test", category: "检索后计算", mode: "agent", prompt: "查规则再算", expected: "6", sources: ["规则"], patterns: ["6"], tools: ["search_knowledge", "calculate"], calculation: { operation: "multiply", operands: [2, 3], result: 6 } };
const result: Pick<EvaluationResult, "completed" | "answer" | "retrieval" | "toolsUsed" | "finishReason"> = {
  completed: true, answer: "2 × 3 = 6 [1]", finishReason: "stop",
  retrieval: { query: "规则", method: "vector", documentCount: 1, chunkCount: 1, durationMs: 1, sources: [{ id: "a", file: "a.md", heading: "项目 / 规则", title: "项目", content: "每组 2 个，共 3 组", citation: 1, score: 0.8, lineStart: 1, lineEnd: 1 }] },
  toolsUsed: [{ id: "s", name: "search_knowledge", args: {}, status: "complete" }, { id: "c", name: "calculate", args: { a: 2, b: 3, operation: "multiply" }, status: "complete", result: 6 }],
};

test("evaluation distinguishes a correct number from missing evidence or skipped tools", () => {
  assert.ok(checkProjectResult(item, result).every((c) => c.passed));
  const noCitation = checkProjectResult(item, { ...result, answer: "2 × 3 = 6" });
  assert.equal(noCitation.find((c) => c.name === "回答线索")?.passed, true);
  assert.equal(noCitation.find((c) => c.name === "引用编号")?.passed, false);
  const noTool = checkProjectResult(item, { ...result, toolsUsed: [] });
  assert.equal(noTool.find((c) => c.name === "工具执行")?.passed, false);
  const wrongOrder = checkProjectResult(item, { ...result, toolsUsed: [...result.toolsUsed].reverse() });
  assert.equal(wrongOrder.find((c) => c.name === "工具执行")?.passed, false);
});

test("unknown questions do not inflate retrieval hits, invalid citations and truncated output fail", () => {
  const unknown = checkProjectResult({ ...item, sources: [], patterns: ["未提供"], tools: [], calculation: undefined }, { ...result, answer: "当前知识库未提供这项信息。", toolsUsed: [] });
  assert.equal(unknown.find((c) => c.name === "检索依据")?.passed, null);
  assert.equal(unknown.find((c) => c.name === "引用编号")?.passed, null);
  assert.equal(checkProjectResult(item, { ...result, answer: "6 [9]" }).find((c) => c.name === "引用编号")?.passed, false);
  assert.equal(checkProjectResult(item, { ...result, finishReason: "length" }).find((c) => c.name === "请求完成")?.passed, false);
});
