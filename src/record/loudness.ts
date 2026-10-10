#!/usr/bin/env bun
import { rename } from "node:fs/promises";
import { extname } from "node:path";
import { parseArgs } from "node:util";

import { log, runOrThrow } from "./shell.ts";

export interface LoudnessPreset {
  lufs: number;
  truePeak: number;
  range: number;
}

export const PRESETS = {
  default: { lufs: -18, truePeak: -2, range: 11 },
  acx: { lufs: -19, truePeak: -3, range: 11 },
} as const satisfies Record<string, LoudnessPreset>;

export type PresetName = keyof typeof PRESETS;

const TOLERANCE_LU = 2;
const ENCODERS: Record<string, string> = { aac: "aac", mp3: "libmp3lame" };

export interface Loudness {
  integrated: number;
  truePeak: number;
  range: number;
  threshold: number;
}

export function resolvePreset(name: string): LoudnessPreset {
  if (!(name in PRESETS)) throw new Error(`Unknown loudness preset: ${name} (use ${Object.keys(PRESETS).join(" or ")})`);
  return PRESETS[name as PresetName];
}

export function loudnormFilter(preset: LoudnessPreset, extra = ""): string {
  return `loudnorm=I=${preset.lufs}:TP=${preset.truePeak}:LRA=${preset.range}${extra}:print_format=json`;
}

function limiterCeiling(preset: LoudnessPreset): number {
  return 10 ** ((preset.truePeak - 1) / 20);
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

export function needsNormalizing(loudness: Loudness, preset: LoudnessPreset = PRESETS.default): boolean {
  return Math.abs(loudness.integrated - preset.lufs) > TOLERANCE_LU;
}

export async function measureLoudness(path: string, preset: LoudnessPreset = PRESETS.default): Promise<Loudness> {
  const { stderr } = await runOrThrow([
    "ffmpeg", "-hide_banner", "-nostats", "-xerror", "-i", path,
    "-af", loudnormFilter(preset), "-f", "null", "-",
  ]).catch((error: Error) => {
    throw new Error(`${path} does not decode cleanly: ${error.message}`);
  });
  return parseLoudnorm(stderr);
}

export async function normalizeLoudness(
  path: string,
  measured: Loudness,
  preset: LoudnessPreset = PRESETS.default,
): Promise<void> {
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
    "-af", `${loudnormFilter(preset, measuredArgs)},aresample=${stream.sample_rate},alimiter=limit=${limiterCeiling(preset).toFixed(3)}:attack=1:level=false`,
    "-c:a", encoder, "-b:a", bitrate, "-ar", stream.sample_rate,
    ...(encoder === "aac" ? ["-movflags", "+faststart"] : []),
    temp,
  ]);
  await rename(temp, path);
}

export async function verifyBook(path: string, preset: LoudnessPreset = PRESETS.default): Promise<void> {
  log("Checking decode and loudness");
  const measured = await measureLoudness(path, preset);
  log(`  ${measured.integrated.toFixed(1)} LUFS integrated, true peak ${measured.truePeak.toFixed(1)} dBTP (target ${preset.lufs} ±${TOLERANCE_LU})`);
  if (!needsNormalizing(measured, preset)) return;
  log(`  Normalizing to ${preset.lufs} LUFS, keeping chapters and metadata`);
  await normalizeLoudness(path, measured, preset);
}

if (import.meta.main) {
  const { values, positionals: files } = parseArgs({
    args: Bun.argv.slice(2),
    options: { loudness: { type: "string", default: "default" } },
    allowPositionals: true,
  });
  if (files.length === 0) {
    console.log("Usage: scripts/normalize_audiobook.sh [--loudness default|acx] BOOK.m4b|BOOK.mp3 ...\nMeasures loudness and re-encodes only when it is off target.");
    process.exit(1);
  }
  (async () => {
    const preset = resolvePreset(values.loudness!);
    for (const file of files) await verifyBook(file, preset);
  })().catch((error: Error) => {
    console.error(`error: ${error.message}`);
    process.exit(1);
  });
}
