// Service mode on a board: venue staff type the service PIN to open calibration (and the
// technician pages). It locks again by itself after a few idle minutes so the next customer
// at the board never finds it open.

import { create } from "zustand";
import { api, setAdminToken } from "@/lib/api";

const KEY = "dartsense.serviceUntil";
const IDLE_MS = 15 * 60_000;

function readUntil(): number {
  try {
    return Number(localStorage.getItem(KEY) ?? 0) || 0;
  } catch {
    return 0;
  }
}

function writeUntil(v: number): void {
  try {
    if (v) localStorage.setItem(KEY, String(v));
    else localStorage.removeItem(KEY);
  } catch {
    /* storage unavailable */
  }
}

interface ServiceState {
  until: number;
  unlocked: () => boolean;
  unlock: (pin: string) => Promise<void>;
  lock: () => void;
  touch: () => void;
}

export const useService = create<ServiceState>((set, get) => ({
  until: readUntil(),
  unlocked: () => get().until > Date.now(),
  unlock: async (pin) => {
    const r = await api.post<{ admin_token: string }>("/api/service/unlock", { pin });
    setAdminToken(r.admin_token);
    const until = Date.now() + IDLE_MS;
    writeUntil(until);
    set({ until });
  },
  lock: () => {
    setAdminToken("");
    writeUntil(0);
    set({ until: 0 });
  },
  touch: () => {
    if (!get().unlocked()) return;
    const until = Date.now() + IDLE_MS;
    // write at most every 30 s
    if (until - get().until > 30_000) {
      writeUntil(until);
      set({ until });
    }
  },
}));

let watching = false;

/** Extends service mode while someone uses the screen and locks it when the time runs out. */
export function watchServiceIdle(): void {
  if (watching) return;
  watching = true;
  const touch = () => useService.getState().touch();
  window.addEventListener("pointerdown", touch, { passive: true });
  window.addEventListener("keydown", touch);
  setInterval(() => {
    const s = useService.getState();
    if (s.until && s.until <= Date.now()) s.lock();
  }, 5000);
}
