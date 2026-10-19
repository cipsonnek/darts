import clsx from "clsx";
import { useEffect, type ReactNode } from "react";

export function Card({ title, actions, children, className, pad = true }: {
  title?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string; pad?: boolean;
}) {
  return (
    <section className={clsx("rounded-2xl border border-[var(--border)] bg-[var(--surface)] shadow-sm", className)}>
      {(title || actions) && (
        <header className="flex items-center justify-between gap-3 border-b border-[var(--border)] px-4 py-3">
          <h2 className="font-display text-[13px] font-bold tracking-[0.08em] text-[var(--muted)] uppercase">{title}</h2>
          <div className="flex items-center gap-2">{actions}</div>
        </header>
      )}
      <div className={clsx(pad && "p-4")}>{children}</div>
    </section>
  );
}

type Variant = "primary" | "secondary" | "ghost" | "danger" | "good";

export function Button({ variant = "secondary", size = "md", className, ...rest }:
  React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: "sm" | "md" | "lg" | "xl" }) {
  return (
    <button
      {...rest}
      className={clsx(
        "inline-flex items-center justify-center gap-2 rounded-xl font-semibold transition select-none [&_svg]:shrink-0",
        "disabled:cursor-not-allowed disabled:opacity-45 focus-visible:outline-2 focus-visible:outline-[var(--accent)]",
        size === "sm" && "px-2.5 py-1.5 text-xs",
        size === "md" && "px-3.5 py-2 text-sm",
        size === "lg" && "px-5 py-3 text-base",
        size === "xl" && "px-6 py-5 text-2xl",
        variant === "primary" && "bg-[var(--accent)] text-white hover:brightness-110",
        variant === "secondary" && "border border-[var(--border)] bg-[var(--surface-2)] hover:brightness-125",
        variant === "ghost" && "hover:bg-[var(--surface-2)]",
        variant === "danger" && "bg-[var(--bad)] text-white hover:brightness-110",
        variant === "good" && "bg-[var(--good)] text-black hover:brightness-110",
        className,
      )}
    />
  );
}

export function Badge({ tone = "info", children, className }: { tone?: "info" | "good" | "warn" | "bad" | "accent"; children: ReactNode; className?: string }) {
  return (
    <span className={clsx("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold",
      tone === "info" && "bg-[var(--surface-2)] text-[var(--muted)]",
      tone === "good" && "bg-[color-mix(in_oklab,var(--good)_20%,transparent)] text-[var(--good)]",
      tone === "warn" && "bg-[color-mix(in_oklab,var(--warn)_20%,transparent)] text-[var(--warn)]",
      tone === "bad" && "bg-[color-mix(in_oklab,var(--bad)_20%,transparent)] text-[var(--bad)]",
      tone === "accent" && "bg-[color-mix(in_oklab,var(--accent)_22%,transparent)] text-[var(--accent)]",
      className)}>
      {children}
    </span>
  );
}

export function Stat({ label, value, hint, tone }: { label: string; value: ReactNode; hint?: ReactNode; tone?: "good" | "warn" | "bad" }) {
  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--surface-2)] p-3">
      <div className="text-xs font-medium text-[var(--muted)]">{label}</div>
      <div className={clsx("font-score text-3xl font-bold leading-tight",
        tone === "good" && "text-[var(--good)]", tone === "warn" && "text-[var(--warn)]", tone === "bad" && "text-[var(--bad)]")}>{value}</div>
      {hint && <div className="text-xs text-[var(--muted)]">{hint}</div>}
    </div>
  );
}

export function Modal({ open, onClose, title, children, wide }: { open: boolean; onClose: () => void; title: ReactNode; children: ReactNode; wide?: boolean }) {
  useEffect(() => {
    if (!open) return;
    const h = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-3 backdrop-blur-sm" onClick={onClose}>
      <div className={clsx("max-h-[92vh] w-full overflow-auto rounded-2xl border border-[var(--border)] bg-[var(--surface)] shadow-2xl", wide ? "max-w-4xl" : "max-w-lg")}
        onClick={(e) => e.stopPropagation()} role="dialog" aria-modal>
        <header className="flex items-center justify-between border-b border-[var(--border)] px-5 py-3">
          <h3 className="font-display text-lg font-bold">{title}</h3>
          <button className="text-2xl leading-none text-[var(--muted)] hover:text-[var(--text)]" onClick={onClose} aria-label="Zamknij">×</button>
        </header>
        <div className="p-5">{children}</div>
      </div>
    </div>
  );
}

export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: ReactNode }) {
  return (
    <label className="flex flex-col gap-1 text-sm">
      <span className="font-medium text-[var(--muted)]">{label}</span>
      {children}
      {hint && <span className="text-xs text-[var(--muted)]">{hint}</span>}
    </label>
  );
}

export const inputCls = "rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-3 py-2 text-sm outline-none focus:border-[var(--accent)]";

export function Toggle({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label?: ReactNode }) {
  return (
    <label className="inline-flex cursor-pointer items-center gap-2 text-sm select-none">
      <span className={clsx("relative h-5 w-9 rounded-full transition", checked ? "bg-[var(--accent)]" : "bg-[var(--border)]")}
        onClick={() => onChange(!checked)}>
        <span className={clsx("absolute top-0.5 h-4 w-4 rounded-full bg-white transition-all", checked ? "left-4.5" : "left-0.5")} />
      </span>
      {label}
    </label>
  );
}

export function Tabs<T extends string>({ value, onChange, items }: { value: T; onChange: (v: T) => void; items: { id: T; label: ReactNode }[] }) {
  return (
    <div className="flex flex-wrap gap-1 rounded-xl border border-[var(--border)] bg-[var(--surface-2)] p-1">
      {items.map((it) => (
        <button key={it.id} onClick={() => onChange(it.id)}
          className={clsx("rounded-lg px-3 py-1.5 text-sm font-semibold transition",
            value === it.id ? "bg-[var(--accent)] text-white" : "text-[var(--muted)] hover:text-[var(--text)]")}>
          {it.label}
        </button>
      ))}
    </div>
  );
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-[var(--border)] p-8 text-center">
      <div className="font-display text-lg font-semibold">{title}</div>
      {children && <div className="max-w-md text-sm text-[var(--muted)]">{children}</div>}
    </div>
  );
}

export function ErrorNote({ error }: { error: unknown }) {
  if (!error) return null;
  const msg = error instanceof Error ? error.message : String(error);
  return <div className="rounded-lg border border-[var(--bad)]/50 bg-[color-mix(in_oklab,var(--bad)_12%,transparent)] px-3 py-2 text-sm text-[var(--bad)]">{msg}</div>;
}

export function Spinner() {
  return <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-[var(--muted)] border-t-transparent" />;
}

export function Check({ ok, label, detail }: { ok: boolean | null; label: ReactNode; detail?: ReactNode }) {
  return (
    <div className="flex items-start gap-2 text-sm">
      <span className={clsx("mt-0.5 font-bold", ok === true && "text-[var(--good)]", ok === false && "text-[var(--bad)]", ok === null && "text-[var(--warn)]")}>
        {ok === true ? "✓" : ok === false ? "✗" : "⚠"}
      </span>
      <span>
        {label}
        {detail && <span className="ml-1 text-[var(--muted)]">{detail}</span>}
      </span>
    </div>
  );
}

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="font-display text-2xl font-bold md:text-3xl">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-[var(--muted)]">{subtitle}</p>}
      </div>
      <div className="flex flex-wrap items-center gap-2">{actions}</div>
    </div>
  );
}
