import clsx from "clsx";
import { Plus, Search } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router";
import { Badge, Button, Card, Empty, ErrorNote, inputCls, PageHeader, Toggle } from "@/components/ui";
import { useApi } from "@/hooks/useApi";
import { VenueForm } from "../forms";
import { n, VENUE_KIND, zl, type VenueRow } from "../lib";
import { VenueMap } from "../VenueMap";

export default function Venues() {
  const { data: venues, error, reload } = useApi<VenueRow[]>("/api/fleet/venues", 60_000);
  const [q, setQ] = useState("");
  const [city, setCity] = useState("");
  const [inactive, setInactive] = useState(false);
  const [adding, setAdding] = useState(false);
  const nav = useNavigate();
  const cities = useMemo(() => [...new Set(venues?.map((v) => v.city).filter(Boolean))].sort((a, b) => a.localeCompare(b, "pl")), [venues]);
  const shown = (venues ?? []).filter((v) => (inactive || v.active) && (!city || v.city === city)
    && (!q || `${v.name} ${v.address} ${v.city} ${v.contact_name}`.toLowerCase().includes(q.toLowerCase())));

  return (
    <div>
      <PageHeader title="Lokale" subtitle="Bary, puby i salony gier, w których stoją tarcze."
        actions={<Button variant="primary" onClick={() => setAdding(true)}><Plus size={16} /> Dodaj lokal</Button>} />
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div className="relative min-w-60 flex-1 sm:max-w-sm">
          <Search size={16} className="absolute top-1/2 left-3 -translate-y-1/2 text-[var(--muted)]" />
          <input className={clsx(inputCls, "w-full pl-9")} value={q} onChange={(e) => setQ(e.target.value)} placeholder="Szukaj nazwy, adresu, kontaktu…" />
        </div>
        <select className={inputCls} value={city} onChange={(e) => setCity(e.target.value)}>
          <option value="">Wszystkie miasta</option>
          {cities.map((c) => <option key={c}>{c}</option>)}
        </select>
        <Toggle checked={inactive} onChange={setInactive} label="Pokaż nieaktywne" />
      </div>
      <ErrorNote error={error} />
      <div className="grid gap-4 2xl:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
        <Card pad={false}>
          {!shown.length ? <div className="p-4"><Empty title="Brak lokali">Dodaj pierwszy lokal przyciskiem „Dodaj lokal”.</Empty></div> : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-left text-xs text-[var(--muted)] uppercase">
                  <tr className="[&>th]:px-3 [&>th]:py-2.5">
                    <th>Lokal</th><th>Tarcze</th><th className="text-right">Gry 30 dni</th><th className="text-right">Przychód 30 dni</th>
                    <th className="text-right">Stawka</th><th className="text-right">Zgłosz.</th>
                  </tr>
                </thead>
                <tbody>
                  {shown.map((v) => (
                    <tr key={v.id} onClick={() => nav(`/operator/venues/${v.id}`)}
                      className={clsx("cursor-pointer border-t border-[var(--border)] hover:bg-[var(--surface-2)] [&>td]:px-3 [&>td]:py-2.5", !v.active && "opacity-50")}>
                      <td>
                        <Link to={`/operator/venues/${v.id}`} className="font-semibold">{v.name}</Link>
                        <div className="text-xs text-[var(--muted)]">{VENUE_KIND[v.kind] ?? v.kind} · {v.address}, {v.city}</div>
                      </td>
                      <td>
                        {v.boards === 0 ? <span className="text-[var(--muted)]">—</span> : (
                          <span className={clsx("font-semibold", v.boards_online < v.boards ? "text-[var(--bad)]" : "text-[var(--good)]")}>
                            {v.boards_online}/{v.boards} online
                          </span>
                        )}
                        {v.alerts > 0 && <Badge tone="warn" className="ml-1.5">{v.alerts} alert</Badge>}
                      </td>
                      <td className="text-right tabular-nums">{n(v.games_30d)}</td>
                      <td className="text-right font-semibold tabular-nums">{zl(v.revenue_30d)}</td>
                      <td className="text-right whitespace-nowrap text-[var(--muted)]">{zl(v.price_per_game, true)} · {v.venue_share_pct}%</td>
                      <td className="text-right">{v.open_tickets > 0 ? <Badge tone="accent">{v.open_tickets}</Badge> : <span className="text-[var(--muted)]">—</span>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
        <Card pad={false} className="2xl:sticky 2xl:top-6 2xl:self-start">
          <VenueMap venues={shown} className="h-[420px] rounded-2xl 2xl:h-[calc(100dvh-180px)]" />
        </Card>
      </div>
      {adding && <VenueForm onClose={() => setAdding(false)} onSaved={(v) => { setAdding(false); reload(); nav(`/operator/venues/${v.id}`); }} />}
    </div>
  );
}
