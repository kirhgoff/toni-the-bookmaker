import { expect, test } from "bun:test";
import { mkdir, mkdtemp, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { pickRunDir } from "./index.ts";

const OLD_RUN = "2026-01-01-0000-omni-local";

async function bookWithRunStartedWith(source: string): Promise<string> {
  const dir = await mkdtemp(join(tmpdir(), "toni-runs-"));
  await mkdir(join(dir, OLD_RUN));
  await writeFile(join(dir, OLD_RUN, "voice_ref.source"), source);
  return dir;
}

test("an unfinished run is resumed only under the voice sample it was started with", async () => {
  const dir = await bookWithRunStartedWith("sample:aaa");
  expect(await pickRunDir(dir, "book", "m4b", "omni-local", "sample:aaa")).toBe(join(dir, OLD_RUN));
  expect(await pickRunDir(dir, "book", "m4b", "omni-local", "sample:bbb")).not.toBe(join(dir, OLD_RUN));
  expect(await pickRunDir(dir, "book", "m4b", "omni-local", "none")).not.toBe(join(dir, OLD_RUN));
});

test("a run that predates the provenance file is still resumed", async () => {
  const dir = await bookWithRunStartedWith("sample:aaa");
  const newer = join(dir, "2026-01-02-0000-omni-local");
  await mkdir(newer);
  expect(await pickRunDir(dir, "book", "m4b", "omni-local", "sample:zzz")).toBe(newer);
});

test("switching the voice sample within the same minute starts a separate run", async () => {
  const dir = await mkdtemp(join(tmpdir(), "toni-runs-"));
  const now = new Date(2026, 0, 5, 9, 30);
  const first = await pickRunDir(dir, "book", "m4b", "omni-local", "sample:aaa", now);
  await mkdir(first);
  await writeFile(join(first, "voice_ref.source"), "sample:aaa");

  const second = await pickRunDir(dir, "book", "m4b", "omni-local", "sample:bbb", now);
  expect(second).toBe(join(dir, "2026-01-05-0930.2-omni-local"));
  await mkdir(second);
  await writeFile(join(second, "voice_ref.source"), "sample:bbb");

  expect(await pickRunDir(dir, "book", "m4b", "omni-local", "sample:aaa", now)).toBe(first);
  expect(await pickRunDir(dir, "book", "m4b", "omni-local", "sample:bbb", now)).toBe(second);
  expect(await pickRunDir(dir, "book", "m4b", "omni-local", "sample:ccc", now)).toBe(join(dir, "2026-01-05-0930.3-omni-local"));
});

test("an unfinished run with a later serial is resumed ahead of the base one", async () => {
  const dir = await mkdtemp(join(tmpdir(), "toni-runs-"));
  for (const run of ["2026-01-05-0930-omni-local", "2026-01-05-0930.2-omni-local", "2026-01-05-0930.10-omni-local"]) {
    await mkdir(join(dir, run));
  }
  expect(await pickRunDir(dir, "book", "m4b", "omni-local", "sample:aaa")).toBe(join(dir, "2026-01-05-0930.10-omni-local"));
});
