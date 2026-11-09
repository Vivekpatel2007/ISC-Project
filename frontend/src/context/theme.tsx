"use client";

import { useEffect, useSyncExternalStore, type ReactNode } from "react";

export type ThemePreference = "light" | "dark" | "system";
export const THEME_STORAGE_KEY = "pulmoscan.theme";
const themeEvent = "pulmoscan:theme-change";
let memoryPreference: ThemePreference = "system";
let useMemoryPreference = false;

function readPreference(): ThemePreference {
  if (useMemoryPreference) return memoryPreference;
  try {
    const value = localStorage.getItem(THEME_STORAGE_KEY);
    return value === "light" || value === "dark" ? value : "system";
  } catch {
    return memoryPreference;
  }
}

function snapshot() {
  const preference = readPreference();
  const systemDark =
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-color-scheme: dark)").matches;
  return `${preference}:${preference === "dark" || (preference === "system" && systemDark) ? "dark" : "light"}`;
}

function subscribe(notify: () => void) {
  const onStorage = (event: StorageEvent) => {
    if (event.key === THEME_STORAGE_KEY || event.key === null) notify();
  };
  const media =
    typeof window.matchMedia === "function"
      ? window.matchMedia("(prefers-color-scheme: dark)")
      : null;
  window.addEventListener(themeEvent, notify);
  window.addEventListener("storage", onStorage);
  media?.addEventListener("change", notify);
  return () => {
    window.removeEventListener(themeEvent, notify);
    window.removeEventListener("storage", onStorage);
    media?.removeEventListener("change", notify);
  };
}

export function setThemePreference(preference: ThemePreference) {
  memoryPreference = preference;
  try {
    localStorage.setItem(THEME_STORAGE_KEY, preference);
    useMemoryPreference = false;
  } catch {
    useMemoryPreference = true;
    /* Retain the choice for this visit. */
  }
  window.dispatchEvent(new Event(themeEvent));
}

export function useTheme() {
  const value = useSyncExternalStore(subscribe, snapshot, () => "system:light");
  const [preference, resolved] = value.split(":") as [
    ThemePreference,
    "light" | "dark",
  ];
  return { preference, resolved, setPreference: setThemePreference };
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const { resolved } = useTheme();
  useEffect(() => {
    // During hydration the server snapshot may briefly differ from the saved theme.
    // Preserve the theme applied by the head script until the store catches up.
    if (snapshot().split(":")[1] !== resolved) return;
    document.documentElement.dataset.theme = resolved;
    document.documentElement.style.colorScheme = resolved;
  }, [resolved]);
  return children;
}
