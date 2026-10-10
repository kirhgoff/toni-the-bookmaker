import { expect, test } from "bun:test";
import { mkdtemp, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { assertPlausibleTranscript, fingerprintOf, needsTranscription, prepareCover } from "./prep.ts";

async function bookDir(): Promise<string> {
  return mkdtemp(join(tmpdir(), "toni-cover-"));
}

test("finds cover.jpg or cover.png next to the book", async () => {
  const dir = await bookDir();
  expect(await prepareCover(undefined, dir)).toBeUndefined();
  await writeFile(join(dir, "cover.png"), "x");
  expect(await prepareCover(undefined, dir)).toBe("cover.png");
});

test("copies an explicit cover into the book folder under a normalised name", async () => {
  const dir = await bookDir();
  const elsewhere = await bookDir();
  await writeFile(join(elsewhere, "Art.JPG"), "x");
  expect(await prepareCover(join(elsewhere, "Art.JPG"), dir)).toBe("cover.jpg");
  expect(await Bun.file(join(dir, "cover.jpg")).exists()).toBe(true);
});

test("rejects unsupported and oversized covers", async () => {
  const dir = await bookDir();
  await writeFile(join(dir, "art.gif"), "x");
  await expect(prepareCover(join(dir, "art.gif"), dir)).rejects.toThrow("jpg or .png");
  await writeFile(join(dir, "big.png"), Buffer.alloc(8 * 1024 * 1024 + 1));
  await expect(prepareCover(join(dir, "big.png"), dir)).rejects.toThrow("8 MB");
});

test("transcript is redone when the clip fingerprint changes or the transcript is missing", () => {
  expect(needsTranscription(true, "10-abc\n", "10-abc")).toBe(false);
  expect(needsTranscription(true, "10-abc", "11-def")).toBe(true);
  expect(needsTranscription(true, undefined, "10-abc")).toBe(true);
  expect(needsTranscription(false, "10-abc", "10-abc")).toBe(true);
});

test("fingerprint changes with the clip contents", async () => {
  const dir = await bookDir();
  const clip = join(dir, "voice_ref.wav");
  await writeFile(clip, "aaaa");
  const first = await fingerprintOf(clip);
  await writeFile(clip, "aaab");
  expect(await fingerprintOf(clip)).not.toBe(first);
});

test("transcript needs at least 1.5 words per second", () => {
  expect(() => assertPlausibleTranscript("one two three four five six", 4)).not.toThrow();
  expect(() => assertPlausibleTranscript("you", 7)).toThrow("no clear speech");
  expect(() => assertPlausibleTranscript("", 5)).toThrow("0 words");
});
