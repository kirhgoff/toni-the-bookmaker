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

export async function prepareSource(input: string, dest: string): Promise<void> {
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
