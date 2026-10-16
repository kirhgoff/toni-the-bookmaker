import { expect, test } from "bun:test";
import { readdirSync } from "node:fs";
import { tmpdir } from "node:os";

import { cliArgs, dockerEnvFlags, getArgv, podmanRunArgv, putArgv, remoteJob, renderFailure, stageInputs, type RenderOptions } from "./render.ts";

const OPTIONS: RenderOptions = {
  projectDir: "/p", bookDir: "/b", runDir: "/b/run", name: "book", format: "m4b",
  bitrate: "64k", pauseMs: 500, workers: 2, language: "en", model: "omni", qc: true,
};

test("passes the lexicon from the input folder only when the book has one", () => {
  expect(cliArgs(OPTIONS, "/books", "/books")).not.toContain("--lexicon");
  const args = cliArgs({ ...OPTIONS, lexicon: "/b/lexicon.txt" }, "/books", "/books");
  expect(args.slice(args.indexOf("--lexicon"))[1]).toBe("/books/lexicon.txt");
});

test("forwards TONI_NORMALIZE to the remote container only when it is set", () => {
  expect(dockerEnvFlags(OPTIONS, {}).join(" ")).not.toContain("TONI_NORMALIZE");
  expect(dockerEnvFlags(OPTIONS, { TONI_NORMALIZE: "0" })).toContain("TONI_NORMALIZE=0");
});

test("forwards every TONI_QC* setting and TONI_BATCH to the remote container", () => {
  const flags = dockerEnvFlags(OPTIONS, { TONI_QC: "0", TONI_QC_WER: "0.4", TONI_BATCH: "4", TONI_OTHER: "x" }).join(" ");
  expect(flags).toContain("TONI_QC=0");
  expect(flags).toContain("TONI_QC_WER=0.4");
  expect(flags).toContain("TONI_BATCH=4");
  expect(flags).not.toContain("TONI_OTHER");
});

test("passes the seed only when given", () => {
  expect(cliArgs(OPTIONS, "/books", "/books")).not.toContain("--seed");
  const args = cliArgs({ ...OPTIONS, seed: "7" }, "/books", "/books");
  expect(args.slice(args.indexOf("--seed"))[1]).toBe("7");
});

test("passes --no-qc only when QC is off", () => {
  expect(cliArgs(OPTIONS, "/books", "/books")).not.toContain("--no-qc");
  expect(cliArgs({ ...OPTIONS, qc: false }, "/books", "/books")).toContain("--no-qc");
});

test("shares one chunk cache per book", () => {
  const args = cliArgs(OPTIONS, "/books", "/out");
  expect(args.slice(args.indexOf("--cache-dir"))[1]).toBe("/books/cache");
});

const NAME = "My Book";
const NAMED = { ...OPTIONS, name: NAME };
const JOB = remoteJob(NAMED, {}, "mac");

test("uploads staged inputs and downloads the book through the localbrains CLI", () => {
  expect(putArgv("/tmp/stage")).toEqual(["localbrains", "put", "/tmp/stage/", "toni/"]);
  expect(getArgv(JOB, "/b/run/book.m4b")).toEqual([
    "localbrains", "get", `toni/${JOB.slug}/run/${JOB.slug}.m4b`, "/b/run/book.m4b",
  ]);
});

test("runs the render as a named, held podman container with per-book cache and shared models", () => {
  const argv = podmanRunArgv(NAMED, JOB, {});
  expect(argv.slice(0, 13)).toEqual([
    "localbrains", "podman", "--as", "toni@mac", "run",
    "--name", `toni-${JOB.slug}`,
    "-v", `./toni/${JOB.slug}/run:/books`,
    "-v", `./toni/${JOB.slug}/cache:/cache`,
    "-v", "toni-models:/models",
  ]);
  expect(argv).toContain("toni:omni");
  expect(argv.slice(argv.indexOf("toni:omni") + 1)).toEqual(cliArgs({ ...NAMED, name: JOB.slug }, "/books", "/books", "/cache"));
});

test("book names are slugified and hash-suffixed so remote paths stay safe and unique", () => {
  const job = remoteJob({ ...OPTIONS, name: "my ../book" }, {}, "mac");
  expect(job.container).toMatch(/^toni-my-\.-book-[0-9a-f]{8}$/);
  expect(job.rel).toBe(`toni/${job.slug}/run`);
  expect(job.output).toBe(`toni/${job.slug}/run/${job.slug}.m4b`);
  expect(remoteJob({ ...OPTIONS, name: "my ../book" }, {}, "mac").slug).toBe(job.slug);
});

test("titles without ASCII letters get distinct slugs", () => {
  const slugOf = (name: string) => remoteJob({ ...OPTIONS, name }, {}, "mac").slug;
  expect(slugOf("Война и мир")).not.toBe(slugOf("Анна Каренина"));
  expect(slugOf("Война и мир")).toMatch(/^[\w.-]+$/);
});

test("exit 75 becomes the busy error carrying the CLI's holder message", () => {
  const error = renderFailure("localbrains", 75, "GPU busy: held by nightcrawl since 10:02\n");
  expect(error?.message).toBe("localbrains GPU is busy or the lease was revoked: GPU busy: held by nightcrawl since 10:02");
  expect(renderFailure("localbrains", 1, "x")?.message).toBe("remote render failed (exit 1)");
  expect(renderFailure("localbrains", 0, "")).toBeUndefined();
});

test("the busy error keeps only the last stderr line, capped in length", () => {
  const noisy = `${"progress line\n".repeat(5000)}${"x".repeat(2000)}\n\n`;
  const message = renderFailure("localbrains", 75, noisy)?.message ?? "";
  expect(message).toBe(`localbrains GPU is busy or the lease was revoked: ${"x".repeat(500)}`);
});

test("a failed staging leaves no temp directory behind", async () => {
  const stages = () => readdirSync(tmpdir()).filter((d) => d.startsWith("toni-stage-"));
  const before = stages();
  const missing = { ...OPTIONS, bookDir: "/nonexistent-book-dir" };
  await expect(stageInputs(missing, remoteJob(missing, {}, "mac"))).rejects.toThrow();
  expect(stages()).toEqual(before);
});
