import { expect, test } from "bun:test";

import { assertMeetsPreset, loudnormFilter, needsNormalizing, parseLoudnorm, PRESETS, resolvePreset } from "./loudness.ts";

const STDERR = `[Parsed_loudnorm_0 @ 0x7e7020e40] \n{\n\t"input_i" : "-37.14",\n\t"input_tp" : "-19.04",\n\t"input_lra" : "5.30",\n\t"input_thresh" : "-48.27",\n\t"output_i" : "-17.95",\n\t"normalization_type" : "dynamic",\n\t"target_offset" : "-0.05"\n}\n[out#0/null @ 0x7e70206c0] video:0KiB audio:750KiB\n`;

test("parses the JSON block loudnorm prints inside ffmpeg's log", () => {
  const measured = parseLoudnorm(STDERR);
  expect(measured).toEqual({ integrated: -37.14, truePeak: -19.04, range: 5.3, threshold: -48.27 });
  expect(needsNormalizing(measured)).toBe(true);
  expect(needsNormalizing({ ...measured, integrated: -18.9 })).toBe(false);
});

test("rejects a silent file", () => {
  expect(() => parseLoudnorm(STDERR.replace('"-37.14"', '"-inf"'))).toThrow();
});

test("default preset keeps the -18 LUFS / -2 dBTP target", () => {
  expect(resolvePreset("default")).toEqual({ lufs: -18, truePeak: -2, range: 11, tolerance: 2 });
  expect(loudnormFilter(PRESETS.default)).toBe("loudnorm=I=-18:TP=-2:LRA=11:print_format=json");
});

test("acx preset targets -19 LUFS with a -3 dBTP ceiling", () => {
  expect(resolvePreset("acx")).toEqual({ lufs: -19, truePeak: -3, range: 11, tolerance: 1 });
  expect(loudnormFilter(PRESETS.acx, ":linear=true")).toBe("loudnorm=I=-19:TP=-3:LRA=11:linear=true:print_format=json");
});

test("a file at -18 passes the default preset but is judged against the acx target", () => {
  const measured = { integrated: -16.5, truePeak: -3, range: 5, threshold: -30 };
  expect(needsNormalizing(measured, PRESETS.default)).toBe(false);
  expect(needsNormalizing(measured, PRESETS.acx)).toBe(true);
});

test("rejects an unknown preset", () => {
  expect(() => resolvePreset("spotify")).toThrow("Unknown loudness preset");
});

test("acx rejects what its ±1 LU window and -3 dBTP ceiling rule out", () => {
  const quiet = { integrated: -19.4, truePeak: -2.5, range: 5, threshold: -30 };
  expect(needsNormalizing(quiet, PRESETS.acx)).toBe(true);
  const loud = { integrated: -17.9, truePeak: -4, range: 5, threshold: -30 };
  expect(needsNormalizing(loud, PRESETS.acx)).toBe(true);
  expect(needsNormalizing({ ...loud, integrated: -18.5 }, PRESETS.acx)).toBe(false);
  expect(needsNormalizing({ ...loud, integrated: -17.9 }, PRESETS.default)).toBe(false);
});

test("a true peak above the preset ceiling triggers normalizing even when loudness is on target", () => {
  const peaky = { integrated: -18, truePeak: -1, range: 5, threshold: -30 };
  expect(needsNormalizing(peaky, PRESETS.default)).toBe(true);
});

test("a book that still misses the preset after normalizing is an error", () => {
  const stillLoud = { integrated: -19, truePeak: -1.5, range: 5, threshold: -30 };
  expect(() => assertMeetsPreset(stillLoud, PRESETS.acx, "book.m4b")).toThrow("still outside the loudness preset");
  expect(() => assertMeetsPreset({ ...stillLoud, truePeak: -3.2 }, PRESETS.acx, "book.m4b")).not.toThrow();
});
