import { useState } from "react";
import { CameraView } from "@/components/camera/CameraView";
import { Badge, Button, Card, ErrorNote, Field, inputCls, Modal, PageHeader, Tabs, Toggle } from "@/components/ui";
import { useAction, useApi } from "@/hooks/useApi";
import { api } from "@/lib/api";
import type { CameraHealth, CameraInfo } from "@/lib/types";
import { useLive } from "@/store/live";

const LAYERS = ["board", "sectors", "labels", "roi", "change", "candidates", "darts", "info"];

export default function Cameras() {
  const { data: cams, reload, error } = useApi<CameraInfo[]>("/api/cameras", 5000);
  const live = useLive((s) => s.cameras);
  const [view, setView] = useState<"raw" | "undistorted" | "topdown">("raw");
  const [layers, setLayers] = useState<string[]>(["board", "darts"]);
  const [edit, setEdit] = useState<CameraInfo | null>(null);
  const [probe, setProbe] = useState<any[] | null>(null);
  const doProbe = useAction(async () => setProbe(await api.get<any[]>("/api/cameras/probe")));

  return (
    <div>
      <PageHeader title="Cameras" subtitle="Live feeds are encoded on the server at reduced size; full-resolution frames never leave the vision engine."
        actions={<Button onClick={() => doProbe.run()} disabled={doProbe.busy}>Probe devices</Button>} />
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <Tabs value={view} onChange={setView} items={[{ id: "raw", label: "Raw" }, { id: "undistorted", label: "Undistorted" }, { id: "topdown", label: "Top-down" }]} />
        <div className="flex flex-wrap gap-1">
          {LAYERS.map((l) => (
            <button key={l} onClick={() => setLayers((s) => (s.includes(l) ? s.filter((x) => x !== l) : [...s, l]))}
              className={`rounded-full border px-2.5 py-1 text-xs font-semibold ${layers.includes(l) ? "border-[var(--accent)] text-[var(--accent)]" : "border-[var(--border)] text-[var(--muted)]"}`}>
              {l}
            </button>
          ))}
        </div>
      </div>
      <ErrorNote error={error ?? doProbe.error} />
      <div className="grid gap-4 xl:grid-cols-3">
        {cams?.map((c) => {
          const h = live.find((x) => x.camera_id === c.id) ?? c.health;
          return (
            <Card key={c.id} pad={false}
              title={<span className="flex items-center gap-2">{c.name} {c.synthetic && <Badge tone="warn">synthetic</Badge>} {!c.enabled && <Badge>disabled</Badge>}</span>}
              actions={<Button size="sm" variant="ghost" onClick={() => setEdit(c)}>Configure</Button>}>
              <div className="p-3">
                {c.enabled ? <CameraView cameraId={c.id} overlay={view === "raw" ? layers : []} view={view} width={800} fps={10} health={h} />
                  : <div className="grid aspect-video place-items-center rounded-xl bg-black text-sm text-[var(--muted)]">disabled</div>}
                <HealthTable h={h} calibrated={c.calibration.pose} grade={c.calibration.grade} />
              </div>
            </Card>
          );
        })}
      </div>
      {edit && <CameraEditor cam={edit} onClose={() => { setEdit(null); reload(); }} />}
      <Modal open={!!probe} onClose={() => setProbe(null)} title="Capture devices">
        {probe && probe.length === 0 && <div className="text-sm text-[var(--muted)]">No devices found (or simulator mode).</div>}
        <div className="flex flex-col gap-2 text-sm">
          {probe?.map((p) => (
            <div key={p.index} className="rounded-lg border border-[var(--border)] p-2">
              <b>Device {p.index}</b> — {p.width}×{p.height} · {p.backend} · {p.frames} frames
              {p.likely_virtual_or_blank && <Badge tone="warn" className="ml-2">blank/virtual?</Badge>}
            </div>
          ))}
        </div>
      </Modal>
    </div>
  );
}

function HealthTable({ h, calibrated, grade }: { h: CameraHealth | null | undefined; calibrated: boolean; grade: string | null }) {
  if (!h) return null;
  const rows: [string, React.ReactNode][] = [
    ["State", <Badge tone={h.connected ? "good" : "bad"}>{h.state}</Badge>],
    ["Calibration", calibrated ? <Badge tone={grade === "good" ? "good" : "warn"}>{grade}</Badge> : <Badge tone="bad">not calibrated</Badge>],
    ["Resolution", `${h.width}×${h.height}`],
    ["FPS (target)", `${h.fps.toFixed(1)} (${h.target_fps})`],
    ["Frame jitter", `${h.frame_interval_jitter_ms.toFixed(1)} ms`],
    ["Brightness / contrast", `${h.brightness.toFixed(0)} / ${h.contrast.toFixed(0)}`],
    ["Over / under-exposed", `${(h.saturated_fraction * 100).toFixed(1)}% / ${(h.dark_fraction * 100).toFixed(1)}%`],
    ["Sharpness", h.sharpness.toFixed(0)],
    ["Frames / corrupted", `${h.frames_total} / ${h.frames_corrupted}`],
    ["Reconnects", h.reconnects],
  ];
  return (
    <div className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
      {rows.map(([k, v]) => (
        <div key={k} className="contents">
          <div className="text-[var(--muted)]">{k}</div>
          <div className="text-right tabular-nums">{v}</div>
        </div>
      ))}
      {h.last_error && <div className="col-span-2 text-xs text-[var(--bad)]">{h.last_error}</div>}
      {h.saturated_fraction > 0.05 && <div className="col-span-2 text-xs text-[var(--warn)]">Image is over-exposed — lower exposure or gain.</div>}
      {h.brightness < 35 && h.connected && <div className="col-span-2 text-xs text-[var(--warn)]">Image is dark — add light or raise exposure.</div>}
    </div>
  );
}

