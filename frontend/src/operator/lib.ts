// Operator panel: API types mirroring backend/services/fleet_service.py, Polish labels and
// formatting helpers.

export interface Venue {
  id: string;
  name: string;
  kind: string;
  address: string;
  city: string;
  postal_code: string;
  lat: number | null;
  lng: number | null;
  contact_name: string;
  phone: string;
  email: string;
  opening_hours: string;
  price_per_game: number;
  venue_share_pct: number;
  notes: string;
  active: boolean;
  created_at: string | null;
}

export interface VenueRow extends Venue {
  boards: number;
  boards_online: number;
  alerts: number;
  games_30d: number;
  revenue_30d: number;
  open_tickets: number;
}

export interface Alert {
  code: string;
  severity: "info" | "warn" | "bad";
  since?: string;
  cameras?: string[];
  status?: string;
}

export interface BoardCamera { id: string; connected: boolean; calibrated: boolean; fps: number | null }

export interface Board {
  id: string;
  name: string;
  serial: string;
  status: string;
  venue_id: string | null;
  venue_name: string | null;
  venue_city: string | null;
  key_prefix: string;
  installed_at: string | null;
  last_seen_at: string | null;
  version: string | null;
  engine: string | null;
  cameras: BoardCamera[];
  active_game: boolean | null;
  uptime_s: number | null;
  mode: string | null;
  notes: string;
  online: boolean;
  alerts: Alert[];
  level: "ok" | "warn" | "bad" | "retired";
  games_30d?: number;
  last_game_at?: string | null;
  open_tickets?: number;
  api_key?: string;
}

export interface BoardDetail extends Board {
  recent_games: { game_id: string; mode: string; status: string; players: number; darts: number; started_at: string; duration_s: number; price: number }[];
}

export interface VenueDetail extends Venue { board_list: Board[] }

export interface Totals {
  games: number;
  revenue: number;
  venue_share: number;
  operator_share: number;
  darts: number;
  avg_duration_s: number;
  avg_players: number;
  games_per_day: number;
}

export interface Stats {
  from: string;
  to: string;
  currency: string;
  timezone: string;
  totals: Totals;
  daily: { date: string; games: number; revenue: number }[];
  heatmap: number[][];
  modes: { mode: string; games: number }[];
  by_venue: { venue_id: string | null; name: string | null; city: string | null; games: number; revenue: number; venue_share: number }[];
  by_board: { board_id: string; name: string; games: number; venue_name: string | null }[];
}

export interface Dashboard {
  currency: string;
  venues_active: number;
  boards: { total: number; online: number; offline: number; maintenance: number; playing: number };
  today: Totals;
  last_30d: Totals;
  prev_30d: Totals;
  daily: Stats["daily"];
  top_venues: Stats["by_venue"];
  open_tickets: Record<string, number>;
  open_tickets_total: number;
  alerts: (Alert & { board_id: string; board_name: string; venue_id: string | null; venue_name: string | null })[];
}

export interface Settlement {
  month: string;
  from: string;
  to: string;
  currency: string;
  venues: { venue_id: string | null; name: string | null; city: string | null; games: number; revenue: number;
    venue_share: number; operator_share: number; prices: number[]; share_pcts: number[] }[];
  totals: { games: number; revenue: number; venue_share: number; operator_share: number };
}

export interface Ticket {
  id: number;
  title: string;
  description: string;
  category: string;
  priority: string;
  status: string;
  assignee: string;
  reporter: string;
  board_id: string | null;
  venue_id: string | null;
  board_name: string | null;
  venue_name: string | null;
  created_at: string;
  updated_at: string;
  closed_at: string | null;
  comments?: { id: number; author: string; text: string; status_change: string; created_at: string }[];
}

// ---------------------------------------------------------------------------- labels
export const VENUE_KIND: Record<string, string> = { bar: "Bar", pub: "Pub", arcade: "Salon gier", club: "Klub", other: "Inne" };
export const BOARD_STATUS: Record<string, string> = { active: "aktywna", maintenance: "serwis", retired: "wycofana" };
export const TICKET_STATUS: Record<string, string> = { open: "nowe", in_progress: "w toku", waiting: "czeka", closed: "zamknięte" };
export const TICKET_PRIORITY: Record<string, string> = { low: "niski", normal: "normalny", high: "wysoki", critical: "krytyczny" };
export const TICKET_CATEGORY: Record<string, string> = { fault: "Awaria", maintenance: "Konserwacja", install: "Montaż", other: "Inne" };
export const PRIORITY_TONE: Record<string, "info" | "warn" | "bad" | "accent"> = { low: "info", normal: "info", high: "warn", critical: "bad" };
export const STATUS_TONE: Record<string, "info" | "good" | "warn" | "bad" | "accent"> = { open: "accent", in_progress: "warn", waiting: "info", closed: "good" };

export function alertText(a: Alert): string {
  switch (a.code) {
    case "offline": return `Offline — ostatni sygnał ${a.since ? ago(a.since) : "—"}`;
    case "never_seen": return "Jeszcze się nie połączyła";
    case "camera_down": return `Kamera odłączona: ${(a.cameras ?? []).join(", ")}`;
    case "uncalibrated": return `Brak kalibracji: ${(a.cameras ?? []).join(", ")}`;
    case "calibration_drift": return a.status === "moved" ? "Kamera się przesunęła — kalibracja nieaktualna" : "Kalibracja do sprawdzenia";
    case "engine_stopped": return "Silnik detekcji zatrzymany";
    case "maintenance": return "W serwisie";
    default: return a.code;
  }
}

export const ALERT_TICKET_TITLE: Record<string, string> = {
  offline: "Tarcza offline", never_seen: "Tarcza nie łączy się z serwerem", camera_down: "Odłączona kamera",
  uncalibrated: "Brak kalibracji kamery", calibration_drift: "Kalibracja do sprawdzenia", engine_stopped: "Silnik detekcji zatrzymany",
};

// ---------------------------------------------------------------------------- formatting
const money = new Intl.NumberFormat("pl-PL", { style: "currency", currency: "PLN", maximumFractionDigits: 0 });
const money2 = new Intl.NumberFormat("pl-PL", { style: "currency", currency: "PLN", minimumFractionDigits: 2, maximumFractionDigits: 2 });
const num = new Intl.NumberFormat("pl-PL");

export function zl(v: number, exact = false): string {
  return (exact ? money2 : money).format(v);
}

export function n(v: number): string {
  return num.format(v);
}

export function dateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("pl-PL", { dateStyle: "medium", timeStyle: "short" });
}

export function dateOnly(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("pl-PL", { dateStyle: "medium" });
}

export function ago(iso: string | null | undefined): string {
  if (!iso) return "nigdy";
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return "przed chwilą";
  if (s < 3600) return `${Math.round(s / 60)} min temu`;
  if (s < 86400) return `${Math.round(s / 3600)} godz. temu`;
  const d = Math.round(s / 86400);
  return d === 1 ? "wczoraj" : `${d} dni temu`;
}

export function duration(sec: number): string {
  const m = Math.round(sec / 60);
  return m < 60 ? `${m} min` : `${Math.floor(m / 60)} h ${m % 60} min`;
}

export function pctChange(cur: number, prev: number): number | null {
  if (!prev) return null;
  return ((cur - prev) / prev) * 100;
}

/** Local date as YYYY-MM-DD. */
export function isoDay(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export const WEEKDAYS = ["pn", "wt", "śr", "cz", "pt", "sb", "nd"];
