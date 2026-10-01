import clsx from "clsx";
import { Link } from "react-router";
import { Dartboard } from "@/components/board/Dartboard";
import { CameraView } from "@/components/camera/CameraView";
import { EventFeed } from "@/components/EventFeed";
import { Scoreboard } from "@/components/game/Scoreboard";
import { TurnPanel } from "@/components/game/TurnPanel";
import { UncertainDialog } from "@/components/game/UncertainDialog";
import { Badge, Button, Card, Empty } from "@/components/ui";
import { useApi } from "@/hooks/useApi";
import { useBoardDarts, useBoardGeometry } from "@/hooks/useBoard";
import { api } from "@/lib/api";
import type { CameraInfo, GameState } from "@/lib/types";
import { useLive } from "@/store/live";
import { usePrefs } from "@/store/prefs";

export default function Play() {
  const game = useLive((s) => s.game);
  const setGame = useLive((s) => s.setGame);
  const lastDart = useLive((s) => s.lastDart);
  const health = useLive((s) => s.cameras);
  const widgets = usePrefs((s) => s.widgets);
  const layout = usePrefs((s) => s.layout);
  const overlay = usePrefs((s) => s.cameraOverlay);
  const board = useBoardGeometry();
  const darts = useBoardDarts();
  const { data: cams } = useApi<CameraInfo[]>("/api/cameras");
  const active = game && (game.status === "running" || game.status === "paused") ? game : null;

  const markers = darts.map((d, i) => ({
    id: d.id, x_mm: d.x_mm, y_mm: d.y_mm, label: d.label, cov: d.cov, uncertain: d.uncertain,
    ghost: i < darts.length - 3,
  }));
  const highlight = active?.checkout_hint ?? [];

  const boardCard = widgets.board && (
    <Card className="flex flex-col" pad={false}>
      <div className="relative mx-auto aspect-square w-full max-w-[min(78vh,760px)] p-3">
        <Dartboard board={board} markers={markers} highlight={widgets.checkout ? highlight : []} />
        {lastDart && (
          <div key={lastDart.dart_id} className="animate-pop absolute top-4 right-4 rounded-2xl border border-[var(--border)] bg-[var(--surface)]/90 px-4 py-2 text-right backdrop-blur">
            <div className={clsx("font-display text-4xl font-black", lastDart.uncertain ? "text-[var(--warn)]" : "text-[var(--accent)]")}>{lastDart.score.label}</div>
            <div className="text-xs text-[var(--muted)]">{lastDart.score.score} pts · {Math.round(lastDart.confidence.overall * 100)}%</div>
          </div>
        )}
      </div>
    </Card>
  );

  const side = (
    <div className="flex min-w-0 flex-col gap-4">
      {active ? (
        <>
          {widgets.scoreboard && (
            <Card title={`${active.mode_name} · leg ${active.state.leg}${active.settings.sets_to_win > 1 ? ` · set ${active.state.set}` : ""}`}
              actions={<>
                {active.status === "paused" && <Badge tone="warn">paused</Badge>}
                {active.status === "paused"
                  ? <Button size="sm" variant="primary" onClick={async () => setGame(await api.post<GameState>(`/api/games/${active.id}/resume`))}>Resume</Button>
                  : <Button size="sm" onClick={async () => setGame(await api.post<GameState>(`/api/games/${active.id}/pause`))}>Pause</Button>}
              </>}>
              <Scoreboard game={active} />
            </Card>
          )}
          {widgets.turn && <Card title="Current turn"><TurnPanel game={active} /></Card>}
          {active.state.finished && (
            <Card>
              <div className="py-6 text-center">
                <div className="text-sm text-[var(--muted)]">Winner</div>
                <div className="font-display text-5xl font-black text-[var(--good)]">{active.winner?.name}</div>
                <Link to="/games"><Button className="mt-4" variant="primary">New game</Button></Link>
              </div>
            </Card>
          )}
          <UncertainDialog game={active} />
        </>
      ) : (
        <Card>
          <Empty title="No game running">
            Free play: detected darts appear on the board. <Link className="text-[var(--accent)] underline" to="/games">Start a game</Link> to keep score.
          </Empty>
        </Card>
      )}
      {widgets.feed && <Card title="Events"><EventFeed /></Card>}
    </div>
  );

  return (
    <div className="flex flex-col gap-4">
      <div className={clsx("grid gap-4",
        layout === "stacked" ? "grid-cols-1" : "lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]")}>
        {layout === "board-right" ? <>{side}{boardCard}</> : <>{boardCard}{side}</>}
      </div>
      {widgets.cameras && cams && (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          {cams.filter((c) => c.enabled).map((c) => (
            <CameraView key={c.id} cameraId={c.id} name={c.name} width={480} fps={6} overlay={overlay}
              health={health.find((h) => h.camera_id === c.id) ?? c.health} />
          ))}
        </div>
      )}
    </div>
  );
}
