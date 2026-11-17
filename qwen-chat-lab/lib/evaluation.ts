import type { RetrievalTrace } from "./knowledge-types";
import type { ToolTrace } from "./chat";

export type ProjectCase = {
  id: string; category: string; mode: "rag" | "agent"; prompt: string; expected: string;
  sources: string[]; patterns: string[]; tools?: string[];
  calculation?: { operation: string; operands: number[]; result: number };
};
export type EvaluationResult = ProjectCase & {
  answer: string; completed: boolean; error?: string; durationMs: number; tokens: number;
  runId?: string; finishReason?: string; retrieval?: RetrievalTrace; toolsUsed: ToolTrace[];
  checks: { name: string; passed: boolean | null; detail: string }[];
  review?: { passed: boolean; stage: string; note: string };
};
export type EvaluationReport = {
  version: 1; id: string; label: string; createdAt: string; finishedAt?: string;
  status: "running" | "complete" | "interrupted"; model: string; think: boolean; system: string;
  total: number; caseSetHash: string; knowledgeHash: string; codeHash: string;
  modelDigest?: string; embeddingDigest?: string;
  knowledgeFiles: { file: string; hash: string }[];
  results: EvaluationResult[]; notes?: string[];
};

/** These narrow checks flag candidates for review; they do not judge semantic correctness. */
export function checkProjectResult(item: ProjectCase, result: Pick<EvaluationResult, "completed" | "answer" | "retrieval" | "toolsUsed" | "finishReason">): EvaluationResult["checks"] {
  const sources = result.retrieval?.sources || [];
  const cited = [...result.answer.matchAll(/\[(\d+)\]/g)].map((match) => Number(match[1]));
  const validIds = new Set(sources.map((source) => source.citation));
  const missingSources = item.sources.filter((heading) => !sources.some((source) => source.heading.endsWith(heading)));
  const missingPatterns = item.patterns.filter((pattern) => !new RegExp(pattern, "iu").test(result.answer));
  const names = result.toolsUsed.filter((tool) => tool.status === "complete").map((tool) => tool.name);
  const expectedTools = item.tools || [];
  const calculation = item.calculation;
  const calculated = !calculation || result.toolsUsed.some((tool) => tool.name === "calculate" && tool.status === "complete" && tool.args.operation === calculation.operation && tool.result === calculation.result &&
    [tool.args.a, tool.args.b].sort((a, b) => Number(a) - Number(b)).every((n, i) => n === [...calculation.operands].sort((a, b) => a - b)[i]));
  const searchIndex = names.indexOf("search_knowledge");
  const calcIndex = names.indexOf("calculate");
  return [
    { name: "请求完成", passed: result.completed && result.finishReason !== "length", detail: result.completed ? result.finishReason === "length" ? "模型达到输出上限，需核对是否截断" : "收到完成事件" : "请求未完成" },
    { name: "检索依据", passed: item.sources.length ? missingSources.length === 0 : null, detail: item.sources.length ? missingSources.length ? `缺少：${missingSources.join("、")}` : "预期依据出现在返回片段中" : "题目所问信息未收录，不以命中率判断" },
    { name: "回答线索", passed: missingPatterns.length === 0, detail: missingPatterns.length ? `未匹配 ${missingPatterns.length} 项关键线索，需看原文和回答` : "匹配关键线索；语义与事实仍需复核" },
    { name: "引用编号", passed: cited.length ? cited.every((id) => validIds.has(id)) : item.sources.length ? false : null, detail: cited.length ? "仅检查编号是否对应返回片段，不检查是否支持结论" : item.sources.length ? "回答没有来源编号" : "资料缺失回答不强制引用" },
    { name: "工具执行", passed: expectedTools.every((name) => names.includes(name)) && calculated && (!calculation || (searchIndex >= 0 && calcIndex > searchIndex)) && !result.toolsUsed.some((tool) => tool.status !== "complete"), detail: calculation ? "核对检索先于计算，运算、输入数字及结果符合预期" : expectedTools.length ? `应实际执行：${expectedTools.join(" → ")}` : "此题不要求工具链" },
  ];
}
