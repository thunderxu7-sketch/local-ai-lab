import { readdir, readFile } from "node:fs/promises";
import path from "node:path";
import type { EvaluationReport } from "@/lib/evaluation";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  const folder = path.join(process.cwd(), ".local/project-evals");
  try {
    const names = (await readdir(folder)).filter((name) => /^\d{13}-[a-f0-9-]{36}\.json$/.test(name)).sort().reverse().slice(0, 12);
    const reports: EvaluationReport[] = [];
    const warnings: string[] = [];
    for (const name of names) {
      try {
        const report = JSON.parse(await readFile(path.join(folder, name), "utf8"));
        if (report.version !== 1 || !Array.isArray(report.results) || !report.id) throw Error("报告格式不正确");
        reports.push(report);
      } catch { warnings.push(`无法读取报告 ${name}`); }
    }
    return Response.json({ reports, warnings }, { headers: { "Cache-Control": "no-store" } });
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return Response.json({ reports: [], warnings: [] });
    return Response.json({ error: "读取本地评测报告失败。" }, { status: 500 });
  }
}
