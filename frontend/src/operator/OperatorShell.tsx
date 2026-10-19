import clsx from "clsx";
import {
  Building2, ChartLine, LayoutDashboard, Menu, MonitorSmartphone, Target, Wallet, Wrench, X, type LucideIcon,
} from "lucide-react";
import { useState } from "react";
import { NavLink, Outlet } from "react-router";
import { useApi } from "@/hooks/useApi";
import { useLive } from "@/store/live";
import type { Dashboard } from "./lib";

interface Item { to: string; label: string; icon: LucideIcon; badge?: (d: Dashboard) => number }

const NAV: Item[] = [
  { to: "/operator", label: "Pulpit", icon: LayoutDashboard },
  { to: "/operator/venues", label: "Lokale", icon: Building2 },
  { to: "/operator/boards", label: "Tarcze", icon: MonitorSmartphone, badge: (d) => d.alerts.filter((a) => a.severity === "bad").length },
  { to: "/operator/stats", label: "Statystyki", icon: ChartLine },
  { to: "/operator/settlements", label: "Rozliczenia", icon: Wallet },
  { to: "/operator/tickets", label: "Serwis", icon: Wrench, badge: (d) => d.open_tickets_total },
];

export function OperatorShell() {
  const [open, setOpen] = useState(false);
  const mode = useLive((s) => s.mode);
  // Polled for the badges; pages load their own data.
  const { data: dash } = useApi<Dashboard>("/api/fleet/dashboard", 60_000);
  const close = () => setOpen(false);
  return (
    <div className="flex min-h-dvh">
      <aside className={clsx("fixed inset-y-0 left-0 z-40 flex w-64 shrink-0 flex-col border-r border-[var(--border)] bg-[var(--surface)] transition-transform md:sticky md:top-0 md:h-dvh md:translate-x-0",
        open ? "translate-x-0" : "-translate-x-full")}>
        <div className="flex items-center gap-3 px-5 py-5">
          <div className="grid h-10 w-10 place-items-center rounded-full bg-[var(--accent)] text-white"><Target size={22} strokeWidth={2.4} /></div>
          <div className="min-w-0 flex-1">
            <div className="truncate font-display text-lg font-extrabold leading-tight">DartSense</div>
            <div className="truncate text-xs text-[var(--muted)]">Panel operatora</div>
          </div>
          <button className="rounded-lg p-1 text-[var(--muted)] md:hidden" onClick={close} aria-label="Zamknij menu"><X size={20} /></button>
        </div>
        <nav className="flex flex-1 flex-col gap-0.5 overflow-y-auto px-3 pb-4">
          {NAV.map((n) => {
            const Icon = n.icon;
            const badge = dash && n.badge ? n.badge(dash) : 0;
            return (
              <NavLink key={n.to} to={n.to} end={n.to === "/operator"} onClick={close}
                className={({ isActive }) => clsx("flex items-center gap-3 rounded-xl px-3 py-2.5 text-[15px] font-semibold transition",
                  isActive ? "bg-[color-mix(in_oklab,var(--accent)_16%,transparent)] text-[var(--text)] shadow-[inset_3px_0_0_var(--accent)]"
                    : "text-[var(--muted)] hover:bg-[var(--surface-2)] hover:text-[var(--text)]")}>
                <Icon size={19} />
                <span className="flex-1">{n.label}</span>
                {badge > 0 && <span className="rounded-full bg-[var(--bad)] px-1.5 text-xs font-bold text-white">{badge}</span>}
              </NavLink>
            );
          })}
          {mode !== "central" && (
            <NavLink to="/" className="mt-auto flex items-center gap-3 rounded-xl border border-[var(--border)] px-3 py-2.5 text-sm font-semibold text-[var(--muted)] hover:bg-[var(--surface-2)]">
              <Target size={18} /> Wróć do tarczy
            </NavLink>
          )}
        </nav>
      </aside>
      {open && <div className="fixed inset-0 z-30 bg-black/60 md:hidden" onClick={close} />}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 flex items-center gap-3 border-b border-[var(--border)] bg-[var(--bg)]/85 px-4 py-2.5 backdrop-blur md:hidden">
          <button className="rounded-lg p-1" onClick={() => setOpen(true)} aria-label="Menu"><Menu size={22} /></button>
          <div className="font-display font-bold">Panel operatora</div>
        </header>
        <main className="mx-auto w-full max-w-[1700px] flex-1 p-3 md:p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
