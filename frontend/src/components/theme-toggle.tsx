"use client";

import { Moon, Sun } from "lucide-react";
import { useTheme } from "@/context/theme";

export function ThemeToggle() {
  const { resolved, setPreference } = useTheme();
  const dark = resolved === "dark";
  return (
    <button
      type="button"
      className="theme-toggle"
      aria-label={`Switch to ${dark ? "light" : "dark"} mode`}
      title={`Switch to ${dark ? "light" : "dark"} mode`}
      onClick={() => setPreference(dark ? "light" : "dark")}
    >
      {dark ? (
        <Sun size={17} aria-hidden="true" />
      ) : (
        <Moon size={17} aria-hidden="true" />
      )}
      <span>{dark ? "Light mode" : "Dark mode"}</span>
    </button>
  );
}
