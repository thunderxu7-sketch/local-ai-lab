import { randomUUID } from "node:crypto";
import { validateInput, type ChatEvent, type ChatMessage, type Run, type ToolTrace } from "@/lib/chat";
import { readNDJSON } from "@/lib/ndjson";
import { OLLAMA_URL } from "@/lib/ollama";
import { saveRun } from "@/lib/runs";
import { calculatorTool, executeToolCall, searchKnowledgeTool, validateSearchQuery, type OllamaToolCall } from "@/lib/tools";
import { knowledgePrompt, retrieveKnowledge } from "@/lib/knowledge";
import { AGENT_SYSTEM, MAX_AGENT_SEARCHES, needsCalculationCheck, registerAgentSources } from "@/lib/agent";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type OllamaMessage =
  | { role: "system"; content: string }
  | ChatMessage
  | { role: "assistant"; content: string; thinking?: string; tool_calls: OllamaToolCall[] }
  | { role: "tool"; tool_name: string; content: string };

type OllamaEvent = ChatEvent & {
  message?: ChatEvent["message"] & { tool_calls?: OllamaToolCall[] };
};

const MAX_TOOL_ROUNDS = 3;
const MAX_TOOL_CALLS = 4;

export async function POST(request: Request) {
  const origin = request.headers.get("origin");
  if (origin) {
    try {
      if (new URL(origin).host !== request.headers.get("host")) return Response.json({ error: "只接受同源请求。" }, { status: 403 });
    } catch { return Response.json({ error: "无效的请求来源。" }, { status: 403 }); }
  }

  let input;
  try {
    const raw = await request.text();
    if (raw.length > 100_000) throw new Error("请求过大。");
    input = validateInput(JSON.parse(raw));
  } catch (error) {
    return Response.json({ error: error instanceof Error ? error.message : "请求格式错误。" }, { status: 400 });
  }

  const started = Date.now();
  const upstreamAbort = new AbortController();
  let timedOut = false;
  let disconnected = false;
  const abort = () => { disconnected = true; upstreamAbort.abort(); };
  request.signal.addEventListener("abort", abort, { once: true });
  if (request.signal.aborted) abort();
  const timeout = setTimeout(() => { timedOut = true; upstreamAbort.abort(); }, 180_000);
  const cleanup = () => { clearTimeout(timeout); request.signal.removeEventListener("abort", abort); };
  const run: Run = {
    id: randomUUID(), createdAt: new Date().toISOString(), model: input.model,
    think: input.think, system: input.system, messages: input.messages,
    prompt: input.messages.at(-1)!.content, response: "", status: "error",
    durationMs: 0, firstTokenMs: null, tokens: 0, tokensPerSecond: null, promptTokens: 0, tools: [], rag: input.rag === true, agent: input.agent === true,
  };
  const persist = async () => {
    run.durationMs = Date.now() - started;
    await saveRun(run).catch((error) => console.error("Could not save local run:", error.message));
  };

  const encoder = new TextEncoder();
  const stream = new ReadableStream<Uint8Array>({
    async start(controller) {
      const send = (event: ChatEvent) => {
        if (!disconnected) controller.enqueue(encoder.encode(JSON.stringify(event) + "\n"));
      };
      let totalTokens = 0;
      let totalPromptTokens = 0;
      let totalEvalDuration = 0;
      let finalDoneReason: string | undefined;

      try {
        let system = input.system;
        if (input.agent) system = `${input.system}\n\n${AGENT_SYSTEM}`;
        if (input.rag) {
          run.retrieval = await retrieveKnowledge(run.prompt, upstreamAbort.signal);
          send({ retrieval: run.retrieval });
          if (upstreamAbort.signal.aborted) throw new Error("请求已停止。");
          if (run.retrieval.sources.length === 0) {
            run.response = run.retrieval.documentCount === 0
              ? "当前知识库还没有 Markdown 文档。请将资料放入项目的 knowledge 文件夹后重新提问。"
              : "当前知识库没有检索到足够相关的段落。请补充资料，或更具体地描述问题。";
            run.status = "complete";
            run.finishReason = "no_sources";
            await persist();
            send({ message: { content: run.response } });
            send({ done: true, done_reason: "no_sources", eval_count: 0, lab: { id: run.id, durationMs: run.durationMs, firstTokenMs: null } });
            return;
          }
          system = `${input.system}\n\n${knowledgePrompt(run.retrieval)}`;
        }
        const messages: OllamaMessage[] = [
          ...(system.trim() ? [{ role: "system" as const, content: system }] : []),
          // Each RAG/Agent task starts fresh; only tool results within this task become evidence.
          ...(input.rag || input.agent ? [input.messages.at(-1)!] : input.messages),
        ];
        let finished = false;
        let callCount = 0;
        let searchCount = 0;

        // Each round either returns the final answer or asks the app to execute a tool.
        for (let round = 0; round <= MAX_TOOL_ROUNDS; round++) {
          if (disconnected) break;
          if (input.agent && JSON.stringify(messages).length > 9000) throw new Error("本次 Agent 工具上下文超过 9000 字符，请缩小任务或缩短文档段落。");
          const upstream = await fetch(`${OLLAMA_URL}/api/chat`, {
            method: "POST", signal: upstreamAbort.signal,
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              model: input.model,
              messages,
              tools: input.agent ? [searchKnowledgeTool, calculatorTool] : input.rag ? undefined : [calculatorTool],
              stream: true, think: input.think, keep_alive: "2m",
              options: { num_ctx: 8192, num_predict: 512, temperature: input.rag || input.agent ? 0.2 : 0.6, top_p: 0.95, seed: 42 },
            }),
          });
          if (!upstream.ok) {
            const detail = await upstream.json().catch(() => ({}));
            throw new Error(detail.error || `Ollama 返回 ${upstream.status}`);
          }
          if (!upstream.body) throw new Error("Ollama 未返回响应流。");

          let assistantText = "";
          let assistantThinking = "";
          const calls: OllamaToolCall[] = [];
          let roundFinished = false;
          for await (const event of readNDJSON<OllamaEvent>(upstream.body)) {
            if (event.error) throw new Error(event.error);
            if (event.message?.thinking) {
              assistantThinking += event.message.thinking;
              send({ message: { thinking: event.message.thinking } });
            }
            if (event.message?.content) {
              if (run.firstTokenMs === null) run.firstTokenMs = Date.now() - started;
              assistantText += event.message.content;
              run.response += event.message.content;
              send({ message: { content: event.message.content } });
            }
            for (const call of event.message?.tool_calls || []) {
              const key = call.id || `index:${call.function.index ?? calls.length}`;
              const existing = calls.findIndex((item) => (item.id || `index:${item.function.index ?? -1}`) === key);
              if (existing < 0) calls.push(call);
              else calls[existing] = { ...calls[existing], ...call, function: { ...calls[existing].function, ...call.function } };
            }
            if (event.done) {
              roundFinished = true;
              totalTokens += event.eval_count || 0;
              totalPromptTokens += event.prompt_eval_count || 0;
              totalEvalDuration += event.eval_duration || 0;
              finalDoneReason = event.done_reason;
            }
          }
          if (!roundFinished) throw new Error("响应提前结束，请重试。");

          if (calls.length === 0) {
            if (input.agent && needsCalculationCheck(assistantText, run.tools!)) {
              run.response = "";
              send({ resetResponse: true, notice: "答案包含算式，正在要求模型调用计算器核验…" });
              if (run.agentCorrections || round >= MAX_TOOL_ROUNDS - 1) throw new Error("模型给出了算式，但未成功调用计算器核验。本次任务未完成，请明确要求使用计算器后重试。");
              run.agentCorrections = 1;
              messages.push(
                { role: "assistant", content: assistantText },
                { role: "user", content: "应用核验反馈：你刚才的草稿包含数值计算式，但本次任务尚无成功的 calculate 结果。请现在调用 calculate 核验算式，收到结果后再给出最终回答及来源，不要重复未经核验的草稿。" },
              );
              continue;
            }
            run.status = "complete";
            run.tokens = totalTokens;
            run.promptTokens = totalPromptTokens;
            run.tokensPerSecond = totalEvalDuration ? totalTokens / (totalEvalDuration / 1e9) : null;
            run.finishReason = finalDoneReason;
            if (run.retrieval) {
              const cited = [...run.response.matchAll(/\[(\d+)\]/g)].map((match) => Number(match[1]));
              const valid = new Set(run.retrieval.sources.map((source) => source.citation));
              if (cited.some((id) => !valid.has(id))) run.retrieval.citationWarning = "回答包含无对应段落的引用编号，请对照原文核对。";
              send({ retrieval: run.retrieval });
            }
            await persist();
            send({
              done: true, done_reason: finalDoneReason, eval_count: totalTokens,
              eval_duration: totalEvalDuration, prompt_eval_count: totalPromptTokens,
              lab: { id: run.id, durationMs: run.durationMs, firstTokenMs: run.firstTokenMs },
            });
            finished = true;
            break;
          }

          if (round === MAX_TOOL_ROUNDS) throw new Error("模型连续请求工具，已达到最大调用轮数。");
          if (callCount + calls.length > MAX_TOOL_CALLS) throw new Error("单次对话的工具调用次数已达上限。");
          callCount += calls.length;
          messages.push({ role: "assistant", content: assistantText, ...(assistantThinking ? { thinking: assistantThinking } : {}), tool_calls: calls });
          if (input.agent) {
            run.response = "";
            send({ resetResponse: true });
          }

          for (const call of calls) {
            const trace: ToolTrace = {
              id: call.id || randomUUID(),
              name: call.function.name,
              args: call.function.arguments && typeof call.function.arguments === "object" && !Array.isArray(call.function.arguments)
                ? call.function.arguments as Record<string, unknown>
                : {},
              status: "running",
              step: run.tools!.length + 1,
              round: round + 1,
            };
            run.tools!.push(trace);
            send({ tool: trace });

            const toolStarted = Date.now();
            let toolResult: unknown;
            try {
              upstreamAbort.signal.throwIfAborted();
              if (input.agent && call.function.name === "search_knowledge") {
                if (searchCount >= MAX_AGENT_SEARCHES) throw new Error("本次任务已检索两次。请根据已有资料回答，缺少信息时明确说明。");
                searchCount++;
                const query = validateSearchQuery(call.function.arguments);
                const found = await retrieveKnowledge(query, upstreamAbort.signal);
                const registered = registerAgentSources(run.retrieval, found, run.prompt);
                run.retrieval = registered.aggregate;
                trace.retrieval = registered.search;
                trace.result = registered.search.sources.length ? `找到 ${registered.search.sources.length} 个原文片段，来源 ${registered.search.sources.map((source) => `[${source.citation}]`).join(" ")}` : "没有找到足够相关的原文。";
                toolResult = registered.content;
                send({ retrieval: run.retrieval });
              } else {
                const calculated = executeToolCall(call);
                toolResult = calculated;
                trace.result = calculated.result;
              }
              trace.status = "complete";
            } catch (error) {
              const detail = error instanceof Error ? error.message : "工具执行失败。";
              trace.status = disconnected ? "cancelled" : "error";
              trace.result = detail;
              toolResult = { error: detail };
              if (upstreamAbort.signal.aborted) throw error;
            } finally {
              trace.durationMs = Date.now() - toolStarted;
              send({ tool: trace });
            }
            messages.push({
              role: "tool", tool_name: call.function.name,
              content: JSON.stringify(toolResult),
            });
          }
        }
        if (!disconnected && !finished) throw new Error("工具调用后模型没有给出最终回答。");
      } catch (error) {
        run.status = disconnected ? "cancelled" : "error";
        run.error = timedOut ? "请求超过 180 秒，请缩短问题或关闭思考后重试。" : error instanceof Error ? error.message : "生成失败。";
        if (!disconnected) send({ error: run.error });
      } finally {
        cleanup();
        run.tokens = totalTokens;
        run.promptTokens = totalPromptTokens;
        run.tokensPerSecond = totalEvalDuration ? totalTokens / (totalEvalDuration / 1e9) : null;
        if (run.status !== "complete") await persist();
        if (!disconnected) controller.close();
      }
    },
    cancel() { abort(); },
  });
  return new Response(stream, { headers: { "Content-Type": "application/x-ndjson; charset=utf-8", "Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no" } });
}
