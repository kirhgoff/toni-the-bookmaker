#!/usr/bin/env bun
import { parseArgs } from "node:util";
import { mkdir, readdir, rm } from "node:fs/promises";
import { basename, resolve } from "node:path";

import { narratorPlan, requestedSource, sha1Hex, type NarratorInput } from "./narrator.ts";
import { verifyBook } from "./loudness.ts";
import { prepareSource, prepareVoiceReference, audioDuration } from "./prep.ts";
import { renderLocal, renderRemote, type RenderOptions } from "./render.ts";
import { log, requireCommand, run, runOrThrow } from "./shell.ts";

const USAGE = `Record an audiobook from a text or PDF file.

  toni-record -i INPUT [-v VOICE] [options]

  -i, --input INPUT     Source .txt or .pdf (required)
  -v, --voice VOICE     Voice sample to clone. Omit for a narrator designed once and reused (omni: en, ru).
  --redesign-voice      Prepare the voice reference again (a fresh clone of -v, or the designed narrator for the current --voice-seed)
  -n, --name NAME       Output folder name (default: input filename stem)
  -t, --tag TAG         Run folder suffix explaining the run (default: <model>-<host or local>)
  -o, --output-dir DIR  Library folder that holds all books (default: $AUDIOBOOK_LIBRARY or ~/Downloads/audiobooks)
  -w, --workers N       Parallel workers (default: 2)
  -b, --bitrate RATE    Audio bitrate (default: 64k)
  -p, --pause MS        Pause between sentences and chunks in milliseconds (default: 500)
  -f, --format FORMAT   m4b (default, with chapters) or mp3
  -c, --chapters REGEX  Chapter heading pattern
  -l, --language LANG   Language code (default: en)
  -m, --model MODEL     TTS engine: omni (default), pocket, kani, espeech, qwen
  --no-qc               Skip the ASR check that regenerates garbled or skipped chunks
  --batch N             Chunks per model call for omni (default: auto)
  --seed N              Base seed; same seed and text give the same audio (default: 0)
  --voice-seed N        Seed of the designed narrator; change it to draw a different voice (default: 0)
  -H, --host HOST       Render on a remote GPU host instead of locally
  -d, --detach          Run in the background, surviving terminal and sleep
  -h, --help            This help

Inputs live in <output-dir>/<name>/; each render gets its own
<output-dir>/<name>/<YYYY-MM-DD-HHMM>/ run folder.
Re-running the same command resumes an unfinished run.
An optional <output-dir>/<name>/lexicon.txt ("term = respelling" per line,
# comments) corrects pronunciation across the whole book.`;

const PROJECT_DIR = resolve(import.meta.dir, "../..");

const RUN_DIR_PATTERN = /^\d{4}-\d{2}-\d{2}-\d{4}-(.+)$/;

