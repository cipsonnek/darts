import clsx from "clsx";
import { useEffect, useRef, useState } from "react";
import { snapshotUrl } from "@/lib/api";
import type { CameraHealth } from "@/lib/types";

interface Props {
  cameraId: string;
  name?: string;
  overlay?: string[];
  view?: "raw" | "undistorted" | "topdown";
  width?: number;
  fps?: number;
  health?: CameraHealth | null;
  className?: string;
  onImageClick?: (p: { x: number; y: number; naturalWidth: number; naturalHeight: number }) => void;
  children?: React.ReactNode; // overlay content (absolute positioned)
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

/** Live camera view, fetched frame by frame. Not an MJPEG stream on purpose: a stream holds
 *  one of the browser's ~6 connections per host for as long as it is open (and browsers do
 *  not always close it when the image unmounts), so a few camera views starved every other
 *  request and froze the UI. Short requests cannot pile up. */
export function CameraView({ cameraId, name, overlay = [], view = "raw", width = 640, fps, health, className, onImageClick, children }: Props) {
  const [src, setSrc] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const imgRef = useRef<HTMLImageElement>(null);
  const overlayKey = overlay.join(",");

  useEffect(() => {
    let stop = false;
    let current: string | null = null;
    const ctrl = new AbortController();
    const period = 1000 / Math.max(0.5, fps ?? 10);
    (async () => {
      while (!stop) {
        if (document.hidden) {
          await sleep(500);
          continue;
        }
        const t0 = performance.now();
        try {
          const url = snapshotUrl(cameraId, { overlay: overlayKey ? overlayKey.split(",") : [], width, view }, Date.now());
          const res = await fetch(url, { signal: ctrl.signal, cache: "no-store" });
          if (!res.ok) throw new Error(String(res.status));
          const blob = await res.blob();
          if (stop) break;
          const next = URL.createObjectURL(blob);
          setSrc(next);
          setFailed(false);
          if (current) URL.revokeObjectURL(current);
          current = next;
        } catch {
          if (stop) break;
          setFailed(true);
          await sleep(2000);
          continue;
        }
        await sleep(Math.max(0, period - (performance.now() - t0)));
      }
    })();
    return () => {
      stop = true;
      ctrl.abort();
      if (current) URL.revokeObjectURL(current);
    };
  }, [cameraId, overlayKey, width, fps, view]);

  function click(e: React.MouseEvent<HTMLImageElement>) {
    const img = imgRef.current;
    if (!img || !onImageClick) return;
    const r = img.getBoundingClientRect();
    // The stream may be downscaled: report coordinates in the stream's own pixels; callers
    // convert to camera pixels using the camera's full width.
    onImageClick({ x: ((e.clientX - r.left) / r.width) * img.naturalWidth, y: ((e.clientY - r.top) / r.height) * img.naturalHeight,
      naturalWidth: img.naturalWidth, naturalHeight: img.naturalHeight });
  }

  return (
    <div className={clsx("relative overflow-hidden rounded-xl border border-[var(--border)] bg-black", className)}>
      {src && !failed ? (
        <img ref={imgRef} src={src} alt={`Camera ${cameraId}`} className={clsx("block h-auto w-full", onImageClick && "cursor-crosshair")}
          onClick={click} draggable={false} />
      ) : (
        <div className="grid aspect-video place-items-center text-sm text-[var(--muted)]">{failed ? `Reconnecting to ${cameraId}…` : "Loading…"}</div>
      )}
      <div className="pointer-events-none absolute inset-x-0 top-0 flex items-center justify-between bg-gradient-to-b from-black/70 to-transparent px-3 py-1.5 text-xs text-white">
        <span className="font-semibold">{name ?? cameraId}</span>
        {health && (
          <span className={clsx(!health.connected && "text-[var(--bad)]", health.low_fps && "text-[var(--warn)]")}>
            {health.connected ? `${health.fps.toFixed(1)} fps` : health.state}
          </span>
        )}
      </div>
      {children}
    </div>
  );
}
