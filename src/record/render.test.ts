import { expect, test } from "bun:test";

import { cliArgs, dockerEnvFlags, remoteScript, type RenderOptions } from "./render.ts";

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
  expect(dockerEnvFlags(OPTIONS, { TONI_NORMALIZE: "0" })).toContain("TONI_NORMALIZE='0'");
});

test("forwards every TONI_QC* setting and TONI_BATCH to the remote container", () => {
  const flags = dockerEnvFlags(OPTIONS, { TONI_QC: "0", TONI_QC_WER: "0.4", TONI_BATCH: "4", TONI_OTHER: "x" }).join(" ");
  expect(flags).toContain("TONI_QC='0'");
  expect(flags).toContain("TONI_QC_WER='0.4'");
  expect(flags).toContain("TONI_BATCH='4'");
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

test("remote renders mount a per-book cache that outlives the run folder", () => {
  const host = { ssh: "u@h", identity: ".ssh/k", shell: "bash -s", workdir: "books" };
  const script = remoteScript(OPTIONS, host, "/home/u/books/book/2026-01-01-0000-omni", "/home/u/books/book/cache");
  expect(script).toContain("-v '/home/u/books/book/cache':/cache");
  expect(script).toContain("'--cache-dir' '/cache'");
  expect(script).not.toContain("/books/cache");
});
