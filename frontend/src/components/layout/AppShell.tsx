import clsx from "clsx";
import {
  Building2, Camera, ChartLine, CirclePlus, Crosshair, Ellipsis, Menu, ScanEye, Settings, SquareTerminal, Target, Tv, Users, X,
  type LucideIcon,
} from "lucide-react";
import { useState } from "react";
import { Navigate, NavLink, Outlet } from "react-router";
import { Badge } from "@/components/ui";
import { ENGINE_STATE, plural, tr } from "@/lib/pl";
import { useLive } from "@/store/live";
import { usePrefs } from "@/store/prefs";

interface NavItem { to: string; label: string; icon: LucideIcon }

const GAME_NAV: NavItem[] = [
  { to: "/", label: "Graj", icon: Target },
  { to: "/games", label: "Nowa gra", icon: CirclePlus },
  { to: "/players", label: "Gracze", icon: Users },
  { to: "/stats", label: "Statystyki", icon: ChartLine },
];

const SYSTEM_NAV: NavItem[] = [
  { to: "/cameras", label: "Kamery", icon: Camera },
  { to: "/calibration", label: "Kalibracja", icon: Crosshair },
  { to: "/detection", label: "Detekcja", icon: ScanEye },
  { to: "/settings", label: "Ustawienia", icon: Settings },
  { to: "/developer", label: "Narzędzia", icon: SquareTerminal },
];

export function EngineBadge() {
  const engine = useLive((s) => s.engineState);
  const ws = useLive((s) => s.events);
  if (ws !== "open") return <Badge tone="bad">● brak połączenia</Badge>;
  const tone = engine === "idle" ? "good" : engine === "obstructed" ? "warn" : engine === "motion" || engine === "processing" ? "accent" : "info";
  return <Badge tone={tone}>● {engine ? tr(ENGINE_STATE, engine) : "…"}</Badge>;
}

function SideLink({ item, onClick }: { item: NavItem; onClick?: () => void }) {
  const Icon = item.icon;
  return (
    <NavLink to={item.to} end={item.to === "/"} onClick={onClick}
      className={({ isActive }) => clsx("flex items-center gap-3 rounded-xl px-3 py-2.5 text-[15px] font-semibold transition",
        isActive ? "bg-[color-mix(in_oklab,var(--accent)_16%,transparent)] text-[var(--text)] shadow-[inset_3px_0_0_var(--accent)]"
          : "text-[var(--muted)] hover:bg-[var(--surface-2)] hover:text-[var(--text)]")}>
      <Icon size={19} strokeWidth={2} />
      {item.label}
    </NavLink>
  );
}

function NavGroup({ title, items, onClick }: { title: string; items: NavItem[]; onClick?: () => void }) {
  return (
    <div className="flex flex-col gap-0.5">
      <div className="px-3 pb-1 text-[11px] font-bold tracking-[0.12em] text-[var(--muted)] uppercase opacity-70">{title}</div>
      {items.map((n) => <SideLink key={n.to} item={n} onClick={onClick} />)}
    </div>
  );
}

export function AppShell() {
  const [open, setOpen] = useState(false);
  const brand = usePrefs((s) => s.brandName);
  const tagline = usePrefs((s) => s.brandTagline);
  const mode = useLive((s) => s.mode);
  const cams = useLive((s) => s.cameras);
  const down = cams.filter((c) => !c.connected).length;
  const close = () => setOpen(false);
  // The central fleet server has no board of its own: its home is the operator panel.
  if (mode === "central") return <Navigate to="/operator" replace />;
  return (
    <div className="flex min-h-dvh">
      <aside className={clsx("fixed inset-y-0 left-0 z-40 flex w-64 shrink-0 flex-col border-r border-[var(--border)] bg-[var(--surface)] transition-transform md:sticky md:top-0 md:h-dvh md:translate-x-0",
        open ? "translate-x-0" : "-translate-x-full")}>
        <div className="flex items-center gap-3 px-5 py-5">
          <div className="grid h-10 w-10 place-items-center rounded-full bg-[var(--accent)] text-white"><Target size={22} strokeWidth={2.4} /></div>
          <div className="min-w-0 flex-1">
            <div className="truncate font-display text-lg font-extrabold leading-tight">{brand}</div>
            <div className="truncate text-xs text-[var(--muted)]">{tagline}</div>
          </div>
          <button className="rounded-lg p-1 text-[var(--muted)] md:hidden" onClick={close} aria-label="Zamknij menu"><X size={20} /></button>
        </div>
        <nav className="flex flex-1 flex-col gap-5 overflow-y-auto px-3 pb-4">
          <NavGroup title="Gra" items={GAME_NAV} onClick={close} />
          <NavGroup title="System" items={SYSTEM_NAV} onClick={close} />
          <NavLink to="/operator" className="mt-auto flex items-center gap-3 rounded-xl px-3 py-2.5 text-[15px] font-semibold text-[var(--muted)] hover:bg-[var(--surface-2)] hover:text-[var(--text)]">
            <Building2 size={19} /> Panel operatora
          </NavLink>
          <NavLink to="/tv" className="flex items-center gap-3 rounded-xl border border-[var(--border)] px-3 py-2.5 text-[15px] font-semibold text-[var(--muted)] hover:bg-[var(--surface-2)] hover:text-[var(--text)]">
            <Tv size={19} /> Tryb TV
          </NavLink>
        </nav>
      </aside>
      {open && <div className="fixed inset-0 z-30 bg-black/60 md:hidden" onClick={close} />}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 flex items-center gap-3 border-b border-[var(--border)] bg-[var(--bg)]/85 px-4 py-2.5 backdrop-blur">
          <button className="rounded-lg p-1 md:hidden" onClick={() => setOpen(true)} aria-label="Menu"><Menu size={22} /></button>
          <div className="flex flex-1 flex-wrap items-center gap-2">
            <EngineBadge />
            {mode === "simulator" && <Badge tone="warn">SYMULATOR — kamery syntetyczne</Badge>}
            {down > 0 && <Badge tone="bad">{down} {plural(down, "kamera odłączona", "kamery odłączone", "kamer odłączonych")}</Badge>}
          </div>
        </header>
        <main className="mx-auto w-full max-w-[1700px] flex-1 p-3 pb-24 md:p-6 md:pb-6">
          <Outlet />
        </main>
        <nav className="fixed inset-x-0 bottom-0 z-20 grid grid-cols-5 border-t border-[var(--border)] bg-[var(--surface)] md:hidden">
          {GAME_NAV.map((n) => {
            const Icon = n.icon;
            return (
              <NavLink key={n.to} to={n.to} end={n.to === "/"}
                className={({ isActive }) => clsx("flex flex-col items-center gap-0.5 py-2 text-[11px] font-semibold", isActive ? "text-[var(--accent)]" : "text-[var(--muted)]")}>
                <Icon size={20} />
                {n.label}
              </NavLink>
            );
          })}
          <button onClick={() => setOpen(true)} className="flex flex-col items-center gap-0.5 py-2 text-[11px] font-semibold text-[var(--muted)]">
            <Ellipsis size={20} />
            Więcej
          </button>
        </nav>
      </div>
    </div>
  );
}
