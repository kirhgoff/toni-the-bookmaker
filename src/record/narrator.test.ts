import { expect, test } from "bun:test";

import { narratorPlan, requestedSource, sha1Hex, type NarratorInput } from "./narrator.ts";

const BASE: NarratorInput = {
  model: "omni", language: "en", seed: "0", instruct: "", refExists: false, redesign: false,
};

const withStored = (input: NarratorInput): NarratorInput => ({
  ...input, refExists: true, storedSource: requestedSource(input),
});

test("designs the narrator once when there is no voice sample", () => {
  expect(narratorPlan(BASE)).toBe("design");
  expect(narratorPlan(withStored(BASE))).toBe("reuse");
});

test("a designed narrator is replaced by a later -v sample", () => {
  const designed = withStored(BASE);
  const sample = { ...designed, voiceSha1: "abc" };
  expect(narratorPlan(sample)).toBe("clone");
  expect(narratorPlan(withStored(sample))).toBe("reuse");
});

test("an old -v clone is not reused once -v is omitted", () => {
  const cloned = withStored({ ...BASE, voiceSha1: "abc" });
  expect(narratorPlan({ ...cloned, voiceSha1: undefined })).toBe("design");
});

test("a changed -v sample is cloned again", () => {
  const cloned = withStored({ ...BASE, voiceSha1: "abc" });
  expect(narratorPlan({ ...cloned, voiceSha1: "def" })).toBe("clone");
});

test("a changed seed, instruct or language redesigns the narrator", () => {
  const designed = withStored(BASE);
  expect(narratorPlan({ ...designed, seed: "1" })).toBe("design");
  expect(narratorPlan({ ...designed, instruct: "female, low pitch" })).toBe("design");
  expect(narratorPlan({ ...designed, language: "ru" })).toBe("design");
});

test("--redesign-voice forces a new reference, with or without -v", () => {
  expect(narratorPlan({ ...withStored(BASE), redesign: true })).toBe("design");
  const cloned = withStored({ ...BASE, voiceSha1: "abc" });
  expect(narratorPlan({ ...cloned, redesign: true })).toBe("clone");
});

test("a reference without provenance or audio is prepared again", () => {
  expect(narratorPlan({ ...BASE, refExists: true })).toBe("design");
  expect(narratorPlan({ ...withStored(BASE), refExists: false })).toBe("design");
});

test("leaves other engines and unsupported languages without a designed narrator", () => {
  expect(narratorPlan({ ...BASE, model: "pocket" })).toBe("none");
  expect(narratorPlan({ ...BASE, language: "de" })).toBe("none");
  expect(narratorPlan({ ...BASE, language: "ru-RU" })).toBe("design");
  expect(narratorPlan({ ...BASE, model: "pocket", voiceSha1: "abc" })).toBe("clone");
});

test("provenance strings follow the documented format", () => {
  expect(requestedSource({ ...BASE, voiceSha1: "abc" })).toBe("sample:abc");
  expect(requestedSource({ ...BASE, seed: "7", instruct: "x" })).toBe(`designed:7:${sha1Hex("xen")}`);
});
