import { Link } from "react-router";
import { Bar, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Card, Empty, ErrorNote, PageHeader } from "@/components/ui";
import { useApi } from "@/hooks/useApi";
import { ALERT_TICKET_TITLE, n, pctChange, TICKET_PRIORITY, zl, type Dashboard as Dash, type VenueRow } from "../lib";
import { AlertLine, Kpi } from "../ui";
import { VenueMap } from "../VenueMap";

export function DailyChart({ data, height = 260 }: { data: { date: string; games: number; revenue: number }[]; height?: number }) {
  return (
    <div style={{ height }}>
      <ResponsiveContainer>
        <ComposedChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -8 }}>
          <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="date" stroke="var(--muted)" tickFormatter={(d: string) => d.slice(8, 10) + "." + d.slice(5, 7)} minTickGap={24} fontSize={12} />
          <YAxis yAxisId="g" stroke="var(--muted)" fontSize={12} allowDecimals={false} />
          <YAxis yAxisId="r" orientation="right" stroke="var(--muted)" fontSize={12} tickFormatter={(v: number) => `${Math.round(v / 100) / 10}k`} />
          <Tooltip contentStyle={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 12 }}
            labelFormatter={(d) => new Date(String(d)).toLocaleDateString("pl-PL", { weekday: "long", day: "numeric", month: "long" })}
            formatter={(v, name) => (name === "revenue" ? [zl(Number(v)), "Przychód"] : [n(Number(v)), "Gry"])} />
          <Bar yAxisId="g" dataKey="games" fill="var(--accent)" radius={[4, 4, 0, 0]} opacity={0.85} isAnimationActive={false} />
          <Line yAxisId="r" dataKey="revenue" stroke="var(--good)" strokeWidth={2.5} dot={false} type="monotone" isAnimationActive={false} />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

export default function Dashboard() {
  const { data: d, error } = useApi<Dash>("/api/fleet/dashboard", 30_000);
  const { data: venues } = useApi<VenueRow[]>("/api/fleet/venues", 60_000);
  if (error) return <ErrorNote error={error} />;
  if (!d) return null;
  const l = d.last_30d;
  return (
    <div className="flex flex-col gap-5">
      <PageHeader title="Pulpit" subtitle={`Sieć: ${d.venues_active} lokali, ${d.boards.total} tarcz. Dane z ostatnich 30 dni.`} />
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-3 2xl:grid-cols-6">
        <Kpi label="Tarcze online" value={`${d.boards.online}/${d.boards.total}`} tone={d.boards.offline ? "warn" : "good"}
          sub={<>{d.boards.playing} w grze · {d.boards.offline} offline</>} />
        <Kpi label="Gry dziś" value={n(d.today.games)} sub={zl(d.today.revenue)} />
        <Kpi label="Gry (30 dni)" value={n(l.games)} change={pctChange(l.games, d.prev_30d.games)} sub="vs poprzednie 30 dni" />
        <Kpi label="Przychód (30 dni)" value={zl(l.revenue)} change={pctChange(l.revenue, d.prev_30d.revenue)} sub="vs poprzednie 30 dni" />
        <Kpi label="Dla operatora" value={zl(l.operator_share)} sub={<>lokale: {zl(l.venue_share)}</>} tone="good" />
        <Kpi label="Otwarte zgłoszenia" value={d.open_tickets_total} tone={d.open_tickets.critical ? "bad" : d.open_tickets.high ? "warn" : undefined}
          sub={Object.entries(d.open_tickets).map(([p, c]) => `${TICKET_PRIORITY[p] ?? p}: ${c}`).join(" · ") || "brak"} />
      </div>
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
        <Card title="Gry i przychód dziennie">
          <DailyChart data={d.daily} />
          <div className="mt-2 flex gap-4 text-xs text-[var(--muted)]">
            <span><span className="mr-1 inline-block h-2 w-3 rounded-sm bg-[var(--accent)]" />gry</span>
            <span><span className="mr-1 inline-block h-0.5 w-3 bg-[var(--good)] align-middle" />przychód</span>
          </div>
        </Card>
        <Card title={`Alerty (${d.alerts.length})`}>
          {!d.alerts.length ? <Empty title="Wszystko działa">Żadna tarcza nie zgłasza problemów.</Empty> : (
            <ul className="flex max-h-80 flex-col divide-y divide-[var(--border)] overflow-y-auto">
              {d.alerts.map((a, i) => (
                <li key={i} className="flex items-center gap-3 py-2">
                  <div className="min-w-0 flex-1">
                    <Link to={`/operator/boards/${a.board_id}`} className="font-semibold hover:text-[var(--accent)]">{a.board_name}</Link>
                    <span className="text-sm text-[var(--muted)]"> · {a.venue_name ?? "bez lokalu"}</span>
                    <div><AlertLine a={a} /></div>
                  </div>
                  <Link className="shrink-0 text-sm font-semibold text-[var(--accent)]"
                    to={`/operator/tickets?new=1&board=${a.board_id}&title=${encodeURIComponent(ALERT_TICKET_TITLE[a.code] ?? a.code)}&priority=${a.severity === "bad" ? "high" : "normal"}`}>
                    Zgłoszenie
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)]">
        <Card title="Najlepsze lokale (30 dni)">
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-[var(--muted)] uppercase"><tr><th className="py-1">Lokal</th><th className="text-right">Gry</th><th className="text-right">Przychód</th></tr></thead>
            <tbody>
              {d.top_venues.map((v, i) => (
                <tr key={v.venue_id ?? i} className="border-t border-[var(--border)]">
                  <td className="py-2">
                    <span className="mr-2 font-score text-lg font-bold text-[var(--muted)]">{i + 1}.</span>
                    {v.venue_id ? <Link className="font-semibold hover:text-[var(--accent)]" to={`/operator/venues/${v.venue_id}`}>{v.name}</Link> : "—"}
                    <span className="text-[var(--muted)]"> · {v.city}</span>
                  </td>
                  <td className="text-right tabular-nums">{n(v.games)}</td>
                  <td className="text-right font-semibold tabular-nums">{zl(v.revenue)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
        <Card title="Mapa lokali" pad={false}>
          {venues && <VenueMap venues={venues} className="h-80 rounded-b-2xl" />}
        </Card>
      </div>
    </div>
  );
}
