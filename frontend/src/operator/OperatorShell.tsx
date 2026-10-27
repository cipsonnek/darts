import clsx from "clsx";
import {
  Building2, ChartLine, KeyRound, LayoutDashboard, LogIn, LogOut, Menu, MonitorSmartphone, Wallet, Wrench, X, type LucideIcon,
} from "lucide-react";
import { lazy, Suspense, useCallback, useEffect, useState } from "react";
import { NavLink, Outlet } from "react-router";
import { Button, ErrorNote, Field, inputCls, Logo, Modal, Spinner } from "@/components/ui";
import { useApi } from "@/hooks/useApi";
import { api, ApiError } from "@/lib/api";
import type { Dashboard } from "./lib";

const Board3D = lazy(() => import("@/components/board/Board3D"));

interface User { id: number; username: string; display_name: string }

interface Item { to: string; label: string; icon: LucideIcon; badge?: (d: Dashboard) => number }

const NAV: Item[] = [
  { to: "/operator", label: "Pulpit", icon: LayoutDashboard },
  { to: "/operator/venues", label: "Lokale", icon: Building2 },
  { to: "/operator/boards", label: "Tarcze", icon: MonitorSmartphone, badge: (d) => d.alerts.filter((a) => a.severity === "bad").length },
  { to: "/operator/stats", label: "Statystyki", icon: ChartLine },
  { to: "/operator/settlements", label: "Rozliczenia", icon: Wallet },
  { to: "/operator/tickets", label: "Serwis", icon: Wrench, badge: (d) => d.open_tickets_total },
];

/** Operator panel: sign-in first, then the panel. */
export function OperatorApp() {
  const [user, setUser] = useState<User | null | undefined>(undefined);
  const check = useCallback(() => {
    api.get<{ user: User }>("/api/auth/me").then((r) => setUser(r.user)).catch(() => setUser(null));
  }, []);
  useEffect(() => {
    check();
    const out = () => setUser(null);
    window.addEventListener("dartsense:signed-out", out);
    return () => window.removeEventListener("dartsense:signed-out", out);
  }, [check]);
  if (user === undefined) return <div className="flex min-h-dvh items-center justify-center"><div className="backdrop" /><Spinner /></div>;
  if (!user) return <Login onDone={setUser} />;
  return <OperatorShell user={user} onSignOut={() => setUser(null)} />;
}

function Login({ onDone }: { onDone: (u: User) => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const r = await api.post<{ user: User }>("/api/auth/login", { username, password });
      onDone(r.user);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid min-h-dvh lg:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]">
      <div className="backdrop" />
      <div className="relative hidden items-center justify-center overflow-hidden lg:flex">
        <div className="pointer-events-none absolute inset-[18%] rounded-full bg-[var(--accent)] opacity-25 blur-[100px]" />
        <div className="aspect-square w-[min(80vh,720px)]">
          <Suspense fallback={null}><Board3D /></Suspense>
        </div>
      </div>
      <div className="flex items-center justify-center p-5">
        <form onSubmit={submit} className="glass animate-rise flex w-full max-w-md flex-col gap-5 rounded-3xl p-7 md:p-9">
          <div className="flex items-center gap-3">
            <Logo size={52} />
            <div>
              <div className="font-display text-3xl leading-none font-extrabold tracking-wide uppercase">DartSense</div>
              <div className="text-sm text-[var(--muted)]">Panel operatora</div>
            </div>
          </div>
          <div>
            <h1 className="font-display text-4xl font-extrabold tracking-wide uppercase">Zaloguj się</h1>
            <p className="text-[var(--muted)]">Lokale, tarcze, statystyki i rozliczenia w jednym miejscu.</p>
          </div>
          <Field label="Login">
            <input className={clsx(inputCls, "h-12 text-base")} autoComplete="username" autoFocus value={username} onChange={(e) => setUsername(e.target.value)} />
          </Field>
          <Field label="Hasło">
            <input className={clsx(inputCls, "h-12 text-base")} type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
          </Field>
          <ErrorNote error={error} />
          <Button size="lg" variant="primary" disabled={busy || !username || !password}>
            {busy ? <Spinner /> : <LogIn size={18} />} Zaloguj
          </Button>
        </form>
      </div>
    </div>
  );
}

function PasswordModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [oldPw, setOld] = useState("");
  const [newPw, setNew] = useState("");
  const [again, setAgain] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [done, setDone] = useState(false);
  const mismatch = again.length > 0 && again !== newPw;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.post("/api/auth/password", { old_password: oldPw, new_password: newPw });
      setDone(true);
      setOld(""); setNew(""); setAgain("");
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal open={open} onClose={() => { setDone(false); onClose(); }} title="Zmień hasło">
      {done ? (
        <div className="flex flex-col gap-4">
          <p>Hasło zmienione. Na innych urządzeniach trzeba zalogować się ponownie.</p>
          <Button variant="primary" onClick={() => { setDone(false); onClose(); }}>OK</Button>
        </div>
      ) : (
        <form onSubmit={submit} className="flex flex-col gap-4">
          <Field label="Obecne hasło"><input className={inputCls} type="password" autoComplete="current-password" value={oldPw} onChange={(e) => setOld(e.target.value)} /></Field>
          <Field label="Nowe hasło" hint="Co najmniej 8 znaków."><input className={inputCls} type="password" autoComplete="new-password" value={newPw} onChange={(e) => setNew(e.target.value)} /></Field>
          <Field label="Powtórz nowe hasło"><input className={inputCls} type="password" autoComplete="new-password" value={again} onChange={(e) => setAgain(e.target.value)} /></Field>
          {mismatch && <div className="text-sm text-[var(--bad)]">Hasła się różnią.</div>}
          <ErrorNote error={error} />
          <Button variant="primary" disabled={busy || !oldPw || newPw.length < 8 || again !== newPw}>Zmień hasło</Button>
        </form>
      )}
    </Modal>
  );
}

function OperatorShell({ user, onSignOut }: { user: User; onSignOut: () => void }) {
  const [open, setOpen] = useState(false);
  const [pw, setPw] = useState(false);
  // Polled for the badges; pages load their own data.
  const { data: dash } = useApi<Dashboard>("/api/fleet/dashboard", 60_000);
  const close = () => setOpen(false);
  async function signOut() {
    await api.post("/api/auth/logout").catch((e) => { if (!(e instanceof ApiError)) throw e; });
    onSignOut();
  }
  return (
    <div className="flex min-h-dvh">
      <div className="backdrop" />
      <aside className={clsx("fixed inset-y-0 left-0 z-40 flex w-72 shrink-0 flex-col border-r border-[var(--border)] bg-[color-mix(in_oklab,var(--surface)_92%,transparent)] backdrop-blur-xl transition-transform md:sticky md:top-0 md:h-dvh md:translate-x-0",
        open ? "translate-x-0" : "-translate-x-full")}>
        <div className="flex items-center gap-3 px-5 py-5">
          <Logo size={44} />
          <div className="min-w-0 flex-1">
            <div className="truncate font-display text-2xl leading-none font-extrabold tracking-wide uppercase">DartSense</div>
            <div className="truncate text-xs text-[var(--muted)]">Panel operatora</div>
          </div>
          <button className="rounded-lg p-1 text-[var(--muted)] md:hidden" onClick={close} aria-label="Zamknij menu"><X size={20} /></button>
        </div>
        <nav className="flex flex-1 flex-col gap-1 overflow-y-auto px-3 pb-4">
          {NAV.map((n) => {
            const Icon = n.icon;
            const badge = dash && n.badge ? n.badge(dash) : 0;
            return (
              <NavLink key={n.to} to={n.to} end={n.to === "/operator"} onClick={close}
                className={({ isActive }) => clsx("flex items-center gap-3 rounded-2xl px-3.5 py-3 font-display text-lg font-bold tracking-wide uppercase transition",
                  isActive ? "bg-[var(--accent)] text-white shadow-[0_10px_24px_-12px_var(--accent)]"
                    : "text-[var(--muted)] hover:bg-[var(--surface-2)] hover:text-[var(--text)]")}>
                <Icon size={20} />
                <span className="flex-1">{n.label}</span>
                {badge > 0 && <span className="rounded-full bg-[var(--bad)] px-2 font-sans text-xs font-bold text-white">{badge}</span>}
              </NavLink>
            );
          })}
        </nav>
        <div className="m-3 rounded-2xl border border-[var(--border)] bg-[var(--surface-2)] p-3">
          <div className="truncate font-semibold">{user.display_name}</div>
          <div className="truncate text-xs text-[var(--muted)]">{user.username}</div>
          <div className="mt-2 flex gap-1.5">
            <Button size="sm" onClick={() => setPw(true)}><KeyRound size={14} /> Hasło</Button>
            <Button size="sm" variant="ghost" onClick={signOut}><LogOut size={14} /> Wyloguj</Button>
          </div>
        </div>
      </aside>
      {open && <div className="fixed inset-0 z-30 bg-black/60 md:hidden" onClick={close} />}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 flex items-center gap-3 border-b border-[var(--border)] bg-[color-mix(in_oklab,var(--bg)_75%,transparent)] px-4 py-2.5 backdrop-blur-xl md:hidden">
          <button className="rounded-lg p-1" onClick={() => setOpen(true)} aria-label="Menu"><Menu size={22} /></button>
          <Logo size={30} />
          <div className="font-display text-xl font-bold tracking-wide uppercase">Panel operatora</div>
        </header>
        <main className="mx-auto w-full max-w-[1700px] flex-1 p-3 md:p-6">
          <Outlet />
        </main>
      </div>
      <PasswordModal open={pw} onClose={() => setPw(false)} />
    </div>
  );
}
