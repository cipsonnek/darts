import clsx from "clsx";
import { CircleCheck, CircleX, Lightbulb, MapPin, PersonStanding, RefreshCw, RotateCcw, RotateCw, Target, TriangleAlert, Wrench } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router";
import { CameraView } from "@/components/camera/CameraView";
import { Badge, Button, ErrorNote, inputCls, Modal, Spinner } from "@/components/ui";
import { useApi } from "@/hooks/useApi";
import { api } from "@/lib/api";
import { DEFAULT_BOARD } from "@/lib/board";
import type { CameraInfo } from "@/lib/types";
import { useLive } from "@/store/live";

interface CalStatus {
  cameras: Record<string, any>;
  overall: { status: string; recommendation: string[] };
}

interface Result {
  state: "waiting" | "running" | "done" | "error";
  ok?: boolean;
  grade?: string;
  reason?: string;
  n?: number;
  az?: number;
}

const GRADE_TEXT: Record<string, { label: string; tone: "good" | "warn" | "bad" }> = {
  good: { label: "Bardzo dobra", tone: "good" },
  fair: { label: "Wystarczająca", tone: "warn" },
  poor: { label: "Słaba", tone: "bad" },
};

const PREP = [
  { icon: Target, text: "Wyjmij wszystkie lotki z tarczy." },
  { icon: Lightbulb, text: "Zapal światło nad tarczą (tak jak podczas gry)." },
  { icon: PersonStanding, text: "Odsuń się — nic nie może zasłaniać tarczy." },
  { icon: MapPin, text: "Przy każdej kamerze wybierz liczbę tarczy, przy której stoi (obok podglądu)." },
];

/** Number of the sector a camera at this clock angle stands next to. */
function sectorAt(az: number): number {
  const b = DEFAULT_BOARD;
  return b.sector_order[Math.round((((az % 360) + 360) % 360) / b.sector_angle_deg) % b.sector_order.length];
}

/** Calibration for venue staff: get the board ready, press one button, check, save. The
 *  technical page (lens, manual points) stays under Obsługa → Kalibracja zaawansowana. */
