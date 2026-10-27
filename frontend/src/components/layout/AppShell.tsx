import clsx from "clsx";
import { CirclePlus, Crosshair, Lock, LockOpen, Target, Tv, Wrench, type LucideIcon } from "lucide-react";
import { useEffect, useState } from "react";
import { Navigate, NavLink, Outlet, useLocation } from "react-router";
import { Badge, Logo } from "@/components/ui";
import { plural } from "@/lib/pl";
import { useLive } from "@/store/live";
import { usePrefs } from "@/store/prefs";
import { useService } from "@/store/service";

interface NavItem { to: string; label: string; icon: LucideIcon; locked?: boolean }

const NAV: NavItem[] = [
  { to: "/", label: "Graj", icon: Target },
  { to: "/games", label: "Nowa gra", icon: CirclePlus },
  { to: "/calibration", label: "Kalibracja", icon: Crosshair, locked: true },
];

/** Board status in plain words, for players and bar staff. */
export function EngineBadge() {
  const engine = useLive((s) => s.engineState);
  const ws = useLive((s) => s.events);
  if (ws !== "open") return <Badge tone="bad">● Łączenie z tarczą…</Badge>;
  if (engine === "obstructed") return <Badge tone="warn">● Coś zasłania tarczę</Badge>;
  if (engine === "motion" || engine === "processing") return <Badge tone="accent">● Liczę rzut…</Badge>;
  if (engine === "idle") return <Badge tone="good">● Gotowa — rzucaj!</Badge>;
  if (engine === "paused") return <Badge tone="warn">● Wykrywanie wstrzymane</Badge>;
  return <Badge tone="info">● Uruchamianie…</Badge>;
}

function useUnlocked(): boolean {
  const until = useService((s) => s.until);
  const [, tick] = useState(0);
  useEffect(() => {
    if (!until) return;
    const t = setInterval(() => tick((n) => n + 1), 10_000);
    return () => clearInterval(t);
  }, [until]);
  return until > Date.now();
}

function TopLink({ item, unlocked }: { item: NavItem; unlocked: boolean }) {
  const Icon = item.icon;
  return (
    <NavLink to={item.to} end={item.to === "/"}
      className={({ isActive }) => clsx("group relative flex items-center gap-2 rounded-2xl px-4 py-2.5 font-display text-lg font-bold tracking-wide uppercase transition",
        isActive ? "bg-[var(--accent)] text-white shadow-[0_10px_24px_-10px_var(--accent)]" : "text-[var(--muted)] hover:bg-[var(--surface-2)] hover:text-[var(--text)]")}>
      <Icon size={20} strokeWidth={2.4} />
      {item.label}
      {item.locked && !unlocked && <Lock size={13} className="opacity-60" />}
    </NavLink>
  );
}

export function AppShell() {
  const brand = usePrefs((s) => s.brandName);
  const tagline = usePrefs((s) => s.brandTagline);
  const mode = useLive((s) => s.mode);
  const cams = useLive((s) => s.cameras);
  const unlocked = useUnlocked();
  const lock = useService((s) => s.lock);
  const loc = useLocation();
  const down = cams.filter((c) => !c.connected).length;
  // The central fleet server has no board of its own: its home is the operator panel.
  if (mode === "central") return <Navigate to="/operator" replace />;
  const inService = loc.pathname.startsWith("/service");
  return (
    <div className="flex min-h-dvh flex-col">
      <div className="backdrop" />
      <header className="sticky top-0 z-30 border-b border-[var(--border)] bg-[color-mix(in_oklab,var(--bg)_72%,transparent)] backdrop-blur-xl">
        <div className="mx-auto flex w-full max-w-[1700px] items-center gap-3 px-3 py-2.5 md:px-6">
          <NavLink to="/" className="flex min-w-0 items-center gap-3">
            <Logo size={42} />
            <div className="hidden min-w-0 sm:block">
              <div className="truncate font-display text-2xl leading-none font-extrabold tracking-wide uppercase">{brand}</div>
              <div className="truncate text-xs text-[var(--muted)]">{tagline}</div>
            </div>
          </NavLink>
          <nav className="mx-auto hidden items-center gap-1.5 md:flex">
            {NAV.map((n) => <TopLink key={n.to} item={n} unlocked={unlocked} />)}
          </nav>
          <div className="ml-auto flex items-center gap-2 md:ml-0">
            <div className="hidden flex-wrap items-center justify-end gap-1.5 lg:flex">
              <EngineBadge />
              {mode === "simulator" && <Badge tone="warn">SYMULATOR</Badge>}
              {down > 0 && <Badge tone="bad">{down} {plural(down, "kamera nie działa", "kamery nie działają", "kamer nie działa")}</Badge>}
            </div>
            <NavLink to="/tv" title="Tryb TV — pełny ekran z wynikami"
              className="hidden rounded-2xl border border-[var(--border)] p-2.5 text-[var(--muted)] transition hover:text-[var(--text)] sm:block">
              <Tv size={20} />
            </NavLink>
            {unlocked ? (
              <div className="flex items-center gap-1 rounded-2xl border border-[var(--good)]/50 bg-[color-mix(in_oklab,var(--good)_12%,transparent)] p-1">
                <NavLink to="/service" className={clsx("flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-sm font-bold", inService ? "bg-[var(--good)] text-black" : "text-[var(--good)]")}>
                  <Wrench size={16} /> Serwis
                </NavLink>
                <button onClick={lock} title="Zablokuj obsługę" className="rounded-xl p-1.5 text-[var(--good)] hover:bg-[var(--good)] hover:text-black">
                  <LockOpen size={16} />
                </button>
              </div>
            ) : (
              <NavLink to="/service" title="Dla obsługi lokalu (PIN)"
                className="flex items-center gap-1.5 rounded-2xl border border-[var(--border)] px-3 py-2 text-sm font-semibold text-[var(--muted)] transition hover:text-[var(--text)]">
                <Lock size={16} /> <span className="hidden sm:inline">Obsługa</span>
              </NavLink>
            )}
          </div>
        </div>
        {/* status for small screens */}
        <div className="flex flex-wrap items-center gap-1.5 px-3 pb-2 lg:hidden">
          <EngineBadge />
          {mode === "simulator" && <Badge tone="warn">SYMULATOR</Badge>}
          {down > 0 && <Badge tone="bad">{down} {plural(down, "kamera nie działa", "kamery nie działają", "kamer nie działa")}</Badge>}
        </div>
      </header>
      <main key={loc.pathname.split("/")[1]} className="animate-rise mx-auto w-full max-w-[1700px] flex-1 p-3 pb-28 md:p-6 md:pb-8">
        <Outlet />
      </main>
      <nav className="fixed inset-x-3 bottom-3 z-30 grid grid-cols-3 gap-1 rounded-3xl border border-[var(--border)] bg-[color-mix(in_oklab,var(--surface)_88%,transparent)] p-1.5 shadow-2xl backdrop-blur-xl md:hidden">
        {NAV.map((n) => {
          const Icon = n.icon;
          return (
            <NavLink key={n.to} to={n.to} end={n.to === "/"}
              className={({ isActive }) => clsx("flex flex-col items-center gap-0.5 rounded-2xl py-2 text-xs font-bold", isActive ? "bg-[var(--accent)] text-white" : "text-[var(--muted)]")}>
              <Icon size={22} />
              {n.label}
            </NavLink>
          );
        })}
      </nav>
    </div>
  );
}
