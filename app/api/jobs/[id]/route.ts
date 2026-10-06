import { NextRequest, NextResponse } from "next/server";
import { authorized } from "@/src/web/auth";
import { getJob } from "@/src/web/jobs";

export const runtime = "nodejs";
export async function GET(request: NextRequest, context: { params: Promise<{ id: string }> }) {
  if (!authorized(request)) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  const { id } = await context.params;
  const job = getJob(id);
  return job ? NextResponse.json({ job }) : NextResponse.json({ error: "Job not found" }, { status: 404 });
}
