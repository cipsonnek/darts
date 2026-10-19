import clsx from "clsx";
import { Dartboard } from "@/components/board/Dartboard";
import { CameraView } from "@/components/camera/CameraView";
import { Badge, Button, Card, Empty, PageHeader, Stat } from "@/components/ui";
import { useApi } from "@/hooks/useApi";
import { useBoardDarts, useBoardGeometry } from "@/hooks/useBoard";
import { api } from "@/lib/api";
import type { CameraInfo, DartDetection, EngineStatus } from "@/lib/types";
import { useLive } from "@/store/live";
import { dartLabel, DETECTION_STATUS, ENGINE_STATE, tr } from "@/lib/pl";

function pct(v: number) {
  return `${(v * 100).toFixed(1)}%`;
}

export default function Detection() {
  const { data: cams } = useApi<CameraInfo[]>("/api/cameras");
  const { data: status, reload } = useApi<EngineStatus>("/api/detection/status", 2000);
  const { data: recent } = useApi<any[]>("/api/detections?limit=15", 3000);
  const lastLive = useLive((s) => s.lastDart);
  const motion = useLive((s) => s.motion);
  const engineState = useLive((s) => s.engineState);
  const sync = useLive((s) => s.syncSpreadMs);
  const board = useBoardGeometry();
  const darts = useBoardDarts();
  const last: DartDetection | null = lastLive ?? status?.last_detection ?? null;
  const stats = status?.stats;

  return (
    <div>
      <PageHeader title="Detekcja" subtitle="Podgląd silnika wizji na żywo: co widzi, co zdecydował i dlaczego."
        actions={<>
          <Button onClick={async () => { await api.post(`/api/detection/pause?paused=${!status?.paused}`); reload(); }}>
            {status?.paused ? "Wznów detekcję" : "Wstrzymaj detekcję"}
          </Button>
          <Button variant="danger" onClick={async () => { await api.post("/api/board/reset?mark_empty=true"); reload(); }}
            title="Zapomnij znane lotki i użyj bieżącego obrazu jako pustej tarczy">Tarcza pusta → reset</Button>
        </>} />
      <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-6">
        <Stat label="Silnik" value={<span className="text-xl">{tr(ENGINE_STATE, engineState ?? status?.state)}</span>} />
        <Stat label="Lotki w tarczy" value={status?.darts_on_board.length ?? 0} />
        <Stat label="Wykryte / niepewne" value={`${stats?.darts ?? 0} / ${stats?.uncertain ?? 0}`} />
        <Stat label="Analiza (średnio / p95)" value={<span className="text-xl">{stats?.processing_ms ? `${stats.processing_ms.mean} / ${stats.processing_ms.p95} ms` : "—"}</span>} />
        <Stat label="Rozsynchronizowanie kamer" value={<span className="text-xl">{sync != null ? `${sync.toFixed(1)} ms` : "—"}</span>} />
        <Stat label="Zasłonięcia / nierozpoznane" value={`${stats?.obstructions ?? 0} / ${stats?.unrecognized ?? 0}`} />
      </div>
      <div className="mb-4 grid gap-3 md:grid-cols-3">
        {cams?.filter((c) => c.enabled).map((c) => (
          <div key={c.id} className="flex flex-col gap-2">
            <CameraView cameraId={c.id} name={c.name} overlay={["roi", "change", "candidates", "darts", "info"]} width={640} fps={8} />
            <div className="flex items-center gap-2 text-xs">
              <span className="w-20 text-[var(--muted)]">ruch</span>
              <div className="h-2 flex-1 overflow-hidden rounded bg-[var(--surface-2)]">
                <div className="h-full bg-[var(--accent)] transition-all" style={{ width: `${Math.min(100, (motion[c.id] ?? 0) * 2000)}%` }} />
              </div>
              <span className="w-16 text-right tabular-nums">{((motion[c.id] ?? 0) * 100).toFixed(2)}%</span>
              <Badge tone={status?.cameras[c.id]?.calibrated ? "good" : "bad"}>{status?.cameras[c.id]?.calibrated ? "skalibrowana" : "nieskalibrowana"}</Badge>
            </div>
          </div>
        ))}
      </div>
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_420px]">
        <Card title="Ostatni odczyt">
          {!last ? <Empty title="Nie wykryto jeszcze żadnej lotki" /> : <DetectionDetail d={last} />}
        </Card>
        <div className="flex flex-col gap-4">
          <Card title="Stan tarczy">
            <div className="aspect-square">
              <Dartboard board={board} markers={darts.map((d) => ({ id: d.id, x_mm: d.x_mm, y_mm: d.y_mm, label: dartLabel(d.label), cov: d.cov, uncertain: d.uncertain }))} />
            </div>
          </Card>
          <Card title="Ostatnie odczyty">
            <div className="flex flex-col gap-1 text-sm">
              {recent?.map((r) => (
                <div key={r.id} className="flex items-center gap-2">
                  <span className="w-14 font-score text-lg font-bold">{dartLabel(r.final_label ?? r.label)}</span>
                  <span className="flex-1 text-xs text-[var(--muted)]">{r.created_at && new Date(r.created_at).toLocaleTimeString("pl-PL")} · {Math.round(r.confidence * 100)}% · {r.cameras_used.join(",")}</span>
                  <Badge tone={r.status === "accepted" ? "good" : r.status === "pending" ? "warn" : "info"}>{tr(DETECTION_STATUS, r.status)}</Badge>
                </div>
              ))}
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}

