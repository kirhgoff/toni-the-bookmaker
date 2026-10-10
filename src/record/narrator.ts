const DESIGN_LANGUAGES = ["en", "ru"];

export type NarratorPlan = "design" | "reuse" | "none";

export interface NarratorInput {
  voice?: string;
  model: string;
  language: string;
  refExists: boolean;
  redesign: boolean;
}

export function narratorPlan(input: NarratorInput): NarratorPlan {
  const base = input.language.toLowerCase().split(/[-_]/)[0]!;
  if (input.voice || input.model !== "omni" || !DESIGN_LANGUAGES.includes(base)) return "none";
  return input.refExists && !input.redesign ? "reuse" : "design";
}
