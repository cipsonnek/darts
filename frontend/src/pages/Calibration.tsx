import clsx from "clsx";
import { useRef, useState } from "react";
import { CameraView } from "@/components/camera/CameraView";
import { Badge, Button, Card, Check, ErrorNote, Field, inputCls, PageHeader, Spinner, Tabs } from "@/components/ui";
import { useAction, useApi } from "@/hooks/useApi";
import { api, snapshotUrl } from "@/lib/api";
import type { CameraInfo } from "@/lib/types";
import { GRADE, tr } from "@/lib/pl";

const CAL_STATUS: Record<string, string> = { ok: "OK", warning: "uwaga", error: "błąd", uncalibrated: "brak kalibracji" };

interface CalStatus {
  cameras: Record<string, any>;
  overall: { status: string; cameras: any[]; board_alignment: number | null; recommendation: string[] };
}

const POINT_LABELS: Record<string, string> = {
  "double_outer:20|1": "Zewnętrzna krawędź pola double na drucie między 20 a 1",
  "double_outer:6|10": "Zewnętrzna krawędź pola double na drucie między 6 a 10",
  "double_outer:3|19": "Zewnętrzna krawędź pola double na drucie między 3 a 19",
  "double_outer:11|14": "Zewnętrzna krawędź pola double na drucie między 11 a 14",
  bull: "Środek bulla (opcjonalnie, poprawia dokładność)",
};

export default function Calibration() {
  const { data: status, reload } = useApi<CalStatus>("/api/calibration", 4000);
  const { data: cams } = useApi<CameraInfo[]>("/api/cameras");
  const [cid, setCid] = useState<string | null>(null);
  const validate = useAction(async () => { await api.post("/api/calibration/validate"); reload(); });
  const current = cid ?? cams?.[0]?.id ?? null;

  return (
    <div>
      <PageHeader title="Kalibracja" subtitle="Obiektyw (parametry wewnętrzne) i położenie każdej kamery względem tarczy, z oceną jakości."
        actions={<Button onClick={() => validate.run()} disabled={validate.busy}>{validate.busy ? <Spinner /> : null} Sprawdź kalibrację teraz</Button>} />
      {status && <Summary status={status} cams={cams ?? []} />}
      <ErrorNote error={validate.error} />
      {cams && current && (
        <div className="mt-5">
          <Tabs value={current} onChange={setCid} items={cams.map((c) => ({ id: c.id, label: c.name }))} />
          <div className="mt-4">
            <CameraCalibration key={current} cam={cams.find((c) => c.id === current)!} st={status?.cameras[current]} onChange={reload} />
          </div>
        </div>
      )}
    </div>
  );
}

function Summary({ status, cams }: { status: CalStatus; cams: CameraInfo[] }) {
  const o = status.overall;
  return (
    <Card title="Stan kalibracji" actions={<Badge tone={o.status === "ok" ? "good" : o.status === "warning" ? "warn" : "bad"}>{tr(CAL_STATUS, o.status)}</Badge>}>
      <div className="grid gap-4 md:grid-cols-3">
        {cams.map((c) => {
          const s = status.cameras[c.id];
          const pose = s?.pose && !s.pose.stale ? s.pose : null;
          const v = s?.validation;
          const m = pose?.metrics ?? {};
          return (
            <div key={c.id} className="rounded-xl border border-[var(--border)] bg-[var(--surface-2)] p-3">
              <div className="mb-2 font-display font-bold">{c.name}</div>
              <div className="flex flex-col gap-1">
                <Check ok={!!s?.connected} label="Połączona" />
                <Check ok={s?.intrinsics ? true : null} label={s?.intrinsics ? "Obiektyw skalibrowany" : "Obiektyw oszacowany z tarczy"}
                  detail={s?.intrinsics ? `${s.intrinsics.rms_px.toFixed(2)} px` : undefined} />
                <Check ok={!!pose} label="Tarcza wykryta" detail={pose ? pose.method : undefined} />
                <Check ok={!!pose} label="Środek / płaszczyzna tarczy" detail={pose && m.board_center_px ? `(${m.board_center_px.join(", ")})` : undefined} />
                <Check ok={pose ? pose.grade !== "poor" : false} label={<>Jakość: <b className="uppercase">{tr(GRADE, pose?.grade)}</b></>}
                  detail={pose ? `krawędzie ${m.edge_rms_px} px · ±${m.pose_sigma_mm} mm` : undefined} />
                {v && <Check ok={v.status === "ok" ? true : v.status === "warning" ? null : false}
                  label={v.status === "ok" ? "Bez przesunięć" : v.message} detail={`dopasowanie ${(v.alignment * 100).toFixed(1)}%`} />}
              </div>
            </div>
          );
        })}
      </div>
      {(o.board_alignment != null || o.recommendation.length > 0) && (
        <div className="mt-3 flex flex-wrap items-center gap-4 text-sm">
          {o.board_alignment != null && <span>Dopasowanie tarczy: <b>{(o.board_alignment * 100).toFixed(1)}%</b></span>}
          {o.recommendation.map((r) => <Badge key={r} tone="warn">Zalecane: {r}</Badge>)}
        </div>
      )}
    </Card>
  );
}

