import { createHash } from "node:crypto";

const DESIGN_LANGUAGES = ["en", "ru"];

export type NarratorPlan = "design" | "clone" | "reuse" | "none";

export interface NarratorInput {
  voiceSha1?: string;
  model: string;
  language: string;
  seed: string;
  instruct: string;
  refExists: boolean;
  redesign: boolean;
  storedSource?: string;
}

export function seedsFrom(values: { seed?: string; "voice-seed"?: string }): { designSeed: string; renderSeed?: string } {
  return { designSeed: values["voice-seed"] ?? "0", ...(values.seed ? { renderSeed: values.seed } : {}) };
}

export function sha1Hex(data: string | Uint8Array): string {
  return createHash("sha1").update(data).digest("hex");
}

export function requestedSource(input: NarratorInput): string | undefined {
  if (input.voiceSha1) return `sample:${input.voiceSha1}`;
  const base = input.language.toLowerCase().split(/[-_]/)[0]!;
  if (input.model !== "omni" || !DESIGN_LANGUAGES.includes(base)) return undefined;
  return `designed:${input.seed}:${sha1Hex(input.instruct + input.language)}`;
}

export function narratorPlan(input: NarratorInput): NarratorPlan {
  const source = requestedSource(input);
  if (!source) return "none";
  if (input.refExists && !input.redesign && input.storedSource === source) return "reuse";
  return source.startsWith("designed:") ? "design" : "clone";
}

export function isSampleReference(input: NarratorInput): boolean {
  return input.voiceSha1 !== undefined;
}
