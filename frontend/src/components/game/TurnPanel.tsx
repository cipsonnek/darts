import clsx from "clsx";
import { useState } from "react";
import { api } from "@/lib/api";
import type { GameState } from "@/lib/types";
import { Button, Modal } from "@/components/ui";
import { useLive } from "@/store/live";

/** Current turn's darts, checkout hint and game controls. */
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

  async function act(path: string, body?: unknown) {
    const g = await api.post<GameState>(`/api/games/${game.id}/${path}`, body);
    setGame(g);
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <div className="text-sm text-[var(--muted)]">
          {player?.name}
          {current?.bust && <span className="ml-2 font-bold text-[var(--bad)]">BUST</span>}
          {st.awaiting_takeout && !st.finished && <span className="ml-2 text-[var(--warn)]">remove darts → next player</span>}
        </div>
        {current && <div className="font-display text-lg font-bold tabular-nums">{current.bust ? 0 : current.points}</div>}
      </div>
      <div className="grid grid-cols-3 gap-2">
        {[0, 1, 2].map((i) => {
          const d = darts[i];
          return (
            <button key={i} disabled={!d || !running} onClick={() => d && setFix(d.dart_id)}
              className={clsx("rounded-xl border px-2 text-center font-display font-black tabular-nums transition",
                big ? "py-6 text-5xl" : "py-3 text-2xl",
                d ? "border-[var(--accent)] bg-[color-mix(in_oklab,var(--accent)_14%,transparent)] hover:brightness-125"
                  : "border-dashed border-[var(--border)] text-[var(--muted)]")}
              title={d ? "Correct this dart" : undefined}>
              {d ? d.label : "–"}
            </button>
          );
        })}
      </div>
      {game.checkout_hint && (
        <div className="rounded-xl border border-[var(--good)]/40 bg-[color-mix(in_oklab,var(--good)_10%,transparent)] px-3 py-2 text-center">
          <span className="text-xs text-[var(--muted)]">Checkout </span>
          <span className={clsx("font-display font-bold text-[var(--good)]", big ? "text-3xl" : "text-xl")}>{game.checkout_hint.join(" · ")}</span>
        </div>
      )}
      {st.message && !st.awaiting_takeout && <div className="text-center text-sm font-semibold text-[var(--warn)]">{st.message}</div>}
      {running && (
        <div className="flex flex-wrap gap-2">
          <Button onClick={() => setEntry(true)}>Enter dart</Button>
          <Button onClick={() => act("undo")}>Undo</Button>
          <Button variant="primary" onClick={() => act("next-turn")}>Next player</Button>
        </div>
      )}
      <DartEntryModal open={entry} onClose={() => setEntry(false)} onPick={async (l) => { await act("darts", { label: l }); setEntry(false); }} />
      <DartEntryModal open={!!fix} title="Correct dart" onClose={() => setFix(null)} allowVoid
        onPick={async (l) => { await act("corrections", { dart_id: fix, label: l }); setFix(null); }} />
    </div>
  );
}

export function DartEntryModal({ open, onClose, onPick, title = "Enter dart", allowVoid }: {
  open: boolean; onClose: () => void; onPick: (label: string) => void; title?: string; allowVoid?: boolean;
}) {
  const [mult, setMult] = useState<"S" | "D" | "T">("S");
  return (
    <Modal open={open} onClose={onClose} title={title}>
      <div className="mb-3 grid grid-cols-3 gap-2">
        {(["S", "D", "T"] as const).map((m) => (
          <Button key={m} variant={mult === m ? "primary" : "secondary"} onClick={() => setMult(m)}>
            {m === "S" ? "Single" : m === "D" ? "Double" : "Triple"}
          </Button>
        ))}
      </div>
      <div className="grid grid-cols-5 gap-2">
        {Array.from({ length: 20 }, (_, i) => i + 1).map((n) => (
          <Button key={n} size="lg" onClick={() => onPick(`${mult}${n}`)}>{n}</Button>
        ))}
      </div>
      <div className="mt-3 grid grid-cols-3 gap-2">
        <Button size="lg" onClick={() => onPick("25")}>25</Button>
        <Button size="lg" onClick={() => onPick("BULL")}>Bull</Button>
        <Button size="lg" onClick={() => onPick("MISS")}>Miss</Button>
      </div>
      {allowVoid && <Button className="mt-3 w-full" variant="danger" onClick={() => onPick("VOID")}>Not a dart (remove)</Button>}
    </Modal>
  );
}
