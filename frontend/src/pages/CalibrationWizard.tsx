import clsx from "clsx";
import { CircleCheck, CircleX, Lightbulb, PersonStanding, RefreshCw, Target, TriangleAlert, Wrench } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router";
import { CameraView } from "@/components/camera/CameraView";
import { Badge, Button, ErrorNote, Spinner } from "@/components/ui";
import { useApi } from "@/hooks/useApi";
import { api } from "@/lib/api";
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
];

/** Calibration for venue staff: get the board ready, press one button, check, save. The
 *  technical page (lens, manual points) stays under Obsługa → Kalibracja zaawansowana. */
export default function CalibrationWizard() {
  const nav = useNavigate();
  const { data: cams } = useApi<CameraInfo[]>("/api/cameras");
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
        setResults((x) => ({ ...x, [c.id]: { state: "done", ok: r.ok, grade: r.grade, reason: r.reason, n: Date.now() } }));
      } catch (e) {
        setResults((x) => ({ ...x, [c.id]: { state: "error", ok: false, reason: e instanceof Error ? e.message : String(e) } }));
      }
    }
  }

  async function save() {
    setSaving(true);
    setError(null);
    try {
      for (const c of good) await api.post(`/api/calibration/${c.id}/board/accept`);
      for (const c of enabled) if (results[c.id]?.state === "done" && !good.includes(c)) {
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
        <p className="text-lg text-[var(--muted)]">Kalibracja zapisana ({good.length} z {enabled.length} kamer). Tarcza liczy punkty.</p>
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
                <div className="px-2 pb-2"><CameraView cameraId={c.id} width={480} fps={4} /></div>
              </div>
            ))}
          </div>
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
                      <img src={`/api/calibration/${c.id}/preview.jpg?width=900&_=${r.n}`} className="h-full w-full object-cover" alt={`Kalibracja ${c.name}`} />
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
                    <div className="px-4 py-2 text-xs text-[var(--muted)]">Kolorowe okręgi i linie powinny leżeć na drutach tarczy.</div>
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
                    <div className="font-display text-2xl font-bold tracking-wide text-[var(--bad)] uppercase">Za mało kamer widzi tarczę</div>
                    <div className="text-[var(--muted)]">Sprawdź światło i czy nic nie zasłania tarczy, potem spróbuj ponownie. Jeśli się nie uda — zgłoś to operatorowi.</div>
                  </>
                )}
              </div>
              <Button size="lg" onClick={calibrate}><RefreshCw size={18} /> Spróbuj ponownie</Button>
              {canSave && <Button size="xl" variant="good" disabled={saving} onClick={save}>{saving ? <Spinner /> : <CircleCheck size={26} />} Zapisz</Button>}
            </div>
          )}
        </div>
      )}

      <Link to="/service/calibration" className="flex w-fit items-center gap-2 text-sm text-[var(--muted)] hover:text-[var(--text)]">
        <Wrench size={14} /> Kalibracja zaawansowana (dla serwisanta): obiektyw, punkty ręcznie
      </Link>
    </div>
  );
}
