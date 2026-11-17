import { readFile, mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { readNDJSON } from "../lib/ndjson.ts";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const args = process.argv.slice(2);
const limitIndex = args.indexOf("--limit");
const limit = limitIndex < 0 ? 8 : Number(args[limitIndex + 1]);
if (!Number.isInteger(limit) || limit < 1 || limit > 8) throw new Error("--limit 必须为 1–8。");
const think = args.includes("--think");
const model = process.env.EVAL_MODEL || "qwen3:14b";
const base = process.env.LAB_URL || "http://127.0.0.1:3010";
const cases = JSON.parse(await readFile(path.join(root, "eval/cases.json"), "utf8")).slice(0, limit);
const results = [];
for (const item of cases) {
  let answer = "";
  let completed = false;
  let metrics;
  try {
    const response = await fetch(`${base}/api/chat`, {
      method: "POST", headers: { "Content-Type": "application/json" }, signal: AbortSignal.timeout(195_000),
      body: JSON.stringify({ model, think, system: "你是一位准确的中文助手。遵循输出格式，不知道时明确说明。", messages: [...(item.history || []), { role: "user", content: item.prompt }] }),
    });
    if (!response.ok) throw new Error((await response.json()).error || `HTTP ${response.status}`);
    for await (const event of readNDJSON(response.body)) {
      if (event.error) throw new Error(event.error);
      answer += event.message?.content || "";
      if (event.done) { completed = true; metrics = event.lab; }
    }
    if (!completed) throw new Error("响应未完成。");
    let passed = null;
    if (item.check === "exact") passed = answer.trim() === item.expected;
    if (item.check === "json") {
      try { const actual = JSON.parse(answer); passed = Object.keys(actual).length === Object.keys(item.expected).length && Object.entries(item.expected).every(([key, value]) => actual[key] === value); }
      catch { passed = false; }
    }
    results.push({ ...item, answer, passed, metrics });
    console.log(`${item.id}: ${passed === null ? "待人工评测" : passed ? "PASS" : "FAIL"} — ${answer.slice(0, 100)}`);
  } catch (error) {
    results.push({ ...item, answer, passed: false, error: error.message });
    console.log(`${item.id}: ERROR — ${error.message}`);
  }
}
const output = { createdAt: new Date().toISOString(), model, think, results };
await mkdir(path.join(root, ".local"), { recursive: true });
const filename = path.join(root, ".local", `eval-${Date.now()}.json`);
await writeFile(filename, JSON.stringify(output, null, 2) + "\n");
console.log(`已保存：${filename}`);
if (results.some((r) => r.passed === false)) process.exitCode = 1;
