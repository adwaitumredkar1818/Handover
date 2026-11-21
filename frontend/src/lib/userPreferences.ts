import type { UserPreferences } from "./types";

export const DEFAULT_USER_PREFERENCES: UserPreferences = {
  theme: "light",
  date_format: "DD MMM YYYY",
  density: "comfortable",
  reduced_motion: false,
  default_landing_page: "/dashboard",
};

export function resolveEffectiveTheme(theme: UserPreferences["theme"]): "light" | "dark" {
  if (theme === "dark") return "dark";
  if (theme === "system" && typeof window !== "undefined") {
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
  return "light";
}

export function applyUserPreferences(prefs?: Partial<UserPreferences> | null): void {
  if (typeof document === "undefined") return;
  const merged: UserPreferences = { ...DEFAULT_USER_PREFERENCES, ...(prefs || {}) };
  const effectiveTheme = resolveEffectiveTheme(merged.theme);

  const root = document.documentElement;
  root.setAttribute("data-theme", effectiveTheme);
  root.setAttribute("data-theme-mode", merged.theme);
  root.classList.toggle("dark", effectiveTheme === "dark");
  root.setAttribute("data-density", merged.density);
  root.setAttribute("data-reduced-motion", String(Boolean(merged.reduced_motion)));

  try {
    localStorage.setItem("th_theme", merged.theme);
    localStorage.setItem("th_density", merged.density);
    localStorage.setItem("th_reduced_motion", String(Boolean(merged.reduced_motion)));
  } catch {
    // ignore storage errors
  }
}

export function clearUserPreferenceCache(): void {
  if (typeof document !== "undefined") {
    applyUserPreferences(DEFAULT_USER_PREFERENCES);
  }
  try {
    localStorage.removeItem("th_theme");
    localStorage.removeItem("th_density");
    localStorage.removeItem("th_reduced_motion");
  } catch {
    // ignore
  }
}
