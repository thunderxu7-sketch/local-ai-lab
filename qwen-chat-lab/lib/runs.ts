import { appendFile, mkdir, readFile } from "node:fs/promises";
import path from "node:path";
import type { Run } from "./chat";

const folder = path.join(process.cwd(), ".local");
const file = path.join(folder, "runs.jsonl");

export async function saveRun(run: Run) {
  await mkdir(folder, { recursive: true });
  await appendFile(file, JSON.stringify(run) + "\n", "utf8");
}

export async function recentRuns(): Promise<Run[]> {
  try {
    return (await readFile(file, "utf8")).trim().split("\n").filter(Boolean).slice(-30).reverse().flatMap((line) => {
      try { return [JSON.parse(line) as Run]; } catch { return []; }
    });
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return [];
    throw error;
  }
}
