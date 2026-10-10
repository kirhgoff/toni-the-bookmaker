import { expect, test } from "bun:test";

import { narratorPlan } from "./narrator.ts";

const BASE = { model: "omni", language: "en", refExists: false, redesign: false };

test("designs the narrator once when there is no voice sample", () => {
  expect(narratorPlan(BASE)).toBe("design");
  expect(narratorPlan({ ...BASE, refExists: true })).toBe("reuse");
});

test("redesign replaces an existing designed narrator", () => {
  expect(narratorPlan({ ...BASE, refExists: true, redesign: true })).toBe("design");
});

test("leaves user samples, other engines and unsupported languages alone", () => {
  expect(narratorPlan({ ...BASE, voice: "/v.wav", redesign: true })).toBe("none");
  expect(narratorPlan({ ...BASE, model: "pocket" })).toBe("none");
  expect(narratorPlan({ ...BASE, language: "de" })).toBe("none");
  expect(narratorPlan({ ...BASE, language: "ru-RU" })).toBe("design");
});
