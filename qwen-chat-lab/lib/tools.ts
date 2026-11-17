import { calculate, type CalculateArgs, type Operation } from "./calculator.ts";

export type OllamaToolCall = {
  id?: string;
  function: { index?: number; name: string; arguments: unknown };
};

export const calculatorTool = {
  type: "function",
  function: {
    name: "calculate",
    description: "精确计算两个数字的加、减、乘、除。遇到算术问题时使用，不要心算猜答案。",
    parameters: {
      type: "object",
      properties: {
        a: { type: "number", description: "第一个数" },
        b: { type: "number", description: "第二个数" },
        operation: { type: "string", enum: ["add", "subtract", "multiply", "divide"] },
      },
      required: ["a", "b", "operation"],
    },
  },
} as const;

export const searchKnowledgeTool = {
  type: "function",
  function: {
    name: "search_knowledge",
    description: "用本地向量检索查找知识库中的规则、限制、操作说明和事实。返回最多两个原文片段及引用编号。涉及文档中的数值时先查询，取得数值后再调用 calculate。",
    parameters: {
      type: "object",
      properties: { query: { type: "string", description: "包含主题和所需信息的完整检索问题", minLength: 1, maxLength: 2000 } },
      required: ["query"],
      additionalProperties: false,
    },
  },
} as const;

export function validateSearchQuery(raw: unknown): string {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) throw new Error("检索参数必须是 JSON 对象。");
  const args = raw as Record<string, unknown>;
  if (Object.keys(args).some((key) => key !== "query")) throw new Error("检索工具只接受 query 参数。");
  if (typeof args.query !== "string" || !args.query.trim() || args.query.length > 2000) throw new Error("检索问题必须是 1–2000 字符的文本。");
  return args.query.trim();
}

/** Dispatch only explicitly implemented tools; never execute model-supplied code. */
export function executeToolCall(call: OllamaToolCall): { result: number } {
  if (call.function.name !== "calculate") throw new Error(`未注册的工具：${call.function.name}`);
  const raw = call.function.arguments;
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) throw new Error("计算器参数必须是 JSON 对象");
  const value = raw as Record<string, unknown>;
  if (typeof value.a !== "number" || typeof value.b !== "number") throw new Error("a 和 b 必须是数字");
  const operations: Operation[] = ["add", "subtract", "multiply", "divide"];
  if (typeof value.operation !== "string" || !operations.includes(value.operation as Operation)) throw new Error("不支持的运算");
  const args: CalculateArgs = { a: value.a, b: value.b, operation: value.operation as Operation };
  return { result: calculate(args) };
}
