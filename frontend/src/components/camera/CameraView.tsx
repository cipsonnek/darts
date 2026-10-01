import clsx from "clsx";
import { useEffect, useRef, useState } from "react";
import { streamUrl } from "@/lib/api";
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

/** Live MJPEG stream. Server-side encoding at the requested size/fps; reconnects on error. */
export function CameraView({ cameraId, name, overlay = [], view = "raw", width = 640, fps, health, className, onImageClick, children }: Props) {
  const [nonce, setNonce] = useState(0);
  const [failed, setFailed] = useState(false);
  const imgRef = useRef<HTMLImageElement>(null);
  const src = streamUrl(cameraId, { overlay, width, fps, view }) + `&n=${nonce}`;

  useEffect(() => {
    if (!failed) return;
    const t = setTimeout(() => {
      setFailed(false);
      setNonce((n) => n + 1);
    }, 2000);
    return () => clearTimeout(t);
  }, [failed]);

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
      {!failed ? (
        <img ref={imgRef} src={src} alt={`Camera ${cameraId}`} className={clsx("block h-auto w-full", onImageClick && "cursor-crosshair")}
          onError={() => setFailed(true)} onClick={click} draggable={false} />
      ) : (
        <div className="grid aspect-video place-items-center text-sm text-[var(--muted)]">Reconnecting to {cameraId}…</div>
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
