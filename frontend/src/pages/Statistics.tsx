import { useSearchParams } from "react-router";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Dartboard } from "@/components/board/Dartboard";
import { Card, Empty, PageHeader, Stat } from "@/components/ui";
import { inputCls } from "@/components/ui";
import { useApi } from "@/hooks/useApi";
import { useBoardGeometry } from "@/hooks/useBoard";
import type { Player } from "@/lib/types";
import { dartLabel } from "@/lib/pl";

function pct(v: number | null | undefined) {
  return v == null ? "–" : `${(v * 100).toFixed(1)}%`;
}

export default function Statistics() {
  const [params, setParams] = useSearchParams();
  const { data: players } = useApi<Player[]>("/api/players");
  const { data: overview } = useApi<any>("/api/stats/overview");
  const pid = params.get("player") ?? players?.[0]?.id ?? null;
  const { data: st } = useApi<any>(pid ? `/api/stats/players/${pid}` : null);
  const { data: heat } = useApi<{ x_mm: number; y_mm: number }[]>(pid ? `/api/stats/heatmap?player_id=${pid}` : null);
  const board = useBoardGeometry();

  return (
    <div>
      <PageHeader title="Statystyki" subtitle="Liczone z rozegranych gier i wykrytych rzutów."
        actions={players?.length ? (
          <select className={inputCls} value={pid ?? ""} onChange={(e) => setParams({ player: e.target.value })}>
            {players.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        ) : null} />
      {overview && (
        <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-4">
          <Stat label="Gracze" value={overview.players} />
          <Stat label="Gry" value={overview.games} hint={`zakończone: ${overview.games_finished}`} />
          <Stat label="Wykryte rzuty" value={overview.detections} />
          <Stat label="Poprawione odczyty" value={pct(overview.corrected_rate)} hint={`niepewne: ${pct(overview.uncertain_rate)}`} />
        </div>
      )}
      {!pid ? <Empty title="Brak graczy" /> : !st ? null : st.darts_thrown === 0 ? (
        <Empty title={`${st.player.name} nie ma jeszcze rzutów`}>Statystyki pojawią się po rozegraniu gier.</Empty>
      ) : (
        <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_420px]">
          <div className="flex flex-col gap-4">
            <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
              <Stat label="Średnia (3 lotki)" value={st.x01.average_3_dart ?? "–"} />
              <Stat label="Średnia z pierwszych 9" value={st.x01.first_9_average ?? "–"} />
              <Stat label="Skuteczność zejść" value={pct(st.x01.checkout_pct)} hint={`lotki na zejście: ${st.x01.checkout_attempts}`} />
              <Stat label="Najwyższe zejście" value={st.x01.highest_checkout ?? "–"} />
              <Stat label="180s" value={st.x01.count_180} />
              <Stat label="140+" value={st.x01.count_140_plus} />
              <Stat label="100+" value={st.x01.count_100_plus} />
              <Stat label="Wygrane gry" value={`${st.games_won}/${st.games_finished}`} hint={pct(st.win_rate)} />
              <Stat label="Rzucone lotki" value={st.darts_thrown} />
              <Stat label="Trafione triple" value={pct(st.hit_distribution.triple_rate)} />
              <Stat label="Trafione double" value={pct(st.hit_distribution.double_rate)} />
              <Stat label="Cricket MPR" value={st.cricket.marks_per_round ?? "–"} />
            </div>
            <Card title="Średnia X01 w kolejnych grach">
              {st.average_history.length < 2 ? <div className="text-sm text-[var(--muted)]">Potrzeba co najmniej dwóch gier X01.</div> : (
                <div className="h-64">
                  <ResponsiveContainer>
                    <LineChart data={st.average_history.map((h: any, i: number) => ({ ...h, n: i + 1 }))}>
                      <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" />
                      <XAxis dataKey="n" stroke="var(--muted)" />
                      <YAxis stroke="var(--muted)" />
                      <Tooltip contentStyle={{ background: "var(--surface)", border: "1px solid var(--border)" }} formatter={(v) => [v, "Średnia"]} labelFormatter={(n) => `Gra ${n}`} />
                      <Line type="monotone" dataKey="average_3_dart" stroke="var(--accent)" strokeWidth={2.5} dot={false} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              )}
            </Card>
            <Card title="Najczęściej trafiane">
              <div className="flex flex-wrap gap-2">
                {Object.entries(st.hit_distribution.labels as Record<string, number>).slice(0, 24).map(([k, v]) => (
                  <span key={k} className="rounded-lg bg-[var(--surface-2)] px-2.5 py-1 text-sm"><b>{dartLabel(k)}</b> <span className="text-[var(--muted)]">{v}</span></span>
                ))}
              </div>
            </Card>
          </div>
          <Card title="Mapa trafień">
            <div className="aspect-square"><Dartboard board={board} heat={heat ?? []} /></div>
            <div className="mt-2 text-xs text-[var(--muted)]">Wykryte trafienia: {heat?.length ?? 0} (tylko rzuty liczone przez kamery)</div>
          </Card>
        </div>
      )}
    </div>
  );
}
