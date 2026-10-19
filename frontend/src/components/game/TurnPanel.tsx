import clsx from "clsx";
import { Keyboard, SkipForward, Undo2 } from "lucide-react";
import { useState } from "react";
import { api } from "@/lib/api";
import { dartLabel, gameMessage } from "@/lib/pl";
import type { GameState } from "@/lib/types";
import { Button, ErrorNote, Modal } from "@/components/ui";
import { useAction } from "@/hooks/useApi";
import { useLive } from "@/store/live";

/** Current visit: three dart slots, visit total, status message and game controls. */
export function TurnPanel({ game, big }: { game: GameState; big?: boolean }) {
  const setGame = useLive((s) => s.setGame);
  const [entry, setEntry] = useState(false);
  const [fix, setFix] = useState<string | null>(null);
  const st = game.state;
  const last = st.turns[st.turns.length - 1];
  const current = last && (!last.finished || st.awaiting_takeout) ? last : null;
  const darts = current?.darts ?? [];
  const player = game.players[current ? current.player_index : st.current_player];
  const running = game.status === "running";
  const message = gameMessage(st.message);

  const act = useAction(async (path: string, body?: unknown) => {
    setGame(await api.post<GameState>(`/api/games/${game.id}/${path}`, body));
  });

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-3">
        <span className="h-3 w-3 shrink-0 rounded-full" style={{ background: player?.color }} />
        <div className="min-w-0 flex-1">
          <div className="text-xs font-semibold tracking-wide text-[var(--muted)] uppercase">Tura</div>
          <div className={clsx("truncate font-display font-bold", big ? "text-3xl" : "text-xl")}>{player?.name}</div>
        </div>
        <div className="text-right">
          <div className="text-xs font-semibold tracking-wide text-[var(--muted)] uppercase">Suma</div>
          <div className={clsx("font-score font-extrabold leading-none", big ? "text-7xl" : "text-5xl", current?.bust && "text-[var(--bad)]")}>
            {current ? (current.bust ? 0 : current.points) : 0}
          </div>
        </div>
      </div>
      <div className="grid grid-cols-3 gap-2">
        {[0, 1, 2].map((i) => {
          const d = darts[i];
          const next = !d && i === darts.length && running && !st.awaiting_takeout;
          return (
            <button key={i} disabled={!d || !running} onClick={() => d && setFix(d.dart_id)}
              className={clsx("flex flex-col items-center justify-center rounded-2xl border-2 px-2 transition",
                big ? "h-36" : "h-24 md:h-28",
                d ? "border-[var(--accent)] bg-[color-mix(in_oklab,var(--accent)_14%,var(--surface))] hover:brightness-125"
                  : next ? "border-dashed border-[var(--accent)]/60 text-[var(--muted)]"
                    : "border-dashed border-[var(--border)] text-[var(--muted)]")}
              title={d ? "Kliknij, aby poprawić ten rzut" : undefined}>
              {d ? (
                <>
                  <span key={d.dart_id} className={clsx("animate-pop font-score font-extrabold leading-none", big ? "text-7xl" : "text-5xl")}>{dartLabel(d.label)}</span>
                  <span className="mt-1 text-xs text-[var(--muted)]">{d.score} pkt</span>
                </>
              ) : (
                <span className={clsx("font-score font-bold", big ? "text-4xl" : "text-2xl")}>{i + 1}</span>
              )}
            </button>
          );
        })}
      </div>
      {(current?.bust || message || st.awaiting_takeout) && !st.finished && (
        <div className={clsx("rounded-xl px-3 py-2 text-center font-semibold",
          current?.bust ? "bg-[color-mix(in_oklab,var(--bad)_18%,transparent)] text-[var(--bad)]" : "bg-[color-mix(in_oklab,var(--warn)_15%,transparent)] text-[var(--warn)]",
          big ? "text-2xl" : "text-base")}>
          {message || (current?.bust ? "BUST — za dużo" : "")}
          {st.awaiting_takeout && <div className={clsx("font-medium", message && "mt-0.5 text-sm opacity-90")}>Wyjmij lotki z tarczy — potem rzuca następny gracz</div>}
        </div>
      )}
      {running && (
        <>
          <div className="grid grid-cols-3 gap-2">
            <Button size="lg" onClick={() => setEntry(true)} disabled={act.busy}><Keyboard size={18} /> Wpisz</Button>
            <Button size="lg" onClick={() => act.run("undo")} disabled={act.busy}><Undo2 size={18} /> Cofnij</Button>
            <Button size="lg" variant="primary" onClick={() => act.run("next-turn")} disabled={act.busy}><SkipForward size={18} /> Dalej</Button>
          </div>
          {darts.length > 0 && <div className="text-center text-xs text-[var(--muted)]">Źle policzony rzut? Kliknij go, aby poprawić.</div>}
        </>
      )}
      <ErrorNote error={act.error} />
      <DartEntryModal open={entry} onClose={() => setEntry(false)} onPick={async (l) => { await act.run("darts", { label: l }); setEntry(false); }} />
      <DartEntryModal open={!!fix} title="Popraw rzut" onClose={() => setFix(null)} allowVoid
        onPick={async (l) => { await act.run("corrections", { dart_id: fix, label: l }); setFix(null); }} />
    </div>
  );
}

export function DartEntryModal({ open, onClose, onPick, title = "Wpisz rzut", allowVoid }: {
  open: boolean; onClose: () => void; onPick: (label: string) => void; title?: string; allowVoid?: boolean;
}) {
  const [mult, setMult] = useState<"S" | "D" | "T">("S");
  return (
    <Modal open={open} onClose={onClose} title={title}>
      <div className="mb-3 grid grid-cols-3 gap-2">
        {(["S", "D", "T"] as const).map((m) => (
          <Button key={m} size="lg" variant={mult === m ? "primary" : "secondary"} onClick={() => setMult(m)}>
            {m === "S" ? "Single" : m === "D" ? "Double" : "Triple"}
          </Button>
        ))}
      </div>
      <div className="grid grid-cols-5 gap-2">
        {Array.from({ length: 20 }, (_, i) => i + 1).map((n) => (
          <Button key={n} size="lg" className="font-score text-2xl" onClick={() => onPick(`${mult}${n}`)}>{n}</Button>
        ))}
      </div>
      <div className="mt-3 grid grid-cols-3 gap-2">
        <Button size="lg" onClick={() => onPick("25")}>25</Button>
        <Button size="lg" onClick={() => onPick("BULL")}>Bull (50)</Button>
        <Button size="lg" onClick={() => onPick("MISS")}>Pudło</Button>
      </div>
      {allowVoid && <Button className="mt-3 w-full" variant="danger" onClick={() => onPick("VOID")}>To nie była lotka (usuń)</Button>}
    </Modal>
  );
}
