import { expect, test } from "bun:test";
import { mkdtemp, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { assertPlausibleTranscript, countWords, discardVoiceReference, fingerprintOf, needsRegeneration, prepareCover } from "./prep.ts";

const PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
  "base64",
);
const GIF = Buffer.from("R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7", "base64");

async function bookDir(): Promise<string> {
  return mkdtemp(join(tmpdir(), "toni-cover-"));
}

test("finds cover.jpg or cover.png next to the book", async () => {
  const dir = await bookDir();
  expect(await prepareCover(undefined, dir)).toBeUndefined();
  await writeFile(join(dir, "cover.png"), PNG);
  expect(await prepareCover(undefined, dir)).toBe("cover.png");
});

test("copies an explicit cover into the book folder under a normalised name", async () => {
  const dir = await bookDir();
  const elsewhere = await bookDir();
  await writeFile(join(elsewhere, "Art.PNG"), PNG);
  expect(await prepareCover(join(elsewhere, "Art.PNG"), dir)).toBe("cover.png");
  expect(await Bun.file(join(dir, "cover.png")).exists()).toBe(true);
});

test("rejects unsupported, oversized and mislabelled covers", async () => {
  const dir = await bookDir();
  await writeFile(join(dir, "art.gif"), GIF);
  await expect(prepareCover(join(dir, "art.gif"), dir)).rejects.toThrow("jpg or .png");
  await writeFile(join(dir, "big.png"), Buffer.alloc(8 * 1024 * 1024 + 1));
  await expect(prepareCover(join(dir, "big.png"), dir)).rejects.toThrow("8 MB");
  await writeFile(join(dir, "fake.png"), "not an image");
  await expect(prepareCover(join(dir, "fake.png"), dir)).rejects.toThrow("valid JPEG or PNG");
  await writeFile(join(dir, "gif.png"), GIF);
  await expect(prepareCover(join(dir, "gif.png"), dir)).rejects.toThrow("valid JPEG or PNG");
});

test("an invalid auto-detected cover is skipped, a valid one beside it is used", async () => {
  const dir = await bookDir();
  await writeFile(join(dir, "cover.jpg"), "not an image");
  expect(await prepareCover(undefined, dir)).toBeUndefined();
  await writeFile(join(dir, "cover.jpg"), Buffer.alloc(8 * 1024 * 1024 + 1));
  expect(await prepareCover(undefined, dir)).toBeUndefined();
  await writeFile(join(dir, "cover.png"), PNG);
  expect(await prepareCover(undefined, dir)).toBe("cover.png");
});

test("an artifact is redone when its source fingerprint changes or the artifact is missing", () => {
  expect(needsRegeneration(true, "10-abc\n", "10-abc")).toBe(false);
  expect(needsRegeneration(true, "10-abc", "11-def")).toBe(true);
  expect(needsRegeneration(true, undefined, "10-abc")).toBe(true);
  expect(needsRegeneration(false, "10-abc", "10-abc")).toBe(true);
});

test("a failed voice reference is discarded entirely so the next run starts clean", async () => {
  const dir = await bookDir();
  for (const name of ["voice_ref.wav", "voice_ref.txt", "voice_ref.fingerprint", "voice_ref.source", "source.txt"]) {
    await writeFile(join(dir, name), "x");
  }
  await discardVoiceReference(dir);
  expect(await Bun.file(join(dir, "voice_ref.wav")).exists()).toBe(false);
  expect(await Bun.file(join(dir, "voice_ref.txt")).exists()).toBe(false);
  expect(await Bun.file(join(dir, "voice_ref.fingerprint")).exists()).toBe(false);
  expect(await Bun.file(join(dir, "voice_ref.source")).exists()).toBe(false);
  expect(await Bun.file(join(dir, "source.txt")).exists()).toBe(true);
});

test("fingerprint changes with the clip contents", async () => {
  const dir = await bookDir();
  const clip = join(dir, "voice_ref.wav");
  await writeFile(clip, "aaaa");
  const first = await fingerprintOf(clip);
  await writeFile(clip, "aaab");
  expect(await fingerprintOf(clip)).not.toBe(first);
});

test("words are counted per language, not by whitespace", () => {
  expect(countWords("Thank you.")).toBe(2);
  expect(countWords("你好，今天天气很好，我们一起去公园散步吧。")).toBeGreaterThan(6);
});

test("transcript needs at least 1 word per second", () => {
  expect(() => assertPlausibleTranscript("one two three four five six", 6)).not.toThrow();
  expect(() => assertPlausibleTranscript("Thank you.", 7)).toThrow("no clear speech");
  expect(() => assertPlausibleTranscript("", 5)).toThrow("0 words");
});

test("a Chinese transcript passes the plausibility check", () => {
  expect(() => assertPlausibleTranscript("你好，今天天气很好，我们一起去公园散步吧。", 7)).not.toThrow();
});
