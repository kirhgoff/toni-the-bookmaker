import { createReadStream } from "node:fs";
import { Readable } from "node:stream";
import { NextRequest, NextResponse } from "next/server";
import { authorized } from "@/src/web/auth";
import { getDownload } from "@/src/web/jobs";

export const runtime = "nodejs";
export async function GET(request: NextRequest, context: { params: Promise<{ id: string }> }) {
  if (!authorized(request)) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  const { id } = await context.params;
  const download = getDownload(id);
  if (!download) return NextResponse.json({ error: "Audiobook is not available." }, { status: 404 });
  const stream = Readable.toWeb(createReadStream(download.path)) as unknown as ReadableStream;
  return new Response(stream, {
    headers: {
      "Content-Type": download.filename.endsWith(".m4b") ? "audio/mp4" : "audio/mpeg",
      "Content-Disposition": `attachment; filename="${download.filename}"`,
      "X-Content-Type-Options": "nosniff",
    },
  });
}
