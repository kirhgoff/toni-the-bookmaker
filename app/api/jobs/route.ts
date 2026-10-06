import { NextRequest, NextResponse } from "next/server";
import { authorized } from "@/src/web/auth";
import { createJob, getMaxRequestBytes, listJobs } from "@/src/web/jobs";

export const runtime = "nodejs";
export const maxDuration = 60;

export async function GET(request: NextRequest) {
  if (!authorized(request)) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  return NextResponse.json({ jobs: listJobs() });
}

export async function POST(request: NextRequest) {
  if (!authorized(request)) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  const contentLength = Number(request.headers.get("content-length") ?? 0);
  if (contentLength > getMaxRequestBytes()) return NextResponse.json({ error: "Upload exceeds the server request limit." }, { status: 413 });
  try {
    const job = await createJob(await request.formData());
    return NextResponse.json({ job }, { status: 202 });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unable to start the audiobook render.";
    return NextResponse.json({ error: message }, { status: 400 });
  }
}
