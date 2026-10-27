import clsx from "clsx";
import { useEffect, type ReactNode } from "react";

export function Card({ title, actions, children, className, pad = true }: {
  title?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string; pad?: boolean;
}) {
  return (
    <section className={clsx("glass rounded-3xl", className)}>
      {(title || actions) && (
        <header className="flex items-center justify-between gap-3 border-b border-[var(--border)] px-5 py-3.5">
          <h2 className="font-display text-[15px] font-bold tracking-[0.1em] text-[var(--muted)] uppercase">{title}</h2>
          <div className="flex items-center gap-2">{actions}</div>
        </header>
      )}
      <div className={clsx(pad && "p-4 md:p-5")}>{children}</div>
    </section>
  );
}

type Variant = "primary" | "secondary" | "ghost" | "danger" | "good";

const BTN_BG: Record<Variant, string | undefined> = {
  primary: "var(--accent)",
  secondary: "var(--surface-2)",
  ghost: undefined,
  danger: "var(--bad)",
  good: "var(--good)",
};

/** Buttons. Everything but small and ghost buttons is a chunky 3D key that sinks when
 *  pressed: easy to see and to hit on a touch screen next to the board. */
export function Button({ variant = "secondary", size = "md", className, style, ...rest }:
  React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: "sm" | "md" | "lg" | "xl" }) {
  const raised = variant !== "ghost" && size !== "sm";
  return (
    <button
      {...rest}
      style={{ ...(raised ? { ["--btn-bg" as string]: BTN_BG[variant] } : null), ...style }}
      className={clsx(
        "inline-flex items-center justify-center gap-2 rounded-2xl font-semibold select-none [&_svg]:shrink-0",
        "disabled:cursor-not-allowed disabled:opacity-45 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent)]",
        raised ? "btn3d mb-[5px]" : "transition",
        size === "sm" && "rounded-xl px-2.5 py-1.5 text-xs",
        size === "md" && "px-4 py-2 text-sm",
        size === "lg" && "px-5 py-3 text-base",
        size === "xl" && "rounded-3xl px-7 py-5 font-display text-3xl font-extrabold tracking-wide uppercase",
        variant === "primary" && "text-white",
        variant === "secondary" && "border border-[var(--border)]",
        variant === "ghost" && "hover:bg-[var(--surface-2)]",
        variant === "danger" && "text-white",
        variant === "good" && "text-black",
        !raised && variant === "primary" && "bg-[var(--accent)] hover:brightness-110",
        !raised && variant === "secondary" && "border border-[var(--border)] bg-[var(--surface-2)] hover:brightness-125",
        !raised && variant === "danger" && "bg-[var(--bad)] hover:brightness-110",
        !raised && variant === "good" && "bg-[var(--good)] hover:brightness-110",
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
    <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface-2)] p-3 shadow-[inset_0_1px_0_rgba(255,255,255,0.05)]">
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
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/65 p-3 backdrop-blur-md" onClick={onClose}>
      <div className={clsx("glass animate-rise max-h-[92vh] w-full overflow-auto rounded-3xl", wide ? "max-w-4xl" : "max-w-lg")}
        onClick={(e) => e.stopPropagation()} role="dialog" aria-modal>
        <header className="flex items-center justify-between border-b border-[var(--border)] px-5 py-3">
          <h3 className="font-display text-2xl font-bold">{title}</h3>
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

export const inputCls = "rounded-xl border border-[var(--border)] bg-[var(--surface-2)] px-3 py-2 text-sm outline-none transition focus:border-[var(--accent)] focus:ring-2 focus:ring-[color-mix(in_oklab,var(--accent)_30%,transparent)]";

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
    <div className="flex flex-wrap gap-1 rounded-2xl border border-[var(--border)] bg-[var(--surface-2)] p-1">
      {items.map((it) => (
        <button key={it.id} onClick={() => onChange(it.id)}
          className={clsx("rounded-xl px-3.5 py-1.5 text-sm font-semibold transition",
            value === it.id ? "bg-[var(--accent)] text-white shadow-[0_6px_16px_-8px_var(--accent)]" : "text-[var(--muted)] hover:text-[var(--text)]")}>
          {it.label}
        </button>
      ))}
    </div>
  );
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-2xl border border-dashed border-[var(--border)] p-8 text-center">
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
        <h1 className="font-display text-3xl font-extrabold tracking-wide uppercase md:text-4xl">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-[var(--muted)]">{subtitle}</p>}
      </div>
      <div className="flex flex-wrap items-center gap-2">{actions}</div>
    </div>
  );
}

/** Leans an element towards the pointer (CSS 3D, see the .tilt class). */
export function useTilt<T extends HTMLElement>(max = 8) {
  return {
    onPointerMove: (e: React.PointerEvent<T>) => {
      if (e.pointerType !== "mouse") return;
      const r = e.currentTarget.getBoundingClientRect();
      const px = (e.clientX - r.left) / r.width - 0.5;
      const py = (e.clientY - r.top) / r.height - 0.5;
      e.currentTarget.style.setProperty("--ry", `${(px * max).toFixed(2)}deg`);
      e.currentTarget.style.setProperty("--rx", `${(-py * max).toFixed(2)}deg`);
    },
    onPointerLeave: (e: React.PointerEvent<T>) => {
      e.currentTarget.style.setProperty("--ry", "0deg");
      e.currentTarget.style.setProperty("--rx", "0deg");
    },
  };
}

/** Round logo: a stylised dartboard in lava colours. */
export function Logo({ size = 40 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" aria-hidden>
      <defs>
        <radialGradient id="lg-lava" cx="35%" cy="30%" r="75%">
          <stop offset="0" stopColor="var(--accent-2)" />
          <stop offset="0.55" stopColor="var(--accent)" />
          <stop offset="1" stopColor="#7a0f1f" />
        </radialGradient>
      </defs>
      <circle cx="20" cy="20" r="19" fill="url(#lg-lava)" />
      <circle cx="20" cy="20" r="13" fill="none" stroke="rgba(0,0,0,.45)" strokeWidth="2.4" />
      <circle cx="20" cy="20" r="7" fill="none" stroke="rgba(0,0,0,.45)" strokeWidth="2.4" />
      <circle cx="20" cy="20" r="2.6" fill="#1b0b07" />
      <path d="M27 6 L21.2 18.6" stroke="#1b0b07" strokeWidth="2.2" strokeLinecap="round" />
      <path d="M27 6 l3.4 -1.2 M27 6 l1 -3.4" stroke="#fff" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}