export function DetectionDetail({ d }: { d: DartDetection }) {
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end gap-6">
        <div>
          <div className={clsx("font-score text-7xl font-extrabold", d.uncertain ? "text-[var(--warn)]" : "text-[var(--accent)]")}>{dartLabel(d.score.label)}</div>
          <div className="text-sm text-[var(--muted)]">{d.score.score} pkt {d.uncertain && <Badge tone="warn">niepewny</Badge>}</div>
        </div>
        <div className="grid flex-1 grid-cols-2 gap-2 sm:grid-cols-4">
          <Stat label="Pewność wykrycia" value={pct(d.confidence.detection)} />
          <Stat label="Pewność miejsca (±2 mm)" value={pct(d.confidence.impact)} />
          <Stat label="Pewność wyniku" value={pct(d.confidence.score)} />
          <Stat label="Łącznie" value={pct(d.confidence.overall)} tone={d.uncertain ? "warn" : "good"} />
        </div>
      </div>
      <div className="grid gap-x-6 gap-y-1 text-sm sm:grid-cols-2">
        <div>Trafienie: <b>({d.impact.x_mm.toFixed(2)}, {d.impact.y_mm.toFixed(2)}) mm</b> · r {d.impact.r_mm.toFixed(1)} mm · θ {d.impact.theta_deg.toFixed(1)}°</div>
        <div>Niepewność 1σ: <b>±{d.sigma_mm.toFixed(2)} mm</b></div>
        <div>Pochylenie lotki: <b>{d.tilt_deg != null ? `${d.tilt_deg.toFixed(1)}°` : "b/d"}</b> · zgodność linii {pct(d.consistency)}</div>
        <div>Kamery: <b>{d.cameras_used.join(", ")}</b>
          {Object.entries(d.cameras_rejected).map(([c, why]) => <Badge key={c} tone="warn" className="ml-1">{c}: {why}</Badge>)}</div>
      </div>
      {d.alternatives.length > 0 && (
        <div className="flex flex-wrap gap-2 text-sm">
          <span className="text-[var(--muted)]">Alternatywy:</span>
          {d.alternatives.map((a) => <Badge key={a.label}>{dartLabel(a.label)} {pct(a.probability)}</Badge>)}
        </div>
      )}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-left text-xs text-[var(--muted)]">
            <tr><th className="py-1">Kamera</th><th>Kandydat</th><th>Grot px</th><th>RMS linii</th><th>Długość</th><th>Rezyduum</th><th>σ linii</th><th>Waga grotu</th></tr>
          </thead>
          <tbody>
            {Object.entries(d.per_camera).map(([c, v]) => (
              <tr key={c} className="border-t border-[var(--border)] tabular-nums">
                <td className="py-1 font-semibold">{c}</td>
                <td>{pct(v.confidence)}</td>
                <td>{v.tip_px.map((x) => x.toFixed(1)).join(", ")} {!v.tip_visible && <Badge tone="warn">niewidoczny</Badge>}</td>
                <td>{v.line_rms_px.toFixed(2)} px</td>
                <td>{v.length_px.toFixed(0)} px</td>
                <td>{v.line_residual_mm.toFixed(2)} mm</td>
                <td>{v.line_sigma_mm.toFixed(2)} mm</td>
                <td>{v.tip_weight.toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
