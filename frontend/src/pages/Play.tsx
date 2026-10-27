import clsx from "clsx";
import { ArrowRight, Hand, Pause, Play as PlayIcon, RotateCcw, Target, Trophy, Tv, UserPlus } from "lucide-react";
import { Link, useNavigate } from "react-router";
import { BoardView } from "@/components/board/BoardView";
import { CameraView } from "@/components/camera/CameraView";
import { EventFeed } from "@/components/EventFeed";
import { Scoreboard } from "@/components/game/Scoreboard";
import { TurnPanel } from "@/components/game/TurnPanel";
import { Badge, Button, Card, ErrorNote, useTilt } from "@/components/ui";
import { useAction, useApi } from "@/hooks/useApi";
import { useBoardDarts, useBoardGeometry } from "@/hooks/useBoard";
import { api } from "@/lib/api";
import { dartLabel, modeName, plural, settingValue } from "@/lib/pl";
import type { CameraInfo, GameState } from "@/lib/types";
import { useLive } from "@/store/live";
import { usePrefs } from "@/store/prefs";
import { useService } from "@/store/service";

/** One-line description of a game's rules, e.g. "501 · Double Out · do 3 legów". */
export function gameSummary(g: { mode: string; settings: Record<string, any> }): string {
  const s = g.settings;
  const parts: string[] = [];
  if (g.mode === "x01") {
    parts.push(String(s.start_score));
    if (s.in_mode && s.in_mode !== "straight") parts.push(settingValue("in_mode", s.in_mode));
    parts.push(settingValue("out_mode", s.out_mode));
  }
  if (g.mode === "cricket" && s.variant === "cutthroat") parts.push("Cut-throat");
  if (g.mode === "shanghai") parts.push(`${s.rounds} ${plural(s.rounds, "runda", "rundy", "rund")}`);
  if (s.sets_to_win > 1) parts.push(`do ${s.sets_to_win} ${plural(s.sets_to_win, "seta", "setów", "setów")}`);
  if (s.legs_to_win_set > 1) parts.push(`do ${s.legs_to_win_set} ${plural(s.legs_to_win_set, "lega", "legów", "legów")}`);
  return parts.join(" · ");
}

export const QUICK_STARTS = [
  { mode: "x01", start: 501, title: "501", sub: "Klasyk turniejowy" },
  { mode: "x01", start: 301, title: "301", sub: "Szybka partia" },
  { mode: "cricket", title: "Cricket", sub: "Zamknij 15–20 i bulla" },
  { mode: "atc", title: "Dookoła", sub: "Pola 1–20 po kolei" },
];

function quickLink(q: (typeof QUICK_STARTS)[number]): string {
  return `/games?mode=${q.mode}${q.start ? `&start=${q.start}` : ""}`;
}

export default function Play() {
  const game = useLive((s) => s.game);
  const active = game && (game.status === "running" || game.status === "paused" || (game.status === "finished" && game.state.finished)) ? game : null;
  return active ? <GameScreen game={active} /> : <Home />;
}

function useStaff(): boolean {
  return useService((s) => s.until) > Date.now();
}

function BoardWithLastDart({ highlight = [], className }: { highlight?: string[]; className?: string }) {
  const lastDart = useLive((s) => s.lastDart);
  const board = useBoardGeometry();
  const darts = useBoardDarts();
  const markers = darts.map((d, i) => ({
    id: d.id, x_mm: d.x_mm, y_mm: d.y_mm, label: dartLabel(d.label), cov: d.cov, uncertain: d.uncertain,
    ghost: i < darts.length - 3,
  }));
  return (
    <div className={clsx("relative mx-auto aspect-square w-full", className)}>
      <BoardView board={board} markers={markers} highlight={highlight} />
      {lastDart && (
        <div key={lastDart.dart_id} className="glass animate-pop absolute top-1 right-1 rounded-3xl px-5 py-3 text-right">
          <div className={clsx("font-score text-6xl font-extrabold leading-none", lastDart.uncertain ? "text-[var(--warn)]" : "lava-text")}>{dartLabel(lastDart.score.label)}</div>
          <div className="mt-1 text-xs text-[var(--muted)]">{lastDart.score.score} pkt{lastDart.uncertain ? " · sprawdź" : ""}</div>
        </div>
      )}
    </div>
  );
}