function CameraCalibration({ cam, st, onChange }: { cam: CameraInfo; st: any; onChange: () => void }) {
  const [step, setStep] = useState<"board" | "intrinsics">("board");
  return (
    <div className="flex flex-col gap-4">
      <Tabs value={step} onChange={setStep} items={[{ id: "board", label: "Położenie tarczy" }, { id: "intrinsics", label: "Obiektyw" }]} />
      {step === "board" ? <BoardStep cam={cam} st={st} onChange={onChange} /> : <IntrinsicsStep cam={cam} st={st} onChange={onChange} />}
    </div>
  );
}

function BoardStep({ cam, st, onChange }: { cam: CameraInfo; st: any; onChange: () => void }) {
  const [azimuth, setAzimuth] = useState<string>(String(cam.config.mount.azimuth_deg ?? ""));
  const [result, setResult] = useState<any>(st?.pending ?? null);
  const [mode, setMode] = useState<"auto" | "manual" | "hint">("auto");
  const [points, setPoints] = useState<Record<string, number[]>>({});
  const [frame, setFrame] = useState(0);
  const [preview, setPreview] = useState(0);
  const imgRef = useRef<HTMLImageElement>(null);
  const order = Object.keys(POINT_LABELS);
  const next = order.find((k) => !points[k]);

  const detect = useAction(async (body: any) => {
    const r = await api.post<any>(`/api/calibration/${cam.id}/board`, body);
    setResult(r);
    setPreview((p) => p + 1);
  });
  const accept = useAction(async () => {
    await api.post(`/api/calibration/${cam.id}/board/accept`);
    setResult(null);
    onChange();
  });

  function clickFrame(e: React.MouseEvent<HTMLImageElement>) {
    const img = imgRef.current!;
    const r = img.getBoundingClientRect();
    const x = ((e.clientX - r.left) / r.width) * img.naturalWidth;
    const y = ((e.clientY - r.top) / r.height) * img.naturalHeight;
    if (mode === "hint") {
      detect.run({ method: "auto", hint: [x, y], azimuth_deg: azimuth === "" ? null : Number(azimuth) });
      setMode("auto");
    } else if (mode === "manual" && next) {
      setPoints({ ...points, [next]: [x, y] });
    }
  }

  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
      <Card title={mode === "auto" ? "Podgląd na żywo" : mode === "hint" ? "Kliknij raz wewnątrz pola single 20" : "Klikaj kolejne punkty"} pad={false}
        actions={<Button size="sm" variant="ghost" onClick={() => setFrame((f) => f + 1)}>Odśwież klatkę</Button>}>
        <div className="p-3">
          {mode === "auto" ? (
            <CameraView cameraId={cam.id} overlay={["board", "sectors", "labels"]} width={1280} fps={6} />
          ) : (
            <div className="relative">
              <img ref={imgRef} src={snapshotUrl(cam.id, {}, frame)} onClick={clickFrame} className="w-full cursor-crosshair rounded-xl" alt="zatrzymana klatka" draggable={false} />
              {Object.entries(points).map(([k, p]) => imgRef.current && (
                <span key={k} className="pointer-events-none absolute h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-white bg-[var(--accent)]"
                  style={{ left: `${(p[0] / imgRef.current.naturalWidth) * 100}%`, top: `${(p[1] / imgRef.current.naturalHeight) * 100}%` }} />
              ))}
            </div>
          )}
        </div>
      </Card>
      <div className="flex flex-col gap-4">
        <Card title="Wykrywanie tarczy">
          <div className="flex flex-col gap-3">
            <Field label="Pozycja kamery (kąt jak na zegarze, stopnie)" hint="0 = nad 20, 90 = po prawej (6), 180 = pod (3), 270 = po lewej (11). Pozwala ustalić obrót tarczy.">
              <input className={inputCls} type="number" min={0} max={360} value={azimuth} onChange={(e) => setAzimuth(e.target.value)} />
            </Field>
            <div className="flex flex-wrap gap-2">
              <Button variant="primary" disabled={detect.busy} onClick={() => detect.run({ method: "auto", azimuth_deg: azimuth === "" ? null : Number(azimuth) })}>
                {detect.busy && <Spinner />} Wykryj automatycznie
              </Button>
              <Button onClick={() => { setMode("hint"); setFrame((f) => f + 1); }}>Wskaż pole 20…</Button>
              <Button onClick={() => { setMode("manual"); setPoints({}); setFrame((f) => f + 1); }}>Punkty ręcznie…</Button>
            </div>
            {mode === "manual" && (
              <div className="rounded-xl border border-[var(--border)] p-3 text-sm">
                <ol className="flex flex-col gap-1">
                  {order.map((k) => (
                    <li key={k} className={clsx(points[k] ? "text-[var(--good)]" : k === next ? "font-semibold" : "text-[var(--muted)]")}>
                      {points[k] ? "✓" : k === next ? "→" : "·"} {POINT_LABELS[k]}
                    </li>
                  ))}
                </ol>
                <div className="mt-3 flex gap-2">
                  <Button size="sm" onClick={() => setPoints({})}>Od nowa</Button>
                  <Button size="sm" variant="primary" disabled={Object.keys(points).length < 4 || detect.busy}
                    onClick={() => detect.run({ method: "manual", points })}>Oblicz z {Object.keys(points).length} punktów</Button>
                  <Button size="sm" variant="ghost" onClick={() => setMode("auto")}>Anuluj</Button>
                </div>
              </div>
            )}
            <ErrorNote error={detect.error} />
          </div>
        </Card>
        {result && (
          <Card title="Wynik" actions={result.ok && <Badge tone={result.grade === "good" ? "good" : result.grade === "fair" ? "warn" : "bad"}>{tr(GRADE, result.grade)}</Badge>}>
            {!result.ok ? (
              <div className="text-sm text-[var(--bad)]">{result.reason}</div>
            ) : (
              <div className="flex flex-col gap-3">
                <img src={`/api/calibration/${cam.id}/preview.jpg?width=900&_=${preview}`} className="w-full rounded-lg" alt="podgląd kalibracji" />
                <div className="text-xs text-[var(--muted)]">Sprawdź, czy zielone/turkusowe okręgi i linie sektorów leżą dokładnie na drutach tarczy.</div>
                <div className="grid grid-cols-1 gap-1">
                  {result.checks.map((c: any) => (
                    <Check key={c.name} ok={c.status === "good" ? true : c.status === "fair" ? null : false} label={c.name} detail={`${c.value} ${c.unit}`} />
                  ))}
                </div>
                <div className="grid grid-cols-2 gap-x-3 text-xs">
                  {Object.entries(result.derived).map(([k, v]) => (
                    <div key={k} className="contents"><span className="text-[var(--muted)]">{k.replace(/_/g, " ")}</span><span className="text-right tabular-nums">{Array.isArray(v) ? v.join(", ") : String(v)}</span></div>
                  ))}
                </div>
                <ErrorNote error={accept.error} />
                <div className="flex gap-2">
                  <Button variant="good" onClick={() => accept.run()} disabled={accept.busy}>Zatwierdź kalibrację</Button>
                  <Button onClick={async () => { await api.post(`/api/calibration/${cam.id}/board/discard`); setResult(null); }}>Odrzuć</Button>
                </div>
              </div>
            )}
          </Card>
        )}
        {st?.pose && !result && (
          <Card title="Aktualna kalibracja">
            <div className="text-sm">
              <div>Metoda: <b>{st.pose.method}</b> · jakość <b className="uppercase">{tr(GRADE, st.pose.grade)}</b>{st.pose.stale && <Badge tone="warn" className="ml-2">nieaktualna — skalibruj ponownie</Badge>}</div>
              <div className="text-[var(--muted)]">{st.pose.calibrated_at && new Date(st.pose.calibrated_at).toLocaleString("pl-PL")} · obiektyw: {st.pose.intrinsics_source}</div>
            </div>
          </Card>
        )}
      </div>
    </div>
  );
}

