#!/usr/bin/env bun
import { parseArgs } from "node:util";
import { mkdir } from "node:fs/promises";
import { basename, dirname, resolve } from "node:path";

import { prepareSource, prepareVoiceReference, audioDuration } from "./prep.ts";
import { renderLocal, renderRemote, type RenderOptions } from "./render.ts";
import { log, requireCommand, run, runOrThrow } from "./shell.ts";

const USAGE = `Record an audiobook from a text or PDF file.

  toni-record -i INPUT [-v VOICE] [options]

  -i, --input INPUT     Source .txt or .pdf (required)
  -v, --voice VOICE     Voice sample to clone. Omit for a designed voice.
  -n, --name NAME       Output folder name (default: input filename stem)
  -o, --output-dir DIR  Library folder that holds all books (default: $AUDIOBOOK_LIBRARY or ~/Downloads/audiobooks)
  -w, --workers N       Parallel workers (default: 2)
  -b, --bitrate RATE    Audio bitrate (default: 64k)
  -f, --format FORMAT   m4b (default, with chapters) or mp3
  -c, --chapters REGEX  Chapter heading pattern
  -l, --language LANG   Language code (default: en)
  -m, --model MODEL     TTS engine: omni (default), pocket, kani
  -H, --host HOST       Render on a remote GPU host instead of locally
  -d, --detach          Run in the background, surviving terminal and sleep
  -h, --help            This help

Output goes to <output-dir>/<name>/.
Re-running the same command resumes an interrupted render.`;

const PROJECT_DIR = resolve(import.meta.dir, "../..");

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
      outputDir: { type: "string", short: "o" },
      workers: { type: "string", short: "w", default: "2" },
      bitrate: { type: "string", short: "b", default: "64k" },
      format: { type: "string", short: "f", default: "m4b" },
      chapters: { type: "string", short: "c" },
      language: { type: "string", short: "l", default: "en" },
      model: { type: "string", short: "m", default: "omni" },
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
  const out = `${library}/${name}`;
  await mkdir(out, { recursive: true });

  if (values.detach && !process.env.TONI_RECORD_CHILD) {
    await detach(Bun.argv.slice(2), `${out}/render.log`);
    console.log(`Recording '${name}' in the background.`);
    console.log(`Log:    ${out}/render.log`);
    console.log(`Output: ${out}/${name}.${values.format}`);
    return;
  }

  await requireCommand("uv", "See https://astral.sh/uv");
  await requireCommand("ffmpeg", "brew install ffmpeg");

  const source = `${out}/source.txt`;
  if (await Bun.file(source).exists()) {
    log("Source already prepared, reusing");
  } else {
    log("Preparing text");
    await prepareSource(input, source);
  }

  const voiceRef = `${out}/voice_ref.wav`;
  const refTextPath = `${out}/voice_ref.txt`;
  if (voice && !(await Bun.file(voiceRef).exists())) {
    log("Preparing voice reference");
    await prepareVoiceReference(voice, voiceRef);
    log("Transcribing reference (once, so render workers never load Whisper)");
    await runOrThrow([
      "uv", "run", "--project", PROJECT_DIR, "--extra", "omni",
      "python", "-m", "toni.transcribe", voiceRef, "-o", refTextPath,
    ]);
    log(`  "${(await Bun.file(refTextPath).text()).slice(0, 60)}..."`);
  } else if (voice) {
    log("Voice reference already prepared, reusing");
  }

  const options: RenderOptions = {
    projectDir: PROJECT_DIR,
    out,
    name,
    format: values.format!,
    bitrate: values.bitrate!,
    workers: Number.parseInt(values.workers!, 10),
    language: values.language!,
    model: values.model!,
    ...(values.chapters ? { chapterPattern: values.chapters } : {}),
    ...(voice ? { voiceRef } : {}),
    ...((await Bun.file(refTextPath).exists())
      ? { refText: await Bun.file(refTextPath).text() }
      : {}),
  };

  if (values.host) await renderRemote(values.host, options);
  else await renderLocal(options);

  const book = `${out}/${name}.${values.format}`;
  const hours = (await audioDuration(book)) / 3600;
  const size = (Bun.file(book).size / 1e6).toFixed(0);
  const { stdout: chapters } = await run([
    "ffprobe", "-v", "error", "-print_format", "csv", "-show_chapters", book,
  ]);
  const chapterCount = chapters.trim() ? chapters.trim().split("\n").length : 0;
  log(`Done: ${book} (${size} MB, ${hours.toFixed(1)}h, ${chapterCount} chapters)`);
  log(`Intermediate chunks in ${out}/work — safe to delete once you are happy`);
}

main().catch((error: Error) => {
  console.error(`error: ${error.message}`);
  process.exit(1);
});
