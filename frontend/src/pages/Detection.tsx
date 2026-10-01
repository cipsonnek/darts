import clsx from "clsx";
import { Dartboard } from "@/components/board/Dartboard";
import { CameraView } from "@/components/camera/CameraView";
import { Badge, Button, Card, Empty, PageHeader, Stat } from "@/components/ui";
import { useApi } from "@/hooks/useApi";
import { useBoardDarts, useBoardGeometry } from "@/hooks/useBoard";
import { api } from "@/lib/api";
import type { CameraInfo, DartDetection, EngineStatus } from "@/lib/types";
import { useLive } from "@/store/live";

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
      <PageHeader title="Detection" subtitle="Live view of the vision engine: what it sees, what it decided and why."
        actions={<>
          <Button onClick={async () => { await api.post(`/api/detection/pause?paused=${!status?.paused}`); reload(); }}>
            {status?.paused ? "Resume detection" : "Pause detection"}
          </Button>
          <Button variant="danger" onClick={async () => { await api.post("/api/board/reset?mark_empty=true"); reload(); }}
            title="Forget known darts and use the current view as the empty board">Board is empty → reset</Button>
        </>} />
      <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-6">
        <Stat label="Engine" value={<span className="text-xl">{engineState ?? status?.state ?? "—"}</span>} />
        <Stat label="Darts on board" value={status?.darts_on_board.length ?? 0} />
        <Stat label="Detected / uncertain" value={`${stats?.darts ?? 0} / ${stats?.uncertain ?? 0}`} />
        <Stat label="Processing (mean / p95)" value={<span className="text-xl">{stats?.processing_ms ? `${stats.processing_ms.mean} / ${stats.processing_ms.p95} ms` : "—"}</span>} />
        <Stat label="Camera sync spread" value={<span className="text-xl">{sync != null ? `${sync.toFixed(1)} ms` : "—"}</span>} />
        <Stat label="Obstructions / unrecognised" value={`${stats?.obstructions ?? 0} / ${stats?.unrecognized ?? 0}`} />
      </div>
      <div className="mb-4 grid gap-3 md:grid-cols-3">
        {cams?.filter((c) => c.enabled).map((c) => (
          <div key={c.id} className="flex flex-col gap-2">
            <CameraView cameraId={c.id} name={c.name} overlay={["roi", "change", "candidates", "darts", "info"]} width={640} fps={8} />
            <div className="flex items-center gap-2 text-xs">
              <span className="w-20 text-[var(--muted)]">motion</span>
              <div className="h-2 flex-1 overflow-hidden rounded bg-[var(--surface-2)]">
                <div className="h-full bg-[var(--accent)] transition-all" style={{ width: `${Math.min(100, (motion[c.id] ?? 0) * 2000)}%` }} />
              </div>
              <span className="w-16 text-right tabular-nums">{((motion[c.id] ?? 0) * 100).toFixed(2)}%</span>
              <Badge tone={status?.cameras[c.id]?.calibrated ? "good" : "bad"}>{status?.cameras[c.id]?.calibrated ? "calibrated" : "uncalibrated"}</Badge>
            </div>
          </div>
        ))}
      </div>
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_420px]">
        <Card title="Last detection">
          {!last ? <Empty title="No dart detected yet" /> : <DetectionDetail d={last} />}
        </Card>
        <div className="flex flex-col gap-4">
          <Card title="Board state">
            <div className="aspect-square">
              <Dartboard board={board} markers={darts.map((d) => ({ id: d.id, x_mm: d.x_mm, y_mm: d.y_mm, label: d.label, cov: d.cov, uncertain: d.uncertain }))} />
            </div>
          </Card>
          <Card title="Recent detections">
            <div className="flex flex-col gap-1 text-sm">
              {recent?.map((r) => (
                <div key={r.id} className="flex items-center gap-2">
                  <span className="w-12 font-display font-bold">{r.final_label ?? r.label}</span>
                  <span className="flex-1 text-xs text-[var(--muted)]">{r.created_at && new Date(r.created_at).toLocaleTimeString()} · {Math.round(r.confidence * 100)}% · {r.cameras_used.join(",")}</span>
                  <Badge tone={r.status === "accepted" ? "good" : r.status === "pending" ? "warn" : "info"}>{r.status}</Badge>
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
          <div className={clsx("font-display text-6xl font-black", d.uncertain ? "text-[var(--warn)]" : "text-[var(--accent)]")}>{d.score.label}</div>
          <div className="text-sm text-[var(--muted)]">{d.score.score} points {d.uncertain && <Badge tone="warn">uncertain</Badge>}</div>
        </div>
        <div className="grid flex-1 grid-cols-2 gap-2 sm:grid-cols-4">
          <Stat label="Detection confidence" value={pct(d.confidence.detection)} />
          <Stat label="Impact confidence (±2 mm)" value={pct(d.confidence.impact)} />
          <Stat label="Score confidence" value={pct(d.confidence.score)} />
          <Stat label="Overall" value={pct(d.confidence.overall)} tone={d.uncertain ? "warn" : "good"} />
        </div>
      </div>
      <div className="grid gap-x-6 gap-y-1 text-sm sm:grid-cols-2">
        <div>Impact: <b>({d.impact.x_mm.toFixed(2)}, {d.impact.y_mm.toFixed(2)}) mm</b> · r {d.impact.r_mm.toFixed(1)} mm · θ {d.impact.theta_deg.toFixed(1)}°</div>
        <div>1-σ uncertainty: <b>±{d.sigma_mm.toFixed(2)} mm</b></div>
        <div>Dart tilt: <b>{d.tilt_deg != null ? `${d.tilt_deg.toFixed(1)}°` : "n/a"}</b> · line consistency {pct(d.consistency)}</div>
        <div>Cameras: <b>{d.cameras_used.join(", ")}</b>
          {Object.entries(d.cameras_rejected).map(([c, why]) => <Badge key={c} tone="warn" className="ml-1">{c}: {why}</Badge>)}</div>
      </div>
      {d.alternatives.length > 0 && (
        <div className="flex flex-wrap gap-2 text-sm">
          <span className="text-[var(--muted)]">Alternatives:</span>
          {d.alternatives.map((a) => <Badge key={a.label}>{a.label} {pct(a.probability)}</Badge>)}
        </div>
      )}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-left text-xs text-[var(--muted)]">
            <tr><th className="py-1">Camera</th><th>Candidate</th><th>Tip px</th><th>Line RMS</th><th>Length</th><th>Residual</th><th>σ line</th><th>Tip weight</th></tr>
          </thead>
          <tbody>
            {Object.entries(d.per_camera).map(([c, v]) => (
              <tr key={c} className="border-t border-[var(--border)] tabular-nums">
                <td className="py-1 font-semibold">{c}</td>
                <td>{pct(v.confidence)}</td>
                <td>{v.tip_px.map((x) => x.toFixed(1)).join(", ")} {!v.tip_visible && <Badge tone="warn">hidden</Badge>}</td>
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