function IntrinsicsStep({ cam, st, onChange }: { cam: CameraInfo; st: any; onChange: () => void }) {
  const [session, setSession] = useState<any>(st?.intrinsics_session ?? null);
  const [last, setLast] = useState<any>(null);
  const [solved, setSolved] = useState<any>(null);
  const start = useAction(async () => setSession(await api.post(`/api/calibration/${cam.id}/intrinsics/start`)));
  const capture = useAction(async () => {
    const r = await api.post<any>(`/api/calibration/${cam.id}/intrinsics/capture`);
    setLast(r);
    setSession(r);
  });
  const solve = useAction(async () => setSolved(await api.post(`/api/calibration/${cam.id}/intrinsics/solve`)));
  const accept = useAction(async () => {
    await api.post(`/api/calibration/${cam.id}/intrinsics/accept`);
    setSession(null);
    setSolved(null);
    onChange();
  });
  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
      <Card title="Podgląd na żywo" pad={false}><div className="p-3"><CameraView cameraId={cam.id} width={1280} fps={8} /></div></Card>
      <div className="flex flex-col gap-4">
        <Card title="Wzorzec ChArUco">
          <div className="flex flex-col gap-2 text-sm">
            <p>Wydrukuj wzorzec w skali 100% i przyklej na płaską, sztywną powierzchnię. Trzymaj go w różnych miejscach, odległościach i pod różnymi kątami, tak by pokryć cały obraz, zwłaszcza rogi. 15–25 ujęć daje pewny wynik.</p>
            <a className="text-[var(--accent)] underline" href="/api/calibration/charuco.png" target="_blank" rel="noreferrer">Otwórz wzorzec do druku (PNG, 300 dpi)</a>
            {st?.intrinsics && <div className="text-[var(--muted)]">Obecnie: RMS {st.intrinsics.rms_px.toFixed(3)} px z {st.intrinsics.n_views} ujęć</div>}
          </div>
        </Card>
        <Card title="Ujęcia">
          {!session ? (
            <Button variant="primary" onClick={() => start.run()} disabled={start.busy}>Rozpocznij sesję</Button>
          ) : (
            <div className="flex flex-col gap-3">
              <div className="flex items-center gap-3">
                <Button variant="primary" size="lg" onClick={() => capture.run()} disabled={capture.busy}>Zrób ujęcie</Button>
                <div className="text-sm">ujęcia {session.views} / {session.min_views}+ · pokrycie {Math.round(session.coverage * 100)}%</div>
              </div>
              {last && <div className={clsx("text-sm", last.accepted ? "text-[var(--good)]" : "text-[var(--warn)]")}>{last.accepted ? `Przyjęte (narożników: ${last.corners})` : last.reason}</div>}
              {session.coverage_grid && (
                <div className="grid gap-0.5" style={{ gridTemplateColumns: `repeat(${session.coverage_grid[0].length}, 1fr)` }}>
                  {session.coverage_grid.flat().map((v: number, i: number) => (
                    <div key={i} className="aspect-video rounded-sm" style={{ background: v ? `color-mix(in oklab, var(--good) ${Math.min(100, 30 + v * 8)}%, transparent)` : "var(--surface-2)" }} />
                  ))}
                </div>
              )}
              <div className="flex gap-2">
                <Button onClick={() => solve.run()} disabled={solve.busy || session.views < session.min_views}>Oblicz</Button>
                <Button variant="ghost" onClick={async () => { await api.del(`/api/calibration/${cam.id}/intrinsics/session`); setSession(null); }}>Anuluj</Button>
              </div>
            </div>
          )}
          <ErrorNote error={start.error ?? capture.error ?? solve.error ?? accept.error} />
        </Card>
        {solved && (
          <Card title="Wynik kalibracji obiektywu" actions={<Badge tone={solved.grade === "good" ? "good" : "warn"}>{tr(GRADE, solved.grade)}</Badge>}>
            <div className="flex flex-col gap-1 text-sm">
              <Check ok={solved.rms_px < 0.8} label="RMS reprojekcji" detail={`${solved.rms_px.toFixed(3)} px`} />
              <Check ok={solved.coverage >= 0.5 ? true : null} label="Pokrycie obrazu" detail={`${Math.round(solved.coverage * 100)}%`} />
              <div className="text-xs text-[var(--muted)]">fx {solved.K[0][0].toFixed(1)} · fy {solved.K[1][1].toFixed(1)} · cx {solved.K[0][2].toFixed(1)} · cy {solved.K[1][2].toFixed(1)}</div>
              <Button className="mt-2" variant="good" onClick={() => accept.run()}>Zatwierdź (potem ponownie położenie tarczy)</Button>
            </div>
          </Card>
        )}
      </div>
    </div>
  );
}
