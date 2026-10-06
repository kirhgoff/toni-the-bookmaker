import { afterEach, describe, expect, test } from "bun:test";
import { NextRequest } from "next/server";
import { authorized } from "./auth.ts";

const originalToken = process.env.WEB_AUTH_TOKEN;
afterEach(() => {
  if (originalToken === undefined) delete process.env.WEB_AUTH_TOKEN;
  else process.env.WEB_AUTH_TOKEN = originalToken;
});

describe("web API authorization", () => {
  test("allows local use when no token is configured", () => {
    delete process.env.WEB_AUTH_TOKEN;
    expect(authorized(new NextRequest("http://localhost/api/jobs"))).toBe(true);
  });
  test("requires a matching bearer token when configured", () => {
    process.env.WEB_AUTH_TOKEN = "test-secret-token";
    expect(authorized(new NextRequest("http://localhost/api/jobs"))).toBe(false);
    expect(authorized(new NextRequest("http://localhost/api/jobs", { headers: { authorization: "Bearer wrong" } }))).toBe(false);
    expect(authorized(new NextRequest("http://localhost/api/jobs", { headers: { authorization: "Bearer test-secret-token" } }))).toBe(true);
  });
});
