#!/usr/bin/env bun
import { rename } from "node:fs/promises";
import { extname } from "node:path";

import { log, runOrThrow } from "./shell.ts";

export const TARGET_LUFS = -18;
const TRUE_PEAK_DBTP = -2;
const LOUDNESS_RANGE_LU = 11;
const TOLERANCE_LU = 2;
const LIMITER_CEILING = 10 ** ((TRUE_PEAK_DBTP - 1) / 20);
const ENCODERS: Record<string, string> = { aac: "aac", mp3: "libmp3lame" };

export interface Loudness {
  integrated: number;
  truePeak: number;
  range: number;
  threshold: number;
}

function loudnorm(extra = ""): string {
  return `loudnorm=I=${TARGET_LUFS}:TP=${TRUE_PEAK_DBTP}:LRA=${LOUDNESS_RANGE_LU}${extra}:print_format=json`;
}

export function parseLoudnorm(stderr: string): Loudness {
  const start = stderr.lastIndexOf("{");
  const end = stderr.lastIndexOf("}");
  if (start < 0 || end < start) throw new Error("loudnorm printed no measurement");
  const m = JSON.parse(stderr.slice(start, end + 1));
  const loudness = {
    integrated: Number(m.input_i),
    truePeak: Number(m.input_tp),
    range: Number(m.input_lra),
    threshold: Number(m.input_thresh),
  };
  if (!Number.isFinite(loudness.integrated)) throw new Error("no audible speech: integrated loudness is -inf");
  return loudness;
}

export function needsNormalizing(loudness: Loudness): boolean {
  return Math.abs(loudness.integrated - TARGET_LUFS) > TOLERANCE_LU;
}

export async function measureLoudness(path: string): Promise<Loudness> {
  const { stderr } = await runOrThrow([
    "ffmpeg", "-hide_banner", "-nostats", "-xerror", "-i", path,
    "-af", loudnorm(), "-f", "null", "-",
  ]).catch((error: Error) => {
    throw new Error(`${path} does not decode cleanly: ${error.message}`);
  });
  return parseLoudnorm(stderr);
}

export async function normalizeLoudness(path: string, measured: Loudness): Promise<void> {
  const ext = extname(path);
  if (!ext) throw new Error(`${path} needs a .m4b or .mp3 extension`);
  const { stdout } = await runOrThrow([
    "ffprobe", "-v", "error", "-select_streams", "a:0",
    "-show_entries", "stream=codec_name,bit_rate,sample_rate", "-of", "json", path,
  ]);
  const stream = JSON.parse(stdout).streams[0];
  const encoder = ENCODERS[stream.codec_name];
  if (!encoder) throw new Error(`cannot re-encode ${stream.codec_name} audio in ${path}`);
  const bitrate = `${Math.round(Number(stream.bit_rate ?? 64000) / 1000)}k`;
  const temp = `${path.slice(0, -ext.length)}.normalizing${ext}`;
  const measuredArgs =
    `:measured_I=${measured.integrated}:measured_TP=${measured.truePeak}` +
    `:measured_LRA=${measured.range}:measured_thresh=${measured.threshold}:linear=true`;

  // loudnorm resamples to 192 kHz internally; -ar restores the source rate
  await runOrThrow([
    "ffmpeg", "-v", "error", "-y", "-i", path,
    "-map", "0:a", "-map_metadata", "0", "-map_chapters", "0",
    "-af", `${loudnorm(measuredArgs)},aresample=${stream.sample_rate},alimiter=limit=${LIMITER_CEILING.toFixed(3)}:attack=1:level=false`,
    "-c:a", encoder, "-b:a", bitrate, "-ar", stream.sample_rate,
    ...(encoder === "aac" ? ["-movflags", "+faststart"] : []),
    temp,
  ]);
  await rename(temp, path);
}

export async function verifyBook(path: string): Promise<void> {
  log("Checking decode and loudness");
  const measured = await measureLoudness(path);
  log(`  ${measured.integrated.toFixed(1)} LUFS integrated, true peak ${measured.truePeak.toFixed(1)} dBTP (target ${TARGET_LUFS} ±${TOLERANCE_LU})`);
  if (!needsNormalizing(measured)) return;
  log(`  Normalizing to ${TARGET_LUFS} LUFS, keeping chapters and metadata`);
  await normalizeLoudness(path, measured);
}

if (import.meta.main) {
  const files = Bun.argv.slice(2);
  if (files.length === 0) {
    console.log("Usage: scripts/normalize_audiobook.sh BOOK.m4b|BOOK.mp3 ...\nMeasures loudness and re-encodes only when it is off target.");
    process.exit(1);
  }
  (async () => { for (const file of files) await verifyBook(file); })().catch((error: Error) => {
    console.error(`error: ${error.message}`);
    process.exit(1);
  });
}
