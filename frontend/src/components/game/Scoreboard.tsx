import clsx from "clsx";
import type { GameState, Turn } from "@/lib/types";
import { dartLabel } from "@/lib/pl";
import { usePrefs } from "@/store/prefs";

/** Big number shown for a player: points left (X01), points (Cricket, Shanghai, Bob's 27), target (ATC). */
function mainValue(game: GameState, i: number): string {
  const s = game.player_summaries[i] ?? {};
  switch (game.mode) {
    case "x01":
      return String(s.remaining ?? "");
    case "cricket":
    case "shanghai":
    case "bobs27":
      return String(s.points ?? 0);
    case "atc":
      return s.target === null ? "✓" : String(s.target === 25 ? "BULL" : s.target);
    default:
      return "";
  }
}

function mainCaption(game: GameState): string {
  switch (game.mode) {
    case "x01": return "pozostało";
    case "atc": return "cel";
    default: return "punkty";
  }
}

/** Last completed turn of a player in the current leg. */
function lastTurn(game: GameState, i: number): Turn | null {
  const turns = game.state.turns;
  for (let k = turns.length - 1; k >= 0; k--) {
    const t = turns[k];
    if (t.player_index === i && t.finished) return t;
  }
  return null;
}

/** Up to three small stats under the big number, depending on the game mode. */
function stats(game: GameState, i: number): { label: string; value: string }[] {
  const s = game.player_summaries[i] ?? {};
  const last = lastTurn(game, i);
  const lastValue = last ? (last.bust ? "BUST" : String(last.points)) : "–";
  switch (game.mode) {
    case "x01":
      return [
        { label: "Średnia", value: s.darts_thrown ? (s.average_3_dart ?? 0).toFixed(1) : "–" },
        { label: "Ostatnia", value: lastValue },
        { label: "Lotki", value: String(s.darts_thrown ?? 0) },
      ];
    case "cricket":
      return [
        { label: "MPR", value: String(s.marks_per_round ?? 0) },
        { label: "Ostatnia", value: lastValue },
      ];
    case "atc":
      return [
        { label: "Postęp", value: `${s.progress ?? 0}/${s.of ?? 0}` },
        { label: "Skuteczność", value: `${Math.round((s.hit_rate ?? 0) * 100)}%` },
      ];
    case "shanghai":
      return [
        { label: "Runda", value: s.target ? String(s.round) : "koniec" },
        { label: "Cel", value: s.target ? String(s.target) : "–" },
      ];
    case "bobs27":
      return [
        { label: "Następny", value: s.eliminated ? "odpada" : (s.target ? dartLabel(s.target) : "–") },
        { label: "Trafione D", value: String(s.doubles_hit ?? 0) },
      ];
    default:
      return [];
  }
}

function LegPips({ won, of }: { won: number; of: number }) {
  if (of <= 1) return null;
  return (
    <div className="flex gap-1" aria-label={`${won} z ${of}`}>
      {Array.from({ length: of }, (_, k) => (
        <span key={k} className={clsx("h-2.5 w-2.5 rounded-full border", k < won ? "border-[var(--good)] bg-[var(--good)]" : "border-[var(--border)]")} />
      ))}
    </div>
  );
}