export default function CalibrationWizard() {
  const nav = useNavigate();
  const { data: cams, reload: reloadCams } = useApi<CameraInfo[]>("/api/cameras");
  const { data: status, reload } = useApi<CalStatus>("/api/calibration", 5000);
  const health = useLive((s) => s.cameras);
  const [phase, setPhase] = useState<"prep" | "run" | "saved">("prep");
  const [results, setResults] = useState<Record<string, Result>>({});
  const [error, setError] = useState<unknown>(null);
  const [saving, setSaving] = useState(false);

  const enabled = cams?.filter((c) => c.enabled) ?? [];
  const connected = (id: string) => health.find((h) => h.camera_id === id)?.connected ?? cams?.find((c) => c.id === id)?.health?.connected ?? false;
  const usable = enabled.filter((c) => connected(c.id));
  const running = Object.values(results).some((r) => r.state === "running" || r.state === "waiting");
  const good = enabled.filter((c) => results[c.id]?.ok && results[c.id]?.grade !== "poor");
  const canSave = !running && good.length >= 2;
  // Found but graded weak: savable on purpose, after looking at the grids.
  const found = enabled.filter((c) => results[c.id]?.ok);
  const canForce = !running && !canSave && found.length >= 2;
  const [saved, setSaved] = useState(0);

  async function calibrate() {
    setError(null);
    setPhase("run");
    const init: Record<string, Result> = {};
    for (const c of usable) init[c.id] = { state: "waiting" };
    setResults(init);
    for (const c of usable) {
      setResults((r) => ({ ...r, [c.id]: { state: "running" } }));
      try {
        const r = await api.post<any>(`/api/calibration/${c.id}/board`, { method: "auto", azimuth_deg: c.config.mount.azimuth_deg ?? null });
        setResults((x) => ({ ...x, [c.id]: { state: "done", ok: r.ok, grade: r.grade, reason: r.reason, n: Date.now(),
          az: r.derived?.camera_azimuth_deg } }));
      } catch (e) {
        setResults((x) => ({ ...x, [c.id]: { state: "error", ok: false, reason: e instanceof Error ? e.message : String(e) } }));
      }
    }
  }

  const [turning, setTurning] = useState(false);
  // Where each camera stands decides which way the grid is turned: wires and colours repeat
  // every 36°, so only this tells the right rotation apart. Staff read it off the board.
  async function setStand(c: CameraInfo, number: number) {
    const i = DEFAULT_BOARD.sector_order.indexOf(number);
    try {
      await api.patch(`/api/cameras/${c.id}`, { mount: { azimuth_deg: i * DEFAULT_BOARD.sector_angle_deg } });
      reloadCams();
    } catch (e) {
      setError(e);
    }
  }
  const stands = enabled.map((c) => c.config.mount.azimuth_deg).filter((a): a is number => a != null).map(sectorAt);
  const sameStand = new Set(stands).size < stands.length;
  const [zoom, setZoom] = useState<{ id: string; name: string } | null>(null);
  async function rotate(c: CameraInfo, steps: number) {
    setTurning(true);
    setError(null);
    try {
      const r = await api.post<any>(`/api/calibration/${c.id}/board/rotate?steps=${steps}`);
      setResults((x) => ({ ...x, [c.id]: { ...x[c.id], n: Date.now(), az: r.derived?.camera_azimuth_deg } }));
    } catch (e) {
      setError(e);
    } finally {
      setTurning(false);
    }
  }

  async function save(which: CameraInfo[]) {
    setSaving(true);
    setError(null);
    try {
      for (const c of which) await api.post(`/api/calibration/${c.id}/board/accept`);
      setSaved(which.length);
      for (const c of enabled) if (results[c.id]?.state === "done" && !which.includes(c)) {
        await api.post(`/api/calibration/${c.id}/board/discard`).catch(() => {});
      }
      reload();
      setPhase("saved");
    } catch (e) {
      setError(e);
    } finally {
      setSaving(false);
    }
  }

  const overallOk = status?.overall.status === "ok";

  if (phase === "saved") {
    return (
      <div className="mx-auto flex max-w-xl flex-col items-center gap-5 py-10 text-center">
        <div className="animate-pop grid h-28 w-28 place-items-center rounded-full bg-[color-mix(in_oklab,var(--good)_20%,transparent)] text-[var(--good)] shadow-[0_0_80px_-10px_var(--good)]">
          <CircleCheck size={64} />
        </div>
        <h1 className="font-display text-5xl font-extrabold tracking-wide uppercase">Gotowe!</h1>
        <p className="text-lg text-[var(--muted)]">Kalibracja zapisana ({saved} z {enabled.length} kamer). Tarcza liczy punkty.</p>
        <Button size="xl" variant="primary" onClick={() => nav("/")}><Target size={28} /> Wróć do gry</Button>
      </div>
    );
  }

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-display text-4xl font-extrabold tracking-wide uppercase md:text-5xl">Kalibracja kamer</h1>
          <p className="mt-1 max-w-2xl text-[var(--muted)]">Rób ją po przestawieniu tarczy lub kamer albo gdy tarcza źle liczy punkty. Trwa około pół minuty.</p>
        </div>
        {status && (
          <Badge tone={overallOk ? "good" : status.overall.status === "warning" ? "warn" : "bad"} className="px-3 py-1 text-sm">
            {overallOk ? "● Obecna kalibracja: OK" : status.overall.status === "warning" ? "● Obecna kalibracja: do sprawdzenia" : "● Tarcza nie jest skalibrowana"}
          </Badge>
        )}
      </div>

      {phase === "prep" && (
        <div className="animate-rise grid gap-5 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
          <div className="glass flex flex-col gap-4 rounded-3xl p-6">
            <h2 className="font-display text-2xl font-bold tracking-wide uppercase">Zanim zaczniesz</h2>
            <ul className="flex flex-col gap-3">
              {PREP.map((p, i) => {
                const Icon = p.icon;
                return (
                  <li key={i} className="flex items-center gap-4 rounded-2xl bg-[var(--surface-2)] p-3">
                    <span className="grid h-12 w-12 shrink-0 place-items-center rounded-xl bg-[var(--surface)] text-[var(--accent)]"><Icon size={24} /></span>
                    <span className="text-lg font-semibold">{p.text}</span>
                  </li>
                );
              })}
            </ul>
            <Button size="xl" variant="primary" className="mt-2" disabled={usable.length < 2} onClick={calibrate}>
              <RefreshCw size={26} /> Kalibruj
            </Button>
            {cams && usable.length < 2 && (
              <div className="flex items-start gap-2 rounded-2xl bg-[color-mix(in_oklab,var(--bad)_14%,transparent)] p-3 text-sm text-[var(--bad)]">
                <TriangleAlert size={18} className="mt-0.5 shrink-0" />
                Działają mniej niż 2 kamery. Sprawdź, czy kable USB są podłączone, i uruchom komputer tarczy ponownie. Jeśli to nie pomoże — zgłoś usterkę operatorowi.
              </div>
            )}
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {enabled.map((c) => (
              <div key={c.id} className="glass overflow-hidden rounded-3xl">
                <div className="flex items-center justify-between px-4 py-2.5">
                  <span className="font-semibold">{c.name}</span>
                  {connected(c.id) ? <Badge tone="good">działa</Badge> : <Badge tone="bad">brak obrazu</Badge>}
                </div>
                <div className="px-2"><CameraView cameraId={c.id} width={480} fps={4} /></div>
                <label className="flex items-center gap-2 px-4 py-3 text-sm">
                  <span className="flex-1 text-[var(--muted)]">Stoi przy liczbie<br /><span className="text-xs">(na podglądzie: na dole, najbliżej kamery)</span></span>
                  <select className={`${inputCls} h-12 w-24 text-center font-score text-2xl`} value={c.config.mount.azimuth_deg == null ? "" : sectorAt(c.config.mount.azimuth_deg)}
                    onChange={(e) => setStand(c, Number(e.target.value))}>
                    {c.config.mount.azimuth_deg == null && <option value="">?</option>}
                    {DEFAULT_BOARD.sector_order.map((n) => <option key={n} value={n}>{n}</option>)}
                  </select>
                </label>
              </div>
            ))}
          </div>
          {sameStand && (
            <div className="flex items-start gap-2 rounded-2xl bg-[color-mix(in_oklab,var(--warn)_14%,transparent)] p-3 text-sm text-[var(--warn)] lg:col-start-2">
              <TriangleAlert size={18} className="mt-0.5 shrink-0" /> Dwie kamery mają wybraną tę samą liczbę — każda stoi przy innej.
            </div>
          )}
        </div>
      )}

      {phase === "run" && (
        <div className="animate-rise flex flex-col gap-5">
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {enabled.map((c) => {
              const r = results[c.id];
              const g = r?.grade ? GRADE_TEXT[r.grade] : null;
              return (
                <div key={c.id} className={clsx("glass flex flex-col overflow-hidden rounded-3xl",
                  r?.state === "done" && r.ok && r.grade !== "poor" && "border-[var(--good)]/60",
                  (r?.state === "error" || (r?.state === "done" && (!r.ok || r.grade === "poor"))) && "border-[var(--bad)]/60")}>
                  <div className="flex items-center justify-between gap-2 px-4 py-3">
                    <span className="font-display text-xl font-bold tracking-wide uppercase">{c.name}</span>
                    {!r ? <Badge tone="bad">pominięta — brak obrazu</Badge>
                      : r.state === "waiting" ? <Badge>czeka…</Badge>
                        : r.state === "running" ? <Badge tone="accent"><Spinner /> szukam tarczy…</Badge>
                          : r.ok && g ? <Badge tone={g.tone}>{g.label}</Badge>
                            : <Badge tone="bad">nie udało się</Badge>}
                  </div>
                  <div className="relative aspect-video bg-[var(--surface-2)]">
                    {r?.state === "done" && r.ok ? (
                      <button className="h-full w-full" onClick={() => setZoom({ id: c.id, name: c.name })} title="Powiększ">
                        <img src={`/api/calibration/${c.id}/preview.jpg?width=900&_=${r.n}`} className="h-full w-full object-cover" alt={`Kalibracja ${c.name}`} />
                      </button>
                    ) : r?.state === "done" || r?.state === "error" ? (
                      <div className="flex h-full flex-col items-center justify-center gap-2 p-4 text-center text-sm text-[var(--bad)]">
                        <CircleX size={36} />
                        {r.reason || "Kamera nie widzi tarczy wyraźnie."}
                      </div>
                    ) : (
                      <div className="grid h-full place-items-center"><Spinner /></div>
                    )}
                  </div>
                  {r?.state === "done" && r.ok && (
                    <div className="flex items-center gap-2 px-3 py-2">
                      <Button onClick={() => rotate(c, -1)} disabled={turning} aria-label="Obróć siatkę w lewo"><RotateCcw size={18} /></Button>
                      <div className="min-w-0 flex-1 text-center text-xs text-[var(--muted)]">
                        Okręgi na drutach, a żółta <b className="text-[var(--text)]">20</b> na prawdziwej 20.
                        {r.az != null && <> Kamera stoi przy <b className="text-[var(--text)]">{sectorAt(r.az)}</b>.</>}
                      </div>
                      <Button onClick={() => rotate(c, 1)} disabled={turning} aria-label="Obróć siatkę w prawo"><RotateCw size={18} /></Button>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
          <ErrorNote error={error} />
          {!running && (
            <div className="glass flex flex-wrap items-center gap-4 rounded-3xl p-5">
              <div className="min-w-0 flex-1">
                {canSave ? (
                  <>
                    <div className="font-display text-2xl font-bold tracking-wide uppercase">Wygląda dobrze?</div>
                    <div className="text-[var(--muted)]">Gotowych kamer: {good.length} z {enabled.length}. Do liczenia punktów potrzebne są co najmniej 2.</div>
                  </>
                ) : (
                  <>
                    <div className="font-display text-2xl font-bold tracking-wide text-[var(--bad)] uppercase">Kalibracja wyszła za słabo</div>
                    <div className="text-[var(--muted)]">
                      Do zapisu potrzebne są co najmniej 2 kamery z dobrą oceną. Sprawdź światło i czy nic nie zasłania tarczy, potem spróbuj ponownie.
                      {canForce && " Jeśli na podglądach kolorowe okręgi leżą dokładnie na drutach tarczy, możesz zapisać mimo słabej oceny — potem sprawdź wyniki kilkoma rzutami."}
                    </div>
                  </>
                )}
              </div>
              <Button size="lg" onClick={calibrate}><RefreshCw size={18} /> Spróbuj ponownie</Button>
              {canSave && <Button size="xl" variant="good" disabled={saving} onClick={() => save(good)}>{saving ? <Spinner /> : <CircleCheck size={26} />} Zapisz</Button>}
              {canForce && (
                <Button size="lg" variant="danger" disabled={saving}
                  onClick={() => window.confirm("Zapisać mimo słabej oceny? Zrób to tylko, jeśli okręgi leżą na drutach tarczy.") && save(found)}>
                  {saving ? <Spinner /> : <CircleCheck size={18} />} Zapisz mimo to
                </Button>
              )}
            </div>
          )}
        </div>
      )}

      {zoom && (
        <Modal open wide onClose={() => setZoom(null)} title={zoom.name}>
          <img src={`/api/calibration/${zoom.id}/preview.jpg?width=1600&_=${results[zoom.id]?.n ?? 0}`} className="w-full rounded-xl" alt={`Kalibracja ${zoom.name}`} />
          <div className="mt-3 flex items-center justify-center gap-3">
            <Button onClick={() => { const c = enabled.find((x) => x.id === zoom.id); if (c) rotate(c, -1); }} disabled={turning}><RotateCcw size={18} /> Obróć</Button>
            <span className="text-sm text-[var(--muted)]">Żółta <b className="text-[var(--text)]">20</b> ma leżeć na prawdziwej 20.</span>
            <Button onClick={() => { const c = enabled.find((x) => x.id === zoom.id); if (c) rotate(c, 1); }} disabled={turning}>Obróć <RotateCw size={18} /></Button>
          </div>
        </Modal>
      )}
      <Link to="/service/calibration" className="flex w-fit items-center gap-2 text-sm text-[var(--muted)] hover:text-[var(--text)]">
        <Wrench size={14} /> Kalibracja zaawansowana (dla serwisanta): obiektyw, punkty ręcznie
      </Link>
    </div>
  );
}
