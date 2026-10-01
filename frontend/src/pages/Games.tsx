import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router";
import { Badge, Button, Card, Empty, ErrorNote, Field, inputCls, Modal, PageHeader, Toggle } from "@/components/ui";
import { useAction, useApi } from "@/hooks/useApi";
import { api } from "@/lib/api";
import type { GameMode, GameState, GameSummary, Player, Turn } from "@/lib/types";
import { useLive } from "@/store/live";

export default function Games() {
  const { data: games, reload, error } = useApi<GameSummary[]>("/api/games?limit=100");
  const [detail, setDetail] = useState<string | null>(null);
  const setGame = useLive((s) => s.setGame);
  const nav = useNavigate();

  async function act(id: string, action: string) {
    const g = await api.post<GameState>(`/api/games/${id}/${action}`);
    if (action === "resume" || action === "start") {
      setGame(g);
      nav("/");
    }
    reload();
  }

  return (
    <div>
      <PageHeader title="Games" subtitle="Create, resume and review games. Rules run on the server; any device can follow along." />
      <div className="grid gap-4 xl:grid-cols-[minmax(0,460px)_minmax(0,1fr)]">
        <NewGame onCreated={(g) => { setGame(g); nav("/"); }} />
        <Card title="Recent games">
          <ErrorNote error={error} />
          {!games?.length ? <Empty title="No games yet" /> : (
            <div className="flex flex-col divide-y divide-[var(--border)]">
              {games.map((g) => (
                <div key={g.id} className="flex flex-wrap items-center gap-3 py-2.5">
                  <div className="min-w-0 flex-1">
                    <div className="font-semibold">
                      {g.mode.toUpperCase()} {g.mode === "x01" && g.settings.start_score}
                      <span className="ml-2 text-sm font-normal text-[var(--muted)]">{g.players.map((p) => p.name).join(" vs ")}</span>
                    </div>
                    <div className="text-xs text-[var(--muted)]">
                      {g.created_at && new Date(g.created_at).toLocaleString()}
                      {g.winner && <> · winner <b className="text-[var(--good)]">{g.winner.name}</b></>}
                    </div>
                  </div>
                  <Badge tone={g.status === "running" ? "good" : g.status === "paused" ? "warn" : "info"}>{g.status}</Badge>
                  <div className="flex gap-1">
                    {(g.status === "paused" || g.status === "created") && <Button size="sm" variant="primary" onClick={() => act(g.id, "resume")}>Resume</Button>}
                    {g.status === "running" && <Button size="sm" onClick={() => act(g.id, "pause")}>Pause</Button>}
                    {(g.status === "running" || g.status === "paused") && <Button size="sm" onClick={() => act(g.id, "abandon")}>Abandon</Button>}
                    <Button size="sm" variant="ghost" onClick={() => setDetail(g.id)}>Details</Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>
      {detail && <GameDetail id={detail} onClose={() => setDetail(null)} />}
    </div>
  );
}

function NewGame({ onCreated }: { onCreated: (g: GameState) => void }) {
  const { data: modes } = useApi<GameMode[]>("/api/game-modes");
  const { data: players } = useApi<Player[]>("/api/players");
  const [modeId, setModeId] = useState("x01");
  const [settings, setSettings] = useState<Record<string, any>>({});
  const [selected, setSelected] = useState<string[]>([]);
  const mode = useMemo(() => modes?.find((m) => m.id === modeId), [modes, modeId]);

  useEffect(() => {
    if (!mode) return;
    setSettings(Object.fromEntries(Object.entries(mode.settings).map(([k, s]) => [k, s.default])));
  }, [mode]);

  const create = useAction(async () => {
    const g = await api.post<GameState>("/api/games", { mode: modeId, settings, player_ids: selected });
    onCreated(g);
  });

  function toggle(id: string) {
    setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));
  }
  function move(i: number, d: number) {
    setSelected((s) => {
      const a = [...s];
      const j = i + d;
      if (j < 0 || j >= a.length) return s;
      [a[i], a[j]] = [a[j], a[i]];
      return a;
    });
  }

  return (
    <Card title="New game">
      <div className="flex flex-col gap-4">
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          {modes?.map((m) => (
            <button key={m.id} onClick={() => setModeId(m.id)}
              className={`rounded-xl border p-3 text-left transition ${m.id === modeId ? "border-[var(--accent)] bg-[color-mix(in_oklab,var(--accent)_12%,transparent)]" : "border-[var(--border)] hover:bg-[var(--surface-2)]"}`}>
              <div className="font-display font-bold">{m.name}</div>
              <div className="text-xs text-[var(--muted)]">{m.description}</div>
            </button>
          ))}
        </div>
        {mode && (
          <div className="grid grid-cols-2 gap-3">
            {Object.entries(mode.settings).map(([k, s]) => (
              <Field key={k} label={k.replace(/_/g, " ")} hint={s.help}>
                {s.type === "enum" ? (
                  <select className={inputCls} value={settings[k] ?? ""} onChange={(e) => setSettings({ ...settings, [k]: e.target.value })}>
                    {s.values!.map((v) => <option key={v} value={v}>{v}</option>)}
                  </select>
                ) : s.type === "boolean" ? (
                  <Toggle checked={!!settings[k]} onChange={(v) => setSettings({ ...settings, [k]: v })} />
                ) : s.presets ? (
                  <select className={inputCls} value={settings[k] ?? ""} onChange={(e) => setSettings({ ...settings, [k]: Number(e.target.value) })}>
                    {s.presets.map((v) => <option key={v} value={v}>{v}</option>)}
                  </select>
                ) : (
                  <input type="number" className={inputCls} min={s.min} max={s.max} value={settings[k] ?? ""}
                    onChange={(e) => setSettings({ ...settings, [k]: Number(e.target.value) })} />
                )}
              </Field>
            ))}
          </div>
        )}
        <div>
          <div className="mb-2 text-sm font-medium text-[var(--muted)]">Players (tap to add; order = throwing order)</div>
          {!players?.length ? (
            <div className="text-sm text-[var(--muted)]">Create players on the Players page first.</div>
          ) : (
            <div className="flex flex-wrap gap-2">
              {players.map((p) => (
                <button key={p.id} onClick={() => toggle(p.id)}
                  className={`rounded-full border px-3 py-1.5 text-sm font-semibold ${selected.includes(p.id) ? "border-transparent text-white" : "border-[var(--border)]"}`}
                  style={selected.includes(p.id) ? { background: p.color } : undefined}>
                  {p.name}
                </button>
              ))}
            </div>
          )}
          {selected.length > 1 && (
            <ol className="mt-3 flex flex-col gap-1">
              {selected.map((id, i) => (
                <li key={id} className="flex items-center gap-2 text-sm">
                  <span className="w-5 text-[var(--muted)]">{i + 1}.</span>
                  <span className="flex-1">{players?.find((p) => p.id === id)?.name}</span>
                  <Button size="sm" variant="ghost" onClick={() => move(i, -1)}>↑</Button>
                  <Button size="sm" variant="ghost" onClick={() => move(i, 1)}>↓</Button>
                </li>
              ))}
            </ol>
          )}
        </div>
        <ErrorNote error={create.error} />
        <Button variant="primary" size="lg" disabled={!selected.length || create.busy} onClick={() => create.run()}>Start game</Button>
      </div>
    </Card>
  );
}

function GameDetail({ id, onClose }: { id: string; onClose: () => void }) {
  const { data: g } = useApi<GameState>(`/api/games/${id}`);
  const legs: { label: string; turns: Turn[] }[] = g
    ? [...g.state.leg_history.map((l) => ({ label: `Leg ${l.leg} (set ${l.set}) — won by ${g.players[l.winner]?.name}`, turns: l.turns })),
      ...(g.state.turns.length ? [{ label: `Leg ${g.state.leg} (current)`, turns: g.state.turns }] : [])]
    : [];
  return (
    <Modal open onClose={onClose} title={g ? `${g.mode_name} — ${g.players.map((p) => p.name).join(" vs ")}` : "Game"} wide>
      {!g ? null : legs.length === 0 ? <Empty title="No darts thrown" /> : (
        <div className="flex flex-col gap-5">
          {legs.map((l) => (
            <div key={l.label}>
              <div className="mb-2 font-semibold">{l.label}</div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="text-left text-[var(--muted)]"><tr><th className="py-1">Player</th><th>Darts</th><th className="text-right">Points</th></tr></thead>
                  <tbody>
                    {l.turns.map((t, i) => (
                      <tr key={i} className="border-t border-[var(--border)]">
                        <td className="py-1">{g.players[t.player_index]?.name}</td>
                        <td className="font-mono">{t.darts.map((d) => d.label).join("  ")} {t.bust && <Badge tone="bad">bust</Badge>}</td>
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