export function Scoreboard({ game, big }: { game: GameState; big?: boolean }) {
  const style = usePrefs((s) => s.scoreStyle);
  const st = game.state;
  const current = st.finished ? -1 : st.current_player;
  const n = game.players.length;
  const compact = style === "compact" || n > 4;
  const huge = big || style === "big";
  const cfg = game.settings;
  const showSets = cfg.sets_to_win > 1;
  return (
    <div className="flex flex-col gap-3">
      <div className={clsx("grid gap-3",
        n === 1 ? "grid-cols-1" : n === 2 ? "grid-cols-2" : n === 3 ? "grid-cols-1 sm:grid-cols-3" : n === 4 ? "grid-cols-2 xl:grid-cols-4" : "grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4")}>
        {game.players.map((p, i) => {
          const active = i === current;
          const won = st.winner === i;
          return (
            <div key={p.id}
              className={clsx("glass relative flex flex-col overflow-hidden rounded-3xl transition duration-300",
                compact ? "p-3" : "p-4 md:p-5",
                won ? "border-[var(--good)] bg-[color-mix(in_oklab,var(--good)_12%,var(--surface))]"
                  : active ? "z-10 -translate-y-1 scale-[1.015] border-[var(--accent)] bg-[color-mix(in_oklab,var(--accent)_12%,var(--surface))] shadow-[0_24px_60px_-24px_var(--accent)]"
                    : "opacity-75")}>
              <div className="absolute inset-x-0 top-0 h-1.5" style={{ background: p.color, boxShadow: `0 0 18px ${p.color}` }} />
              <div className="flex items-center gap-2">
                {active && !st.awaiting_takeout && <span className="h-2.5 w-2.5 shrink-0 animate-pulse rounded-full bg-[var(--accent)]" aria-label="rzuca" />}
                <div className={clsx("min-w-0 flex-1 truncate font-display font-bold tracking-wide uppercase", compact ? "text-lg" : "text-xl md:text-2xl")}>{p.name}</div>
                <div className="flex flex-col items-end gap-1 text-xs text-[var(--muted)]">
                  {showSets && <div className="flex items-center gap-1.5">S <LegPips won={st.sets_won[i]} of={cfg.sets_to_win} /></div>}
                  {cfg.legs_to_win_set > 1 && <div className="flex items-center gap-1.5">L <LegPips won={st.legs_won[i]} of={cfg.legs_to_win_set} /></div>}
                </div>
              </div>
              <div className="mt-1 flex items-end justify-between gap-2">
                <div className={clsx("font-score font-extrabold leading-[0.9]",
                  compact ? "text-6xl" : huge ? "text-[7rem] md:text-[9rem]" : active ? "text-7xl sm:text-[5.5rem] md:text-[7.5rem]" : "text-6xl sm:text-7xl md:text-8xl",
                  won && "text-[var(--good)]", active && !won && "drop-shadow-[0_6px_24px_color-mix(in_oklab,var(--accent)_45%,transparent)]")}>
                  {mainValue(game, i)}
                </div>
                <div className="hidden pb-2 text-xs font-medium tracking-wide text-[var(--muted)] uppercase sm:block">{mainCaption(game)}</div>
              </div>
              {active && game.checkout_hint && game.checkout_hint.length > 0 && (
                <div className="mt-2 flex flex-wrap items-center gap-1.5">
                  {game.checkout_hint.map((h, k) => (
                    <span key={k} className="rounded-lg bg-[var(--good)] px-2.5 py-0.5 font-score text-xl font-bold text-black">{dartLabel(h)}</span>
                  ))}
                </div>
              )}
              <div className={clsx("mt-3 grid gap-2 border-t border-[var(--border)] pt-3", stats(game, i).length === 3 ? "grid-cols-3" : "grid-cols-2")}>
                {stats(game, i).map((x) => (
                  <div key={x.label} className="min-w-0">
                    <div className="truncate text-[11px] font-semibold tracking-wide text-[var(--muted)] uppercase">{x.label}</div>
                    <div className={clsx("truncate font-score font-bold leading-tight", compact ? "text-xl" : "text-xl sm:text-2xl md:text-3xl", x.value === "BUST" && "text-[var(--bad)]")}>{x.value}</div>
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>
      {game.mode === "cricket" && <CricketTable game={game} />}
    </div>
  );
}

const CRICKET = ["20", "19", "18", "17", "16", "15", "25"];

function Mark({ n }: { n: number }) {
  if (n <= 0) return <span className="text-[var(--border)]">·</span>;
  if (n === 1) return <span>/</span>;
  if (n === 2) return <span>✕</span>;
  return <span className="grid h-8 w-8 place-items-center rounded-full border-[3px] border-[var(--good)] text-[var(--good)]">✕</span>;
}

function CricketTable({ game }: { game: GameState }) {
  return (
    <div className="glass overflow-x-auto rounded-3xl">
      <table className="w-full text-center">
        <thead>
          <tr className="text-sm text-[var(--muted)]">
            <th className="px-3 py-2 text-left">Pole</th>
            {game.players.map((p) => <th key={p.id} className="px-3 py-2"><span className="inline-block h-2 w-2 rounded-full" style={{ background: p.color }} /> {p.name}</th>)}
          </tr>
        </thead>
        <tbody>
          {CRICKET.map((n) => {
            const closedByAll = game.players.every((_, i) => (game.player_summaries[i]?.marks?.[n] ?? 0) >= 3);
            return (
              <tr key={n} className={clsx("border-t border-[var(--border)]", closedByAll && "opacity-40")}>
                <td className="px-3 py-1.5 text-left font-score text-2xl font-bold">{n === "25" ? "Bull" : n}</td>
                {game.players.map((p, i) => (
                  <td key={p.id} className="px-3 py-1.5 font-score text-2xl font-bold">
                    <span className="inline-grid place-items-center"><Mark n={game.player_summaries[i]?.marks?.[n] ?? 0} /></span>
                  </td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
