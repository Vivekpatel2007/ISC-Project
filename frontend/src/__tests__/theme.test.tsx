import React from "react";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  ThemeProvider,
  THEME_STORAGE_KEY,
  setThemePreference,
} from "@/context/theme";
import { ThemeToggle } from "@/components/theme-toggle";

describe("Appearance preferences", () => {
  let systemDark = false;
  let listeners: Set<() => void>;

  beforeEach(() => {
    localStorage.clear();
    setThemePreference("system");
    delete document.documentElement.dataset.theme;
    systemDark = false;
    listeners = new Set();
    vi.stubGlobal(
      "matchMedia",
      vi.fn(() => ({
        get matches() {
          return systemDark;
        },
        addEventListener: (_event: string, listener: () => void) =>
          listeners.add(listener),
        removeEventListener: (_event: string, listener: () => void) =>
          listeners.delete(listener),
      })),
    );
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  function showToggle() {
    return render(
      <ThemeProvider>
        <ThemeToggle />
      </ThemeProvider>,
    );
  }

  it("uses the device theme on a first visit and toggles to light", () => {
    systemDark = true;
    showToggle();
    expect(document.documentElement).toHaveAttribute("data-theme", "dark");
    fireEvent.click(
      screen.getByRole("button", { name: "Switch to light mode" }),
    );
    expect(document.documentElement).toHaveAttribute("data-theme", "light");
    expect(document.documentElement.style.colorScheme).toBe("light");
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe("light");
  });

  it("remembers dark mode across a fresh mount", () => {
    const page = showToggle();
    fireEvent.click(
      screen.getByRole("button", { name: "Switch to dark mode" }),
    );
    page.unmount();
    showToggle();
    expect(document.documentElement).toHaveAttribute("data-theme", "dark");
    expect(
      screen.getByRole("button", { name: "Switch to light mode" }),
    ).toBeInTheDocument();
  });

  it("responds to system changes until an explicit preference is chosen", () => {
    showToggle();
    act(() => {
      systemDark = true;
      listeners.forEach((listener) => listener());
    });
    expect(document.documentElement).toHaveAttribute("data-theme", "dark");
    fireEvent.click(
      screen.getByRole("button", { name: "Switch to light mode" }),
    );
    act(() => {
      systemDark = false;
      listeners.forEach((listener) => listener());
      systemDark = true;
      listeners.forEach((listener) => listener());
    });
    expect(document.documentElement).toHaveAttribute("data-theme", "light");
  });

  it("synchronizes a theme change made in another tab", () => {
    showToggle();
    act(() => {
      localStorage.setItem(THEME_STORAGE_KEY, "dark");
      window.dispatchEvent(
        new StorageEvent("storage", { key: THEME_STORAGE_KEY }),
      );
    });
    expect(document.documentElement).toHaveAttribute("data-theme", "dark");
  });

  it("still toggles when localStorage is unavailable", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("Storage blocked");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("Storage blocked");
    });
    showToggle();
    fireEvent.click(
      screen.getByRole("button", { name: "Switch to dark mode" }),
    );
    expect(document.documentElement).toHaveAttribute("data-theme", "dark");
  });

  it("ignores an invalid stored preference and follows the device", () => {
    localStorage.setItem(THEME_STORAGE_KEY, "invalid");
    systemDark = true;
    showToggle();
    expect(document.documentElement).toHaveAttribute("data-theme", "dark");
  });
});
