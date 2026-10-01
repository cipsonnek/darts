import { useState } from "react";
import { api } from "@/lib/api";
import type { GameState, PendingDetection } from "@/lib/types";
import { Button, Modal } from "@/components/ui";
import { Dartboard } from "@/components/board/Dartboard";
import { DartEntryModal } from "./TurnPanel";
import { useLive } from "@/store/live";

/** Shown when the engine is not confident enough to score a dart on its own. */
export function UncertainDialog({ game }: { game: GameState }) {
  const setGame = useLive((s) => s.setGame);
  const [manual, setManual] = useState(false);
  const pending: PendingDetection | undefined = game.pending.find((p) => p.status === "pending");
  if (!pending) return null;

  async function resolve(choice: "accept" | "label" | "reject", label?: string) {
    const g = await api.post<GameState>(`/api/detections/${pending!.id}/resolve`, { choice, label });
    if (g && (g as any).players) setGame(g);
    setManual(false);
  }

  const alts = pending.alternatives.filter((a) => a.label !== pending.label).slice(0, 3);
  return (
    <>
      <Modal open={!manual} onClose={() => {}} title={<span className="text-[var(--warn)]">⚠ Uncertain detection</span>}>
        <div className="grid gap-4 sm:grid-cols-[1fr_200px]">
          <div className="flex flex-col gap-3">
            <div>
              <div className="text-sm text-[var(--muted)]">Predicted</div>
              <div className="font-display text-5xl font-black">{pending.label}</div>
              <div className="text-sm text-[var(--muted)]">
                probability {Math.round((pending.score_probability ?? 0) * 100)}% · confidence {Math.round(pending.confidence * 100)}%
                {pending.sigma_mm != null && <> · ±{pending.sigma_mm.toFixed(1)} mm</>} · cameras {pending.cameras_used.join(", ")}
              </div>
            </div>
            <Button variant="good" size="lg" onClick={() => resolve("accept")}>Accept {pending.label}</Button>
            {alts.length > 0 && (
              <div className="flex flex-col gap-2">
                <div className="text-xs text-[var(--muted)]">Alternatives</div>
                {alts.map((a) => (
                  <Button key={a.label} size="lg" onClick={() => resolve("label", a.label)}>
                    Choose {a.label} <span className="text-xs text-[var(--muted)]">{Math.round(a.probability * 100)}%</span>
                  </Button>
                ))}
              </div>
            )}
            <div className="flex gap-2">
              <Button className="flex-1" onClick={() => setManual(true)}>Manual correction</Button>
              <Button className="flex-1" variant="danger" onClick={() => resolve("reject")}>Not a dart</Button>
            </div>
          </div>
          <div className="aspect-square">
            <Dartboard markers={[{ id: pending.id, x_mm: pending.x_mm, y_mm: pending.y_mm, uncertain: true,
              cov: pending.sigma_mm ? [[pending.sigma_mm ** 2, 0], [0, pending.sigma_mm ** 2]] : undefined }]} numbers />
          </div>
        </div>
      </Modal>
      <DartEntryModal open={manual} onClose={() => setManual(false)} title="Actual dart" onPick={(l) => resolve("label", l)} />
    </>
  );
}
