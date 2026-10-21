import { useState } from "react";
import { CameraPicker } from "@/components/camera/CameraPicker";
import { CameraView } from "@/components/camera/CameraView";
import { Badge, Button, Card, ErrorNote, Field, inputCls, Modal, PageHeader, Tabs, Toggle } from "@/components/ui";
import { useAction, useApi } from "@/hooks/useApi";
import { api } from "@/lib/api";
import type { CameraHealth, CameraInfo } from "@/lib/types";
import { useLive } from "@/store/live";
import { GRADE, OVERLAY_LABELS, tr } from "@/lib/pl";

const LAYERS = ["board", "sectors", "labels", "roi", "change", "candidates", "darts", "info"];

export default function Cameras() {
  const { data: cams, reload, error } = useApi<CameraInfo[]>("/api/cameras", 5000);
  const live = useLive((s) => s.cameras);
  const [view, setView] = useState<"raw" | "undistorted" | "topdown">("raw");
  const [layers, setLayers] = useState<string[]>(["board", "darts"]);
  const [edit, setEdit] = useState<CameraInfo | null>(null);
  const [picking, setPicking] = useState(false);
  const realUsb = cams?.some((c) => !c.synthetic && c.config.source.type === "opencv");

  return (
    <div>
      <PageHeader title="Kamery" subtitle="Podgląd jest kodowany na serwerze w zmniejszonym rozmiarze; pełne klatki nie opuszczają silnika wizji."
        actions={realUsb && <Button variant="primary" onClick={() => setPicking(true)}>Wybierz kamery</Button>} />
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <Tabs value={view} onChange={setView} items={[{ id: "raw", label: "Surowy" }, { id: "undistorted", label: "Bez zniekształceń" }, { id: "topdown", label: "Z góry" }]} />
        <div className="flex flex-wrap gap-1">
          {LAYERS.map((l) => (
            <button key={l} onClick={() => setLayers((s) => (s.includes(l) ? s.filter((x) => x !== l) : [...s, l]))}
              className={`rounded-full border px-2.5 py-1 text-xs font-semibold ${layers.includes(l) ? "border-[var(--accent)] text-[var(--accent)]" : "border-[var(--border)] text-[var(--muted)]"}`}>
              {OVERLAY_LABELS[l] ?? l}
            </button>
          ))}
        </div>
      </div>
      <ErrorNote error={error} />
      <div className="grid gap-4 xl:grid-cols-3">
        {cams?.map((c) => {
          const h = live.find((x) => x.camera_id === c.id) ?? c.health;
          return (
            <Card key={c.id} pad={false}
              title={<span className="flex items-center gap-2">{c.name} {c.synthetic && <Badge tone="warn">syntetyczna</Badge>} {!c.enabled && <Badge>wyłączona</Badge>}</span>}
              actions={<Button size="sm" variant="ghost" onClick={() => setEdit(c)}>Konfiguruj</Button>}>
              <div className="p-3">
                {c.enabled ? <CameraView cameraId={c.id} overlay={view === "raw" ? layers : []} view={view} width={800} fps={10} health={h} />
                  : <div className="grid aspect-video place-items-center rounded-xl bg-black text-sm text-[var(--muted)]">wyłączona</div>}
                <HealthTable h={h} calibrated={c.calibration.pose} grade={c.calibration.grade} />
              </div>
            </Card>
          );
        })}
      </div>
      {edit && <CameraEditor cam={edit} onClose={() => { setEdit(null); reload(); }} />}
      {picking && cams && <CameraPicker cams={cams} onClose={() => { setPicking(false); reload(); }} />}
    </div>
  );
}

