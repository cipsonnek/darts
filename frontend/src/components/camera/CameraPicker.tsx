import clsx from "clsx";
import { RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";
import { Badge, Button, ErrorNote, Modal } from "@/components/ui";
import { useAction } from "@/hooks/useApi";
import { api } from "@/lib/api";
import type { CameraInfo } from "@/lib/types";

interface Device {
  index: number;
  opened: boolean;
  in_use_by: string | null;
  width?: number | null;
  height?: number | null;
  frames?: number;
  likely_virtual_or_blank?: boolean;
}

interface AssignResult {
  camera_id: string;
  device: number;
  swapped_with: string | null;
  recalibrate: string[];
}

/** Pick which USB device feeds each camera slot, by looking at a picture from every device.
 *  Choosing a device another slot uses swaps the two (calibrations move with them). */
export function CameraPicker({ cams, onClose }: { cams: CameraInfo[]; onClose: () => void }) {
  const usb = cams.filter((c) => !c.synthetic && c.config.source.type === "opencv");
  const [devices, setDevices] = useState<Device[] | null>(null);
  const [showBlank, setShowBlank] = useState(false);
  const [tick, setTick] = useState(0);
  const [done, setDone] = useState<AssignResult | null>(null);
  const probe = useAction(async () => setDevices(await api.get<Device[]>("/api/cameras/probe")));
  const assign = useAction(async (cameraId: string, device: number) => {
    setDone(await api.post<AssignResult>(`/api/cameras/${cameraId}/device`, { device }));
    await probe.run();
    setTick((t) => t + 1);
  });

  useEffect(() => {
    probe.run();
    const t = setInterval(() => setTick((x) => x + 1), 3000);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const name = (id: string | null) => cams.find((c) => c.id === id)?.name ?? id ?? "";
  const shown = devices?.filter((d) => showBlank || !d.likely_virtual_or_blank) ?? [];
  const hidden = (devices?.length ?? 0) - shown.length;

  return (
    <Modal open onClose={onClose} wide title="Wybierz kamery">
      <p className="mb-3 text-sm text-[var(--muted)]">
        Każdy obrazek to jedno urządzenie USB. Kliknij, którą kamerą ma być. Jeśli to urządzenie jest już używane przez
        inną kamerę, zamienią się miejscami razem z kalibracją.
      </p>
      <ErrorNote error={probe.error ?? assign.error} />
      {done && (
        <div className="mb-3 rounded-xl border border-[var(--border)] bg-[var(--surface-2)] px-3 py-2 text-sm">
          {name(done.camera_id)} → urządzenie {done.device}.{" "}
          {done.swapped_with
            ? `Zamieniono z: ${name(done.swapped_with)} (kalibracje zamienione).`
            : done.recalibrate.length > 0 ? "To inna kamera — skalibruj ją ponownie na stronie Kalibracja." : ""}
        </div>
      )}
      {!devices && <div className="py-8 text-center text-sm text-[var(--muted)]">Wyszukiwanie urządzeń…</div>}
      {devices && shown.length === 0 && <div className="py-8 text-center text-sm text-[var(--muted)]">Nie znaleziono kamer USB.</div>}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {shown.map((d) => (
          <div key={d.index} className={clsx("overflow-hidden rounded-xl border", d.in_use_by ? "border-[var(--accent)]" : "border-[var(--border)]")}>
            <div className="relative aspect-video bg-black">
              <img src={`/api/cameras/devices/${d.index}/preview.jpg?width=480&_=${tick}`} alt={`Urządzenie ${d.index}`}
                className="h-full w-full object-contain" onError={(e) => (e.currentTarget.style.visibility = "hidden")}
                onLoad={(e) => (e.currentTarget.style.visibility = "visible")} />
              <div className="absolute top-2 left-2 flex gap-1">
                <Badge tone={d.in_use_by ? "accent" : "info"}>Urządzenie {d.index}</Badge>
                {d.likely_virtual_or_blank && <Badge tone="warn">puste/wirtualne?</Badge>}
              </div>
            </div>
            <div className="p-2.5">
              <div className="mb-2 text-xs text-[var(--muted)]">
                {d.in_use_by ? <>Teraz: <b className="text-[var(--text)]">{name(d.in_use_by)}</b></> : "Nieużywane"}
                {d.width ? ` · ${d.width}×${d.height}` : ""}
              </div>
              <div className="flex flex-wrap gap-1.5">
                {usb.map((c) => (
                  <Button key={c.id} size="sm" variant={d.in_use_by === c.id ? "primary" : "secondary"}
                    disabled={assign.busy || d.in_use_by === c.id} onClick={() => assign.run(c.id, d.index)}>
                    {c.name.replace(/\s*\(.*\)$/, "")}
                  </Button>
                ))}
              </div>
            </div>
          </div>
        ))}
      </div>
      <div className="mt-4 flex items-center gap-2">
        {hidden > 0 && <Button size="sm" variant="ghost" onClick={() => setShowBlank(true)}>Pokaż puste urządzenia ({hidden})</Button>}
        <div className="flex-1" />
        <Button size="sm" onClick={() => probe.run()} disabled={probe.busy}><RefreshCw size={14} /> Odśwież</Button>
        <Button size="sm" variant="primary" onClick={onClose}>Gotowe</Button>
      </div>
    </Modal>
  );
}
