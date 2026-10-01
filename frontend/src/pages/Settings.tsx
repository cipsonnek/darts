import { useEffect, useState } from "react";
import { Badge, Button, Card, ErrorNote, Field, inputCls, PageHeader, Toggle } from "@/components/ui";
import { useAction, useApi } from "@/hooks/useApi";
import { api, getAdminToken, setAdminToken } from "@/lib/api";
import { THEMES, usePrefs, type DashboardWidgets } from "@/store/prefs";

const NUM_FIELDS: { section: string; key: string; label: string; step?: number; hint?: string }[] = [
  { section: "scoring", key: "confidence_threshold", label: "Confidence threshold", step: 0.01, hint: "Darts below this need confirmation" },
  { section: "motion", key: "settle_time_ms", label: "Settle time (ms)", step: 10, hint: "Stillness required before analysing a throw" },
  { section: "detection", key: "change_min_delta", label: "Minimum change level", step: 1 },
  { section: "detection", key: "obstruction_area_fraction", label: "Obstruction area fraction", step: 0.01 },
  { section: "detection", key: "max_dart_tilt_deg", label: "Max dart tilt (°)", step: 1 },
  { section: "fusion", key: "model_sigma_mm", label: "Model uncertainty (mm)", step: 0.05 },
  { section: "fusion", key: "outlier_sigma", label: "Camera outlier threshold (σ)", step: 0.5 },
  { section: "tracking", key: "duplicate_radius_mm", label: "Duplicate radius (mm)", step: 0.5 },
  { section: "validation", key: "interval_s", label: "Calibration check interval (s)", step: 5 },
  { section: "performance", key: "stream_jpeg_quality", label: "Stream JPEG quality", step: 5 },
];

