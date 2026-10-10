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
