import { recentRuns } from "@/lib/runs";
export const dynamic = "force-dynamic";
export async function GET() {
  return Response.json({ runs: await recentRuns() }, { headers: { "Cache-Control": "no-store" } });
}
