import { describe, expect, test } from "bun:test";
import { isWithinRoot, safeTitle, validateOptions, validateVoiceInstruction } from "./jobs.ts";

const hosts = ["render-node"];
const valid = { model: "pocket", format: "m4b", host: "render-node", workers: 1, language: "en", hasVoice: false };

describe("web render options", () => {
  test("accepts safe default settings", () => {
    expect(() => validateOptions(valid, hosts)).not.toThrow();
  });
  test("rejects unknown models and unconfigured hosts", () => {
    expect(() => validateOptions({ ...valid, model: "unknown" }, hosts)).toThrow("supported model");
    expect(() => validateOptions({ ...valid, host: "arbitrary-host" }, hosts)).toThrow("configured remote");
  });
  test("requires a voice sample for engines that cannot design voices", () => {
    expect(() => validateOptions({ ...valid, model: "qwen" }, hosts)).toThrow("requires an uploaded voice");
    expect(() => validateOptions({ ...valid, model: "espeech" }, hosts)).toThrow("requires an uploaded voice");
    expect(() => validateOptions({ ...valid, model: "qwen", hasVoice: true }, hosts)).not.toThrow();
  });
  test("bounds expensive options and validates language and format", () => {
    expect(() => validateOptions({ ...valid, workers: 5 }, hosts)).toThrow("between 1 and 4");
    expect(() => validateOptions({ ...valid, language: "../book" }, hosts)).toThrow("language code");
    expect(() => validateOptions({ ...valid, format: "exe" }, hosts)).toThrow("M4B or MP3");
  });
  test("allows a short voice design only for OmniVoice", () => {
    expect(() => validateVoiceInstruction("omni", "Warm and unhurried.")).not.toThrow();
    expect(() => validateVoiceInstruction("pocket", "Warm and unhurried.")).toThrow("only by OmniVoice");
    expect(() => validateVoiceInstruction("omni", "x".repeat(301))).toThrow("300 characters");
  });
});

describe("upload names", () => {
  test("strips path components and unsafe characters", () => {
    expect(safeTitle("../../my book?.pdf")).toBe("my-book");
    expect(safeTitle("?.txt")).toBe("audiobook");
  });
  test("confines outputs to the configured library", () => {
    expect(isWithinRoot("/library", "/library/book/run/book.m4b")).toBe(true);
    expect(isWithinRoot("/library", "/library-copy/book.m4b")).toBe(false);
    expect(isWithinRoot("/library", "/other/book.m4b")).toBe(false);
  });
});
