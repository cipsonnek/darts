import { useMemo, useRef } from "react";
import { covEllipse, DEFAULT_BOARD, polarToXY, scoreAt, toSvg, wedgePath } from "@/lib/board";
import type { BoardInfo } from "@/lib/types";
import { usePrefs } from "@/store/prefs";

export interface BoardMarker {
  id: string;
  x_mm: number;
  y_mm: number;
  label?: string;
  color?: string;
  cov?: number[][];
  uncertain?: boolean;
  ghost?: boolean;
  shape?: "dot" | "cross";
}

interface Props {
  board?: BoardInfo;
  markers?: BoardMarker[];
  heat?: { x_mm: number; y_mm: number }[];
  onClick?: (p: { x_mm: number; y_mm: number; label: string }) => void;
  highlight?: string[]; // labels to highlight (e.g. checkout route)
  className?: string;
  numbers?: boolean;
}

const PALETTES = {
  classic: { black: "#1d1d1f", white: "#e9dfc6", red: "#d0263b", green: "#16894a", wire: "#b8bcc4", surround: "#121214", number: "#f3f3f3" },
  minimal: { black: "#2a2f3a", white: "#3a4150", red: "#c2414f", green: "#2f8a5a", wire: "#5b6375", surround: "#161a22", number: "#cfd6e6" },
  neon: { black: "#0f1117", white: "#1d2230", red: "#ff2d55", green: "#00e68a", wire: "#3d4660", surround: "#07080c", number: "#9fe8ff" },
};

export function Dartboard({ board = DEFAULT_BOARD, markers = [], heat, onClick, highlight = [], className, numbers }: Props) {
  const style = usePrefs((s) => s.boardStyle);
  const showNumbers = usePrefs((s) => s.showBoardNumbers);
  const showUncertainty = usePrefs((s) => s.showUncertainty);
  const pal = PALETTES[style];
  const svgRef = useRef<SVGSVGElement>(null);
  const R = board.board_radius_mm;
  const rr = board.radii_mm;
  const half = board.sector_angle_deg / 2;

  const wedges = useMemo(() => {
    const out: { d: string; fill: string; label: string }[] = [];
    board.sector_order.forEach((sector, i) => {
      const a0 = i * board.sector_angle_deg - half;
      const a1 = a0 + board.sector_angle_deg;
      const even = i % 2 === 0;
      const single = even ? pal.black : pal.white;
      const ring = even ? pal.red : pal.green;
      out.push({ d: wedgePath(rr.outer_bull, rr.triple_inner, a0, a1), fill: single, label: `S${sector}` });
      out.push({ d: wedgePath(rr.triple_inner, rr.triple_outer, a0, a1), fill: ring, label: `T${sector}` });
      out.push({ d: wedgePath(rr.triple_outer, rr.double_inner, a0, a1), fill: single, label: `S${sector}` });
      out.push({ d: wedgePath(rr.double_inner, rr.double_outer, a0, a1), fill: ring, label: `D${sector}` });
    });
    return out;
  }, [board, pal, half, rr]);

  const heatCells = useMemo(() => {
    if (!heat?.length) return null;
    const cell = 8;
    const counts = new Map<string, number>();
    for (const p of heat) {
      const k = `${Math.floor(p.x_mm / cell)},${Math.floor(p.y_mm / cell)}`;
      counts.set(k, (counts.get(k) ?? 0) + 1);
    }
    const max = Math.max(...counts.values());
    return [...counts.entries()].map(([k, n]) => {
      const [i, j] = k.split(",").map(Number);
      return { x: i * cell, y: (j + 1) * cell, n, a: 0.15 + 0.75 * (n / max), cell };
    });
  }, [heat]);

  function handleClick(e: React.MouseEvent<SVGSVGElement>) {
    if (!onClick || !svgRef.current) return;
    const pt = svgRef.current.createSVGPoint();
    pt.x = e.clientX;
    pt.y = e.clientY;
    const m = svgRef.current.getScreenCTM();
    if (!m) return;
    const p = pt.matrixTransform(m.inverse());
    const x = p.x;
    const y = -p.y;
    onClick({ x_mm: x, y_mm: y, label: scoreAt(board, x, y).label });
  }

  const pad = 8;
  const hl = new Set(highlight);
  return (
    <svg
      ref={svgRef}
      viewBox={`${-R - pad} ${-R - pad} ${2 * (R + pad)} ${2 * (R + pad)}`}
      className={className}
      onClick={handleClick}
      style={{ cursor: onClick ? "crosshair" : undefined, display: "block", width: "100%", height: "100%" }}
      role="img"
      aria-label="Tarcza"
    >
      <circle r={R} fill={pal.surround} />
      {wedges.map((w, i) => (
        <path key={i} d={w.d} fill={w.fill} stroke={pal.wire} strokeWidth={board.wire_width_mm * 0.6}
          opacity={hl.size && !hl.has(w.label) ? 0.35 : 1} />
      ))}
      <circle r={rr.outer_bull} fill={pal.green} stroke={pal.wire} strokeWidth={0.7} opacity={hl.size && !hl.has("25") ? 0.35 : 1} />
      <circle r={rr.inner_bull} fill={pal.red} stroke={pal.wire} strokeWidth={0.7} opacity={hl.size && !hl.has("BULL") ? 0.35 : 1} />
      {(numbers ?? showNumbers) &&
        board.sector_order.map((s, i) => {
          const [x, y] = toSvg(...polarToXY((rr.double_outer + R) / 2, i * board.sector_angle_deg));
          return (
            <text key={s} x={x} y={y} fill={pal.number} fontSize={19} fontWeight={700} textAnchor="middle" dominantBaseline="central"
              style={{ fontFamily: "var(--font-display)", userSelect: "none" }}>
              {s}
            </text>
          );
        })}
      {heatCells?.map((c, i) => (
        <rect key={i} x={c.x} y={-c.y} width={c.cell} height={c.cell} fill="var(--accent)" opacity={c.a} />
      ))}
      {markers.map((m) => {
        const [x, y] = toSvg(m.x_mm, m.y_mm);
        const color = m.color ?? (m.uncertain ? "var(--warn)" : "var(--accent)");
        const ell = m.cov && showUncertainty ? covEllipse(m.cov) : null;
        return (
          <g key={m.id} opacity={m.ghost ? 0.45 : 1} style={{ pointerEvents: "none" }}>
            {ell && ell.rx > 0.3 && (
              <ellipse cx={x} cy={y} rx={ell.rx} ry={ell.ry} transform={`rotate(${-ell.angle} ${x} ${y})`}
                fill={color} fillOpacity={0.18} stroke={color} strokeOpacity={0.7} strokeWidth={0.8} />
            )}
            {m.shape === "cross" ? (
              <g stroke={color} strokeWidth={2.2}>
                <line x1={x - 5} y1={y - 5} x2={x + 5} y2={y + 5} />
                <line x1={x - 5} y1={y + 5} x2={x + 5} y2={y - 5} />
              </g>
            ) : (
              <>
                <circle cx={x} cy={y} r={5.5} fill={color} stroke="#000" strokeWidth={1.2} />
                <circle cx={x} cy={y} r={1.6} fill="#fff" />
              </>
            )}
            {m.label && (
              <text x={x + 8} y={y - 8} fontSize={14} fontWeight={800} fill="#fff" stroke="#000" strokeWidth={3} paintOrder="stroke"
                style={{ fontFamily: "var(--font-display)" }}>
                {m.label}
              </text>
            )}
          </g>
        );
      })}
    </svg>
  );
}
