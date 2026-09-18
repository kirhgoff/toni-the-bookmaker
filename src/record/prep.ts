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
const MAX_UNTRIMMED = 12;
const MIN_CLIP = 3;

/**
 * Cut the voice sample to a short clip bounded by natural pauses.
 *
 * The reference is prepended as conditioning to every generation, so its
 * length is a per-chunk cost paid thousands of times; OmniVoice recommends
 * 3-10s.
 */
export async function prepareVoiceReference(source: string, dest: string): Promise<void> {
  const total = await audioDuration(source);

  let from = 0;
  let to = total;
  if (total > MAX_UNTRIMMED) {
    const silences = await detectSilences(source);
    const lead = silences.find((s) => s.start < 1);
    from = lead ? lead.end : 0;

    const candidates = silences.filter((s) => s.start >= from + MIN_CLIP);
    const best = candidates
      .map((s) => ({ at: s.start, delta: Math.abs(s.start - (from + TARGET_SECONDS)) }))
      .sort((a, b) => a.delta - b.delta)[0];
    to = best ? best.at : Math.min(from + TARGET_SECONDS, total);
  }

  await runOrThrow([
    "ffmpeg", "-v", "error", "-y",
    "-i", source,
    "-ss", from.toFixed(3), "-to", to.toFixed(3),
    "-ar", "24000", "-ac", "1",
    dest,
  ]);
  log(`  voice reference trimmed to ${(to - from).toFixed(1)}s`);
}
