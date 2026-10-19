import clsx from "clsx";
import { ArrowLeft, KeyRound, Pencil, Wrench } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router";
import { Badge, Button, Card, Empty, ErrorNote, PageHeader } from "@/components/ui";
import { useAction, useApi } from "@/hooks/useApi";
import { api } from "@/lib/api";
import { modeName } from "@/lib/pl";
import { BoardForm, KeyModal } from "../forms";
import {
  ago, ALERT_TICKET_TITLE, dateOnly, dateTime, duration, n, STATUS_TONE, TICKET_STATUS, zl, type BoardDetail as BD, type Stats, type Ticket,
} from "../lib";
import { AlertLine, BoardStatus, Kpi, LevelDot } from "../ui";
import { DailyChart } from "./Dashboard";

const ENGINE: Record<string, string> = { idle: "gotowy", motion: "ruch", processing: "analiza", obstructed: "zasłonięta", stopped: "zatrzymany", starting: "uruchamianie" };

export default function BoardDetail() {
  const { id } = useParams();
  const { data: b, error, reload } = useApi<BD>(`/api/fleet/boards/${id}`, 15_000);
  const { data: stats } = useApi<Stats>(`/api/fleet/stats?board_id=${id}`);
  const { data: tickets } = useApi<Ticket[]>(`/api/fleet/tickets?board_id=${id}`);
  const [edit, setEdit] = useState(false);
  const [key, setKey] = useState<string | null>(null);
  const rotate = useAction(async () => {
    if (!confirm("Wygenerować nowy klucz? Tarcza przestanie się łączyć, dopóki nie wpiszesz nowego klucza w jej konfiguracji.")) return;
    setKey((await api.post<{ api_key: string }>(`/api/fleet/boards/${id}/rotate-key`)).api_key);
    reload();
  });
  if (error) return <ErrorNote error={error} />;
  if (!b) return null;
  const first = b.alerts.find((a) => a.severity !== "info");
  return (
    <div className="flex flex-col gap-5">
      <Link to="/operator/boards" className="inline-flex items-center gap-1 text-sm text-[var(--muted)] hover:text-[var(--text)]"><ArrowLeft size={16} /> Tarcze</Link>
      <PageHeader title={b.name}
        subtitle={<span className="inline-flex flex-wrap items-center gap-2">
          <LevelDot level={b.level} online={b.online} /> <BoardStatus b={b} />
          {b.venue_id ? <Link className="hover:text-[var(--accent)]" to={`/operator/venues/${b.venue_id}`}>{b.venue_name}, {b.venue_city}</Link> : "magazyn / bez lokalu"}
          {b.serial && <> · nr {b.serial}</>}
        </span>}
        actions={<>
          <Link to={`/operator/tickets?new=1&board=${b.id}${first ? `&title=${encodeURIComponent(ALERT_TICKET_TITLE[first.code] ?? "")}&priority=${first.severity === "bad" ? "high" : "normal"}` : ""}`}>
            <Button><Wrench size={16} /> Zgłoszenie</Button>
          </Link>
          <Button onClick={() => rotate.run()} disabled={rotate.busy}><KeyRound size={16} /> Nowy klucz</Button>
          <Button variant="primary" onClick={() => setEdit(true)}><Pencil size={16} /> Edytuj</Button>
        </>} />
      <ErrorNote error={rotate.error} />
      {b.alerts.length > 0 && (
        <div className="flex flex-col gap-1 rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-4">
          {b.alerts.map((a, i) => <AlertLine key={i} a={a} />)}
        </div>
      )}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Kpi label="Ostatni sygnał" value={<span className="text-3xl">{ago(b.last_seen_at)}</span>} sub={dateTime(b.last_seen_at)} tone={b.online ? "good" : "bad"} />
        <Kpi label="Silnik" value={<span className="text-3xl">{b.engine ? ENGINE[b.engine] ?? b.engine : "—"}</span>}
          sub={<>{b.online && b.active_game ? "trwa gra" : "brak gry"}{b.uptime_s ? ` · działa ${duration(b.uptime_s)}` : ""}</>} />
        <Kpi label="Gry (30 dni)" value={stats ? n(stats.totals.games) : "–"} sub={stats && zl(stats.totals.revenue)} />
        <Kpi label="Oprogramowanie" value={<span className="text-3xl">{b.version ?? "—"}</span>} sub={<>klucz {b.key_prefix}… · od {dateOnly(b.installed_at)}</>} />
      </div>
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        <div className="flex flex-col gap-4">
          {stats && <Card title="Gry dziennie (30 dni)"><DailyChart data={stats.daily} height={200} /></Card>}
          <Card title="Ostatnie gry">
            {!b.recent_games.length ? <Empty title="Ta tarcza nie zgłosiła jeszcze żadnej gry" /> : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="text-left text-xs text-[var(--muted)] uppercase">
                    <tr><th className="py-1">Start</th><th>Tryb</th><th>Gracze</th><th>Czas</th><th className="text-right">Cena</th></tr>
                  </thead>
                  <tbody>
                    {b.recent_games.map((g) => (
                      <tr key={g.game_id} className="border-t border-[var(--border)]">
                        <td className="py-1.5">{dateTime(g.started_at)}</td>
                        <td>{modeName(g.mode)} {g.status === "abandoned" && <Badge>przerwana</Badge>}</td>
                        <td>{g.players}</td>
                        <td>{duration(g.duration_s)}</td>
                        <td className="text-right tabular-nums">{zl(g.price, true)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </div>
        <div className="flex flex-col gap-4">
          <Card title="Kamery">
            {!b.cameras.length ? <div className="text-sm text-[var(--muted)]">Brak danych — tarcza jeszcze nie wysłała stanu.</div> : (
              <div className="grid grid-cols-3 gap-2">
                {b.cameras.map((c) => (
                  <div key={c.id} className={clsx("rounded-xl border p-3 text-center",
                    !c.connected ? "border-[var(--bad)]" : !c.calibrated ? "border-[var(--warn)]" : "border-[var(--border)]")}>
                    <div className="font-semibold">{c.id}</div>
                    <div className={clsx("text-sm", c.connected ? "text-[var(--good)]" : "text-[var(--bad)]")}>{c.connected ? "połączona" : "odłączona"}</div>
                    <div className={clsx("text-xs", c.calibrated ? "text-[var(--muted)]" : "text-[var(--warn)]")}>{c.calibrated ? "skalibrowana" : "bez kalibracji"}</div>
                    {c.fps != null && <div className="text-xs text-[var(--muted)]">{c.fps} fps</div>}
                  </div>
                ))}
              </div>
            )}
          </Card>
          <Card title="Zgłoszenia">
            {!tickets?.length ? <div className="text-sm text-[var(--muted)]">Brak zgłoszeń dla tej tarczy.</div> : (
              <ul className="flex flex-col gap-2 text-sm">
                {tickets.map((t) => (
                  <li key={t.id} className="flex items-center gap-2">
                    <Badge tone={STATUS_TONE[t.status]}>{TICKET_STATUS[t.status]}</Badge>
                    <Link to={`/operator/tickets?id=${t.id}`} className="min-w-0 flex-1 truncate hover:text-[var(--accent)]">{t.title}</Link>
                    <span className="text-xs text-[var(--muted)]">{ago(t.created_at)}</span>
                  </li>
                ))}
              </ul>
            )}
          </Card>
          {b.notes && <Card title="Notatki"><div className="text-sm whitespace-pre-wrap">{b.notes}</div></Card>}
        </div>
      </div>
      {edit && <BoardForm board={b} onClose={() => setEdit(false)} onSaved={() => { setEdit(false); reload(); }} />}
      {key && <KeyModal board={b} apiKey={key} onClose={() => setKey(null)} />}
    </div>
  );
}
