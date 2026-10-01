import clsx from "clsx";
import { useEffect, useMemo, useRef, useState } from "react";
import { Dartboard, type BoardMarker } from "@/components/board/Dartboard";
import { Badge, Button, Card, Empty, ErrorNote, Field, inputCls, PageHeader, Stat, Tabs } from "@/components/ui";
import { useAction, useApi } from "@/hooks/useApi";
import { useBoardGeometry } from "@/hooks/useBoard";
import { api } from "@/lib/api";
import { useLive } from "@/store/live";

type Tab = "simulator" | "recordings" | "logs" | "events" | "system" | "benchmark";

export default function Developer() {
  const mode = useLive((s) => s.mode);
  const [tab, setTab] = useState<Tab | null>(null);
  const current: Tab = tab ?? (mode === "simulator" ? "simulator" : "recordings");
  return (
    <div>
      <PageHeader title="Developer" subtitle="Ground truth, recordings, replay evaluation, logs and system diagnostics." />
      <Tabs value={current} onChange={setTab} items={[
        { id: "simulator", label: "Simulator" }, { id: "recordings", label: "Recordings & ground truth" },
        { id: "benchmark", label: "Benchmark" }, { id: "logs", label: "Logs" }, { id: "events", label: "Events" }, { id: "system", label: "System" },
      ]} />
      <div className="mt-4">
        {current === "simulator" && <Simulator />}
        {current === "recordings" && <Recordings />}
        {current === "benchmark" && <Benchmark />}
        {current === "logs" && <Logs />}
        {current === "events" && <Events />}
        {current === "system" && <System />}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------- simulator
function Simulator() {
  const mode = useLive((s) => s.mode);
  const board = useBoardGeometry();
  const [scatter, setScatter] = useState(0);
  const { data: gt, reload } = useApi<any[]>(mode === "simulator" ? "/api/simulator/ground-truth" : null, 2000);
  const { data: dets } = useApi<any[]>("/api/detections?limit=60", 2000);
  const throwAt = useAction(async (body: any) => { await api.post("/api/simulator/throw", body); setTimeout(reload, 300); });
  const misc = useAction(async (path: string, body?: any) => { await api.post(`/api/simulator/${path}`, body); reload(); });

  const rows = useMemo(() => {
    if (!gt || !dets) return [];
    return [...gt].reverse().slice(0, 30).map((g) => {
      let best: any = null;
      let bestD = Infinity;
      for (const d of dets) {
        const dist = Math.hypot(d.x_mm - g.impact_mm[0], d.y_mm - g.impact_mm[1]);
        if (dist < bestD) { bestD = dist; best = d; }
      }
      return { g, d: bestD < 25 ? best : null, err: bestD };
    });
  }, [gt, dets]);
  const errs = rows.filter((r) => r.d).map((r) => r.err);
  const correct = rows.filter((r) => r.d && (r.d.final_label ?? r.d.label) === r.g.score.label).length;

  if (mode !== "simulator") return <Empty title="Simulator not active">Start the server with <code>python -m backend --simulator</code> to drive three synthetic cameras.</Empty>;
  const markers: BoardMarker[] = rows.flatMap((r, i) => [
    { id: `g${i}`, x_mm: r.g.impact_mm[0], y_mm: r.g.impact_mm[1], shape: "cross" as const, color: "var(--good)" },
    ...(r.d ? [{ id: `d${i}`, x_mm: r.d.x_mm, y_mm: r.d.y_mm, color: "var(--accent)" }] : []),
  ]);
  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,560px)_minmax(0,1fr)]">
      <Card title="Click the board to throw">
        <div className="aspect-square"><Dartboard board={board} markers={markers} onClick={(p) => throwAt.run({ target: [p.x_mm, p.y_mm], scatter_mm: scatter })} /></div>
        <div className="mt-2 text-xs text-[var(--muted)]">× true impact (simulator) · ● detected</div>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <Field label={`Aim scatter ${scatter} mm`}><input type="range" min={0} max={40} value={scatter} onChange={(e) => setScatter(Number(e.target.value))} /></Field>
          <Button onClick={() => throwAt.run({ scatter_mm: 0 })}>Random throw</Button>
          {["T20", "D16", "BULL", "T19"].map((l) => <Button key={l} size="sm" onClick={() => throwAt.run({ label: l, scatter_mm: scatter })}>{l}</Button>)}
        </div>
        <ErrorNote error={throwAt.error ?? misc.error} />
      </Card>
      <div className="flex flex-col gap-4">
        <Card title="Scene">
          <div className="flex flex-wrap gap-2">
            <Button variant="primary" onClick={() => misc.run("takeout")}>Pull darts (takeout)</Button>
            <Button onClick={() => misc.run("hand")}>Hand passes by</Button>
            <Button onClick={() => misc.run("auto-calibrate")}>Auto-calibrate all cameras</Button>
          </div>
          <div className="mt-3 flex flex-wrap gap-1">
            {["neutral", "led_ring", "warm", "dim", "bright", "uneven", "side_light"].map((l) => (
              <Button key={l} size="sm" variant="ghost" onClick={() => misc.run("lighting", { preset: l })}>{l}</Button>
            ))}
          </div>
        </Card>
        <Card title="Ground truth vs detection (synthetic)">
          <div className="mb-3 grid grid-cols-3 gap-2">
            <Stat label="Matched" value={`${errs.length}/${rows.length}`} />
            <Stat label="Score correct" value={rows.length ? `${Math.round((correct / rows.length) * 100)}%` : "–"} />
            <Stat label="Mean error" value={errs.length ? `${(errs.reduce((a, b) => a + b, 0) / errs.length).toFixed(2)} mm` : "–"} />
          </div>
          <div className="max-h-80 overflow-auto text-sm">
            <table className="w-full">
              <thead className="text-left text-xs text-[var(--muted)]"><tr><th>True</th><th>Detected</th><th className="text-right">Error</th><th /></tr></thead>
              <tbody>
                {rows.map((r, i) => (
                  <tr key={i} className="border-t border-[var(--border)]">
                    <td className="py-1 font-semibold">{r.g.score.label}</td>
                    <td>{r.d ? (r.d.final_label ?? r.d.label) : <span className="text-[var(--muted)]">—</span>}</td>
                    <td className="text-right tabular-nums">{r.d ? `${r.err.toFixed(2)} mm` : ""}</td>
                    <td className="text-right">{r.d && <Badge tone={(r.d.final_label ?? r.d.label) === r.g.score.label ? "good" : "bad"}>{(r.d.final_label ?? r.d.label) === r.g.score.label ? "✓" : "✗"}</Badge>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------- recordings
function Recordings() {
  const { data, reload } = useApi<{ recordings: any[]; active: any }>("/api/recordings", 3000);
  const [name, setName] = useState("");
  const [open, setOpen] = useState<string | null>(null);
  const start = useAction(async () => { await api.post("/api/recordings/start", { name: name || null }); setName(""); reload(); });
  const stop = useAction(async () => { await api.post("/api/recordings/stop"); reload(); });
  if (open) return <RecordingViewer name={open} onClose={() => { setOpen(null); reload(); }} />;
  return (
    <div className="grid gap-4 lg:grid-cols-[360px_minmax(0,1fr)]">
      <Card title="Record">
        {data?.active ? (
          <div className="flex flex-col gap-3">
            <div className="flex items-center gap-2"><span className="h-3 w-3 animate-pulse rounded-full bg-[var(--bad)]" /> Recording <b>{data.active.name}</b></div>
            <div className="text-sm text-[var(--muted)]">{Object.entries(data.active.frame_counts).map(([c, n]) => `${c}: ${n}`).join(" · ")} · dropped {data.active.dropped_frames}</div>
            <Button variant="danger" onClick={() => stop.run()}>Stop</Button>
          </div>
        ) : (
          <div className="flex flex-col gap-3">
            <Field label="Name (optional)" hint="letters, digits, _ - ."><input className={inputCls} value={name} onChange={(e) => setName(e.target.value)} placeholder="session_…" /></Field>
            <Button variant="primary" onClick={() => start.run()}>Start recording</Button>
            <p className="text-xs text-[var(--muted)]">Saves every camera frame, timestamps, calibration and engine events, for replay and ground-truth evaluation.</p>
          </div>
        )}
        <ErrorNote error={start.error ?? stop.error} />
      </Card>
      <Card title="Recordings">
        {!data?.recordings.length ? <Empty title="No recordings" /> : (
          <div className="flex flex-col divide-y divide-[var(--border)]">
            {data.recordings.map((r) => (
              <div key={r.name} className="flex items-center gap-3 py-2">
                <div className="flex-1">
                  <div className="font-semibold">{r.name} {r.synthetic && <Badge tone="warn">synthetic</Badge>}</div>
                  <div className="text-xs text-[var(--muted)]">{r.started_at && new Date(r.started_at).toLocaleString()} · {r.duration_s?.toFixed?.(1)} s · {Object.values(r.frame_counts ?? {}).join("/")} frames</div>
                </div>
                <Button size="sm" onClick={() => setOpen(r.name)}>Open</Button>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}

function RecordingViewer({ name, onClose }: { name: string; onClose: () => void }) {
  const { data, reload } = useApi<any>(`/api/recordings/${encodeURIComponent(name)}`);
  const board = useBoardGeometry();
  const cams: string[] = data?.metadata?.cameras ?? [];
  const [cam, setCam] = useState<string | null>(null);
  const [pos, setPos] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [pending, setPending] = useState<{ x_mm: number; y_mm: number; label: string } | null>(null);
  const imgRef = useRef<HTMLImageElement>(null);
  const c = cam ?? cams[0];
  const frames = data?.frames?.[c] ?? [];
  const frame = frames[Math.min(pos, frames.length - 1)];
  const evaluate = useAction(async () => { await api.post(`/api/recordings/${encodeURIComponent(name)}/evaluate`); reload(); });
  const annotate = useAction(async () => {
    await api.post(`/api/recordings/${encodeURIComponent(name)}/ground-truth`, { entries: [{ ...pending, timestamp: frame?.timestamp }] });
    setPending(null);
    reload();
  });

  useEffect(() => {
    if (!playing) return;
    const t = setInterval(() => setPos((p) => (p + 1 < frames.length ? p + 1 : p)), 100);
    return () => clearInterval(t);
  }, [playing, frames.length]);

  async function clickFrame(e: React.MouseEvent<HTMLImageElement>) {
    const img = imgRef.current!;
    const r = img.getBoundingClientRect();
    const x = ((e.clientX - r.left) / r.width) * img.naturalWidth;
    const y = ((e.clientY - r.top) / r.height) * img.naturalHeight;
    try {
      const p = await api.get<any>(`/api/recordings/${encodeURIComponent(name)}/pixel-to-board?camera_id=${c}&x=${x}&y=${y}`);
      setPending({ x_mm: p.x_mm, y_mm: p.y_mm, label: p.score.label });
    } catch (err) {
      annotate.setError(err);
    }
  }

  const ev = data?.evaluation;
  const markers: BoardMarker[] = [
    ...(data?.ground_truth ?? []).map((g: any, i: number) => ({ id: `g${i}`, x_mm: g.impact_mm[0], y_mm: g.impact_mm[1], shape: "cross" as const, color: "var(--good)" })),
    ...(ev?.detections ?? []).map((d: any, i: number) => ({ id: `d${i}`, x_mm: d.x_mm, y_mm: d.y_mm, color: "var(--accent)" })),
    ...(pending ? [{ id: "pending", x_mm: pending.x_mm, y_mm: pending.y_mm, shape: "cross" as const, color: "var(--warn)", label: pending.label }] : []),
  ];
  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-3">
        <Button onClick={onClose}>← Back</Button>
        <div className="font-display text-xl font-bold">{name}</div>
        {data?.metadata?.synthetic && <Badge tone="warn">synthetic</Badge>}
      </div>
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        <Card title="Frames — click the dart's entry point to annotate the true impact" pad={false}
          actions={<Tabs value={c} onChange={(v) => setCam(v)} items={cams.map((x) => ({ id: x, label: x }))} />}>
          <div className="p-3">
            {frame ? (
              <img ref={imgRef} onClick={clickFrame} className="w-full cursor-crosshair rounded-lg" alt="frame" draggable={false}
                src={`/api/recordings/${encodeURIComponent(name)}/frames/${c}/${frame.index}.jpg?overlay=board,sectors`} />
            ) : <Empty title="No frames" />}
            <div className="mt-3 flex items-center gap-3">
              <Button size="sm" onClick={() => setPlaying(!playing)}>{playing ? "Pause" : "Play"}</Button>
              <Button size="sm" onClick={() => setPos(Math.max(0, pos - 1))}>‹</Button>
              <input type="range" min={0} max={Math.max(0, frames.length - 1)} value={pos} onChange={(e) => setPos(Number(e.target.value))} className="flex-1" />
              <Button size="sm" onClick={() => setPos(Math.min(frames.length - 1, pos + 1))}>›</Button>
              <span className="w-28 text-right text-xs tabular-nums text-[var(--muted)]">{pos + 1}/{frames.length} · {frame ? (frame.timestamp - frames[0].timestamp).toFixed(2) : 0}s</span>
            </div>
            {pending && (
              <div className="mt-3 flex items-center gap-3 rounded-lg border border-[var(--warn)] p-2 text-sm">
                True impact: <b>{pending.label}</b> ({pending.x_mm.toFixed(1)}, {pending.y_mm.toFixed(1)}) mm
                <Button size="sm" variant="primary" onClick={() => annotate.run()}>Save ground truth</Button>
                <Button size="sm" variant="ghost" onClick={() => setPending(null)}>Cancel</Button>
              </div>
            )}
            <ErrorNote error={annotate.error} />
          </div>
        </Card>
        <div className="flex flex-col gap-4">
          <Card title="Predicted (●) vs ground truth (×)" actions={<Button size="sm" variant="primary" onClick={() => evaluate.run()} disabled={evaluate.busy}>{evaluate.busy ? "Replaying…" : "Replay & evaluate"}</Button>}>
            <div className="aspect-square"><Dartboard board={board} markers={markers} /></div>
            <ErrorNote error={evaluate.error} />
            {ev?.metrics && (
              <div className="mt-3 grid grid-cols-2 gap-2">
                <Stat label="Detected" value={`${ev.metrics.detected}/${ev.metrics.darts}`} />
                <Stat label="Score accuracy" value={ev.metrics.score_accuracy != null ? `${(ev.metrics.score_accuracy * 100).toFixed(1)}%` : "–"} />
                <Stat label="Mean error" value={ev.metrics.impact_error_mm ? `${ev.metrics.impact_error_mm.mean} mm` : "–"} />
                <Stat label="p95 error" value={ev.metrics.impact_error_mm ? `${ev.metrics.impact_error_mm.p95} mm` : "–"} />
                <Stat label="False positives" value={ev.metrics.false_positives} />
                <Stat label="Missed" value={ev.metrics.missed} />
              </div>
            )}
            {ev?.note && <div className="mt-2 text-sm text-[var(--muted)]">{ev.note}</div>}
            {ev?.rows && (
              <div className="mt-3 max-h-56 overflow-auto text-sm">
                {ev.rows.map((r: any, i: number) => (
                  <div key={i} className="flex justify-between border-t border-[var(--border)] py-1">
                    <span>{r.gt} → {r.detected ? r.pred : "missed"}</span>
                    <span className={clsx("tabular-nums", r.detected && r.pred !== r.gt && "text-[var(--bad)]")}>{r.detected ? `${r.error_mm.toFixed(2)} mm` : ""}</span>
                  </div>
                ))}
              </div>
            )}
          </Card>
          <Card title="Recorded events">
            <div className="max-h-64 overflow-auto text-xs">
              {(data?.events ?? []).map((e: any, i: number) => (
                <div key={i} className="border-t border-[var(--border)] py-1">
                  <b>{e.type}</b> {e.type === "dart_detected" ? e.data.score.label : ""} <span className="text-[var(--muted)]">{e.timestamp?.toFixed?.(2)}</span>
                </div>
              ))}
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------- benchmark, logs, events, system
function Benchmark() {
  const { data, error } = useApi<any>("/api/benchmarks/latest");
  if (error) return <Empty title="No benchmark yet">Run <code>python scripts/benchmark.py</code> on the server.</Empty>;
  if (!data) return null;
  const o = data.overall;
  return (
    <div className="flex flex-col gap-4">
      <div className="rounded-xl border border-[var(--warn)]/50 bg-[color-mix(in_oklab,var(--warn)_10%,transparent)] p-3 text-sm">
        {data.note} Generated {data.generated_at} · calibration mode <b>{data.settings.calibration}</b>.
      </div>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Darts" value={o.darts_thrown} />
        <Stat label="Detection rate" value={`${(o.detection_rate * 100).toFixed(1)}%`} />
        <Stat label="Score accuracy" value={`${(o.score_accuracy_all_thrown * 100).toFixed(1)}%`} />
        <Stat label="Wrong scores auto-accepted" value={o.wrong_auto_accepted} tone={o.wrong_auto_accepted ? "bad" : "good"} />
        <Stat label="Impact error mean" value={`${o.impact_error_mm?.mean} mm`} />
        <Stat label="Impact error p95" value={`${o.impact_error_mm?.p95} mm`} />
        <Stat label="False positives / duplicates" value={`${o.false_positives} / ${o.duplicates}`} />
        <Stat label="Flagged uncertain" value={`${(o.uncertain_rate * 100).toFixed(1)}%`} />
      </div>
      <Card title="By condition">
        <div className="overflow-x-auto text-sm">
          <table className="w-full">
            <thead className="text-left text-xs text-[var(--muted)]"><tr><th>Condition</th><th>Darts</th><th>Score acc.</th><th>Mean err</th><th>p95 err</th><th>FP</th><th>Uncertain</th></tr></thead>
            <tbody>
              {Object.entries(data.by_condition as Record<string, any>).map(([k, m]) => (
                <tr key={k} className="border-t border-[var(--border)] tabular-nums">
                  <td className="py-1">{k}</td><td>{m.darts_thrown}</td><td>{(m.score_accuracy_all_thrown * 100).toFixed(1)}%</td>
                  <td>{m.impact_error_mm?.mean}</td><td>{m.impact_error_mm?.p95}</td><td>{m.false_positives}</td><td>{(m.uncertain_rate * 100).toFixed(0)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

function Logs() {
  const [level, setLevel] = useState("");
  const [text, setText] = useState("");
  const [rows, setRows] = useState<any[]>([]);
  const after = useRef(0);
  useEffect(() => {
    after.current = 0;
    setRows([]);
    let alive = true;
    const load = async () => {
      const q = new URLSearchParams({ after: String(after.current), limit: "500" });
      if (level) q.set("level", level);
      if (text) q.set("text", text);
      try {
        const r = await api.get<any[]>(`/api/logs?${q}`);
        if (!alive || !r.length) return;
        after.current = r[r.length - 1].seq;
        setRows((cur) => [...r.reverse(), ...cur].slice(0, 1000));
      } catch { /* retry next tick */ }
    };
    load();
    const t = setInterval(load, 2000);
    return () => { alive = false; clearInterval(t); };
  }, [level, text]);
  return (
    <Card title="Logs" actions={<>
      <select className={inputCls} value={level} onChange={(e) => setLevel(e.target.value)}>
        <option value="">All levels</option><option>INFO</option><option>WARNING</option><option>ERROR</option>
      </select>
      <input className={inputCls} placeholder="filter" value={text} onChange={(e) => setText(e.target.value)} />
    </>}>
      <div className="max-h-[65vh] overflow-auto font-mono text-xs">
        {rows.map((r) => (
          <div key={r.seq} className="flex gap-2 border-t border-[var(--border)] py-0.5">
            <span className="shrink-0 text-[var(--muted)]">{r.time?.slice(11, 23)}</span>
            <span className={clsx("w-14 shrink-0", r.level === "ERROR" && "text-[var(--bad)]", r.level === "WARNING" && "text-[var(--warn)]")}>{r.level}</span>
            <span className="w-36 shrink-0 truncate text-[var(--muted)]">{r.logger}</span>
            <span className="break-all">{r.message} {Object.entries(r).filter(([k]) => !["ts", "time", "level", "logger", "message", "seq"].includes(k)).map(([k, v]) => `${k}=${typeof v === "object" ? JSON.stringify(v) : v}`).join(" ")}</span>
          </div>
        ))}
      </div>
    </Card>
  );
}

function Events() {
  const { data } = useApi<any[]>("/api/events?limit=300", 3000);
  return (
    <Card title="Engine events (persisted)">
      <div className="max-h-[65vh] overflow-auto text-xs">
        {data?.map((e) => (
          <div key={e.id} className="border-t border-[var(--border)] py-1">
            <span className="text-[var(--muted)]">{new Date(e.created_at).toLocaleString()}</span> <b>{e.type}</b> <span className="font-mono">{JSON.stringify(e.data).slice(0, 200)}</span>
          </div>
        ))}
      </div>
    </Card>
  );
}

function System() {
  const { data } = useApi<any>("/api/system", 3000);
  return (
    <Card title="System">
      <pre className="max-h-[70vh] overflow-auto text-xs">{JSON.stringify(data, null, 2)}</pre>
    </Card>
  );
}
