import clsx from "clsx";
import { useState } from "react";
import { NavLink, Outlet } from "react-router";
import { useLive } from "@/store/live";
import { usePrefs } from "@/store/prefs";
import { Badge } from "@/components/ui";

const NAV = [
  { to: "/", label: "Play", icon: "◎" },
  { to: "/games", label: "Games", icon: "▤" },
  { to: "/players", label: "Players", icon: "☺" },
  { to: "/stats", label: "Statistics", icon: "▲" },
  { to: "/cameras", label: "Cameras", icon: "◉" },
  { to: "/calibration", label: "Calibration", icon: "⊕" },
  { to: "/detection", label: "Detection", icon: "✦" },
  { to: "/settings", label: "Settings", icon: "⚙" },
  { to: "/developer", label: "Developer", icon: "⌘" },
];

export function EngineBadge() {
  const engine = useLive((s) => s.engineState);
  const ws = useLive((s) => s.events);
  if (ws !== "open") return <Badge tone="bad">● offline</Badge>;
  const tone = engine === "idle" ? "good" : engine === "obstructed" ? "warn" : engine === "motion" || engine === "processing" ? "accent" : "info";
  return <Badge tone={tone as any}>● {engine ?? "…"}</Badge>;
}

export function AppShell() {
  const [open, setOpen] = useState(false);
  const brand = usePrefs((s) => s.brandName);
  const tagline = usePrefs((s) => s.brandTagline);
  const mode = useLive((s) => s.mode);
  const cams = useLive((s) => s.cameras);
  const down = cams.filter((c) => !c.connected).length;
  return (
    <div className="flex min-h-dvh">
      <aside className={clsx("fixed inset-y-0 left-0 z-40 w-60 shrink-0 border-r border-[var(--border)] bg-[var(--surface)] transition-transform md:static md:translate-x-0",
        open ? "translate-x-0" : "-translate-x-full")}>
        <div className="flex items-center gap-3 px-5 py-5">
          <div className="grid h-10 w-10 place-items-center rounded-full border-4 border-[var(--accent)] font-display text-lg font-black">◎</div>
          <div>
            <div className="font-display text-lg font-bold leading-tight">{brand}</div>
            <div className="text-xs text-[var(--muted)]">{tagline}</div>
          </div>
        </div>
        <nav className="flex flex-col gap-0.5 px-3">
          {NAV.map((n) => (
            <NavLink key={n.to} to={n.to} end={n.to === "/"} onClick={() => setOpen(false)}
              className={({ isActive }) => clsx("flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-semibold transition",
                isActive ? "bg-[color-mix(in_oklab,var(--accent)_18%,transparent)] text-[var(--text)]" : "text-[var(--muted)] hover:bg-[var(--surface-2)] hover:text-[var(--text)]")}>
              <span className="w-5 text-center text-base">{n.icon}</span>
              {n.label}
            </NavLink>
          ))}
          <NavLink to="/tv" className="mt-3 flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-semibold text-[var(--muted)] hover:bg-[var(--surface-2)]">
            <span className="w-5 text-center">▭</span> TV mode
          </NavLink>
        </nav>
      </aside>
      {open && <div className="fixed inset-0 z-30 bg-black/50 md:hidden" onClick={() => setOpen(false)} />}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 flex items-center gap-3 border-b border-[var(--border)] bg-[var(--bg)]/85 px-4 py-2.5 backdrop-blur">
          <button className="rounded-lg px-2 py-1 text-xl md:hidden" onClick={() => setOpen(true)} aria-label="Menu">☰</button>
          <div className="flex flex-1 flex-wrap items-center gap-2">
            <EngineBadge />
            {mode === "simulator" && <Badge tone="warn">SIMULATOR — synthetic cameras</Badge>}
            {down > 0 && <Badge tone="bad">{down} camera{down > 1 ? "s" : ""} disconnected</Badge>}
          </div>
        </header>
        <main className="mx-auto w-full max-w-[1600px] flex-1 p-3 pb-24 md:p-6 md:pb-6">
          <Outlet />
        </main>
        <nav className="fixed inset-x-0 bottom-0 z-20 grid grid-cols-5 border-t border-[var(--border)] bg-[var(--surface)] md:hidden">
          {NAV.slice(0, 5).map((n) => (
            <NavLink key={n.to} to={n.to} end={n.to === "/"}
              className={({ isActive }) => clsx("flex flex-col items-center py-2 text-[11px] font-semibold", isActive ? "text-[var(--accent)]" : "text-[var(--muted)]")}>
              <span className="text-lg leading-none">{n.icon}</span>
              {n.label}
            </NavLink>
          ))}
        </nav>
      </div>
    </div>
  );
}
