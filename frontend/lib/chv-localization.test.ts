import { describe, expect, it } from "vitest";

import {
  CHV_SUPPORTED_LANGUAGES,
  CHV_UI_TRANSLATIONS,
  chvTranslate,
  normalizeChvLanguage,
} from "@/lib/chv-localization";

describe("CHV UI localization dictionaries", () => {
  it("keeps required English, Kiswahili, and Dholuo keys in parity", () => {
    const englishKeys = Object.keys(CHV_UI_TRANSLATIONS.en).sort();

    for (const language of CHV_SUPPORTED_LANGUAGES) {
      expect(Object.keys(CHV_UI_TRANSLATIONS[language]).sort()).toEqual(englishKeys);
    }
  });

  it("normalizes unsupported language requests and interpolates labels", () => {
    expect(normalizeChvLanguage("SW")).toBe("sw");
    expect(normalizeChvLanguage("fr")).toBe("en");
    expect(chvTranslate("luo", "status.pendingCount", { count: 2 })).toContain("2");
  });

  it("keeps public-health triage recommendation copy out of UI chrome dictionaries", () => {
    for (const language of CHV_SUPPORTED_LANGUAGES) {
      expect(Object.keys(CHV_UI_TRANSLATIONS[language]).filter((key) => key.startsWith("recommendation."))).toEqual([]);
    }
  });
});
