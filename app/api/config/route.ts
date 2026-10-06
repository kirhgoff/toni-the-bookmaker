import { NextRequest, NextResponse } from "next/server";
import { authorized } from "@/src/web/auth";
import { getConfig } from "@/src/web/jobs";

export const runtime = "nodejs";
export function GET(request: NextRequest) {
  if (!authorized(request)) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  return NextResponse.json(getConfig());
}
