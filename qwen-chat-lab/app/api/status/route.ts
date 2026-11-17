import { OLLAMA_URL } from "@/lib/ollama";
export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const response = await fetch(`${OLLAMA_URL}/api/tags`, { cache: "no-store", signal: AbortSignal.timeout(5000) });
    if (!response.ok) throw new Error("Ollama 返回异常。");
    const data = await response.json();
    const models = await Promise.all(data.models.map(async (m: { name: string; size: number; capabilities?: string[] }) => {
      let capabilities = m.capabilities;
      if (!capabilities) {
        const detail = await fetch(`${OLLAMA_URL}/api/show`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ model: m.name }), signal: AbortSignal.timeout(5000) });
        if (!detail.ok) return null;
        capabilities = (await detail.json()).capabilities;
      }
      return capabilities?.includes("completion") ? { name: m.name, size: m.size } : null;
    }));
    return Response.json({ connected: true, models: models.filter(Boolean) });
  } catch {
    return Response.json({ connected: false, models: [], error: "无法连接 Ollama，请在终端运行 ollama serve。" }, { status: 503 });
  }
}
