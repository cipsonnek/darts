import clsx from "clsx";
import type { GameState } from "@/lib/types";
import { usePrefs } from "@/store/prefs";

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

function subValue(game: GameState, i: number): string {
  const s = game.player_summaries[i] ?? {};
  switch (game.mode) {
    case "x01":
      return `avg ${s.average_3_dart?.toFixed?.(1) ?? "–"} · ${s.darts_thrown ?? 0} darts`;
    case "cricket":
      return `MPR ${s.marks_per_round ?? 0}`;
    case "atc":
      return `${s.progress}/${s.of} · hit ${Math.round((s.hit_rate ?? 0) * 100)}%`;
    case "shanghai":
      return s.target ? `round ${s.round} → ${s.target}` : "done";
    case "bobs27":
      return s.eliminated ? "eliminated" : `next ${s.target ?? "–"}`;
    default:
      return "";
  }
}

const CRICKET = ["20", "19", "18", "17", "16", "15", "25"];

function marks(n: number) {
  return n >= 3 ? "Ⓧ" : n === 2 ? "✕" : n === 1 ? "/" : "";
}

export function Scoreboard({ game, big }: { game: GameState; big?: boolean }) {
  const style = usePrefs((s) => s.scoreStyle);
  const st = game.state;
  const current = st.awaiting_takeout ? -1 : st.current_player;
  const size = big || style === "big" ? "text-7xl md:text-8xl" : style === "compact" ? "text-3xl" : "text-5xl md:text-6xl";
  return (
    <div className="flex flex-col gap-3">
      <div className={clsx("grid gap-3", game.players.length > 2 ? "sm:grid-cols-2 xl:grid-cols-3" : "sm:grid-cols-2")}>
        {game.players.map((p, i) => (
          <div key={p.id}
            className={clsx("relative overflow-hidden rounded-2xl border p-4 transition",
              i === current ? "border-[var(--accent)] bg-[color-mix(in_oklab,var(--accent)_10%,var(--surface))] shadow-[0_0_30px_-8px_var(--accent)]"
                : "border-[var(--border)] bg-[var(--surface-2)]",
              st.winner === i && "border-[var(--good)]")}>
            <div className="absolute inset-y-0 left-0 w-1.5" style={{ background: p.color }} />
            <div className="flex items-center justify-between gap-2">
              <div className="truncate font-display text-lg font-bold">{p.name}</div>
              <div className="flex gap-1 text-xs text-[var(--muted)]">
                {game.settings.sets_to_win > 1 && <span>S {st.sets_won[i]}</span>}
                {(game.settings.legs_to_win_set > 1 || game.settings.sets_to_win > 1) && <span>L {st.legs_won[i]}</span>}
              </div>
            </div>
            <div className={clsx("font-display font-black tabular-nums leading-none tracking-tight", size)}>{mainValue(game, i)}</div>
            <div className="mt-1 text-sm text-[var(--muted)]">{subValue(game, i)}</div>
          </div>
        ))}
      </div>
      {game.mode === "cricket" && (
        <div className="overflow-x-auto rounded-xl border border-[var(--border)]">
          <table className="w-full text-center text-sm">
            <thead className="bg-[var(--surface-2)]">
              <tr>
                <th className="px-2 py-1 text-left">#</th>
                {game.players.map((p) => <th key={p.id} className="px-2 py-1">{p.name}</th>)}
              </tr>
            </thead>
            <tbody>
              {CRICKET.map((n) => (
                <tr key={n} className="border-t border-[var(--border)]">
                  <td className="px-2 py-1 text-left font-bold">{n === "25" ? "Bull" : n}</td>
                  {game.players.map((p, i) => (
                    <td key={p.id} className="px-2 py-1 text-lg font-bold">{marks(game.player_summaries[i]?.marks?.[n] ?? 0)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
