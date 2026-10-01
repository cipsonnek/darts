// UI customisation, persisted per browser (localStorage) and optionally on the server.

import { create } from "zustand";
import { persist } from "zustand/middleware";

export type ThemeName = "oche" | "midnight" | "light" | "pub" | "contrast";
export type ScoreStyle = "classic" | "big" | "compact";
export type BoardStyle = "classic" | "minimal" | "neon";

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
  oche: { label: "Oche (dark)", vars: { "--bg": "#0b0d12", "--surface": "#141821", "--surface-2": "#1b2130", "--border": "#262e40", "--text": "#eef1f6", "--muted": "#8b94a8", "--good": "#2ecc71", "--warn": "#f5b942", "--bad": "#ef4f5f" } },
  midnight: { label: "Midnight blue", vars: { "--bg": "#060b1a", "--surface": "#0e1730", "--surface-2": "#15213f", "--border": "#22325c", "--text": "#e8eefc", "--muted": "#8796bd", "--good": "#34d399", "--warn": "#fbbf24", "--bad": "#f87171" } },
  light: { label: "Light", vars: { "--bg": "#f3f5f9", "--surface": "#ffffff", "--surface-2": "#eef1f6", "--border": "#d8dde8", "--text": "#121826", "--muted": "#5d6779", "--good": "#16a34a", "--warn": "#b7791f", "--bad": "#dc2626" } },
  pub: { label: "Pub (warm)", vars: { "--bg": "#14100c", "--surface": "#1f1813", "--surface-2": "#2a2019", "--border": "#3d2f24", "--text": "#f7ecdf", "--muted": "#b39c86", "--good": "#7cc66b", "--warn": "#f0b04a", "--bad": "#e5654f" } },
  contrast: { label: "High contrast", vars: { "--bg": "#000000", "--surface": "#0d0d0d", "--surface-2": "#1a1a1a", "--border": "#ffffff", "--text": "#ffffff", "--muted": "#d0d0d0", "--good": "#00ff7f", "--warn": "#ffd400", "--bad": "#ff3b3b" } },
};

export const usePrefs = create<Prefs>()(
  persist(
    (set) => ({
      theme: "oche",
      accent: "#e8324a",
      brandName: "DartSense",
      brandTagline: "Automatic scoring",
      scoreStyle: "classic",
      boardStyle: "classic",
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
    { name: "dartsense.prefs", version: 1 },
  ),
);

export function applyTheme(theme: ThemeName, accent: string): void {
  const root = document.documentElement;
  for (const [k, v] of Object.entries(THEMES[theme].vars)) root.style.setProperty(k, v);
  root.style.setProperty("--accent", accent);
  root.dataset.theme = theme;
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", THEMES[theme].vars["--bg"]);
}
