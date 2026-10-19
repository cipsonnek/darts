import clsx from "clsx";
import { ArrowDown, ArrowUp, Check, Minus, Plus, UserPlus, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router";
import { Badge, Button, Card, Empty, ErrorNote, inputCls, Modal, PageHeader, Toggle } from "@/components/ui";
import { useAction, useApi } from "@/hooks/useApi";
import { api } from "@/lib/api";
import { dartLabel, GAME_STATUS, MODE_DESCRIPTIONS, modeName, plural, settingLabel, SETTING_HINTS, settingValue, tr } from "@/lib/pl";
import type { GameMode, GameState, GameSummary, Player, SettingSchema, Turn } from "@/lib/types";
import { useLive } from "@/store/live";
import { gameSummary } from "./Play";

const COLORS = ["#e8324a", "#2ecc71", "#3b82f6", "#f5b942", "#a855f7", "#14b8a6", "#f97316", "#ec4899"];

export default function Games() {
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
      <PageHeader title="Nowa gra" subtitle="Wybierz tryb, ustaw zasady i dodaj graczy." />
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_420px]">
        <NewGame onCreated={(g) => { setGame(g); nav("/"); }} />
        <div className="flex flex-col gap-4">
          {unfinished.length > 0 && (
            <Card title="Niedokończone gry">
              <div className="flex flex-col divide-y divide-[var(--border)]">
                {unfinished.map((g) => (
                  <GameRow key={g.id} g={g} onDetail={() => setDetail(g.id)}>
                    <Button size="sm" variant="primary" onClick={() => act.run(g.id, "resume")}>Wznów</Button>
                    <Button size="sm" variant="ghost" onClick={() => act.run(g.id, "abandon")}>Przerwij</Button>
                  </GameRow>
                ))}
              </div>
            </Card>
          )}
          <Card title="Historia gier">
            <ErrorNote error={error ?? act.error} />
            {!done.length ? <Empty title="Brak rozegranych gier" /> : (
              <div className="flex max-h-[60vh] flex-col divide-y divide-[var(--border)] overflow-y-auto">
                {done.map((g) => <GameRow key={g.id} g={g} onDetail={() => setDetail(g.id)} />)}
              </div>
            )}
          </Card>
        </div>
      </div>
      {detail && <GameDetail id={detail} onClose={() => setDetail(null)} />}
    </div>
  );
}

function GameRow({ g, onDetail, children }: { g: GameSummary; onDetail: () => void; children?: React.ReactNode }) {
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

function Step({ n, title, children }: { n: number; title: string; children: React.ReactNode }) {
  return (
    <section className="flex flex-col gap-3">
      <h2 className="flex items-center gap-2.5 font-display text-lg font-bold">
        <span className="grid h-7 w-7 place-items-center rounded-full bg-[var(--accent)] text-sm text-white">{n}</span>
        {title}
      </h2>
      {children}
    </section>
  );
}

function Segmented<T extends string | number>({ value, options, onChange, format }: {
  value: T; options: T[]; onChange: (v: T) => void; format?: (v: T) => string;
}) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {options.map((o) => (
        <button key={String(o)} type="button" onClick={() => onChange(o)}
          className={clsx("min-w-16 rounded-xl border px-4 py-2 font-semibold transition",
            o === value ? "border-[var(--accent)] bg-[var(--accent)] text-white" : "border-[var(--border)] bg-[var(--surface-2)] hover:border-[var(--muted)]")}>
          {format ? format(o) : String(o)}
        </button>
      ))}
    </div>
  );
}

function Stepper({ value, min = 0, max = 99, onChange }: { value: number; min?: number; max?: number; onChange: (v: number) => void }) {
  return (
    <div className="inline-flex items-center overflow-hidden rounded-xl border border-[var(--border)] bg-[var(--surface-2)]">
      <button type="button" className="px-3 py-2 hover:bg-[var(--border)] disabled:opacity-40" disabled={value <= min} onClick={() => onChange(Math.max(min, value - 1))} aria-label="Mniej"><Minus size={16} /></button>
      <span className="min-w-12 text-center font-score text-2xl font-bold">{value}</span>
      <button type="button" className="px-3 py-2 hover:bg-[var(--border)] disabled:opacity-40" disabled={value >= max} onClick={() => onChange(Math.min(max, value + 1))} aria-label="Więcej"><Plus size={16} /></button>
    </div>
  );
}

