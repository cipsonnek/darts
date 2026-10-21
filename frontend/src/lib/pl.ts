// Polish labels for values that come from the backend in English (game modes, settings,
// statuses, engine states, game messages). The backend stays language-neutral.

export const MODE_NAMES: Record<string, string> = {
  x01: "X01",
  cricket: "Cricket",
  atc: "Dookoła tarczy",
  shanghai: "Shanghai",
  bobs27: "Bob's 27",
};

export const MODE_DESCRIPTIONS: Record<string, string> = {
  x01: "Odliczaj od wyniku startowego i zejdź dokładnie do zera.",
  cricket: "Zamknij pola 15–20 i bulla; punktuj na polach, których rywale jeszcze nie zamknęli.",
  atc: "Traf kolejno pola od 1 do 20 (opcjonalnie na końcu bull).",
  shanghai: "W rundzie n liczą się tylko trafienia w n. Single + double + triple w jednej turze wygrywa od razu.",
  bobs27: "Trening doubli: start z 27 pkt, +2n za trafienie D(n), −2n za rundę bez trafienia.",
};

export function modeName(id: string, fallback?: string): string {
  return MODE_NAMES[id] ?? fallback ?? id;
}

export const SETTING_LABELS: Record<string, string> = {
  start_score: "Wynik startowy",
  in_mode: "Wejście",
  out_mode: "Zejście",
  legs_to_win_set: "Legi do wygrania seta",
  sets_to_win: "Sety do wygrania meczu",
  variant: "Wariant",
  max_rounds: "Limit rund",
  include_bull: "Bull na końcu",
  multiplier_advances: "Double/triple przeskakuje pola",
  rounds: "Liczba rund",
};

export const SETTING_HINTS: Record<string, string> = {
  max_rounds: "0 = bez limitu; inaczej po tylu rundach wygrywa najwyższy wynik",
  multiplier_advances: "Double przesuwa o 2 pola, triple o 3",
};

const SETTING_VALUES: Record<string, Record<string, string>> = {
  in_mode: { straight: "Dowolne", double: "Double In", master: "Master In" },
  out_mode: { straight: "Single Out", double: "Double Out", master: "Master Out" },
  variant: { standard: "Standardowy", cutthroat: "Cut-throat" },
};

export function settingLabel(key: string): string {
  return SETTING_LABELS[key] ?? key.replace(/_/g, " ");
}

export function settingValue(key: string, value: unknown): string {
  if (typeof value === "boolean") return value ? "tak" : "nie";
  return SETTING_VALUES[key]?.[String(value)] ?? String(value);
}

export const GAME_STATUS: Record<string, string> = {
  created: "utworzona",
  running: "w trakcie",
  paused: "wstrzymana",
  finished: "zakończona",
  abandoned: "przerwana",
};

export const ENGINE_STATE: Record<string, string> = {
  starting: "uruchamianie",
  idle: "gotowy",
  motion: "ruch",
  processing: "analiza",
  obstructed: "zasłonięta",
  stopped: "zatrzymany",
};

export const DETECTION_STATUS: Record<string, string> = {
  accepted: "przyjęty",
  pending: "oczekuje",
  rejected: "odrzucony",
  resolved: "rozstrzygnięty",
  ignored: "pominięty (wyjmowanie)",
};

export const GRADE: Record<string, string> = { good: "dobra", fair: "średnia", poor: "słaba" };

export const OVERLAY_LABELS: Record<string, string> = {
  board: "tarcza", sectors: "sektory", labels: "opisy", roi: "obszar analizy", change: "zmiany",
  candidates: "kandydaci", darts: "lotki", info: "info",
};

export function tr(dict: Record<string, string>, v: string | null | undefined): string {
  if (v == null) return "—";
  return dict[v] ?? v;
}

/** Translate the free-text message the game engine puts in state.message. */
export function gameMessage(msg: string): string {
  if (!msg) return "";
  if (msg === "BUST") return "BUST — za dużo";
  let m = msg.match(/^(.*) wins leg (\d+)$/);
  if (m) return `${m[1]} wygrywa lega ${m[2]}`;
  m = msg.match(/^(.*) wins set (\d+)$/);
  if (m) return `${m[1]} wygrywa seta ${m[2]}`;
  m = msg.match(/^(.*) wins the game$/);
  if (m) return `${m[1]} wygrywa mecz`;
  return msg;
}

/** Dart label for display: "S20" → "20", others unchanged ("T20", "D16", "BULL", "MISS"). */
export function dartLabel(label: string): string {
  if (label === "MISS") return "Pudło";
  if (label === "BULL") return "Bull";
  if (/^S\d+$/.test(label)) return label.slice(1);
  return label;
}

export function plural(n: number, one: string, few: string, many: string): string {
  if (n === 1) return one;
  const d = n % 10;
  const h = n % 100;
  return d >= 2 && d <= 4 && (h < 12 || h > 14) ? few : many;
}
