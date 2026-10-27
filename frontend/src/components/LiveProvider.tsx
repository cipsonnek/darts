import { useEffect } from "react";
import { api } from "@/lib/api";
import type { GameState } from "@/lib/types";
import { LiveSocket } from "@/lib/ws";
import { useLive } from "@/store/live";
import { applyTheme, usePrefs } from "@/store/prefs";
import { watchServiceIdle } from "@/store/service";

/** Finds out what this server is (a board or the operator's central server), then on a board
 *  opens the event and diagnostics WebSockets once for the whole app and loads the active
 *  game. Keeps the theme applied. */
export function LiveProvider({ children }: { children: React.ReactNode }) {
  const handle = useLive((s) => s.handle);
  const setStatus = useLive((s) => s.setStatus);
  const setGame = useLive((s) => s.setGame);
  const setMode = useLive((s) => s.setMode);
  const mode = useLive((s) => s.mode);
  const theme = usePrefs((s) => s.theme);
  const accent = usePrefs((s) => s.accent);

  useEffect(() => applyTheme(theme, accent), [theme, accent]);

  useEffect(() => {
    let stop = false;
    let retry: ReturnType<typeof setTimeout>;
    const probe = () => {
      api.get<{ mode: string }>("/api/health")
        .then((h) => !stop && setMode(h.mode))
        .catch(() => { if (!stop) retry = setTimeout(probe, 2000); });
    };
    probe();
    return () => {
      stop = true;
      clearTimeout(retry);
    };
  }, [setMode]);

  const board = mode !== null && mode !== "central";
  useEffect(() => {
    if (!board) return;
    watchServiceIdle();
    const ev = new LiveSocket("/ws/events", handle, (s) => {
      setStatus("events", s);
      if (s === "open") {
        api.get<GameState | null>("/api/games/active").then((g) => setGame(g)).catch(() => {});
      }
    });
    const det = new LiveSocket("/ws/detection", handle, (s) => setStatus("detection", s));
    ev.start();
    det.start();
    return () => {
      ev.stop();
      det.stop();
    };
  }, [board, handle, setStatus, setGame]);

  return <>{children}</>;
}
