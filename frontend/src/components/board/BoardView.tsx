import { Component, lazy, Suspense, useMemo, type ReactNode } from "react";
import type { BoardInfo } from "@/lib/types";
import { usePrefs } from "@/store/prefs";
import { Dartboard, type BoardMarker } from "./Dartboard";
import { webglAvailable } from "./webgl";

// three.js is large: load it only when a 3D board is actually shown.
const Board3D = lazy(() => import("./Board3D"));

class Fallback extends Component<{ fallback: ReactNode; children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    return this.state.failed ? this.props.fallback : this.props.children;
  }
}

/** The board for display: 3D when the "3d" style is chosen and the browser has WebGL,
 *  otherwise (and while the 3D code loads, or if it fails) the flat SVG board. */
export function BoardView({ board, markers, highlight, interactive = true }: {
  board?: BoardInfo; markers?: BoardMarker[]; highlight?: string[]; interactive?: boolean;
}) {
  const style = usePrefs((s) => s.boardStyle);
  const gl = useMemo(webglAvailable, []);
  const flat = <Dartboard board={board} markers={markers} highlight={highlight} />;
  if (style !== "3d" || !gl) return flat;
  return (
    <Fallback fallback={flat}>
      <Suspense fallback={flat}>
        <Board3D board={board} markers={markers} highlight={highlight} interactive={interactive} />
      </Suspense>
    </Fallback>
  );
}
