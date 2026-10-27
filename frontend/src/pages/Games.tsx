import clsx from "clsx";
import { ArrowDown, ArrowLeft, ArrowRight, ArrowUp, Check, Minus, Plus, Settings2, Target, UserPlus, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router";
import { Badge, Button, ErrorNote, inputCls, Toggle, useTilt } from "@/components/ui";
import { useAction, useApi } from "@/hooks/useApi";
import { api } from "@/lib/api";
import { MODE_DESCRIPTIONS, modeName, plural, settingLabel, SETTING_HINTS, settingValue } from "@/lib/pl";
import type { GameMode, GameState, GameSummary, Player, SettingSchema } from "@/lib/types";
import { useLive } from "@/store/live";
import { gameSummary } from "./Play";

const COLORS = ["#ff5a1f", "#34d399", "#3b82f6", "#fbbf24", "#a855f7", "#14b8a6", "#f43f5e", "#ec4899"];
const MAX_PLAYERS = 8;

/** Short taglines on the mode cards. */
const MODE_TAG: Record<string, string> = {
  x01: "Najpopularniejsza",
  cricket: "Taktyczna",
  atc: "Dla początkujących",
  shanghai: "Na szczęście",
  bobs27: "Trening",
};

function Segmented<T extends string | number>({ value, options, onChange, format }: {
  value: T; options: T[]; onChange: (v: T) => void; format?: (v: T) => string;
}) {
  return (
    <div className="flex flex-wrap gap-2">
      {options.map((o) => (
        <button key={String(o)} type="button" onClick={() => onChange(o)}
          className={clsx("min-w-16 rounded-2xl border-2 px-4 py-2.5 text-lg font-bold transition",
            o === value ? "border-[var(--accent)] bg-[var(--accent)] text-white shadow-[0_8px_20px_-10px_var(--accent)]" : "border-[var(--border)] bg-[var(--surface-2)] hover:border-[var(--muted)]")}>
          {format ? format(o) : String(o)}
        </button>
      ))}
    </div>
  );
}

function Stepper({ value, min = 0, max = 99, onChange }: { value: number; min?: number; max?: number; onChange: (v: number) => void }) {
  return (
    <div className="inline-flex items-center overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--surface-2)]">
      <button type="button" className="px-4 py-3 hover:bg-[var(--border)] disabled:opacity-40" disabled={value <= min} onClick={() => onChange(Math.max(min, value - 1))} aria-label="Mniej"><Minus size={18} /></button>
      <span className="min-w-14 text-center font-score text-3xl font-bold">{value}</span>
      <button type="button" className="px-4 py-3 hover:bg-[var(--border)] disabled:opacity-40" disabled={value >= max} onClick={() => onChange(Math.min(max, value + 1))} aria-label="Więcej"><Plus size={18} /></button>
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
    <div className="flex flex-col gap-2">
      <div className="font-semibold">{settingLabel(k)}</div>
      {control}
      {SETTING_HINTS[k] && <div className="text-sm text-[var(--muted)]">{SETTING_HINTS[k]}</div>}
    </div>
  );
}

const STEPS = ["Gra", "Gracze", "Start"];

function StepBar({ step, onPick }: { step: number; onPick: (i: number) => void }) {
  return (
    <ol className="flex items-center gap-2">
      {STEPS.map((s, i) => (
        <li key={s} className="flex flex-1 items-center gap-2">
          <button type="button" disabled={i > step} onClick={() => onPick(i)}
            className={clsx("flex items-center gap-2.5 rounded-2xl px-2 py-1 text-left transition disabled:cursor-default",
              i === step ? "text-[var(--text)]" : i < step ? "text-[var(--good)] hover:bg-[var(--surface-2)]" : "text-[var(--muted)]")}>
            <span className={clsx("grid h-10 w-10 shrink-0 place-items-center rounded-full font-score text-xl font-bold",
              i === step ? "bg-[var(--accent)] text-white shadow-[0_0_0_5px_color-mix(in_oklab,var(--accent)_25%,transparent)]"
                : i < step ? "bg-[var(--good)] text-black" : "bg-[var(--surface-2)]")}>
              {i < step ? <Check size={20} /> : i + 1}
            </span>
            <span className="font-display text-xl font-bold tracking-wide uppercase">{s}</span>
          </button>
          {i < STEPS.length - 1 && <span className={clsx("h-1 flex-1 rounded-full", i < step ? "bg-[var(--good)]" : "bg-[var(--border)]")} />}
        </li>
      ))}
    </ol>
  );
}

function ModeCard({ m, selected, onPick }: { m: GameMode; selected: boolean; onPick: () => void }) {
  const tilt = useTilt<HTMLButtonElement>(9);
  return (
    <button onClick={onPick} {...tilt}
      className={clsx("glass tilt relative flex min-h-44 flex-col rounded-3xl p-5 text-left",
        selected ? "border-[var(--accent)] bg-[color-mix(in_oklab,var(--accent)_14%,var(--surface))]" : "hover:border-[var(--muted)]")}>
      {MODE_TAG[m.id] && <span className="pop-out mb-3 w-fit rounded-full bg-[var(--surface-2)] px-2.5 py-0.5 text-xs font-bold tracking-wider text-[var(--accent)] uppercase">{MODE_TAG[m.id]}</span>}
      {selected && <span className="absolute top-4 right-4 grid h-8 w-8 place-items-center rounded-full bg-[var(--accent)] text-white"><Check size={18} /></span>}
      <div className="pop-out font-score text-5xl leading-none font-extrabold">{modeName(m.id, m.name)}</div>
      <div className="mt-3 text-[var(--muted)]">{MODE_DESCRIPTIONS[m.id] ?? m.description}</div>
    </button>
  );
}

/** New game in three big steps: pick a game, type the players' names, start. */
export default function NewGame() {
  const [params] = useSearchParams();
  const nav = useNavigate();
  const setGame = useLive((s) => s.setGame);
  const { data: modes } = useApi<GameMode[]>("/api/game-modes");
  const { data: players } = useApi<Player[]>("/api/players");
  const { data: recent } = useApi<GameSummary[]>("/api/games?limit=20");
  const preset = params.get("mode");
  const [step, setStep] = useState(preset ? 1 : 0);
  const [modeId, setModeId] = useState(preset ?? "x01");
  const [settings, setSettings] = useState<Record<string, any>>({});
  const [names, setNames] = useState<string[]>(["", ""]);
  const [showRules, setShowRules] = useState(false);
  const firstInput = useRef<HTMLInputElement>(null);
  const mode = useMemo(() => modes?.find((m) => m.id === modeId), [modes, modeId]);

  useEffect(() => {
    if (!mode) return;
    const defaults = Object.fromEntries(Object.entries(mode.settings).map(([k, s]) => [k, s.default]));
    const start = Number(params.get("start"));
    if (mode.id === "x01" && start) defaults.start_score = start;
    setSettings(defaults);
  }, [mode, params]);

  useEffect(() => {
    if (step === 1) firstInput.current?.focus();
  }, [step]);

  const finalNames = names.map((n, i) => n.trim() || `Gracz ${i + 1}`);
  const duplicate = finalNames.find((n, i) => finalNames.findIndex((x) => x.toLowerCase() === n.toLowerCase()) !== i);

  const create = useAction(async () => {
    // Reuse players by name, create the new ones.
    const known = new Map((players ?? []).map((p) => [p.name.toLowerCase(), p]));
    const ids: string[] = [];
    for (const [i, name] of finalNames.entries()) {
      const p = known.get(name.toLowerCase())
        ?? await api.post<Player>("/api/players", { name, color: COLORS[i % COLORS.length] });
      ids.push(p.id);
    }
    const g = await api.post<GameState>("/api/games", { mode: modeId, settings, player_ids: ids });
    setGame(g);
    nav("/");
  });

  // Names from recent games, for one-tap entry.
  const suggestions = useMemo(() => {
    const seen = new Set(names.map((n) => n.trim().toLowerCase()));
    const out: string[] = [];
    for (const g of recent ?? []) for (const p of g.players) {
      const k = p.name.toLowerCase();
      if (!seen.has(k) && !/^gracz \d+$/i.test(p.name)) {
        seen.add(k);
        out.push(p.name);
      }
    }
    return out.slice(0, 10);
  }, [recent, names]);

  function addName(v = "") {
    setNames((ns) => {
      const empty = ns.findIndex((n) => !n.trim());
      if (v && empty >= 0) return ns.map((n, i) => (i === empty ? v : n));
      return ns.length < MAX_PLAYERS ? [...ns, v] : ns;
    });
  }
  function move(i: number, d: number) {
    setNames((s) => {
      const a = [...s];
      const j = i + d;
      if (j < 0 || j >= a.length) return s;
      [a[i], a[j]] = [a[j], a[i]];
      return a;
    });
  }

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h1 className="font-display text-4xl font-extrabold tracking-wide uppercase md:text-5xl">Nowa gra</h1>
        <div className="w-full md:w-[560px]"><StepBar step={step} onPick={setStep} /></div>
      </div>

      {step === 0 && (
        <section className="animate-rise flex flex-col gap-4">
          <p className="text-lg text-[var(--muted)]">W co gramy? Dotknij gry.</p>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {modes?.map((m) => (
              <ModeCard key={m.id} m={m} selected={m.id === modeId} onPick={() => { setModeId(m.id); setStep(1); }} />
            ))}
          </div>
        </section>
      )}

      {step === 1 && (
        <section className="animate-rise grid gap-6 lg:grid-cols-[minmax(0,1fr)_340px]">
          <div className="glass flex flex-col gap-4 rounded-3xl p-5">
            <div>
              <h2 className="font-display text-3xl font-bold tracking-wide uppercase">Kto gra?</h2>
              <p className="text-[var(--muted)]">Wpisz imiona. Pierwszy na liście rzuca pierwszy. Puste pole = „Gracz 1”, „Gracz 2”…</p>
            </div>
            <ol className="flex flex-col gap-2.5">
              {names.map((n, i) => (
                <li key={i} className="flex items-center gap-2">
                  <span className="grid h-12 w-12 shrink-0 place-items-center rounded-2xl font-score text-2xl font-bold text-white" style={{ background: COLORS[i % COLORS.length] }}>{i + 1}</span>
                  <input ref={i === 0 ? firstInput : undefined} className={clsx(inputCls, "h-12 min-w-0 flex-1 text-lg")} value={n} maxLength={64}
                    placeholder={`Gracz ${i + 1}`} onChange={(e) => setNames((ns) => ns.map((x, j) => (j === i ? e.target.value : x)))}
                    onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); if (i === names.length - 1 && names.length < MAX_PLAYERS && n.trim()) addName(); else setStep(2); } }} />
                  <Button size="sm" variant="ghost" onClick={() => move(i, -1)} disabled={i === 0} aria-label="Wyżej"><ArrowUp size={18} /></Button>
                  <Button size="sm" variant="ghost" onClick={() => move(i, 1)} disabled={i === names.length - 1} aria-label="Niżej"><ArrowDown size={18} /></Button>
                  <Button size="sm" variant="ghost" onClick={() => setNames((ns) => ns.filter((_, j) => j !== i))} disabled={names.length === 1} aria-label="Usuń gracza"><X size={18} /></Button>
                </li>
              ))}
            </ol>
            {names.length < MAX_PLAYERS && (
              <Button size="lg" className="w-fit" onClick={() => addName()}><UserPlus size={18} /> Dodaj gracza</Button>
            )}
            {duplicate && <div className="text-sm font-semibold text-[var(--warn)]">Dwóch graczy ma to samo imię („{duplicate}”) — zmień jedno z nich.</div>}
          </div>
          <div className="flex flex-col gap-4">
            {suggestions.length > 0 && (
              <div className="glass rounded-3xl p-5">
                <div className="mb-3 font-display text-lg font-bold tracking-wide text-[var(--muted)] uppercase">Grali niedawno</div>
                <div className="flex flex-wrap gap-2">
                  {suggestions.map((s) => (
                    <button key={s} onClick={() => addName(s)} className="rounded-full border border-[var(--border)] bg-[var(--surface-2)] px-3.5 py-1.5 font-semibold transition hover:border-[var(--accent)]">
                      + {s}
                    </button>
                  ))}
                </div>
              </div>
            )}
            <div className="glass rounded-3xl p-5">
              <div className="font-display text-lg font-bold tracking-wide text-[var(--muted)] uppercase">Wybrana gra</div>
              <div className="font-score text-4xl font-extrabold">{mode ? modeName(mode.id, mode.name) : "…"}</div>
              <Button size="sm" variant="ghost" className="mt-1" onClick={() => setStep(0)}><ArrowLeft size={14} /> zmień</Button>
            </div>
          </div>
          <div className="flex justify-between gap-3 lg:col-span-2">
            <Button size="lg" onClick={() => setStep(0)}><ArrowLeft size={18} /> Wstecz</Button>
            <Button size="lg" variant="primary" disabled={!!duplicate} onClick={() => setStep(2)}>Dalej <ArrowRight size={18} /></Button>
          </div>
        </section>
      )}

      {step === 2 && mode && (
        <section className="animate-rise flex flex-col gap-5">
          <div className="glass relative overflow-hidden rounded-3xl p-6 md:p-8">
            <div className="pointer-events-none absolute -top-20 -right-10 h-64 w-64 rounded-full bg-[var(--accent)] opacity-20 blur-3xl" />
            <div className="text-sm font-bold tracking-[0.2em] text-[var(--muted)] uppercase">Gotowe do gry</div>
            <div className="mt-1 flex flex-wrap items-baseline gap-x-4">
              <div className="font-display text-6xl font-extrabold tracking-wide uppercase"><span className="lava-text">{modeName(mode.id, mode.name)}</span></div>
              <div className="text-xl text-[var(--muted)]">{gameSummary({ mode: mode.id, settings })}</div>
            </div>
            <div className="mt-5 flex flex-wrap gap-2">
              {finalNames.map((n, i) => (
                <span key={i} className="flex items-center gap-2 rounded-full py-1.5 pr-4 pl-1.5 text-lg font-bold text-white" style={{ background: COLORS[i % COLORS.length] }}>
                  <span className="grid h-8 w-8 place-items-center rounded-full bg-black/25 font-score">{i + 1}</span>{n}
                </span>
              ))}
            </div>
            <div className="mt-6 flex flex-wrap items-center gap-4">
              <Button size="xl" variant="primary" className="animate-pulse-ring" disabled={create.busy} onClick={() => create.run()}>
                <Target size={30} /> Zaczynamy!
              </Button>
              <span className="text-[var(--muted)]">{finalNames.length} {plural(finalNames.length, "gracz", "graczy", "graczy")} · po 3 lotkach wyjmij je z tarczy</span>
            </div>
            <ErrorNote error={create.error} />
          </div>

          {Object.keys(mode.settings).length > 0 && (
            <div className="glass rounded-3xl">
              <button className="flex w-full items-center gap-3 px-5 py-4 text-left" onClick={() => setShowRules((v) => !v)}>
                <Settings2 size={20} className="text-[var(--accent)]" />
                <span className="flex-1 font-display text-xl font-bold tracking-wide uppercase">Zasady <span className="text-base font-normal tracking-normal text-[var(--muted)] normal-case">— opcjonalnie, domyślne są w porządku</span></span>
                <span className={clsx("transition", showRules && "rotate-90")}>›</span>
              </button>
              {showRules && (
                <div className="grid gap-6 border-t border-[var(--border)] p-5 sm:grid-cols-2">
                  {Object.entries(mode.settings).map(([k, s]) => (
                    <SettingControl key={k} k={k} s={s} value={settings[k]} onChange={(v) => setSettings({ ...settings, [k]: v })} />
                  ))}
                </div>
              )}
            </div>
          )}
          <div><Button size="lg" onClick={() => setStep(1)}><ArrowLeft size={18} /> Wstecz</Button></div>
        </section>
      )}
    </div>
  );
}
