import clsx from "clsx";
import { Pause, Play as PlayIcon, RotateCcw, Trophy, Tv } from "lucide-react";
import { Link, useNavigate } from "react-router";
import { Dartboard } from "@/components/board/Dartboard";
import { CameraView } from "@/components/camera/CameraView";
import { EventFeed } from "@/components/EventFeed";
import { Scoreboard } from "@/components/game/Scoreboard";
import { TurnPanel } from "@/components/game/TurnPanel";
import { Badge, Button, Card, ErrorNote } from "@/components/ui";
import { useAction, useApi } from "@/hooks/useApi";
import { useBoardDarts, useBoardGeometry } from "@/hooks/useBoard";
import { api } from "@/lib/api";
import { dartLabel, modeName, plural, settingValue } from "@/lib/pl";
import type { CameraInfo, GameState } from "@/lib/types";
import { useLive } from "@/store/live";
import { usePrefs } from "@/store/prefs";

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
  { mode: "x01", start: 501, title: "501", sub: "Double Out — klasyk" },
  { mode: "x01", start: 301, title: "301", sub: "Szybsza partia" },
  { mode: "cricket", title: "Cricket", sub: "Zamykanie pól 15–20 i bulla" },
  { mode: "atc", title: "Dookoła tarczy", sub: "Trening: pola 1–20 po kolei" },
  { mode: "shanghai", title: "Shanghai", sub: "Runda po rundzie" },
  { mode: "bobs27", title: "Bob's 27", sub: "Trening doubli" },
];

function quickLink(q: (typeof QUICK_STARTS)[number]): string {
  return `/games?mode=${q.mode}${q.start ? `&start=${q.start}` : ""}`;
}

export default function Play() {
  const game = useLive((s) => s.game);
  const active = game && (game.status === "running" || game.status === "paused" || (game.status === "finished" && game.state.finished)) ? game : null;
  return active ? <GameScreen game={active} /> : <Home />;
}

function BoardWithLastDart({ highlight = [] }: { highlight?: string[] }) {
  const lastDart = useLive((s) => s.lastDart);
  const board = useBoardGeometry();
  const darts = useBoardDarts();
  const markers = darts.map((d, i) => ({
    id: d.id, x_mm: d.x_mm, y_mm: d.y_mm, label: dartLabel(d.label), cov: d.cov, uncertain: d.uncertain,
    ghost: i < darts.length - 3,
  }));
  return (
    <div className="relative mx-auto aspect-square w-full max-w-[min(70vh,680px)]">
      <Dartboard board={board} markers={markers} highlight={highlight} />
      {lastDart && (
        <div key={lastDart.dart_id} className="animate-pop absolute top-0 right-0 rounded-2xl border border-[var(--border)] bg-[var(--surface)]/90 px-4 py-2 text-right backdrop-blur">
          <div className={clsx("font-score text-5xl font-extrabold leading-none", lastDart.uncertain ? "text-[var(--warn)]" : "text-[var(--accent)]")}>{dartLabel(lastDart.score.label)}</div>
          <div className="mt-1 text-xs text-[var(--muted)]">{lastDart.score.score} pkt · pewność {Math.round(lastDart.confidence.overall * 100)}%</div>
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
    <details className="group rounded-2xl border border-[var(--border)] bg-[var(--surface)]">
      <summary className="cursor-pointer list-none px-4 py-3 text-[13px] font-bold tracking-[0.08em] text-[var(--muted)] uppercase select-none">
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
  const st = game.state;
  const cfg = game.settings;
  const toggle = useAction(async () => {
    setGame(await api.post<GameState>(`/api/games/${game.id}/${game.status === "paused" ? "resume" : "pause"}`));
  });

  const turn = widgets.turn && !st.finished && (
    <Card className="h-full"><TurnPanel game={game} /></Card>
  );
  const board = widgets.board && (
    <Card className={clsx("h-full", layout === "board-left" && "lg:order-first")}><BoardWithLastDart highlight={widgets.checkout ? game.checkout_hint ?? [] : []} /></Card>
  );

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-baseline gap-x-3">
            <h1 className="font-display text-2xl font-extrabold md:text-3xl">{modeName(game.mode, game.mode_name)}</h1>
            <span className="text-[var(--muted)]">{gameSummary(game)}</span>
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
            <Button onClick={() => toggle.run()} disabled={toggle.busy} variant={game.status === "paused" ? "primary" : "secondary"}>
              {game.status === "paused" ? <><PlayIcon size={16} /> Wznów</> : <><Pause size={16} /> Pauza</>}
            </Button>
          )}
          <Link to="/tv"><Button><Tv size={16} /> Tryb TV</Button></Link>
        </div>
      </div>
      <ErrorNote error={toggle.error} />

      {st.finished && <WinnerCard game={game} />}
      {widgets.scoreboard && <Scoreboard game={game} />}

      {(turn || board) && (
        <div className={clsx("grid gap-4", layout === "stacked" || !turn || !board ? "grid-cols-1" : "lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]")}>
          {turn}{board}
        </div>
      )}

      {widgets.feed && <Card title="Zdarzenia"><EventFeed limit={8} /></Card>}
      <CameraStrip />
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
    <Card className="animate-rise border-[var(--good)]/50">
      <div className="flex flex-wrap items-center gap-5">
        <div className="grid h-16 w-16 place-items-center rounded-full bg-[color-mix(in_oklab,var(--good)_20%,transparent)] text-[var(--good)]"><Trophy size={34} /></div>
        <div className="min-w-0 flex-1">
          <div className="text-sm font-semibold tracking-wide text-[var(--muted)] uppercase">Zwycięzca</div>
          <div className="truncate font-display text-4xl font-extrabold text-[var(--good)] md:text-5xl">{game.winner?.name}</div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button size="lg" variant="primary" onClick={() => rematch.run()} disabled={rematch.busy}><RotateCcw size={18} /> Rewanż</Button>
          <Button size="lg" onClick={() => { setGame(null); nav("/games"); }}>Nowa gra</Button>
        </div>
      </div>
      <ErrorNote error={rematch.error} />
    </Card>
  );
}

function Home() {
  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="font-display text-3xl font-extrabold md:text-4xl">Zagrajmy!</h1>
        <p className="mt-1 text-[var(--muted)]">Wybierz grę, dodaj graczy i rzucaj — punkty liczą się same.</p>
      </div>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        {QUICK_STARTS.map((q) => (
          <Link key={q.title} to={quickLink(q)}
            className="group flex min-h-32 flex-col justify-between rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-4 transition hover:-translate-y-0.5 hover:border-[var(--accent)]">
            <div className="font-score text-4xl font-extrabold leading-none group-hover:text-[var(--accent)]">{q.title}</div>
            <div className="mt-3 text-sm text-[var(--muted)]">{q.sub}</div>
          </Link>
        ))}
      </div>
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
        <Card title="Wolna gra">
          <BoardWithLastDart />
          <p className="mt-3 text-center text-sm text-[var(--muted)]">Bez rozpoczętej gry wykryte lotki pojawiają się na tarczy, ale nie są liczone.</p>
        </Card>
        <div className="flex flex-col gap-4">
          <Card title="Zdarzenia"><EventFeed /></Card>
        </div>
      </div>
      <CameraStrip />
    </div>
  );
}
