import clsx from "clsx";
import { TrendingDown, TrendingUp } from "lucide-react";
import type { ReactNode } from "react";
import { Badge } from "@/components/ui";
import { alertText, BOARD_STATUS, type Alert, type Board } from "./lib";

export function Kpi({ label, value, sub, change, tone }: {
  label: string; value: ReactNode; sub?: ReactNode; change?: number | null; tone?: "good" | "warn" | "bad";
}) {
  return (
    <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-4">
      <div className="text-xs font-semibold tracking-wide text-[var(--muted)] uppercase">{label}</div>
      <div className={clsx("mt-1 font-score text-4xl font-bold leading-none",
        tone === "good" && "text-[var(--good)]", tone === "warn" && "text-[var(--warn)]", tone === "bad" && "text-[var(--bad)]")}>{value}</div>
      <div className="mt-2 flex flex-wrap items-center gap-2 text-sm text-[var(--muted)]">
        {change != null && Number.isFinite(change) && (
          <span className={clsx("inline-flex items-center gap-0.5 font-semibold", change >= 0 ? "text-[var(--good)]" : "text-[var(--bad)]")}>
            {change >= 0 ? <TrendingUp size={14} /> : <TrendingDown size={14} />}
            {change >= 0 ? "+" : ""}{change.toFixed(0)}%
          </span>
        )}
        {sub}
      </div>
    </div>
  );
}

export function LevelDot({ level, online }: { level: Board["level"]; online: boolean }) {
  const c = level === "retired" ? "var(--muted)" : !online || level === "bad" ? "var(--bad)" : level === "warn" ? "var(--warn)" : "var(--good)";
  return <span className={clsx("inline-block h-2.5 w-2.5 shrink-0 rounded-full", online && level === "ok" && "shadow-[0_0_8px_var(--good)]")} style={{ background: c }} />;
}

export function BoardStatus({ b }: { b: Board }) {
  if (b.status !== "active") return <Badge tone={b.status === "maintenance" ? "warn" : "info"}>{BOARD_STATUS[b.status]}</Badge>;
  return b.online ? <Badge tone="good">online</Badge> : <Badge tone="bad">offline</Badge>;
}

export function AlertLine({ a }: { a: Alert }) {
  return (
    <span className={clsx("inline-flex items-center gap-1.5 text-sm",
      a.severity === "bad" ? "text-[var(--bad)]" : a.severity === "warn" ? "text-[var(--warn)]" : "text-[var(--muted)]")}>
      <span className="h-1.5 w-1.5 rounded-full bg-current" />{alertText(a)}
    </span>
  );
}

export function Section({ title, children, actions }: { title: string; children: ReactNode; actions?: ReactNode }) {
  return (
    <section className="flex flex-col gap-3">
      <div className="flex items-center justify-between gap-2">
        <h2 className="font-display text-lg font-bold">{title}</h2>
        {actions}
      </div>
      {children}
    </section>
  );
}
