import clsx from "clsx";
import { useEffect } from "react";
import { Link } from "react-router";
import { BoardView } from "@/components/board/BoardView";
import { Scoreboard } from "@/components/game/Scoreboard";
import { TurnPanel } from "@/components/game/TurnPanel";
import { EngineBadge } from "@/components/layout/AppShell";
import { useBoardDarts, useBoardGeometry } from "@/hooks/useBoard";
import { useLive } from "@/store/live";
import { usePrefs } from "@/store/prefs";
import { dartLabel, modeName } from "@/lib/pl";
import { gameSummary } from "./Play";

/** Full-screen view for a TV/monitor next to the board: large type, no navigation. */
export default function TvMode() {
  const game = useLive((s) => s.game);
  const lastDart = useLive((s) => s.lastDart);
  const brand = usePrefs((s) => s.brandName);
  const scale = usePrefs((s) => s.tvScale);
  const board = useBoardGeometry();
  const darts = useBoardDarts();

  useEffect(() => {
    const el = document.documentElement;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "f") (document.fullscreenElement ? document.exitFullscreen() : el.requestFullscreen()).catch(() => {});
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const active = game && game.status !== "finished" && game.status !== "abandoned" ? game : game?.state.finished ? game : null;
  return (
    <div className="flex h-dvh flex-col gap-4 overflow-hidden p-4" style={{ zoom: scale }}>
      <div className="backdrop" />
      <div className="flex items-center justify-between">
        <div className="flex items-baseline gap-4">
          <div className="font-display text-3xl font-extrabold tracking-wide uppercase">{brand}</div>
          {active && <div className="text-xl text-[var(--muted)]"><b className="text-[var(--text)]">{modeName(active.mode, active.mode_name)}</b> {gameSummary(active)} · Leg {active.state.leg}</div>}
        </div>
        <div className="flex items-center gap-3">
          <EngineBadge />
          <button className="rounded-lg border border-[var(--border)] px-3 py-1 text-sm" onClick={() => document.documentElement.requestFullscreen().catch(() => {})}>
            Pełny ekran (F)
          </button>
          <Link to="/" className="rounded-lg border border-[var(--border)] px-3 py-1 text-sm">Wyjdź</Link>
        </div>
      </div>
      <div className="grid min-h-0 flex-1 grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)]">
        <div className="relative flex min-h-0 items-center justify-center">
          <div className="aspect-square h-full max-h-full max-w-full">
            <BoardView board={board} markers={darts.map((d, i) => ({ id: d.id, x_mm: d.x_mm, y_mm: d.y_mm, label: dartLabel(d.label), cov: d.cov, uncertain: d.uncertain, ghost: i < darts.length - 3 }))}
              highlight={active?.checkout_hint ?? []} />
          </div>
          {lastDart && (
            <div key={lastDart.dart_id} className={clsx("animate-pop absolute top-2 right-2 font-score text-9xl font-extrabold drop-shadow-xl",
              lastDart.uncertain ? "text-[var(--warn)]" : "text-[var(--accent)]")}>{dartLabel(lastDart.score.label)}</div>
          )}
        </div>
        <div className="flex min-h-0 flex-col gap-6 overflow-auto">
          {active ? (
            <>
              <Scoreboard game={active} big />
              {!active.state.finished && <TurnPanel game={active} big />}
              {active.state.finished && (
                <div className="text-center font-display text-7xl font-extrabold text-[var(--good)]">{active.winner?.name} wygrywa!</div>
              )}
            </>
          ) : (
            <div className="grid flex-1 place-items-center text-center text-3xl text-[var(--muted)]">Czekam na grę…</div>
          )}
        </div>
      </div>
    </div>
  );
}