function SettingControl({ k, s, value, onChange }: { k: string; s: SettingSchema; value: any; onChange: (v: any) => void }) {
  let control: React.ReactNode;
  if (s.type === "enum") control = <Segmented value={value} options={s.values ?? []} onChange={onChange} format={(v) => settingValue(k, v)} />;
  else if (s.type === "boolean") control = <Toggle checked={!!value} onChange={onChange} label={value ? "tak" : "nie"} />;
  else if (s.presets) {
    control = (
      <div className="flex flex-wrap items-center gap-2">
        <Segmented value={value} options={s.presets} onChange={onChange} />
        {!s.presets.includes(value) && <Badge tone="accent">{value}</Badge>}
      </div>
    );
  } else control = <Stepper value={Number(value ?? 0)} min={s.min} max={s.max} onChange={onChange} />;
  return (
    <div className="flex flex-col gap-1.5">
      <div className="text-sm font-semibold text-[var(--muted)]">{settingLabel(k)}</div>
      {control}
      {SETTING_HINTS[k] && <div className="text-xs text-[var(--muted)]">{SETTING_HINTS[k]}</div>}
    </div>
  );
}

function NewGame({ onCreated }: { onCreated: (g: GameState) => void }) {
  const [params] = useSearchParams();
  const { data: modes } = useApi<GameMode[]>("/api/game-modes");
  const { data: players, reload: reloadPlayers } = useApi<Player[]>("/api/players");
  const [modeId, setModeId] = useState(params.get("mode") ?? "x01");
  const [settings, setSettings] = useState<Record<string, any>>({});
  const [selected, setSelected] = useState<string[]>([]);
  const [newName, setNewName] = useState("");
  const mode = useMemo(() => modes?.find((m) => m.id === modeId), [modes, modeId]);

  useEffect(() => {
    if (!mode) return;
    const defaults = Object.fromEntries(Object.entries(mode.settings).map(([k, s]) => [k, s.default]));
    const start = Number(params.get("start"));
    if (mode.id === "x01" && start) defaults.start_score = start;
    setSettings(defaults);
  }, [mode, params]);

  const create = useAction(async () => {
    onCreated(await api.post<GameState>("/api/games", { mode: modeId, settings, player_ids: selected }));
  });
  const addPlayer = useAction(async () => {
    const p = await api.post<Player>("/api/players", { name: newName.trim(), color: COLORS[(players?.length ?? 0) % COLORS.length] });
    setNewName("");
    setSelected((s) => [...s, p.id]);
    reloadPlayers();
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
  const active = players?.filter((p) => !p.archived) ?? [];
  const byId = (id: string) => players?.find((p) => p.id === id);

  return (
    <Card>
      <div className="flex flex-col gap-7">
        <Step n={1} title="Tryb gry">
          <div className="grid grid-cols-2 gap-2 md:grid-cols-3 2xl:grid-cols-5">
            {modes?.map((m) => (
              <button key={m.id} onClick={() => setModeId(m.id)}
                className={clsx("relative flex flex-col rounded-2xl border-2 p-4 text-left transition",
                  m.id === modeId ? "border-[var(--accent)] bg-[color-mix(in_oklab,var(--accent)_10%,transparent)]" : "border-[var(--border)] hover:border-[var(--muted)]")}>
                {m.id === modeId && <Check size={18} className="absolute top-3 right-3 text-[var(--accent)]" />}
                <div className="font-score text-3xl font-extrabold leading-none">{modeName(m.id, m.name)}</div>
                <div className="mt-2 text-sm text-[var(--muted)]">{MODE_DESCRIPTIONS[m.id] ?? m.description}</div>
              </button>
            ))}
          </div>
        </Step>

        {mode && Object.keys(mode.settings).length > 0 && (
          <Step n={2} title="Zasady">
            <div className="grid gap-5 sm:grid-cols-2">
              {Object.entries(mode.settings).map(([k, s]) => (
                <SettingControl key={k} k={k} s={s} value={settings[k]} onChange={(v) => setSettings({ ...settings, [k]: v })} />
              ))}
            </div>
          </Step>
        )}

        <Step n={3} title="Gracze">
          <div className="text-sm text-[var(--muted)]">Kliknij, aby dodać do gry. Kolejność na liście = kolejność rzucania.</div>
          <div className="flex flex-wrap gap-2">
            {active.map((p) => {
              const on = selected.includes(p.id);
              return (
                <button key={p.id} onClick={() => toggle(p.id)}
                  className={clsx("flex items-center gap-2 rounded-full border-2 py-1.5 pr-4 pl-1.5 font-semibold transition",
                    on ? "border-transparent text-white" : "border-[var(--border)] hover:border-[var(--muted)]")}
                  style={on ? { background: p.color } : undefined}>
                  <span className="grid h-7 w-7 place-items-center rounded-full text-sm font-bold text-white" style={{ background: on ? "rgba(0,0,0,.25)" : p.color }}>
                    {on ? selected.indexOf(p.id) + 1 : p.name.slice(0, 1).toUpperCase()}
                  </span>
                  {p.name}
                </button>
              );
            })}
          </div>
          <form className="flex max-w-md gap-2" onSubmit={(e) => { e.preventDefault(); if (newName.trim()) addPlayer.run(); }}>
            <input className={clsx(inputCls, "flex-1")} value={newName} maxLength={64} onChange={(e) => setNewName(e.target.value)} placeholder="Nowy gracz — wpisz imię" />
            <Button disabled={!newName.trim() || addPlayer.busy}><UserPlus size={16} /> Dodaj</Button>
          </form>
          <ErrorNote error={addPlayer.error} />
          {selected.length > 0 && (
            <ol className="flex flex-col gap-1.5">
              {selected.map((id, i) => {
                const p = byId(id);
                return (
                  <li key={id} className="flex items-center gap-3 rounded-xl border border-[var(--border)] bg-[var(--surface-2)] px-3 py-2">
                    <span className="w-6 font-score text-xl font-bold text-[var(--muted)]">{i + 1}.</span>
                    <span className="h-3 w-3 rounded-full" style={{ background: p?.color }} />
                    <span className="flex-1 font-semibold">{p?.name}</span>
                    <Button size="sm" variant="ghost" onClick={() => move(i, -1)} disabled={i === 0} aria-label="W górę"><ArrowUp size={16} /></Button>
                    <Button size="sm" variant="ghost" onClick={() => move(i, 1)} disabled={i === selected.length - 1} aria-label="W dół"><ArrowDown size={16} /></Button>
                    <Button size="sm" variant="ghost" onClick={() => toggle(id)} aria-label="Usuń z gry"><X size={16} /></Button>
                  </li>
                );
              })}
            </ol>
          )}
        </Step>

        <ErrorNote error={create.error} />
        <div className="sticky bottom-20 flex flex-wrap items-center gap-3 rounded-2xl border border-[var(--border)] bg-[var(--surface-2)] p-3 md:bottom-4">
          <div className="min-w-0 flex-1">
            <div className="font-display font-bold">{mode ? modeName(mode.id, mode.name) : "—"} <span className="font-normal text-[var(--muted)]">{mode && gameSummary({ mode: mode.id, settings })}</span></div>
            <div className="text-sm text-[var(--muted)]">
              {selected.length ? `${selected.length} ${plural(selected.length, "gracz", "graczy", "graczy")}` : "Wybierz przynajmniej jednego gracza"}
            </div>
          </div>
          <Button variant="primary" size="lg" disabled={!selected.length || create.busy} onClick={() => create.run()}>Rozpocznij grę</Button>
        </div>
      </div>
    </Card>
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
