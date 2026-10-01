// Live state fed by the WebSockets: connection, engine status, detections, active game.

import { create } from "zustand";
import type { CameraHealth, DartDetection, GameState, WsMessage } from "@/lib/types";
import type { WsStatus } from "@/lib/ws";

export interface FeedItem {
  id: number;
  ts: number;
  type: string;
  text: string;
  tone: "info" | "good" | "warn" | "bad";
  data?: any;
}

interface LiveState {
  events: WsStatus;
  detection: WsStatus;
  mode: string | null;
  engineState: string | null;
  dartsOnBoard: number;
  cameras: CameraHealth[];
  motion: Record<string, number>;
  syncSpreadMs: number | null;
  stats: Record<string, any> | null;
  recording: any;
  lastDart: DartDetection | null;
  game: GameState | null;
  uncertain: { game_id: string; detection: DartDetection } | null;
  relabel: { dart_id: string; label: string; n: number } | null;
  feed: FeedItem[];
  setStatus: (ch: "events" | "detection", s: WsStatus) => void;
  setGame: (g: GameState | null) => void;
  clearUncertain: () => void;
  handle: (m: WsMessage) => void;
}

let feedSeq = 0;

function describe(m: WsMessage): FeedItem | null {
  const d = m.data ?? {};
  const base = { id: ++feedSeq, ts: m.ts * 1000, type: m.type, data: d };
  switch (m.type) {
    case "dart_detected":
      return { ...base, tone: d.uncertain ? "warn" : "good",
        text: `${d.score?.label} (${Math.round((d.confidence?.overall ?? 0) * 100)}%)${d.uncertain ? " — uncertain" : ""}` };
    case "darts_removed":
      return { ...base, tone: "info", text: `${d.dart_ids?.length ?? 0} dart(s) removed${d.board_clear ? " — board clear" : ""}` };
    case "obstruction":
      return { ...base, tone: "warn", text: `Board obstructed (${(d.cameras ?? []).join(", ")})` };
    case "unrecognized_change":
      return { ...base, tone: "warn", text: "Change not recognised as a dart — enter manually if a dart was thrown" };
    case "motion_without_change":
      return d.possible_bounce_out ? { ...base, tone: "warn", text: "Motion without a dart (possible bounce-out)" } : null;
    case "engine_error":
      return { ...base, tone: "bad", text: `Engine error: ${d.error}` };
    case "calibration_status": {
      const bad = Object.values(d as Record<string, any>).filter((v: any) => v && typeof v === "object" && v.status !== "ok");
      return bad.length ? { ...base, tone: "warn", text: `Calibration check: ${bad.map((v: any) => `${v.camera_id} ${v.status}`).join(", ")}` } : null;
    }
    case "baseline_set":
      return { ...base, tone: "info", text: "Board baseline captured" };
    case "dart_relabelled":
      return { ...base, tone: "info", text: `Dart corrected to ${d.label}` };
    case "dart_moved":
      return { ...base, tone: "info", text: "A dart in the board moved (not scored)" };
    default:
      return null;
  }
}

export const useLive = create<LiveState>((set, get) => ({
  events: "connecting",
  detection: "connecting",
  mode: null,
  engineState: null,
  dartsOnBoard: 0,
  cameras: [],
  motion: {},
  syncSpreadMs: null,
  stats: null,
  recording: null,
  lastDart: null,
  game: null,
  uncertain: null,
  relabel: null,
  feed: [],
  setStatus: (ch, s) => set({ [ch]: s } as Partial<LiveState>),
  setGame: (g) => set({ game: g }),
  clearUncertain: () => set({ uncertain: null }),
  handle: (m) => {
    const d = m.data;
    switch (m.type) {
      case "hello":
        // Both sockets greet; only the events socket carries mode/engine.
        if (d.mode) set({ mode: d.mode });
        if (d.engine) set({ engineState: d.engine });
        break;
      case "status":
        set({
          engineState: d.engine?.state ?? null,
          dartsOnBoard: d.engine?.darts_on_board ?? 0,
          stats: d.engine?.stats ?? null,
          cameras: d.cameras ?? [],
          motion: d.motion ?? {},
          syncSpreadMs: d.sync_spread_ms ?? null,
          recording: d.recording ?? null,
        });
        break;
      case "engine_state":
        set({ engineState: d.state });
        break;
      case "dart_detected":
        set({ lastDart: d as DartDetection });
        break;
      case "game_state":
      case "game_created": {
        const cur = get().game;
        if (!cur || cur.id === d.id || d.status === "running") set({ game: d as GameState });
        break;
      }
      case "dart_uncertain":
        set({ uncertain: d });
        break;
      case "dart_relabelled":
        set({ relabel: { ...d, n: m.seq } });
        break;
      default:
        break;
    }
    const item = describe(m);
    if (item) set({ feed: [item, ...get().feed].slice(0, 200) });
  },
}));
