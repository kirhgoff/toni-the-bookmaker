import { expect, test } from "bun:test";

import { cliArgs, dockerEnvFlags, type RenderOptions } from "./render.ts";

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

test("passes the seed only when given", () => {
  expect(cliArgs(OPTIONS, "/books", "/books")).not.toContain("--seed");
  const args = cliArgs({ ...OPTIONS, seed: "7" }, "/books", "/books");
  expect(args.slice(args.indexOf("--seed"))[1]).toBe("7");
});

test("passes --no-qc only when QC is off", () => {
  expect(cliArgs(OPTIONS, "/books", "/books")).not.toContain("--no-qc");
  expect(cliArgs({ ...OPTIONS, qc: false }, "/books", "/books")).toContain("--no-qc");
});
