import { timingSafeEqual } from "node:crypto";
import type { NextRequest } from "next/server";

export function authorized(request: NextRequest) {
  const expected = process.env.WEB_AUTH_TOKEN;
  if (!expected) return true;
  const supplied = request.headers.get("authorization")?.replace(/^Bearer\s+/i, "") ?? "";
  const left = Buffer.from(supplied);
  const right = Buffer.from(expected);
  return left.length === right.length && timingSafeEqual(left, right);
}
