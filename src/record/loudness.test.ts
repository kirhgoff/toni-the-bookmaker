import { expect, test } from "bun:test";

import { needsNormalizing, parseLoudnorm } from "./loudness.ts";

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
