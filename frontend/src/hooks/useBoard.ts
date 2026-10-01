import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { DEFAULT_BOARD } from "@/lib/board";
import type { BoardInfo, DartDetection } from "@/lib/types";
import { useLive } from "@/store/live";

let cachedBoard: BoardInfo | null = null;

/** Board geometry from the server (cached). */
export function useBoardGeometry(): BoardInfo {
  const [b, setB] = useState<BoardInfo>(cachedBoard ?? DEFAULT_BOARD);
  useEffect(() => {
    if (cachedBoard) return;
    api.get<BoardInfo>("/api/board").then((x) => {
      cachedBoard = x;
      setB(x);
    }).catch(() => {});
  }, []);
  return b;
}

export interface BoardDart {
  id: string;
  x_mm: number;
  y_mm: number;
  label: string;
  cov?: number[][];
  uncertain?: boolean;
}

/** Darts currently in the board: initial state from the API, then live from events. */
export function useBoardDarts(): BoardDart[] {
  const [darts, setDarts] = useState<BoardDart[]>([]);
  const lastDart = useLive((s) => s.lastDart);
  const feed = useLive((s) => s.feed);

  useEffect(() => {
    api.get<{ darts: { dart_id: string; impact_mm: number[]; label: string }[] }>("/api/board/state")
      .then((r) => setDarts(r.darts.map((d) => ({ id: d.dart_id, x_mm: d.impact_mm[0], y_mm: d.impact_mm[1], label: d.label }))))
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (!lastDart) return;
    const d: DartDetection = lastDart;
    setDarts((cur) => cur.some((c) => c.id === d.dart_id) ? cur : [...cur,
      { id: d.dart_id, x_mm: d.impact.x_mm, y_mm: d.impact.y_mm, label: d.score.label, cov: d.covariance_mm2, uncertain: d.uncertain }]);
  }, [lastDart]);

  const relabel = useLive((s) => s.relabel);
  useEffect(() => {
    if (!relabel) return;
    setDarts((cur) => cur.map((d) => (d.id === relabel.dart_id ? { ...d, label: relabel.label, uncertain: false } : d)));
  }, [relabel]);

  // Apply each removal event exactly once (the feed also changes for unrelated events).
  const handled = useRef<number>(-1);
  useEffect(() => {
    const removed = feed.find((f) => f.type === "darts_removed");
    if (!removed || removed.id <= handled.current) return;
    handled.current = removed.id;
    const ids = new Set<string>(removed.data?.dart_ids ?? []);
    setDarts((cur) => (removed.data?.board_clear ? [] : cur.filter((c) => !ids.has(c.id))));
  }, [feed]);

  return darts;
}
