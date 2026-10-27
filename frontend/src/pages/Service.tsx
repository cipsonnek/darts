import clsx from "clsx";
import {
  Camera, ChartLine, Crosshair, Delete, History, Lock, ScanEye, Settings, SquareTerminal, Users, type LucideIcon,
} from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router";
import { Button, ErrorNote, PageHeader, useTilt } from "@/components/ui";
import { useService } from "@/store/service";

function useUnlocked(): boolean {
  const until = useService((s) => s.until);
  return until > Date.now();
}

/** Big touch keypad for the service PIN. */
function PinPad({ title, hint }: { title: string; hint: ReactNode }) {
  const unlock = useService((s) => s.unlock);
  const [pin, setPin] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function submit(value = pin) {
    if (!value || busy) return;
    setBusy(true);
    setError(null);
    try {
      await unlock(value);
    } catch (e) {
      setError(e);
      setPin("");
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if (/^\d$/.test(e.key)) setPin((p) => (p.length < 12 ? p + e.key : p));
      else if (e.key === "Backspace") setPin((p) => p.slice(0, -1));
      else if (e.key === "Enter") submit();
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  });

  return (
    <div className="mx-auto flex max-w-sm flex-col items-center gap-5 py-6 text-center">
      <div className="grid h-20 w-20 place-items-center rounded-full bg-[color-mix(in_oklab,var(--accent)_18%,transparent)] text-[var(--accent)]">
        <Lock size={36} />
      </div>
      <div>
        <h1 className="font-display text-4xl font-extrabold tracking-wide uppercase">{title}</h1>
        <p className="mt-1 text-[var(--muted)]">{hint}</p>
      </div>
      <div className="flex h-14 items-center justify-center gap-3" aria-label="Wpisany PIN">
        {Array.from({ length: Math.max(6, pin.length) }, (_, i) => (
          <span key={i} className={clsx("h-4 w-4 rounded-full border-2 transition", i < pin.length ? "scale-110 border-[var(--accent)] bg-[var(--accent)]" : "border-[var(--border)]")} />
        ))}
      </div>
      <div className="grid w-full grid-cols-3 gap-3">
        {["1", "2", "3", "4", "5", "6", "7", "8", "9"].map((d) => (
          <Button key={d} size="lg" className="h-16 font-score text-3xl!" onClick={() => setPin((p) => p + d)}>{d}</Button>
        ))}
        <Button size="lg" className="h-16" onClick={() => setPin((p) => p.slice(0, -1))} aria-label="Usuń cyfrę"><Delete size={24} /></Button>
        <Button size="lg" className="h-16 font-score text-3xl!" onClick={() => setPin((p) => p + "0")}>0</Button>
        <Button size="lg" variant="primary" className="h-16 text-lg!" disabled={!pin || busy} onClick={() => submit()}>OK</Button>
      </div>
      <ErrorNote error={error} />
    </div>
  );
}

/** Wraps pages for venue staff: shows the PIN pad until service mode is unlocked. */
export function ServiceGate({ children, title = "Tylko dla obsługi" }: { children: ReactNode; title?: string }) {
  const unlocked = useUnlocked();
  if (!unlocked) {
    return <PinPad title={title} hint="Wpisz PIN obsługi lokalu. Gracze nie potrzebują tej części — wystarczy „Graj” i „Nowa gra”." />;
  }
  return <>{children}</>;
}

interface Tile { to: string; title: string; text: string; icon: LucideIcon; main?: boolean }

const TILES: Tile[] = [
  { to: "/calibration", title: "Kalibracja kamer", text: "Po przestawieniu tarczy lub kamer albo gdy wyniki się nie zgadzają.", icon: Crosshair, main: true },
  { to: "/service/cameras", title: "Kamery", text: "Podgląd, przypisanie kamer, ostrość i ekspozycja.", icon: Camera },
  { to: "/service/history", title: "Historia gier", text: "Rozegrane i przerwane gry.", icon: History },
  { to: "/service/players", title: "Gracze", text: "Lista graczy, kolory, archiwum.", icon: Users },
  { to: "/service/stats", title: "Statystyki", text: "Średnie, heatmapy, rekordy.", icon: ChartLine },
  { to: "/service/detection", title: "Wykrywanie", text: "Diagnostyka rozpoznawania lotek (dla serwisanta).", icon: ScanEye },
  { to: "/service/settings", title: "Ustawienia", text: "Wygląd, progi pewności, dźwięk.", icon: Settings },
  { to: "/service/developer", title: "Narzędzia", text: "Nagrania, symulator, logi (dla serwisanta).", icon: SquareTerminal },
];

function ServiceTile({ t }: { t: Tile }) {
  const tilt = useTilt<HTMLAnchorElement>(6);
  const Icon = t.icon;
  return (
    <Link to={t.to} {...tilt}
      className={clsx("glass tilt flex flex-col gap-3 rounded-3xl p-5 hover:border-[var(--accent)]", t.main && "sm:col-span-2 bg-[color-mix(in_oklab,var(--accent)_12%,var(--surface))]")}>
      <div className={clsx("pop-out grid h-12 w-12 place-items-center rounded-2xl", t.main ? "bg-[var(--accent)] text-white" : "bg-[var(--surface-2)] text-[var(--accent)]")}>
        <Icon size={24} />
      </div>
      <div>
        <div className="font-display text-2xl font-bold tracking-wide uppercase">{t.title}</div>
        <div className="text-sm text-[var(--muted)]">{t.text}</div>
      </div>
    </Link>
  );
}

export default function Service() {
  const lock = useService((s) => s.lock);
  return (
    <ServiceGate>
      <PageHeader title="Obsługa tarczy" subtitle="Tryb serwisowy zablokuje się sam po 15 minutach bezczynności."
        actions={<Button onClick={lock}><Lock size={16} /> Zablokuj teraz</Button>} />
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {TILES.map((t) => <ServiceTile key={t.to} t={t} />)}
      </div>
    </ServiceGate>
  );
}