function HealthTable({ h, calibrated, grade }: { h: CameraHealth | null | undefined; calibrated: boolean; grade: string | null }) {
  if (!h) return null;
  const rows: [string, React.ReactNode][] = [
    ["Stan", <Badge tone={h.connected ? "good" : "bad"}>{h.state}</Badge>],
    ["Kalibracja", calibrated ? <Badge tone={grade === "good" ? "good" : "warn"}>{tr(GRADE, grade)}</Badge> : <Badge tone="bad">brak</Badge>],
    ["Rozdzielczość", `${h.width}×${h.height}`],
    ["FPS (docelowo)", `${h.fps.toFixed(1)} (${h.target_fps})`],
    ["Rozrzut klatek", `${h.frame_interval_jitter_ms.toFixed(1)} ms`],
    ["Jasność / kontrast", `${h.brightness.toFixed(0)} / ${h.contrast.toFixed(0)}`],
    ["Prześwietl. / niedoświetl.", `${(h.saturated_fraction * 100).toFixed(1)}% / ${(h.dark_fraction * 100).toFixed(1)}%`],
    ["Ostrość", h.sharpness.toFixed(0)],
    ["Klatki / uszkodzone", `${h.frames_total} / ${h.frames_corrupted}`],
    ["Ponowne połączenia", h.reconnects],
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
      {h.saturated_fraction > 0.05 && <div className="col-span-2 text-xs text-[var(--warn)]">Obraz prześwietlony — zmniejsz ekspozycję lub wzmocnienie.</div>}
      {h.brightness < 35 && h.connected && <div className="col-span-2 text-xs text-[var(--warn)]">Obraz za ciemny — dodaj światła lub zwiększ ekspozycję.</div>}
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
    <Modal open onClose={onClose} title={`Konfiguracja: ${cam.name}`}>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Nazwa"><input className={inputCls} value={form.name} onChange={(e) => set("name", e.target.value)} /></Field>
        <Field label="Włączona"><Toggle checked={form.enabled} onChange={(v) => set("enabled", v)} /></Field>
        {!cam.synthetic && (
          <>
            <Field label="Źródło">
              <select className={inputCls} value={form.type} onChange={(e) => set("type", e.target.value)}>
                <option value="opencv">USB / UVC</option><option value="rtsp">RTSP / sieć</option>
              </select>
            </Field>
            {form.type === "opencv"
              ? <Field label="Numer urządzenia"><input className={inputCls} type="number" value={form.device} onChange={(e) => set("device", e.target.value)} /></Field>
              : <Field label="Adres strumienia"><input className={inputCls} value={form.url} onChange={(e) => set("url", e.target.value)} placeholder="rtsp://…" /></Field>}
          </>
        )}
        <Field label="Szerokość"><input className={inputCls} type="number" value={form.width} onChange={(e) => set("width", e.target.value)} /></Field>
        <Field label="Wysokość"><input className={inputCls} type="number" value={form.height} onChange={(e) => set("height", e.target.value)} /></Field>
        <Field label="FPS"><input className={inputCls} type="number" value={form.fps} onChange={(e) => set("fps", e.target.value)} /></Field>
        <Field label="Auto-ekspozycja" hint="Zalecane wyłączenie: zmiany ekspozycji wyglądają jak ruch"><Toggle checked={form.auto_exposure} onChange={(v) => set("auto_exposure", v)} /></Field>
        <Field label="Ekspozycja"><input className={inputCls} type="number" value={form.exposure} onChange={(e) => set("exposure", e.target.value)} /></Field>
        <Field label="Wzmocnienie"><input className={inputCls} type="number" value={form.gain} onChange={(e) => set("gain", e.target.value)} /></Field>
        <Field label="Pozycja (kąt jak na zegarze, °)" hint="0 = góra (20), 90 = prawo, 180 = dół">
          <input className={inputCls} type="number" min={0} max={360} value={form.azimuth} onChange={(e) => set("azimuth", e.target.value)} />
        </Field>
        <Field label="Opis"><input className={inputCls} value={form.description} onChange={(e) => set("description", e.target.value)} /></Field>
      </div>
      <ErrorNote error={save.error ?? controls.error} />
      <div className="mt-4 flex gap-2">
        <Button onClick={() => controls.run()} disabled={controls.busy}>Zastosuj ekspozycję/wzmocnienie</Button>
        <div className="flex-1" />
        <Button onClick={onClose}>Anuluj</Button>
        <Button variant="primary" onClick={() => save.run()} disabled={save.busy}>Zapisz i uruchom ponownie</Button>
      </div>
    </Modal>
  );
}
