import { copyFile, rm } from "node:fs/promises";
import { dirname, extname } from "node:path";

import { log, run, runOrThrow } from "./shell.ts";

const GUTENBERG_START = /\*\*\*\s*START OF (?:THE|THIS) PROJECT GUTENBERG[^\n]*\n/;
const GUTENBERG_END = /\*\*\*\s*END OF (?:THE|THIS) PROJECT GUTENBERG/;

/** Strip Project Gutenberg header and licence footer, if present. */
export function stripBoilerplate(raw: string): { text: string; stripped: number } {
  const start = raw.match(GUTENBERG_START);
  const end = raw.match(GUTENBERG_END);
  const from = start?.index !== undefined ? start.index + start[0].length : 0;
  const to = end?.index !== undefined ? end.index : raw.length;
  const body = raw.slice(from, to).trim();
  return { text: `${body}\n`, stripped: raw.length - body.length };
}

export const CHAPTER_TITLES_FILE = "source.txt.chapters.txt";

export async function prepareSource(input: string, dest: string, projectDir: string): Promise<void> {
  if (extname(input).toLowerCase() === ".epub") {
    await runOrThrow([
      "uv", "run", "--project", projectDir, "python", "-m", "toni.text_extractor",
      input, "-o", dest, "--cover-dir", dirname(dest),
    ]);
    return;
  }
  const raw = await Bun.file(input).text();
  const { text, stripped } = stripBoilerplate(raw);
  if (stripped > 200) log(`  stripped ${stripped} chars of Project Gutenberg boilerplate`);
  await Bun.write(dest, text);
}

export async function audioDuration(path: string): Promise<number> {
  const { stdout } = await runOrThrow([
    "ffprobe", "-v", "error",
    "-show_entries", "format=duration",
    "-of", "default=noprint_wrappers=1:nokey=1",
    path,
  ]);
  return Number.parseFloat(stdout.trim());
}

interface Silence {
  start: number;
  end: number;
}

async function detectSilences(path: string): Promise<Silence[]> {
  const { stderr } = await run([
    "ffmpeg", "-hide_banner", "-i", path,
    "-af", "silencedetect=noise=-30dB:d=0.2",
    "-f", "null", "-",
  ]);

  const silences: Silence[] = [];
  let pending: number | null = null;
  for (const line of stderr.split("\n")) {
    const startMatch = line.match(/silence_start:\s*([\d.]+)/);
    if (startMatch?.[1]) pending = Number.parseFloat(startMatch[1]);
    const endMatch = line.match(/silence_end:\s*([\d.]+)/);
    if (endMatch?.[1] && pending !== null) {
      silences.push({ start: pending, end: Number.parseFloat(endMatch[1]) });
      pending = null;
    }
  }
  return silences;
}

const TARGET_SECONDS = 7;
const MAX_CLIP = 10;
const MIN_CLIP = 3;

/**
 * Cut the voice sample to a short clip that starts and ends on a natural pause,
 * anywhere in the recording; a clip cut mid-word makes F5-TTS-style models
 * speak the transcript's dangling words into the narration.
 *
 * The reference is prepended as conditioning to every generation, so its
 * length is a per-chunk cost paid thousands of times; OmniVoice recommends
 * 3-10s, and F5-TTS silently clips anything over 12s while keeping the full
 * transcript, which makes the model hallucinate the clipped words.
 */
export function pickClipWindow(silences: Silence[], total: number): { from: number; to: number } {
  if (total <= MAX_CLIP) return { from: 0, to: total };

  const edges = [{ start: 0, end: 0 }, ...silences, { start: total, end: total }];
  let best: { from: number; to: number; delta: number } | undefined;
  for (const opening of edges) {
    for (const closing of edges) {
      const length = closing.start - opening.end;
      if (length < MIN_CLIP || length > MAX_CLIP) continue;
      const delta = Math.abs(length - TARGET_SECONDS);
      if (!best || delta < best.delta) best = { from: opening.end, to: closing.start, delta };
    }
  }
  if (best) return { from: best.from, to: best.to };

  const lead = silences.find((s) => s.start < 1);
  const from = lead ? lead.end : 0;
  return { from, to: Math.min(from + MAX_CLIP, total) };
}

