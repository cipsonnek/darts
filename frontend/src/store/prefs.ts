// UI customisation, persisted per browser (localStorage) and optionally on the server.

import { create } from "zustand";
import { persist } from "zustand/middleware";

export type ThemeName = "lava" | "oche" | "midnight" | "light" | "pub" | "contrast";
export type ScoreStyle = "classic" | "big" | "compact";
export type BoardStyle = "3d" | "classic" | "minimal" | "neon";

export interface DashboardWidgets {
  board: boolean;
  scoreboard: boolean;
  cameras: boolean;
  feed: boolean;
  turn: boolean;
  checkout: boolean;
}

interface Prefs {
  theme: ThemeName;
  accent: string;
  brandName: string;
  brandTagline: string;
  scoreStyle: ScoreStyle;
  boardStyle: BoardStyle;
  showBoardNumbers: boolean;
  showUncertainty: boolean;
  widgets: DashboardWidgets;
  layout: "board-left" | "board-right" | "stacked";
  cameraOverlay: string[];
  soundEnabled: boolean;
  tvScale: number;
  set: (p: Partial<Omit<Prefs, "set" | "toggleWidget">>) => void;
  toggleWidget: (k: keyof DashboardWidgets) => void;
}

export const THEMES: Record<ThemeName, { label: string; vars: Record<string, string> }> = {
  lava: { label: "Lawa (domyślny)", vars: { "--bg": "#0b0807", "--surface": "#17110f", "--surface-2": "#221916", "--border": "#3a2a24", "--text": "#fbf3ee", "--muted": "#b9a69c", "--good": "#34d399", "--warn": "#fbbf24", "--bad": "#ff4d5e", "--accent-2": "#ffb020", "--glow-1": "#ff5a1f", "--glow-2": "#b3122e" } },
  oche: { label: "Oche (ciemny)", vars: { "--bg": "#090c12", "--surface": "#121721", "--surface-2": "#1a2130", "--border": "#283244", "--text": "#f2f5fa", "--muted": "#a1abbe", "--good": "#2ecc71", "--warn": "#f5b942", "--bad": "#ef4f5f", "--accent-2": "#f5b942", "--glow-1": "#e8324a", "--glow-2": "#2547a8" } },
  midnight: { label: "Granatowy", vars: { "--bg": "#060b1a", "--surface": "#0e1730", "--surface-2": "#15213f", "--border": "#22325c", "--text": "#e8eefc", "--muted": "#9aa8cc", "--good": "#34d399", "--warn": "#fbbf24", "--bad": "#f87171", "--accent-2": "#60a5fa", "--glow-1": "#3b82f6", "--glow-2": "#7c3aed" } },
  light: { label: "Jasny", vars: { "--bg": "#f6f2ef", "--surface": "#ffffff", "--surface-2": "#f1ebe7", "--border": "#e1d6cf", "--text": "#1d1512", "--muted": "#6d5f58", "--good": "#16a34a", "--warn": "#b7791f", "--bad": "#dc2626", "--accent-2": "#f59e0b", "--glow-1": "#ffb38f", "--glow-2": "#ffd6c2" } },
  pub: { label: "Pub (ciepły)", vars: { "--bg": "#14100c", "--surface": "#1f1813", "--surface-2": "#2a2019", "--border": "#3d2f24", "--text": "#f7ecdf", "--muted": "#c2ab95", "--good": "#7cc66b", "--warn": "#f0b04a", "--bad": "#e5654f", "--accent-2": "#f0b04a", "--glow-1": "#a86b2d", "--glow-2": "#3d6b3a" } },
  contrast: { label: "Wysoki kontrast", vars: { "--bg": "#000000", "--surface": "#0d0d0d", "--surface-2": "#1a1a1a", "--border": "#ffffff", "--text": "#ffffff", "--muted": "#d0d0d0", "--good": "#00ff7f", "--warn": "#ffd400", "--bad": "#ff3b3b", "--accent-2": "#ffd400", "--glow-1": "#000000", "--glow-2": "#000000" } },
};

export const usePrefs = create<Prefs>()(
  persist(
    (set) => ({
      theme: "lava",
      accent: "#ff5a1f",
      brandName: "DartSense",
      brandTagline: "Automatyczne liczenie",
      scoreStyle: "classic",
      boardStyle: "3d",
      showBoardNumbers: true,
      showUncertainty: true,
      widgets: { board: true, scoreboard: true, cameras: true, feed: true, turn: true, checkout: true },
      layout: "board-left",
      cameraOverlay: ["board", "darts"],
      soundEnabled: false,
      tvScale: 1,
      set: (p) => set(p),
      toggleWidget: (k) => set((s) => ({ widgets: { ...s.widgets, [k]: !s.widgets[k] } })),
    }),
    {
      name: "dartsense.prefs",
      version: 3,
      // v2: Polish UI — replace the old English default tagline if the user never changed it.
      // v3: "lava" look with the 3D board — move browsers still on the old defaults to it.
      migrate: (state: any, version) => {
        if (version < 2 && state?.brandTagline === "Automatic scoring") state.brandTagline = "Automatyczne liczenie";
        if (version < 3 && state) {
          if (state.theme === "oche" && state.accent === "#e8324a") Object.assign(state, { theme: "lava", accent: "#ff5a1f" });
          if (state.boardStyle === "classic") state.boardStyle = "3d";
        }
        return state;
      },
    },
  ),
);

export function applyTheme(theme: ThemeName, accent: string): void {
  const root = document.documentElement;
  for (const [k, v] of Object.entries(THEMES[theme].vars)) root.style.setProperty(k, v);
  root.style.setProperty("--accent", accent);
  root.dataset.theme = theme;
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", THEMES[theme].vars["--bg"]);
}
