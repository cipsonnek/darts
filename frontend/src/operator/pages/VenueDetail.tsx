import { ArrowLeft, Mail, MapPin, Pencil, Phone, Plus, Clock } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router";
import { Badge, Button, Card, Empty, ErrorNote, PageHeader } from "@/components/ui";
import { useAction, useApi } from "@/hooks/useApi";
import { api } from "@/lib/api";
import { BoardForm, VenueForm } from "../forms";
import {
  ago, n, STATUS_TONE, TICKET_STATUS, VENUE_KIND, zl, type Stats, type Ticket, type VenueDetail as VD, type VenueRow,
} from "../lib";
import { AlertLine, BoardStatus, Kpi, LevelDot } from "../ui";
import { VenueMap } from "../VenueMap";
import { DailyChart } from "./Dashboard";
import { Heatmap } from "./Stats";

export default function VenueDetail() {
  const { id } = useParams();
  const { data: v, error, reload } = useApi<VD>(`/api/fleet/venues/${id}`, 30_000);
  const { data: stats } = useApi<Stats>(`/api/fleet/stats?venue_id=${id}`);
  const { data: tickets } = useApi<Ticket[]>(`/api/fleet/tickets?venue_id=${id}`);
  const [edit, setEdit] = useState(false);
  const [addBoard, setAddBoard] = useState(false);
  const toggle = useAction(async () => { await api.patch(`/api/fleet/venues/${id}`, { active: !v?.active }); reload(); });
  if (error) return <ErrorNote error={error} />;
  if (!v) return null;
  const row: VenueRow = { ...v, boards: v.board_list.length, boards_online: v.board_list.filter((b) => b.online).length,
    alerts: 0, games_30d: stats?.totals.games ?? 0, revenue_30d: stats?.totals.revenue ?? 0, open_tickets: 0 };
  const t = stats?.totals;
  return (
    <div className="flex flex-col gap-5">
      <Link to="/operator/venues" className="inline-flex items-center gap-1 text-sm text-[var(--muted)] hover:text-[var(--text)]"><ArrowLeft size={16} /> Lokale</Link>
      <PageHeader title={v.name}
        subtitle={<>{VENUE_KIND[v.kind] ?? v.kind} · {v.address}, {v.postal_code} {v.city} {!v.active && <Badge tone="warn" className="ml-1">nieaktywny</Badge>}</>}
        actions={<>
          <Button onClick={() => toggle.run()} disabled={toggle.busy}>{v.active ? "Dezaktywuj" : "Aktywuj"}</Button>
          <Button variant="primary" onClick={() => setEdit(true)}><Pencil size={16} /> Edytuj</Button>
        </>} />
      <ErrorNote error={toggle.error} />
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Kpi label="Gry (30 dni)" value={t ? n(t.games) : "–"} sub={t && `${t.games_per_day.toLocaleString("pl-PL")} dziennie`} />
        <Kpi label="Przychód (30 dni)" value={t ? zl(t.revenue) : "–"} />
        <Kpi label={`Dla lokalu (${v.venue_share_pct}%)`} value={t ? zl(t.venue_share) : "–"} />
        <Kpi label="Dla operatora" value={t ? zl(t.operator_share) : "–"} tone="good" />
      </div>
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
        <div className="flex flex-col gap-4">
          <Card title={`Tarcze (${v.board_list.length})`} actions={<Button size="sm" onClick={() => setAddBoard(true)}><Plus size={14} /> Dodaj tarczę</Button>}>
            {!v.board_list.length ? <Empty title="Brak tarcz w tym lokalu" /> : (
              <ul className="flex flex-col divide-y divide-[var(--border)]">
                {v.board_list.map((b) => (
                  <li key={b.id} className="flex flex-wrap items-center gap-3 py-2.5">
                    <LevelDot level={b.level} online={b.online} />
                    <div className="min-w-0 flex-1">
                      <Link to={`/operator/boards/${b.id}`} className="font-semibold hover:text-[var(--accent)]">{b.name}</Link>
                      <span className="text-sm text-[var(--muted)]"> · ostatni sygnał {ago(b.last_seen_at)}{b.active_game && b.online ? " · trwa gra" : ""}</span>
                      <div className="flex flex-wrap gap-x-3">{b.alerts.map((a, i) => <AlertLine key={i} a={a} />)}</div>
                    </div>
                    <BoardStatus b={b} />
                  </li>
                ))}
              </ul>
            )}
          </Card>
          {stats && (
            <Card title="Gry i przychód — ostatnie 30 dni"><DailyChart data={stats.daily} height={220} /></Card>
          )}
          {stats && <Card title="Kiedy się gra (30 dni)"><Heatmap data={stats.heatmap} /></Card>}
        </div>
        <div className="flex flex-col gap-4">
          <Card title="Kontakt i warunki">
            <div className="flex flex-col gap-2 text-sm">
              <div className="font-semibold">{v.contact_name || "—"}</div>
              {v.phone && <a href={`tel:${v.phone}`} className="flex items-center gap-2 hover:text-[var(--accent)]"><Phone size={15} /> {v.phone}</a>}
              {v.email && <a href={`mailto:${v.email}`} className="flex items-center gap-2 hover:text-[var(--accent)]"><Mail size={15} /> {v.email}</a>}
              {v.opening_hours && <div className="flex items-center gap-2"><Clock size={15} /> {v.opening_hours}</div>}
              <div className="flex items-center gap-2"><MapPin size={15} /> {v.lat != null ? `${v.lat}, ${v.lng}` : "brak lokalizacji"}</div>
              <div className="mt-2 grid grid-cols-2 gap-2 rounded-xl bg-[var(--surface-2)] p-3">
                <div><div className="text-xs text-[var(--muted)]">Cena gry</div><div className="font-score text-2xl font-bold">{zl(v.price_per_game, true)}</div></div>
                <div><div className="text-xs text-[var(--muted)]">Lokal / operator</div><div className="font-score text-2xl font-bold">{v.venue_share_pct}% / {100 - v.venue_share_pct}%</div></div>
              </div>
              {v.notes && <div className="mt-1 whitespace-pre-wrap text-[var(--muted)]">{v.notes}</div>}
            </div>
          </Card>
          <Card pad={false}><VenueMap venues={[row]} className="h-64 rounded-2xl" /></Card>
          <Card title="Zgłoszenia serwisowe" actions={<Link className="text-sm font-semibold text-[var(--accent)]" to={`/operator/tickets?new=1&venue=${v.id}`}>Nowe</Link>}>
            {!tickets?.length ? <div className="text-sm text-[var(--muted)]">Brak zgłoszeń.</div> : (
              <ul className="flex flex-col gap-2 text-sm">
                {tickets.slice(0, 8).map((tk) => (
                  <li key={tk.id} className="flex items-center gap-2">
                    <Badge tone={STATUS_TONE[tk.status]}>{TICKET_STATUS[tk.status]}</Badge>
                    <Link to={`/operator/tickets?id=${tk.id}`} className="min-w-0 flex-1 truncate hover:text-[var(--accent)]">{tk.title}</Link>
                    <span className="text-xs text-[var(--muted)]">{ago(tk.created_at)}</span>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      </div>
      {edit && <VenueForm venue={v} onClose={() => setEdit(false)} onSaved={() => { setEdit(false); reload(); }} />}
      {addBoard && <BoardForm venueId={v.id} onClose={() => setAddBoard(false)} onSaved={() => { setAddBoard(false); reload(); }} />}
    </div>
  );
}
