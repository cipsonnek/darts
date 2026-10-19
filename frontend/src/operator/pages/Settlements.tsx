import { ChevronLeft, ChevronRight, Download } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";
import { Button, Card, Empty, ErrorNote, PageHeader } from "@/components/ui";
import { useApi } from "@/hooks/useApi";
import { n, zl, type Settlement } from "../lib";
import { Kpi } from "../ui";

function shift(month: string, d: number): string {
  const [y, m] = month.split("-").map(Number);
  const dt = new Date(y, m - 1 + d, 1);
  return `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, "0")}`;
}

function monthLabel(month: string): string {
  const [y, m] = month.split("-").map(Number);
  const s = new Date(y, m - 1, 1).toLocaleDateString("pl-PL", { month: "long", year: "numeric" });
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function exportCsv(s: Settlement) {
  const num = (v: number) => v.toFixed(2).replace(".", ",");
  const rows = [["Lokal", "Miasto", "Gry", "Przychód", "Udział lokalu %", "Dla lokalu", "Dla operatora"],
    ...s.venues.map((v) => [v.name ?? "", v.city ?? "", String(v.games), num(v.revenue), v.share_pcts.join("/"), num(v.venue_share), num(v.operator_share)]),
    ["Razem", "", String(s.totals.games), num(s.totals.revenue), "", num(s.totals.venue_share), num(s.totals.operator_share)]];
  // Semicolons and a BOM so Excel with Polish settings opens it correctly.
  const csv = "﻿" + rows.map((r) => r.map((c) => `"${c.replace(/"/g, '""')}"`).join(";")).join("\r\n");
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
  a.download = `rozliczenie-${s.month}.csv`;
  a.click();
  URL.revokeObjectURL(a.href);
}

export default function Settlements() {
  const now = new Date();
  const current = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
  const [month, setMonth] = useState(current);
  const { data: s, error } = useApi<Settlement>(`/api/fleet/settlements?month=${month}`);
  return (
    <div className="flex flex-col gap-5">
      <PageHeader title="Rozliczenia" subtitle="Podział przychodu z lokalami za wybrany miesiąc. Każda gra jest liczona po stawce i udziale obowiązującym w chwili gry."
        actions={s && s.venues.length > 0 && <Button onClick={() => exportCsv(s)}><Download size={16} /> Eksport CSV</Button>} />
      <div className="flex items-center gap-2">
        <Button onClick={() => setMonth(shift(month, -1))} aria-label="Poprzedni miesiąc"><ChevronLeft size={18} /></Button>
        <div className="min-w-48 text-center font-display text-xl font-bold">{monthLabel(month)}</div>
        <Button onClick={() => setMonth(shift(month, 1))} disabled={month >= current} aria-label="Następny miesiąc"><ChevronRight size={18} /></Button>
        {month === current && <span className="text-sm text-[var(--warn)]">miesiąc w toku</span>}
      </div>
      <ErrorNote error={error} />
      {s && (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Kpi label="Gry" value={n(s.totals.games)} />
            <Kpi label="Przychód" value={zl(s.totals.revenue)} />
            <Kpi label="Do wypłaty lokalom" value={zl(s.totals.venue_share)} />
            <Kpi label="Dla operatora" value={zl(s.totals.operator_share)} tone="good" />
          </div>
          <Card pad={false}>
            {!s.venues.length ? <div className="p-4"><Empty title="Brak płatnych gier w tym miesiącu" /></div> : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="text-left text-xs text-[var(--muted)] uppercase">
                    <tr className="[&>th]:px-3 [&>th]:py-2.5">
                      <th>Lokal</th><th className="text-right">Gry</th><th className="text-right">Cena gry</th><th className="text-right">Przychód</th>
                      <th className="text-right">Udział lokalu</th><th className="text-right">Dla lokalu</th><th className="text-right">Dla operatora</th>
                    </tr>
                  </thead>
                  <tbody>
                    {s.venues.map((v, i) => (
                      <tr key={v.venue_id ?? i} className="border-t border-[var(--border)] [&>td]:px-3 [&>td]:py-2.5">
                        <td>{v.venue_id ? <Link className="font-semibold hover:text-[var(--accent)]" to={`/operator/venues/${v.venue_id}`}>{v.name}</Link> : "—"}
                          <span className="text-[var(--muted)]"> · {v.city}</span></td>
                        <td className="text-right tabular-nums">{n(v.games)}</td>
                        <td className="text-right tabular-nums text-[var(--muted)]">{v.prices.map((p) => zl(p, true)).join(" / ")}</td>
                        <td className="text-right font-semibold tabular-nums">{zl(v.revenue, true)}</td>
                        <td className="text-right tabular-nums text-[var(--muted)]">{v.share_pcts.map((p) => `${p}%`).join(" / ")}</td>
                        <td className="text-right font-semibold tabular-nums">{zl(v.venue_share, true)}</td>
                        <td className="text-right font-semibold tabular-nums text-[var(--good)]">{zl(v.operator_share, true)}</td>
                      </tr>
                    ))}
                  </tbody>
                  <tfoot>
                    <tr className="border-t-2 border-[var(--border)] font-bold [&>td]:px-3 [&>td]:py-3">
                      <td>Razem</td><td className="text-right tabular-nums">{n(s.totals.games)}</td><td />
                      <td className="text-right tabular-nums">{zl(s.totals.revenue, true)}</td><td />
                      <td className="text-right tabular-nums">{zl(s.totals.venue_share, true)}</td>
                      <td className="text-right tabular-nums text-[var(--good)]">{zl(s.totals.operator_share, true)}</td>
                    </tr>
                  </tfoot>
                </table>
              </div>
            )}
          </Card>
          <p className="text-sm text-[var(--muted)]">
            Gdy w trakcie miesiąca zmieniła się cena albo udział, w kolumnach widać kilka wartości. Kwoty są policzone dla każdej gry osobno.
          </p>
        </>
      )}
    </div>
  );
}
