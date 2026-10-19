import { useState } from "react";
import { Link } from "react-router";
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Card, Empty, ErrorNote, inputCls, PageHeader, Tabs } from "@/components/ui";
import { useApi } from "@/hooks/useApi";
import { modeName } from "@/lib/pl";
import { duration, isoDay, n, WEEKDAYS, zl, type Stats as S, type VenueRow } from "../lib";
import { Kpi } from "../ui";
import { DailyChart } from "./Dashboard";

/** Games by weekday (rows) and local hour (columns). */
export function Heatmap({ data }: { data: number[][] }) {
  const max = Math.max(1, ...data.flat());
  return (
    <div className="overflow-x-auto">
      <div className="grid min-w-[560px] gap-0.5" style={{ gridTemplateColumns: "28px repeat(24, minmax(0, 1fr))" }}>
        <div />
        {Array.from({ length: 24 }, (_, h) => (
          <div key={h} className="text-center text-[10px] text-[var(--muted)]">{h % 3 === 0 ? h : ""}</div>
        ))}
        {data.map((row, d) => (
          <div key={d} className="contents">
            <div className="self-center text-xs text-[var(--muted)]">{WEEKDAYS[d]}</div>
            {row.map((v, h) => (
              <div key={h} title={`${WEEKDAYS[d]} ${h}:00–${h + 1}:00 · ${v} gier`} className="aspect-square rounded-[3px]"
                style={{ background: v ? `color-mix(in oklab, var(--accent) ${Math.round(12 + 88 * (v / max))}%, var(--surface-2))` : "var(--surface-2)" }} />
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

type Preset = "7" | "30" | "90" | "365" | "custom";

export default function Stats() {
  const { data: venues } = useApi<VenueRow[]>("/api/fleet/venues");
  const [preset, setPreset] = useState<Preset>("30");
  const [from, setFrom] = useState(isoDay(new Date(Date.now() - 29 * 864e5)));
  const [to, setTo] = useState(isoDay(new Date()));
  const [venue, setVenue] = useState("");
  const range = preset === "custom" ? { from, to } : { from: isoDay(new Date(Date.now() - (Number(preset) - 1) * 864e5)), to: isoDay(new Date()) };
  const q = new URLSearchParams({ ...range, ...(venue ? { venue_id: venue } : {}) });
  const { data: s, error } = useApi<S>(`/api/fleet/stats?${q}`);
  const t = s?.totals;

  return (
    <div className="flex flex-col gap-5">
      <PageHeader title="Statystyki" subtitle="Ruch i przychody całej sieci albo jednego lokalu." />
      <div className="flex flex-wrap items-center gap-3">
        <Tabs value={preset} onChange={setPreset} items={[
          { id: "7", label: "7 dni" }, { id: "30", label: "30 dni" }, { id: "90", label: "90 dni" }, { id: "365", label: "Rok" }, { id: "custom", label: "Zakres" },
        ]} />
        {preset === "custom" && (
          <>
            <input type="date" className={inputCls} value={from} max={to} onChange={(e) => setFrom(e.target.value)} />
            <span className="text-[var(--muted)]">–</span>
            <input type="date" className={inputCls} value={to} min={from} onChange={(e) => setTo(e.target.value)} />
          </>
        )}
        <select className={inputCls} value={venue} onChange={(e) => setVenue(e.target.value)}>
          <option value="">Cała sieć</option>
          {venues?.map((v) => <option key={v.id} value={v.id}>{v.name} ({v.city})</option>)}
        </select>
      </div>
      <ErrorNote error={error} />
      {t && s && (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-3 2xl:grid-cols-6">
            <Kpi label="Gry" value={n(t.games)} sub={`${t.games_per_day.toLocaleString("pl-PL")} dziennie`} />
            <Kpi label="Przychód" value={zl(t.revenue)} />
            <Kpi label="Dla lokali" value={zl(t.venue_share)} />
            <Kpi label="Dla operatora" value={zl(t.operator_share)} tone="good" />
            <Kpi label="Średni czas gry" value={duration(t.avg_duration_s)} sub={`${t.avg_players.toLocaleString("pl-PL")} gracza średnio`} />
            <Kpi label="Rzucone lotki" value={n(t.darts)} />
          </div>
          {t.games === 0 ? <Empty title="Brak gier w tym okresie" /> : (
            <>
              <Card title="Gry i przychód dziennie"><DailyChart data={s.daily} /></Card>
              <div className="grid gap-4 xl:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
                <Card title="Kiedy się gra (dzień tygodnia × godzina)"><Heatmap data={s.heatmap} /></Card>
                <Card title="Tryby gier">
                  <div style={{ height: 240 }}>
                    <ResponsiveContainer>
                      <BarChart data={s.modes.map((m) => ({ ...m, name: modeName(m.mode) }))} layout="vertical" margin={{ left: 20, right: 16 }}>
                        <XAxis type="number" stroke="var(--muted)" fontSize={12} allowDecimals={false} />
                        <YAxis type="category" dataKey="name" stroke="var(--muted)" fontSize={13} width={110} />
                        <Tooltip contentStyle={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 12 }}
                          formatter={(v) => [`${n(Number(v))} (${Math.round((Number(v) / t.games) * 100)}%)`, "Gry"]} cursor={{ fill: "var(--surface-2)" }} />
                        <Bar dataKey="games" fill="var(--accent)" radius={[0, 6, 6, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </Card>
              </div>
              <div className="grid gap-4 xl:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
                {!venue && (
                  <Card title="Ranking lokali">
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead className="text-left text-xs text-[var(--muted)] uppercase">
                          <tr><th className="py-1">Lokal</th><th className="text-right">Gry</th><th className="text-right">Przychód</th><th className="text-right">Dla lokalu</th><th className="w-40" /></tr>
                        </thead>
                        <tbody>
                          {s.by_venue.map((v, i) => (
                            <tr key={v.venue_id ?? i} className="border-t border-[var(--border)]">
                              <td className="py-2">{v.venue_id ? <Link className="font-semibold hover:text-[var(--accent)]" to={`/operator/venues/${v.venue_id}`}>{v.name}</Link> : "Bez lokalu"}
                                <span className="text-[var(--muted)]"> · {v.city}</span></td>
                              <td className="text-right tabular-nums">{n(v.games)}</td>
                              <td className="text-right font-semibold tabular-nums">{zl(v.revenue)}</td>
                              <td className="text-right tabular-nums text-[var(--muted)]">{zl(v.venue_share)}</td>
                              <td className="pl-3">
                                <div className="h-2 rounded-full bg-[var(--surface-2)]">
                                  <div className="h-2 rounded-full bg-[var(--accent)]" style={{ width: `${(v.revenue / (s.by_venue[0]?.revenue || 1)) * 100}%` }} />
                                </div>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </Card>
                )}
                <Card title="Najczęściej używane tarcze">
                  <ul className="flex flex-col gap-1.5 text-sm">
                    {s.by_board.map((b) => (
                      <li key={b.board_id} className="flex items-center gap-2">
                        <Link className="font-semibold hover:text-[var(--accent)]" to={`/operator/boards/${b.board_id}`}>{b.name}</Link>
                        <span className="min-w-0 flex-1 truncate text-[var(--muted)]">{b.venue_name}</span>
                        <span className="tabular-nums">{n(b.games)}</span>
                      </li>
                    ))}
                  </ul>
                </Card>
              </div>
            </>
          )}
        </>
      )}
    </div>
  );
}
