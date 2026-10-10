import { expect, test } from "bun:test";
import { mkdtemp, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { prepareCover } from "./prep.ts";

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