function CameraStrip() {
  const widgets = usePrefs((s) => s.widgets);
  const overlay = usePrefs((s) => s.cameraOverlay);
  const health = useLive((s) => s.cameras);
  const { data: cams } = useApi<CameraInfo[]>(widgets.cameras ? "/api/cameras" : null);
  if (!widgets.cameras || !cams) return null;
  return (
    <details className="glass group rounded-3xl">
      <summary className="cursor-pointer list-none px-5 py-3.5 font-display text-[15px] font-bold tracking-[0.1em] text-[var(--muted)] uppercase select-none">
        <span className="inline-block transition group-open:rotate-90">›</span> Podgląd kamer
      </summary>
      <div className="grid grid-cols-1 gap-3 p-3 pt-0 sm:grid-cols-3">
        {cams.filter((c) => c.enabled).map((c) => (
          <CameraView key={c.id} cameraId={c.id} name={c.name} width={480} fps={6} overlay={overlay}
            health={health.find((h) => h.camera_id === c.id) ?? c.health} />
        ))}
      </div>
    </details>
  );
}

function GameScreen({ game }: { game: GameState }) {
  const setGame = useLive((s) => s.setGame);
  const widgets = usePrefs((s) => s.widgets);
  const layout = usePrefs((s) => s.layout);
  const staff = useStaff();
  const st = game.state;
  const cfg = game.settings;
  const toggle = useAction(async () => {
    setGame(await api.post<GameState>(`/api/games/${game.id}/${game.status === "paused" ? "resume" : "pause"}`));
  });

  const turn = widgets.turn && !st.finished && (
    <Card className="h-full"><TurnPanel game={game} /></Card>
  );
  const board = widgets.board && (
    <div className={clsx("flex items-center justify-center", layout === "board-left" && "lg:order-first")}>
      <BoardWithLastDart highlight={widgets.checkout ? game.checkout_hint ?? [] : []} className="max-w-[min(72vh,720px)]" />
    </div>
  );

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <div className="min-w-0 flex-1 basis-full sm:basis-auto">
          <div className="flex flex-wrap items-baseline gap-x-3">
            <h1 className="font-display text-4xl font-extrabold tracking-wide uppercase md:text-5xl">{modeName(game.mode, game.mode_name)}</h1>
            <span className="text-lg text-[var(--muted)]">{gameSummary(game)}</span>
          </div>
          <div className="mt-0.5 flex flex-wrap items-center gap-2 text-sm text-[var(--muted)]">
            {cfg.sets_to_win > 1 && <span>Set <b className="text-[var(--text)]">{st.set}</b></span>}
            <span>Leg <b className="text-[var(--text)]">{st.leg}</b></span>
            {game.status === "paused" && <Badge tone="warn">wstrzymana</Badge>}
            {st.finished && <Badge tone="good">zakończona</Badge>}
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          {!st.finished && (
            <Button size="lg" onClick={() => toggle.run()} disabled={toggle.busy} variant={game.status === "paused" ? "primary" : "secondary"}>
              {game.status === "paused" ? <><PlayIcon size={18} /> Wznów</> : <><Pause size={18} /> Pauza</>}
            </Button>
          )}
          <Link to="/tv"><Button size="lg"><Tv size={18} /> Tryb TV</Button></Link>
        </div>
      </div>
      <ErrorNote error={toggle.error} />

      {st.finished && <WinnerCard game={game} />}
      {widgets.scoreboard && <Scoreboard game={game} />}

      {(turn || board) && (
        <div className={clsx("grid items-start gap-5", layout === "stacked" || !turn || !board ? "grid-cols-1" : "lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]")}>
          {turn}{board}
        </div>
      )}

      {staff && widgets.feed && <Card title="Zdarzenia"><EventFeed limit={8} /></Card>}
      {staff && <CameraStrip />}
    </div>
  );
}

function WinnerCard({ game }: { game: GameState }) {
  const setGame = useLive((s) => s.setGame);
  const nav = useNavigate();
  const rematch = useAction(async () => {
    setGame(await api.post<GameState>("/api/games", { mode: game.mode, settings: game.settings, player_ids: game.players.map((p) => p.id) }));
  });
  return (
    <div className="glass animate-rise relative overflow-hidden rounded-3xl border-[var(--good)]/60 p-6 md:p-8">
      <div className="pointer-events-none absolute -top-24 -right-24 h-72 w-72 rounded-full bg-[var(--good)] opacity-15 blur-3xl" />
      <div className="flex flex-wrap items-center gap-6">
        <div className="animate-float grid h-24 w-24 place-items-center rounded-full bg-[color-mix(in_oklab,var(--accent-2)_25%,transparent)] text-[var(--accent-2)] shadow-[0_0_60px_-10px_var(--accent-2)]">
          <Trophy size={50} />
        </div>
        <div className="min-w-0 flex-1">
          <div className="text-sm font-bold tracking-[0.2em] text-[var(--muted)] uppercase">Zwycięzca</div>
          <div className="truncate font-display text-6xl font-extrabold tracking-wide uppercase md:text-7xl"><span className="lava-text">{game.winner?.name}</span></div>
        </div>
        <div className="flex flex-wrap gap-3">
          <Button size="xl" variant="primary" onClick={() => rematch.run()} disabled={rematch.busy}><RotateCcw size={26} /> Rewanż</Button>
          <Button size="xl" onClick={() => { setGame(null); nav("/games"); }}>Nowa gra</Button>
        </div>
      </div>
      <ErrorNote error={rematch.error} />
    </div>
  );
}