function timestampedRunName(now: Date, tag: string): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  const stamp = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}-${pad(now.getHours())}${pad(now.getMinutes())}`;
  return `${stamp}-${tag}`;
}

export async function pickRunDir(bookDir: string, name: string, format: string, tag: string): Promise<string> {
  const entries = await readdir(bookDir, { withFileTypes: true }).catch(() => []);
  const runDirs = entries
    .filter((entry) => entry.isDirectory() && RUN_DIR_PATTERN.exec(entry.name)?.[1] === tag)
    .map((entry) => entry.name)
    .sort()
    .reverse();

  for (const runDir of runDirs) {
    const finished = await Bun.file(`${bookDir}/${runDir}/${name}.${format}`).exists();
    if (!finished) return `${bookDir}/${runDir}`;
  }

  return `${bookDir}/${timestampedRunName(new Date(), tag)}`;
}

async function detach(argv: string[], logPath: string): Promise<void> {
  const cmd = ["bun", import.meta.path, ...argv.filter((a) => a !== "-d" && a !== "--detach")];
  const wrapped = process.platform === "darwin" ? ["caffeinate", "-i", ...cmd] : cmd;
  await Bun.write(logPath, "");
  const logFile = Bun.file(logPath);

  Bun.spawn(wrapped, {
    env: { ...process.env, TONI_RECORD_CHILD: "1" },
    stdout: logFile,
    stderr: logFile,
    stdin: "ignore",
  }).unref();
}

async function main(): Promise<void> {
  const { values } = parseArgs({
    args: Bun.argv.slice(2),
    options: {
      input: { type: "string", short: "i" },
      voice: { type: "string", short: "v" },
      name: { type: "string", short: "n" },
      tag: { type: "string", short: "t" },
      outputDir: { type: "string", short: "o" },
      workers: { type: "string", short: "w", default: "2" },
      bitrate: { type: "string", short: "b", default: "64k" },
      pause: { type: "string", short: "p", default: "500" },
      format: { type: "string", short: "f", default: "m4b" },
      chapters: { type: "string", short: "c" },
      language: { type: "string", short: "l", default: "en" },
      model: { type: "string", short: "m", default: "omni" },
      seed: { type: "string" },
      "voice-seed": { type: "string", default: "0" },
      "redesign-voice": { type: "boolean", default: false },
      batch: { type: "string" },
      "no-qc": { type: "boolean", default: false },
      host: { type: "string", short: "H" },
      detach: { type: "boolean", short: "d", default: false },
      help: { type: "boolean", short: "h", default: false },
    },
    allowPositionals: false,
  });

  if (values.help || !values.input) {
    console.log(USAGE);
    process.exit(values.input ? 0 : 1);
  }
  if (!["m4b", "mp3"].includes(values.format!)) {
    throw new Error(`Unsupported format: ${values.format} (use m4b or mp3)`);
  }

  const input = resolve(values.input);
  if (!(await Bun.file(input).exists())) throw new Error(`Input not found: ${input}`);
  const voice = values.voice ? resolve(values.voice) : undefined;
  if (voice && !(await Bun.file(voice).exists())) throw new Error(`Voice sample not found: ${voice}`);

  const name = values.name ?? basename(input).replace(/\.[^.]+$/, "");
  const library = values.outputDir ?? process.env.AUDIOBOOK_LIBRARY ?? `${process.env.HOME}/Downloads/audiobooks`;
  const bookDir = `${library}/${name}`;
  await mkdir(bookDir, { recursive: true });

  const tag = (values.tag ?? `${values.model}-${values.host ?? "local"}`).replace(/[^\w.-]+/g, "-");
  const runDir = await pickRunDir(bookDir, name, values.format!, tag);
  await mkdir(runDir, { recursive: true });

  if (values.detach && !process.env.TONI_RECORD_CHILD) {
    await detach(Bun.argv.slice(2), `${runDir}/render.log`);
    console.log(`Recording '${name}' in the background.`);
    console.log(`Run:    ${runDir}`);
    console.log(`Log:    ${runDir}/render.log`);
    console.log(`Output: ${runDir}/${name}.${values.format}`);
    return;
  }

  await requireCommand("uv", "See https://astral.sh/uv");
  await requireCommand("ffmpeg", "brew install ffmpeg");

  const source = `${bookDir}/source.txt`;
  if (await Bun.file(source).exists()) {
    log("Source already prepared, reusing");
  } else {
    log("Preparing text");
    await prepareSource(input, source);
  }

  const voiceRef = `${bookDir}/voice_ref.wav`;
  const refTextPath = `${bookDir}/voice_ref.txt`;
  const refSourcePath = `${bookDir}/voice_ref.source`;
  const narrator: NarratorInput = {
    ...(voice ? { voiceSha1: sha1Hex(new Uint8Array(await Bun.file(voice).arrayBuffer())) } : {}),
    model: values.model!,
    language: values.language!,
    seed: values["voice-seed"]!,
    instruct: process.env.TONI_OMNI_INSTRUCT ?? "",
    refExists: await Bun.file(voiceRef).exists(),
    redesign: values["redesign-voice"],
    ...((await Bun.file(refSourcePath).exists()) ? { storedSource: (await Bun.file(refSourcePath).text()).trim() } : {}),
  };
  const plan = narratorPlan(narrator);
  if (plan === "design" || plan === "clone") {
    await Promise.all([voiceRef, refTextPath, refSourcePath].map((path) => rm(path, { force: true })));
  }
  if (plan === "design") {
    log("Designing narrator voice (once, so the voice never drifts)");
    await runOrThrow([
      "uv", "run", "--project", PROJECT_DIR, "--extra", "omni",
      "python", "-m", "toni.design_voice", "--out", voiceRef, "--text-out", refTextPath,
      "--language", values.language!, "--seed", values["voice-seed"]!,
    ]);
    log(`Designed narrator voice: listen to ${voiceRef} before the render finishes`);
  } else if (plan === "clone") {
    log("Preparing voice reference");
    await prepareVoiceReference(voice!, voiceRef);
    log("Transcribing reference (once, so render workers never load Whisper)");
    await runOrThrow([
      "uv", "run", "--project", PROJECT_DIR, "--extra", "omni",
      "python", "-m", "toni.transcribe", voiceRef, "-o", refTextPath,
    ]);
    log(`  "${(await Bun.file(refTextPath).text()).slice(0, 60)}..."`);
  } else if (plan === "reuse") {
    log("Voice reference already prepared, reusing");
  }
  if (plan === "design" || plan === "clone") await Bun.write(refSourcePath, requestedSource(narrator)!);

  const lexicon = `${bookDir}/lexicon.txt`;

  const options: RenderOptions = {
    projectDir: PROJECT_DIR,
    bookDir,
    runDir,
    name,
    format: values.format!,
    bitrate: values.bitrate!,
    pauseMs: Number.parseInt(values.pause!, 10),
    workers: Number.parseInt(values.workers!, 10),
    language: values.language!,
    model: values.model!,
    ...(values.seed ? { seed: values.seed } : {}),
    ...(values.batch ? { batch: values.batch } : {}),
    qc: !values["no-qc"],
    ...(values.chapters ? { chapterPattern: values.chapters } : {}),
    ...(plan !== "none" ? { voiceRef } : {}),
    ...((await Bun.file(lexicon).exists()) ? { lexicon } : {}),
    ...((await Bun.file(refTextPath).exists())
      ? { refText: await Bun.file(refTextPath).text() }
      : {}),
  };

  if (values.host) await renderRemote(values.host, options);
  else await renderLocal(options);

  const book = `${runDir}/${name}.${values.format}`;
  await verifyBook(book);
  const hours = (await audioDuration(book)) / 3600;
  const size = (Bun.file(book).size / 1e6).toFixed(0);
  const { stdout: chapters } = await run([
    "ffprobe", "-v", "error", "-print_format", "csv", "-show_chapters", book,
  ]);
  const chapterCount = chapters.trim() ? chapters.trim().split("\n").length : 0;
  if (values.format === "m4b" && chapterCount === 0) {
    log("Warning: no chapters embedded; check the heading pattern (-c) against source.txt");
  }
  log(`Done: ${book} (${size} MB, ${hours.toFixed(1)}h, ${chapterCount} chapters)`);
  log(`Intermediate chunks in ${runDir}/work — safe to delete once you are happy`);
}

if (import.meta.main) {
  main().catch((error: Error) => {
    console.error(`error: ${error.message}`);
    process.exit(1);
  });
}
