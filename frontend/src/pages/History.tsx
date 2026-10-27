import { useState } from "react";
import { useNavigate } from "react-router";
import { Badge, Button, Card, Empty, ErrorNote, Modal, PageHeader } from "@/components/ui";
import { useAction, useApi } from "@/hooks/useApi";
import { api } from "@/lib/api";
import { dartLabel, GAME_STATUS, modeName, tr } from "@/lib/pl";
import type { GameState, GameSummary, Turn } from "@/lib/types";
import { useLive } from "@/store/live";
import { gameSummary } from "./Play";

/** Played and interrupted games (service area of a board). */
export default function History() {
  const { data: games, reload, error } = useApi<GameSummary[]>("/api/games?limit=100");
  const [detail, setDetail] = useState<string | null>(null);
  const setGame = useLive((s) => s.setGame);
  const nav = useNavigate();

  const act = useAction(async (id: string, action: string) => {
    const g = await api.post<GameState>(`/api/games/${id}/${action}`);
    if (action === "resume" || action === "start") {
      setGame(g);
      nav("/");
    }
    reload();
  });

  const unfinished = games?.filter((g) => g.status === "running" || g.status === "paused" || g.status === "created") ?? [];
  const done = games?.filter((g) => !unfinished.includes(g)) ?? [];

  return (
    <div>
      <PageHeader title="Historia gier" subtitle="Kliknij grę, aby zobaczyć wszystkie rzuty." />
      <div className="grid gap-4 xl:grid-cols-[420px_minmax(0,1fr)]">
        <Card title="Niedokończone">
          {!unfinished.length ? <Empty title="Brak niedokończonych gier" /> : (
            <div className="flex flex-col divide-y divide-[var(--border)]">
              {unfinished.map((g) => (
                <GameRow key={g.id} g={g} onDetail={() => setDetail(g.id)}>
                  <Button size="sm" variant="primary" onClick={() => act.run(g.id, "resume")}>Wznów</Button>
                  <Button size="sm" variant="ghost" onClick={() => act.run(g.id, "abandon")}>Przerwij</Button>
                </GameRow>
              ))}
            </div>
          )}
        </Card>
        <Card title="Rozegrane">
          <ErrorNote error={error ?? act.error} />
          {!done.length ? <Empty title="Brak rozegranych gier" /> : (
            <div className="flex max-h-[70vh] flex-col divide-y divide-[var(--border)] overflow-y-auto">
              {done.map((g) => <GameRow key={g.id} g={g} onDetail={() => setDetail(g.id)} />)}
            </div>
          )}
        </Card>
      </div>
      {detail && <GameDetail id={detail} onClose={() => setDetail(null)} />}
    </div>
  );
}

export function GameRow({ g, onDetail, children }: { g: GameSummary; onDetail: () => void; children?: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-center gap-2 py-2.5">
      <button className="min-w-0 flex-1 text-left" onClick={onDetail}>
        <div className="font-semibold">
          {modeName(g.mode)} <span className="font-normal text-[var(--muted)]">{gameSummary(g)}</span>
        </div>
        <div className="truncate text-sm text-[var(--muted)]">{g.players.map((p) => p.name).join(" vs ")}</div>
        <div className="text-xs text-[var(--muted)]">
          {g.created_at && new Date(g.created_at).toLocaleString("pl-PL", { dateStyle: "medium", timeStyle: "short" })}
          {g.winner && <> · wygrał(a) <b className="text-[var(--good)]">{g.winner.name}</b></>}
        </div>
      </button>
      <Badge tone={g.status === "running" ? "good" : g.status === "paused" ? "warn" : "info"}>{tr(GAME_STATUS, g.status)}</Badge>
      {children && <div className="flex gap-1">{children}</div>}
    </div>
  );
}

function GameDetail({ id, onClose }: { id: string; onClose: () => void }) {
  const { data: g } = useApi<GameState>(`/api/games/${id}`);
  const legs: { label: string; turns: Turn[] }[] = g
    ? [...g.state.leg_history.map((l) => ({ label: `Leg ${l.leg}${g.settings.sets_to_win > 1 ? ` (set ${l.set})` : ""} — wygrał(a) ${g.players[l.winner]?.name}`, turns: l.turns })),
      ...(g.state.turns.length && !g.state.finished ? [{ label: `Leg ${g.state.leg} (w trakcie)`, turns: g.state.turns }] : [])]
    : [];
  return (
    <Modal open onClose={onClose} title={g ? `${modeName(g.mode, g.mode_name)} — ${g.players.map((p) => p.name).join(" vs ")}` : "Gra"} wide>
      {!g ? null : legs.length === 0 ? <Empty title="Nie rzucono jeszcze żadnej lotki" /> : (
        <div className="flex flex-col gap-5">
          {legs.map((l) => (
            <div key={l.label}>
              <div className="mb-2 font-semibold">{l.label}</div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="text-left text-[var(--muted)]"><tr><th className="py-1">Gracz</th><th>Rzuty</th><th className="text-right">Punkty</th></tr></thead>
                  <tbody>
                    {l.turns.map((t, i) => (
                      <tr key={i} className="border-t border-[var(--border)]">
                        <td className="py-1">{g.players[t.player_index]?.name}</td>
                        <td className="font-mono">{t.darts.map((d) => dartLabel(d.label)).join("  ")} {t.bust && <Badge tone="bad">bust</Badge>}</td>
                        <td className="text-right tabular-nums">{t.points}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ))}
        </div>
      )}
    </Modal>
  );
}