function QuickTile({ q }: { q: (typeof QUICK_STARTS)[number] }) {
  const tilt = useTilt<HTMLAnchorElement>(10);
  return (
    <Link to={quickLink(q)} {...tilt}
      className="glass tilt group flex min-h-32 flex-col justify-between rounded-3xl p-4 hover:border-[var(--accent)]">
      <div className="pop-out font-score text-5xl leading-none font-extrabold transition group-hover:text-[var(--accent)]">{q.title}</div>
      <div className="mt-3 flex items-center justify-between gap-2 text-sm text-[var(--muted)]">
        {q.sub}
        <ArrowRight size={16} className="shrink-0 opacity-0 transition group-hover:translate-x-1 group-hover:opacity-100" />
      </div>
    </Link>
  );
}

const HOW = [
  { icon: Target, title: "Wybierz grę", text: "Kliknij „Nowa gra” albo jedną z gier poniżej." },
  { icon: UserPlus, title: "Wpisz graczy", text: "Wystarczą imiona — kolejność rzucania ustawisz strzałkami." },
  { icon: Hand, title: "Rzucaj!", text: "Punkty liczą się same. Po 3 lotkach wyjmij je z tarczy." },
];

function Home() {
  const nav = useNavigate();
  return (
    <div className="flex flex-col gap-10">
      <section className="grid items-center gap-8 lg:min-h-[calc(100dvh-170px)] lg:grid-cols-[minmax(0,1fr)_minmax(0,1.05fr)]">
        <div className="flex flex-col gap-6">
          <div className="inline-flex w-fit items-center gap-2 rounded-full border border-[var(--border)] bg-[var(--surface)] px-3 py-1 text-xs font-bold tracking-[0.18em] text-[var(--muted)] uppercase">
            <span className="h-2 w-2 animate-pulse rounded-full bg-[var(--good)]" /> Automatyczne liczenie punktów
          </div>
          <h1 className="font-display text-6xl leading-[0.92] font-extrabold tracking-wide uppercase md:text-7xl xl:text-8xl">
            Rzucaj.<br /><span className="lava-text">Reszta liczy się sama.</span>
          </h1>
          <p className="max-w-xl text-lg text-[var(--muted)]">
            Trzy kamery widzą każdą lotkę. Nie musisz niczego wpisywać — wybierz grę, dodaj graczy i graj.
          </p>
          <div>
            <Button size="xl" variant="primary" className="animate-pulse-ring" onClick={() => nav("/games")}>
              <Target size={30} /> Nowa gra
            </Button>
          </div>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {QUICK_STARTS.map((q) => <QuickTile key={q.title} q={q} />)}
          </div>
        </div>
        <div className="relative">
          <div className="pointer-events-none absolute inset-[12%] rounded-full bg-[var(--accent)] opacity-20 blur-[90px]" />
          <BoardWithLastDart className="max-w-[min(78vh,760px)]" />
        </div>
      </section>

      <section className="grid gap-4 md:grid-cols-3">
        {HOW.map((h, i) => {
          const Icon = h.icon;
          return (
            <div key={h.title} className="glass flex items-start gap-4 rounded-3xl p-5">
              <div className="relative grid h-14 w-14 shrink-0 place-items-center rounded-2xl bg-[var(--surface-2)] text-[var(--accent)]">
                <Icon size={26} />
                <span className="absolute -top-2 -left-2 grid h-7 w-7 place-items-center rounded-full bg-[var(--accent)] font-score text-lg font-bold text-white">{i + 1}</span>
              </div>
              <div>
                <div className="font-display text-2xl font-bold tracking-wide uppercase">{h.title}</div>
                <div className="text-[var(--muted)]">{h.text}</div>
              </div>
            </div>
          );
        })}
      </section>
      <p className="text-center text-sm text-[var(--muted)]">Bez rozpoczętej gry rzucone lotki też pojawią się na tarczy — ale nie są liczone.</p>
    </div>
  );
}
