import type { ThemePreference } from "@/lib/auth";

export const THEME_PREFERENCE_KEY = "cchis.theme_preference";

export function applyThemePreference(themePreference: ThemePreference | null) {
  if (typeof document === "undefined") {
    return;
  }

  if (!themePreference || themePreference === "SYSTEM") {
    document.documentElement.removeAttribute("data-theme");
    return;
  }

  document.documentElement.setAttribute("data-theme", themePreference.toLowerCase());
}

export function persistThemePreference(themePreference: ThemePreference | null) {
  if (typeof window === "undefined") {
    return;
  }

  if (!themePreference || themePreference === "SYSTEM") {
    window.localStorage.removeItem(THEME_PREFERENCE_KEY);
    return;
  }

  window.localStorage.setItem(THEME_PREFERENCE_KEY, themePreference);
}
