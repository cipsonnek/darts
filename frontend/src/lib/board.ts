// Board drawing / hit-testing helpers in board millimetres (y up, θ clockwise from the 20),
// parameterised by the geometry served at /api/board — no dimensions are hard-coded here.

import type { BoardInfo } from "./types";

export const DEFAULT_BOARD: BoardInfo = {
  radii_mm: { inner_bull: 6.35, outer_bull: 15.9, triple_inner: 99, triple_outer: 107, double_inner: 162, double_outer: 170 },
  board_radius_mm: 225.5,
  sector_order: [20, 1, 18, 4, 13, 6, 10, 15, 2, 17, 3, 19, 7, 16, 8, 11, 14, 9, 12, 5],
  sector_angle_deg: 18,
  wire_width_mm: 1.2,
};

export function polarToXY(r: number, thetaDeg: number): [number, number] {
  const t = (thetaDeg * Math.PI) / 180;
  return [r * Math.sin(t), r * Math.cos(t)];
}

/** Board mm (y up) → SVG coordinates (y down), centred at 0. */
export function toSvg(x: number, y: number): [number, number] {
  return [x, -y];
}

export function scoreAt(b: BoardInfo, x: number, y: number): { label: string; sector: number; multiplier: number } {
  const r = Math.hypot(x, y);
  const theta = ((Math.atan2(x, y) * 180) / Math.PI + 360) % 360;
  const rr = b.radii_mm;
  const half = b.sector_angle_deg / 2;
  const idx = Math.floor(((theta + half) % 360) / b.sector_angle_deg) % b.sector_order.length;
  const sector = b.sector_order[idx];
  if (r <= rr.inner_bull) return { label: "BULL", sector: 25, multiplier: 2 };
  if (r <= rr.outer_bull) return { label: "25", sector: 25, multiplier: 1 };
  if (r > rr.double_outer) return { label: "MISS", sector: 0, multiplier: 0 };
  if (r >= rr.double_inner) return { label: `D${sector}`, sector, multiplier: 2 };
  if (r >= rr.triple_inner && r <= rr.triple_outer) return { label: `T${sector}`, sector, multiplier: 3 };
  return { label: `S${sector}`, sector, multiplier: 1 };
}

/** SVG path of an annular wedge between radii r0..r1 and angles a0..a1 (clockwise from up). */
export function wedgePath(r0: number, r1: number, a0: number, a1: number): string {
  const p = (r: number, a: number) => toSvg(...polarToXY(r, a));
  const [x1, y1] = p(r1, a0);
  const [x2, y2] = p(r1, a1);
  const [x3, y3] = p(r0, a1);
  const [x4, y4] = p(r0, a0);
  const large = a1 - a0 > 180 ? 1 : 0;
  return `M${x1} ${y1}A${r1} ${r1} 0 ${large} 1 ${x2} ${y2}L${x3} ${y3}A${r0} ${r0} 0 ${large} 0 ${x4} ${y4}Z`;
}

/** 1-σ ellipse (rx, ry, rotation°) of a 2x2 covariance, scaled by k (k=2.45 ≈ 95 %). */
export function covEllipse(cov: number[][], k = 2.45): { rx: number; ry: number; angle: number } {
  const a = cov[0][0];
  const b = cov[0][1];
  const c = cov[1][1];
  const tr = (a + c) / 2;
  const det = Math.sqrt(Math.max(((a - c) / 2) ** 2 + b * b, 0));
  const l1 = tr + det;
  const l2 = Math.max(tr - det, 0);
  const angle = (Math.atan2(l1 - a, b || 1e-12) * 180) / Math.PI;
  return { rx: k * Math.sqrt(l1), ry: k * Math.sqrt(l2), angle };
}