export default function Settings() {
  const p = usePrefs();
  const { data: server, reload } = useApi<any>("/api/settings");
  const [vals, setVals] = useState<Record<string, number>>({});
  const [token, setToken] = useState(getAdminToken());

  useEffect(() => {
    if (!server) return;
    const v: Record<string, number> = {};
    for (const f of NUM_FIELDS) v[`${f.section}.${f.key}`] = server.vision[f.section]?.[f.key];
    setVals(v);
  }, [server]);

  const save = useAction(async () => {
    const patch: Record<string, Record<string, number>> = {};
    for (const f of NUM_FIELDS) {
      const k = `${f.section}.${f.key}`;
      if (vals[k] !== server.vision[f.section]?.[f.key]) (patch[f.section] ??= {})[f.key] = Number(vals[k]);
    }
    await api.put("/api/settings/vision", patch);
    reload();
  });

  const checkToken = useAction(async () => {
    setAdminToken(token.trim());
    await api.get("/api/admin/check");
  });

  return (
    <div>
      <PageHeader title="Settings" />
      <div className="grid gap-4 xl:grid-cols-2">
        <Card title="Appearance">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Theme">
              <select className={inputCls} value={p.theme} onChange={(e) => p.set({ theme: e.target.value as any })}>
                {Object.entries(THEMES).map(([k, t]) => <option key={k} value={k}>{t.label}</option>)}
              </select>
            </Field>
            <Field label="Accent colour">
              <input type="color" className="h-10 w-full cursor-pointer rounded-lg border border-[var(--border)] bg-transparent" value={p.accent} onChange={(e) => p.set({ accent: e.target.value })} />
            </Field>
            <Field label="Brand name"><input className={inputCls} value={p.brandName} maxLength={40} onChange={(e) => p.set({ brandName: e.target.value })} /></Field>
            <Field label="Tagline"><input className={inputCls} value={p.brandTagline} maxLength={60} onChange={(e) => p.set({ brandTagline: e.target.value })} /></Field>
            <Field label="Board style">
              <select className={inputCls} value={p.boardStyle} onChange={(e) => p.set({ boardStyle: e.target.value as any })}>
                <option value="classic">Classic</option><option value="minimal">Minimal</option><option value="neon">Neon</option>
              </select>
            </Field>
            <Field label="Score display">
              <select className={inputCls} value={p.scoreStyle} onChange={(e) => p.set({ scoreStyle: e.target.value as any })}>
                <option value="classic">Classic</option><option value="big">Big</option><option value="compact">Compact</option>
              </select>
            </Field>
            <Field label="Play layout">
              <select className={inputCls} value={p.layout} onChange={(e) => p.set({ layout: e.target.value as any })}>
                <option value="board-left">Board left</option><option value="board-right">Board right</option><option value="stacked">Stacked</option>
              </select>
            </Field>
            <Field label={`TV mode scale (${p.tvScale.toFixed(2)}×)`}>
              <input type="range" min={0.7} max={1.6} step={0.05} value={p.tvScale} onChange={(e) => p.set({ tvScale: Number(e.target.value) })} />
            </Field>
          </div>
          <div className="mt-4 flex flex-wrap gap-4">
            <Toggle checked={p.showBoardNumbers} onChange={(v) => p.set({ showBoardNumbers: v })} label="Board numbers" />
            <Toggle checked={p.showUncertainty} onChange={(v) => p.set({ showUncertainty: v })} label="Show uncertainty ellipses" />
          </div>
          <div className="mt-4">
            <div className="mb-2 text-sm font-medium text-[var(--muted)]">Play screen widgets</div>
            <div className="flex flex-wrap gap-4">
              {(Object.keys(p.widgets) as (keyof DashboardWidgets)[]).map((w) => (
                <Toggle key={w} checked={p.widgets[w]} onChange={() => p.toggleWidget(w)} label={w} />
              ))}
            </div>
          </div>
          <div className="mt-4">
            <div className="mb-2 text-sm font-medium text-[var(--muted)]">Camera overlays on the play screen</div>
            <div className="flex flex-wrap gap-1">
              {["board", "sectors", "darts", "candidates", "change", "info"].map((l) => (
                <button key={l} onClick={() => p.set({ cameraOverlay: p.cameraOverlay.includes(l) ? p.cameraOverlay.filter((x) => x !== l) : [...p.cameraOverlay, l] })}
                  className={`rounded-full border px-2.5 py-1 text-xs font-semibold ${p.cameraOverlay.includes(l) ? "border-[var(--accent)] text-[var(--accent)]" : "border-[var(--border)] text-[var(--muted)]"}`}>{l}</button>
              ))}
            </div>
          </div>
        </Card>
        <div className="flex flex-col gap-4">
          <Card title="Detection" actions={<Badge tone="warn">admin</Badge>}>
            <div className="grid gap-3 sm:grid-cols-2">
              {NUM_FIELDS.map((f) => {
                const k = `${f.section}.${f.key}`;
                return (
                  <Field key={k} label={f.label} hint={f.hint}>
                    <input type="number" step={f.step} className={inputCls} value={vals[k] ?? ""} onChange={(e) => setVals({ ...vals, [k]: Number(e.target.value) })} />
                  </Field>
                );
              })}
            </div>
            <ErrorNote error={save.error} />
            <Button className="mt-4" variant="primary" onClick={() => save.run()} disabled={save.busy || !server}>Save detection settings</Button>
          </Card>
          <Card title="Administration">
            <div className="flex flex-col gap-3 text-sm">
              <p className="text-[var(--muted)]">
                Administrative actions (calibration, camera configuration, deleting data) are allowed without a token on the server machine itself.
                From other devices, enter the token stored in <code>data/admin_token.txt</code> on the server.
              </p>
              <div className="flex gap-2">
                <input className={`${inputCls} flex-1`} type="password" value={token} onChange={(e) => setToken(e.target.value)} placeholder="Admin token" />
                <Button onClick={() => checkToken.run()}>Save &amp; verify</Button>
              </div>
              {checkToken.error ? <ErrorNote error={checkToken.error} /> : checkToken.busy ? null : token && <span className="text-[var(--good)]">Token stored in this browser.</span>}
              {server && <div className="text-xs text-[var(--muted)]">Mode: {server.mode} · admin policy: {server.server.admin_auth} · database: {server.database.url}</div>}
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
