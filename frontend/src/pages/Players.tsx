import { useState } from "react";
import { Link } from "react-router";
import { Button, Card, Empty, ErrorNote, Field, inputCls, PageHeader } from "@/components/ui";
import { useAction, useApi } from "@/hooks/useApi";
import { api } from "@/lib/api";
import type { Player } from "@/lib/types";

const COLORS = ["#e8324a", "#2ecc71", "#3b82f6", "#f5b942", "#a855f7", "#14b8a6", "#f97316", "#ec4899"];

export default function Players() {
  const [archived, setArchived] = useState(false);
  const { data: players, reload, error } = useApi<Player[]>(`/api/players?include_archived=${archived}`);
  const [name, setName] = useState("");
  const [color, setColor] = useState(COLORS[0]);
  const [editing, setEditing] = useState<Player | null>(null);

  const add = useAction(async () => {
    await api.post("/api/players", { name, color });
    setName("");
    setColor(COLORS[(players?.length ?? 0) % COLORS.length]);
    reload();
  });

  const save = useAction(async (p: Player) => {
    await api.patch(`/api/players/${p.id}`, { name: p.name, nickname: p.nickname || null, color: p.color, archived: p.archived });
    setEditing(null);
    reload();
  });

  return (
    <div>
      <PageHeader title="Players" actions={<Button variant="ghost" onClick={() => setArchived(!archived)}>{archived ? "Hide archived" : "Show archived"}</Button>} />
      <div className="grid gap-4 lg:grid-cols-[360px_minmax(0,1fr)]">
        <Card title="Add player">
          <form className="flex flex-col gap-3" onSubmit={(e) => { e.preventDefault(); add.run(); }}>
            <Field label="Name"><input className={inputCls} value={name} maxLength={64} onChange={(e) => setName(e.target.value)} required /></Field>
            <ColorPicker value={color} onChange={setColor} />
            <ErrorNote error={add.error} />
            <Button variant="primary" disabled={!name.trim() || add.busy}>Add</Button>
          </form>
        </Card>
        <Card title="All players">
          <ErrorNote error={error} />
          {!players?.length ? <Empty title="No players yet">Add the people who throw on this board.</Empty> : (
            <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
              {players.map((p) => (
                <div key={p.id} className="flex items-center gap-3 rounded-xl border border-[var(--border)] bg-[var(--surface-2)] p-3">
                  <div className="grid h-11 w-11 shrink-0 place-items-center rounded-full font-display text-lg font-bold text-white" style={{ background: p.color }}>
                    {p.name.slice(0, 1).toUpperCase()}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="truncate font-semibold">{p.name} {p.archived && <span className="text-xs text-[var(--muted)]">(archived)</span>}</div>
                    <Link to={`/stats?player=${p.id}`} className="text-xs text-[var(--accent)]">Statistics →</Link>
                  </div>
                  <Button size="sm" variant="ghost" onClick={() => setEditing({ ...p })}>Edit</Button>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>
      {editing && (
        <div className="fixed inset-0 z-50 grid place-items-center bg-black/60 p-4" onClick={() => setEditing(null)}>
          <div className="w-full max-w-sm rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-5" onClick={(e) => e.stopPropagation()}>
            <div className="mb-3 font-display text-lg font-bold">Edit player</div>
            <div className="flex flex-col gap-3">
              <Field label="Name"><input className={inputCls} value={editing.name} onChange={(e) => setEditing({ ...editing, name: e.target.value })} /></Field>
              <Field label="Nickname"><input className={inputCls} value={editing.nickname ?? ""} onChange={(e) => setEditing({ ...editing, nickname: e.target.value })} /></Field>
              <ColorPicker value={editing.color} onChange={(c) => setEditing({ ...editing, color: c })} />
              <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={editing.archived} onChange={(e) => setEditing({ ...editing, archived: e.target.checked })} /> Archived</label>
              <ErrorNote error={save.error} />
              <div className="flex gap-2">
                <Button className="flex-1" onClick={() => setEditing(null)}>Cancel</Button>
                <Button className="flex-1" variant="primary" onClick={() => save.run(editing)}>Save</Button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function ColorPicker({ value, onChange }: { value: string; onChange: (c: string) => void }) {
  return (
    <Field label="Colour">
      <div className="flex flex-wrap items-center gap-2">
        {COLORS.map((c) => (
          <button type="button" key={c} onClick={() => onChange(c)} aria-label={c}
            className={`h-7 w-7 rounded-full border-2 ${value === c ? "border-white" : "border-transparent"}`} style={{ background: c }} />
        ))}
        <input type="color" value={value} onChange={(e) => onChange(e.target.value)} className="h-8 w-10 cursor-pointer rounded border border-[var(--border)] bg-transparent" />
      </div>
    </Field>
  );
}
