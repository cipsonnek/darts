import clsx from "clsx";
import { Plus, Search } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router";
import { Badge, Button, Card, Empty, ErrorNote, inputCls, PageHeader, Tabs } from "@/components/ui";
import { useApi } from "@/hooks/useApi";
import { BoardForm } from "../forms";
import { ago, n, type Board } from "../lib";
import { AlertLine, BoardStatus, LevelDot } from "../ui";

type Filter = "all" | "problems" | "offline" | "maintenance";

export default function Boards() {
  const { data: boards, error, reload } = useApi<Board[]>("/api/fleet/boards", 20_000);
  const [filter, setFilter] = useState<Filter>("all");
  const [q, setQ] = useState("");
  const [adding, setAdding] = useState(false);
  const nav = useNavigate();
  const live = (boards ?? []).filter((b) => b.status !== "retired");
  const count = (f: Filter) => live.filter((b) => match(b, f)).length;
  function match(b: Board, f: Filter) {
    if (f === "problems") return b.level === "bad" || b.level === "warn";
    if (f === "offline") return b.status === "active" && !b.online;
    if (f === "maintenance") return b.status === "maintenance";
    return true;
  }
  const shown = (filter === "all" ? boards ?? [] : live).filter((b) => match(b, filter)
    && (!q || `${b.name} ${b.serial} ${b.venue_name ?? ""} ${b.venue_city ?? ""}`.toLowerCase().includes(q.toLowerCase())));

  return (
    <div>
      <PageHeader title="Tarcze" subtitle="Stan wszystkich tarcz: połączenie, kamery, kalibracja, wersja oprogramowania."
        actions={<Button variant="primary" onClick={() => setAdding(true)}><Plus size={16} /> Dodaj tarczę</Button>} />
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <Tabs value={filter} onChange={setFilter} items={[
          { id: "all", label: `Wszystkie (${boards?.length ?? 0})` }, { id: "problems", label: `Problemy (${count("problems")})` },
          { id: "offline", label: `Offline (${count("offline")})` }, { id: "maintenance", label: `Serwis (${count("maintenance")})` },
        ]} />
        <div className="relative min-w-60 flex-1 sm:max-w-sm">
          <Search size={16} className="absolute top-1/2 left-3 -translate-y-1/2 text-[var(--muted)]" />
          <input className={clsx(inputCls, "w-full pl-9")} value={q} onChange={(e) => setQ(e.target.value)} placeholder="Szukaj tarczy, lokalu, miasta…" />
        </div>
      </div>
      <ErrorNote error={error} />
      <Card pad={false}>
        {!shown.length ? <div className="p-4"><Empty title="Brak tarcz w tym widoku" /></div> : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-xs text-[var(--muted)] uppercase">
                <tr className="[&>th]:px-3 [&>th]:py-2.5">
                  <th>Tarcza</th><th>Lokal</th><th>Stan</th><th>Ostatni sygnał</th><th>Kamery</th><th>Wersja</th><th className="text-right">Gry 30 dni</th>
                </tr>
              </thead>
              <tbody>
                {shown.map((b) => (
                  <tr key={b.id} onClick={() => nav(`/operator/boards/${b.id}`)}
                    className={clsx("cursor-pointer border-t border-[var(--border)] align-top hover:bg-[var(--surface-2)] [&>td]:px-3 [&>td]:py-2.5", b.status === "retired" && "opacity-50")}>
                    <td>
                      <div className="flex items-center gap-2"><LevelDot level={b.level} online={b.online} />
                        <Link to={`/operator/boards/${b.id}`} className="font-semibold">{b.name}</Link></div>
                      {b.serial && <div className="pl-4.5 text-xs text-[var(--muted)]">{b.serial}</div>}
                    </td>
                    <td>{b.venue_name ? <>{b.venue_name}<div className="text-xs text-[var(--muted)]">{b.venue_city}</div></> : <span className="text-[var(--muted)]">magazyn</span>}</td>
                    <td>
                      <div className="flex flex-wrap items-center gap-1.5"><BoardStatus b={b} />{b.online && b.active_game && <Badge tone="accent">gra</Badge>}</div>
                      <div className="mt-1 flex flex-col">{b.alerts.filter((a) => a.code !== "maintenance").map((a, i) => <AlertLine key={i} a={a} />)}</div>
                    </td>
                    <td className="whitespace-nowrap text-[var(--muted)]">{ago(b.last_seen_at)}</td>
                    <td>
                      {b.cameras.length ? (
                        <div className="flex gap-1">
                          {b.cameras.map((c) => (
                            <span key={c.id} title={`${c.id}: ${c.connected ? "połączona" : "odłączona"}${c.connected && !c.calibrated ? ", bez kalibracji" : ""}`}
                              className={clsx("grid h-6 w-6 place-items-center rounded-md text-[10px] font-bold",
                                !c.connected ? "bg-[var(--bad)] text-white" : !c.calibrated ? "bg-[var(--warn)] text-black" : "bg-[color-mix(in_oklab,var(--good)_25%,transparent)] text-[var(--good)]")}>
                              {c.id.replace(/\D/g, "") || "?"}
                            </span>
                          ))}
                        </div>
                      ) : <span className="text-[var(--muted)]">—</span>}
                    </td>
                    <td className="text-[var(--muted)]">{b.version ?? "—"}</td>
                    <td className="text-right tabular-nums">{n(b.games_30d ?? 0)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
      {adding && <BoardForm onClose={() => setAdding(false)} onSaved={() => { setAdding(false); reload(); }} />}
    </div>
  );
}