function CameraEditor({ cam, onClose }: { cam: CameraInfo; onClose: () => void }) {
  const c = cam.config;
  const [form, setForm] = useState({
    name: c.name, enabled: c.enabled, width: c.width, height: c.height, fps: c.fps, auto_exposure: c.auto_exposure,
    exposure: c.exposure ?? "", gain: c.gain ?? "", device: c.source.device ?? "", url: c.source.url ?? "",
    type: c.source.type, azimuth: c.mount.azimuth_deg ?? "", description: c.mount.description,
  });
  const save = useAction(async () => {
    await api.patch(`/api/cameras/${cam.id}`, {
      name: form.name, enabled: form.enabled, width: Number(form.width), height: Number(form.height), fps: Number(form.fps),
      auto_exposure: form.auto_exposure, exposure: form.exposure === "" ? null : Number(form.exposure),
      gain: form.gain === "" ? null : Number(form.gain),
      ...(cam.synthetic ? {} : { source: { type: form.type, device: form.type === "opencv" ? (form.device === "" ? null : Number(form.device)) : null, url: form.type === "rtsp" ? form.url : null } }),
      mount: { azimuth_deg: form.azimuth === "" ? null : Number(form.azimuth), description: form.description },
    });
    onClose();
  });
  const controls = useAction(async () => {
    await api.post(`/api/cameras/${cam.id}/controls`, { auto_exposure: form.auto_exposure,
      exposure: form.exposure === "" ? null : Number(form.exposure), gain: form.gain === "" ? null : Number(form.gain) });
  });
  const set = (k: string, v: any) => setForm({ ...form, [k]: v });
  return (
    <Modal open onClose={onClose} title={`Configure ${cam.name}`}>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Name"><input className={inputCls} value={form.name} onChange={(e) => set("name", e.target.value)} /></Field>
        <Field label="Enabled"><Toggle checked={form.enabled} onChange={(v) => set("enabled", v)} /></Field>
        {!cam.synthetic && (
          <>
            <Field label="Source">
              <select className={inputCls} value={form.type} onChange={(e) => set("type", e.target.value)}>
                <option value="opencv">USB / UVC</option><option value="rtsp">RTSP / network</option>
              </select>
            </Field>
            {form.type === "opencv"
              ? <Field label="Device index"><input className={inputCls} type="number" value={form.device} onChange={(e) => set("device", e.target.value)} /></Field>
              : <Field label="Stream URL"><input className={inputCls} value={form.url} onChange={(e) => set("url", e.target.value)} placeholder="rtsp://…" /></Field>}
          </>
        )}
        <Field label="Width"><input className={inputCls} type="number" value={form.width} onChange={(e) => set("width", e.target.value)} /></Field>
        <Field label="Height"><input className={inputCls} type="number" value={form.height} onChange={(e) => set("height", e.target.value)} /></Field>
        <Field label="FPS"><input className={inputCls} type="number" value={form.fps} onChange={(e) => set("fps", e.target.value)} /></Field>
        <Field label="Auto exposure" hint="Off is recommended: exposure changes look like motion"><Toggle checked={form.auto_exposure} onChange={(v) => set("auto_exposure", v)} /></Field>
        <Field label="Exposure"><input className={inputCls} type="number" value={form.exposure} onChange={(e) => set("exposure", e.target.value)} /></Field>
        <Field label="Gain"><input className={inputCls} type="number" value={form.gain} onChange={(e) => set("gain", e.target.value)} /></Field>
        <Field label="Position (clock angle °)" hint="0 = top (20), 90 = right, 180 = bottom">
          <input className={inputCls} type="number" min={0} max={360} value={form.azimuth} onChange={(e) => set("azimuth", e.target.value)} />
        </Field>
        <Field label="Description"><input className={inputCls} value={form.description} onChange={(e) => set("description", e.target.value)} /></Field>
      </div>
      <ErrorNote error={save.error ?? controls.error} />
      <div className="mt-4 flex gap-2">
        <Button onClick={() => controls.run()} disabled={controls.busy}>Apply exposure/gain now</Button>
        <div className="flex-1" />
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="primary" onClick={() => save.run()} disabled={save.busy}>Save &amp; restart camera</Button>
      </div>
    </Modal>
  );
}
