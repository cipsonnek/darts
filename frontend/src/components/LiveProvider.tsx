import { useEffect } from "react";
import { api } from "@/lib/api";
import type { GameState } from "@/lib/types";
import { LiveSocket } from "@/lib/ws";
import { useLive } from "@/store/live";
import { applyTheme, usePrefs } from "@/store/prefs";

/** Opens the event and diagnostics WebSockets once for the whole app, loads the active
 *  game, and keeps the theme applied. */
export function LiveProvider({ children }: { children: React.ReactNode }) {
  const handle = useLive((s) => s.handle);
  const setStatus = useLive((s) => s.setStatus);
  const setGame = useLive((s) => s.setGame);
  const theme = usePrefs((s) => s.theme);
  const accent = usePrefs((s) => s.accent);

  useEffect(() => applyTheme(theme, accent), [theme, accent]);

  useEffect(() => {
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
  }, [handle, setStatus, setGame]);

  return <>{children}</>;
}
