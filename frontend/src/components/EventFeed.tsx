import clsx from "clsx";
import { useLive } from "@/store/live";

export function EventFeed({ limit = 12 }: { limit?: number }) {
  const feed = useLive((s) => s.feed);
  if (!feed.length) return <div className="py-4 text-center text-sm text-[var(--muted)]">No events yet.</div>;
  return (
    <ul className="flex flex-col gap-1.5 text-sm">
      {feed.slice(0, limit).map((f) => (
        <li key={f.id} className="flex items-baseline gap-2">
          <span className="w-16 shrink-0 text-xs tabular-nums text-[var(--muted)]">{new Date(f.ts).toLocaleTimeString()}</span>
          <span className={clsx("h-2 w-2 shrink-0 rounded-full",
            f.tone === "good" && "bg-[var(--good)]", f.tone === "warn" && "bg-[var(--warn)]",
            f.tone === "bad" && "bg-[var(--bad)]", f.tone === "info" && "bg-[var(--muted)]")} />
          <span>{f.text}</span>
        </li>
      ))}
    </ul>
  );
}