export async function prepareVoiceReference(source: string, dest: string): Promise<void> {
  const total = await audioDuration(source);
  const silences = total > MAX_CLIP ? await detectSilences(source) : [];
  const { from, to } = pickClipWindow(silences, total);

  await runOrThrow([
    "ffmpeg", "-v", "error", "-y",
    "-i", source,
    "-ss", from.toFixed(3), "-to", to.toFixed(3),
    "-ar", "24000", "-ac", "1",
    dest,
  ]);
  log(`  voice reference trimmed to ${(to - from).toFixed(1)}s`);
}

const COVER_EXTENSIONS = [".jpg", ".jpeg", ".png"];
const MAX_COVER_BYTES = 8 * 1024 * 1024;

const COVER_CODECS = ["mjpeg", "png"];

async function assertValidCover(path: string): Promise<void> {
  if (Bun.file(path).size > MAX_COVER_BYTES) throw new Error(`Cover is larger than 8 MB: ${path}`);
  const { code, stdout, stderr } = await run([
    "ffprobe", "-v", "error", "-select_streams", "v:0",
    "-show_entries", "stream=codec_name", "-of", "csv=p=0", path,
  ]);
  if (code !== 0 || stderr.trim() || !COVER_CODECS.includes(stdout.trim())) {
    throw new Error(`Cover is not a valid JPEG or PNG image: ${path}`);
  }
}

/** Resolve the cover to a file inside bookDir, so local and remote renders find it the same way. */
export async function prepareCover(explicit: string | undefined, bookDir: string): Promise<string | undefined> {
  if (!explicit) {
    for (const extension of COVER_EXTENSIONS) {
      const found = `${bookDir}/cover${extension}`;
      if (!(await Bun.file(found).exists())) continue;
      try {
        await assertValidCover(found);
      } catch (error) {
        log(`  ignoring ${found}: ${(error as Error).message}; pass --cover to use another image`);
        continue;
      }
      return `cover${extension}`;
    }
    return undefined;
  }

  const extension = extname(explicit).toLowerCase();
  if (!COVER_EXTENSIONS.includes(extension)) throw new Error(`Cover must be a .jpg or .png file: ${explicit}`);
  if (!(await Bun.file(explicit).exists())) throw new Error(`Cover not found: ${explicit}`);
  await assertValidCover(explicit);

  const coverFile = `cover${extension}`;
  if (`${bookDir}/${coverFile}` !== explicit) await copyFile(explicit, `${bookDir}/${coverFile}`);
  return coverFile;
}

const MIN_WORDS_PER_SECOND = 1.0;
const WORD_SEGMENTER = new Intl.Segmenter(undefined, { granularity: "word" });

export function countWords(text: string): number {
  let count = 0;
  for (const part of WORD_SEGMENTER.segment(text)) if (part.isWordLike) count++;
  return count;
}

export async function fingerprintOf(path: string): Promise<string> {
  const bytes = await Bun.file(path).bytes();
  return `${bytes.length}-${new Bun.CryptoHasher("sha1").update(bytes).digest("hex")}`;
}

export function needsRegeneration(artifactExists: boolean, storedFingerprint: string | undefined, fingerprint: string): boolean {
  return !artifactExists || storedFingerprint?.trim() !== fingerprint;
}

export async function discardVoiceReference(bookDir: string): Promise<void> {
  for (const name of ["voice_ref.wav", "voice_ref.txt", "voice_ref.fingerprint", "voice_ref.source"]) {
    await rm(`${bookDir}/${name}`, { force: true });
  }
}

export function assertPlausibleTranscript(transcript: string, clipSeconds: number): void {
  const words = countWords(transcript);
  if (words / clipSeconds >= MIN_WORDS_PER_SECOND) return;
  throw new Error(
    `Voice sample transcript has ${words} words for ${clipSeconds.toFixed(1)}s of audio ` +
    `(expected at least ${MIN_WORDS_PER_SECOND.toFixed(1)}/s). The sample probably has no clear speech; ` +
    "use a clean recording of one speaker talking continuously, then re-run.",
  );
}
