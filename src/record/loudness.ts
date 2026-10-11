#!/usr/bin/env bun
import { rename, rm } from "node:fs/promises";
import { extname } from "node:path";
import { parseArgs } from "node:util";

import { log, runOrThrow } from "./shell.ts";

export interface LoudnessPreset {
  lufs: number;
  truePeak: number;
  range: number;
  tolerance: number;
  enforcePeak: boolean;
}

export const PRESETS = {
  default: { lufs: -18, truePeak: -2, range: 11, tolerance: 2, enforcePeak: false },
  acx: { lufs: -19, truePeak: -3, range: 11, tolerance: 1, enforcePeak: true },
} as const satisfies Record<string, LoudnessPreset>;

export type PresetName = keyof typeof PRESETS;

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

const MAX_NORMALIZE_ATTEMPTS = 3;

export function initialCeiling(preset: LoudnessPreset): number {
  return preset.truePeak - 1;
}

export function lowerCeiling(ceilingDb: number, normalized: Loudness, preset: LoudnessPreset): number {
  return ceilingDb - (normalized.truePeak - preset.truePeak) - 0.5;
}

export function raisedTarget(targetLufs: number, normalized: Loudness, preset: LoudnessPreset): number {
  const recovered = targetLufs + preset.lufs - normalized.integrated;
  return Math.min(Math.max(recovered, preset.lufs), preset.lufs + preset.tolerance);
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
  return Math.abs(loudness.integrated - preset.lufs) > preset.tolerance ||
    (preset.enforcePeak && loudness.truePeak > preset.truePeak);
}

function describeLoudness(loudness: Loudness, preset: LoudnessPreset): string {
  return `${loudness.integrated.toFixed(1)} LUFS integrated (target ${preset.lufs} ±${preset.tolerance}), ` +
    `true peak ${loudness.truePeak.toFixed(1)} dBTP (max ${preset.truePeak})`;
}

export function assertMeetsPreset(loudness: Loudness, preset: LoudnessPreset, path: string): void {
  if (needsNormalizing(loudness, preset)) {
    throw new Error(`${path} is still outside the loudness preset after normalizing (the file is kept): ${describeLoudness(loudness, preset)}`);
  }
}

function warnAboutPeak(loudness: Loudness, preset: LoudnessPreset): void {
  if (!preset.enforcePeak && loudness.truePeak > preset.truePeak) {
    log(`  Warning: true peak ${loudness.truePeak.toFixed(1)} dBTP is above ${preset.truePeak} dBTP; use --loudness acx to enforce a ceiling`);
  }
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
  ceilingDb: number = initialCeiling(preset),
  targetLufs: number = preset.lufs,
): Promise<string> {
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

  const target = { ...preset, lufs: targetLufs };
  // loudnorm resamples to 192 kHz internally; -ar restores the source rate
  await runOrThrow([
    "ffmpeg", "-v", "error", "-y", "-i", path,
    "-map", "0:a", "-map_metadata", "0", "-map_chapters", "0",
    "-af", `${loudnormFilter(target, measuredArgs)},alimiter=limit=${(10 ** (ceilingDb / 20)).toFixed(3)}:attack=1:level=false,aresample=${stream.sample_rate}`,
    "-c:a", encoder, "-b:a", bitrate, "-ar", stream.sample_rate,
    ...(encoder === "aac" ? ["-movflags", "+faststart"] : []),
    temp,
  ]).catch(async (error: Error) => {
    await rm(temp, { force: true });
    throw error;
  });
  return temp;
}

export async function verifyBook(path: string, preset: LoudnessPreset = PRESETS.default): Promise<void> {
  log("Checking decode and loudness");
  const measured = await measureLoudness(path, preset);
  log(`  ${describeLoudness(measured, preset)}`);
  if (!needsNormalizing(measured, preset)) {
    warnAboutPeak(measured, preset);
    return;
  }
  log(`  Normalizing to ${preset.lufs} LUFS, keeping chapters and metadata`);
  let ceiling = initialCeiling(preset);
  let target = preset.lufs;
  let temp = "";
  let normalized = measured;
  for (let attempt = 1; ; attempt++) {
    temp = await normalizeLoudness(path, measured, preset, ceiling, target);
    normalized = await measureLoudness(temp, preset);
    log(`  After normalizing: ${describeLoudness(normalized, preset)}`);
    const overshoot = normalized.truePeak - preset.truePeak;
    if (!preset.enforcePeak || overshoot <= 0 || attempt === MAX_NORMALIZE_ATTEMPTS) break;
    ceiling = lowerCeiling(ceiling, normalized, preset);
    target = raisedTarget(target, normalized, preset);
    log(`  The encoder overshoots the ${preset.truePeak} dBTP ceiling by ${overshoot.toFixed(1)} dB; limiting at ${ceiling.toFixed(1)} dB, aiming at ${target.toFixed(1)} LUFS and encoding again`);
  }
  await rename(temp, path);
  assertMeetsPreset(normalized, preset, path);
  warnAboutPeak(normalized, preset);
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
