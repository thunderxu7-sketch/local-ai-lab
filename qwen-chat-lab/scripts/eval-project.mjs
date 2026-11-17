import { readFile, readdir, mkdir, writeFile, rename } from "node:fs/promises";
import { createHash, randomUUID } from "node:crypto";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { readNDJSON } from "../lib/ndjson.ts";
import { checkProjectResult } from "../lib/evaluation.ts";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const args = process.argv.slice(2);
const option = (name, fallback) => { const i = args.indexOf(name); if (i < 0) return fallback; if (!args[i + 1] || args[i + 1].startsWith("--")) throw Error(`${name} 缺少值`); return args[i + 1]; };
const label = option("--label", "项目问答评测");
const requested = option("--ids", "").split(",").filter(Boolean);
const base = process.env.LAB_URL || "http://127.0.0.1:3010";
if (!["127.0.0.1", "localhost", "[::1]"].includes(new URL(base).hostname)) throw Error("项目评测只允许连接本机 Qwen Lab。");
const hash = (text) => createHash("sha256").update(text).digest("hex");
const caseText = await readFile(path.join(root, "eval/project-cases.json"), "utf8");
const allCases = JSON.parse(caseText);
if (requested.some((id) => !allCases.some((item) => item.id === id))) throw Error("--ids 包含未知题号。");
const cases = allCases.filter((item) => !requested.length || requested.includes(item.id));
const knowledgeFiles = await Promise.all((await readdir(path.join(root, "knowledge"))).filter((file) => file.endsWith(".md")).sort().map(async (file) => ({ file, hash: hash(await readFile(path.join(root, "knowledge", file))) })));
const implementation = await Promise.all(["app/api/chat/route.ts", "lib/agent.ts", "lib/tools.ts", "lib/knowledge.ts", "lib/embeddings.ts", "lib/vector-index.ts", "lib/evaluation.ts"].map(async (file) => `${file}\n${await readFile(path.join(root, file), "utf8")}`));
const status = await fetch(`${base}/api/status`).then((r) => r.json());
if (!status.connected) throw Error("本机 Ollama 未连接，请先启动服务。");
const model = process.env.EVAL_MODEL || "qwen3:14b";
if (!status.models.some((m) => m.name === model)) throw Error(`未找到聊天模型 ${model}`);
const tags = await fetch("http://127.0.0.1:11434/api/tags").then((r) => r.json());
const report = {
  version: 1, id: `${Date.now()}-${randomUUID()}`, label, createdAt: new Date().toISOString(), status: "running",
  model, think: args.includes("--think"), system: "你是一位耐心、准确的中文技术助手。回答简洁清晰；不确定时明确说明，不编造事实。遇到算术问题时请调用计算器工具，依据工具结果回答，不要心算猜答案。",
  total: cases.length, caseSetHash: hash(caseText), knowledgeHash: hash(JSON.stringify(knowledgeFiles)), codeHash: hash(implementation.join("\n")), knowledgeFiles,
  modelDigest: tags.models.find((m) => m.name === model)?.digest,
  embeddingDigest: tags.models.find((m) => m.name === "qwen3-embedding:0.6b")?.digest,
  results: [], notes: ["问题与预期在运行前固定；发送给聊天模型的只有问题和系统提示，不含参考答案或评分规则。", "规则检查通过不等于回答正确，内容需对照实际返回原文复核。小样本结果不代表泛化能力。"],
};
const folder = path.join(root, ".local/project-evals");
await mkdir(folder, { recursive: true });
const filename = path.join(folder, `${report.id}.json`);
const save = async () => { await writeFile(`${filename}.tmp`, JSON.stringify(report, null, 2) + "\n"); await rename(`${filename}.tmp`, filename); };
let interrupted = false;
let active;
process.on("SIGINT", () => { interrupted = true; active?.abort(); });
process.on("SIGTERM", () => { interrupted = true; active?.abort(); });
await save();
console.log(`报告：${filename}`);
for (const item of cases) {
  if (interrupted) break;
  const start = Date.now();
  active = new AbortController();
  const result = { ...item, answer: "", completed: false, durationMs: 0, tokens: 0, toolsUsed: [], checks: [] };
  try {
    const response = await fetch(`${base}/api/chat`, {
      method: "POST", headers: { "Content-Type": "application/json" }, signal: AbortSignal.any([active.signal, AbortSignal.timeout(195_000)]),
      body: JSON.stringify({ model, think: report.think, system: report.system, rag: item.mode === "rag", agent: item.mode === "agent", messages: [{ role: "user", content: item.prompt }] }),
    });
    if (!response.ok) throw Error((await response.json()).error || `HTTP ${response.status}`);
    if (!response.body) throw Error("没有响应流");
    for await (const event of readNDJSON(response.body)) {
      if (event.resetResponse) result.answer = "";
      if (event.message?.content) result.answer += event.message.content;
      if (event.retrieval) result.retrieval = event.retrieval;
      if (event.tool) { const index = result.toolsUsed.findIndex((tool) => tool.id === event.tool.id); if (index < 0) result.toolsUsed.push(event.tool); else result.toolsUsed[index] = event.tool; }
      if (event.error) throw Error(event.error);
      if (event.done) { result.completed = true; result.runId = event.lab?.id; result.tokens = event.eval_count || 0; result.finishReason = event.done_reason; }
    }
    if (!result.completed) throw Error("响应提前结束");
  } catch (error) { result.error = interrupted ? "评测已停止" : error.message; }
  result.durationMs = Date.now() - start;
  result.checks = checkProjectResult(item, result);
  report.results.push(result);
  await save();
  console.log(`${item.id} ${item.mode} ${(result.durationMs / 1000).toFixed(1)}s ${result.checks.some((c) => c.passed === false) ? "需核对" : "规则检查通过"} — ${result.answer.replaceAll("\n", " ").slice(0, 160)}${result.error ? ` ERROR: ${result.error}` : ""}`);
}
report.status = interrupted ? "interrupted" : "complete";
report.finishedAt = new Date().toISOString();
await save();
console.log(`完成 ${report.results.length}/${report.total}，规则检查通过 ${report.results.filter((r) => r.checks.every((c) => c.passed !== false)).length} 题。内容复核待完成。`);
if (interrupted || report.results.some((r) => r.error)) process.exitCode = 1;
