import clsx from "clsx";
import { Plus, Send } from "lucide-react";
import { useState } from "react";
import { Link, useSearchParams } from "react-router";
import { Badge, Button, Card, Empty, ErrorNote, inputCls, PageHeader, Tabs } from "@/components/ui";
import { useAction, useApi } from "@/hooks/useApi";
import { api } from "@/lib/api";
import { TicketForm } from "../forms";
import {
  ago, dateTime, PRIORITY_TONE, STATUS_TONE, TICKET_CATEGORY, TICKET_PRIORITY, TICKET_STATUS, type Ticket,
} from "../lib";

const AUTHOR_KEY = "dartsense.operatorName";

function authorName(): string {
  try {
    return localStorage.getItem(AUTHOR_KEY) ?? "";
  } catch {
    return "";
  }
}

function saveAuthor(name: string) {
  try {
    localStorage.setItem(AUTHOR_KEY, name);
  } catch {
    /* storage unavailable */
  }
}

function statusChange(s: string): string {
  const [a, b] = s.split("->");
  return `${TICKET_STATUS[a] ?? a} → ${TICKET_STATUS[b] ?? b}`;
}

type Filter = "active" | "open" | "in_progress" | "waiting" | "closed" | "";

export default function Tickets() {
  const [params, setParams] = useSearchParams();
  const [filter, setFilter] = useState<Filter>("active");
  const { data: tickets, error, reload } = useApi<Ticket[]>(`/api/fleet/tickets${filter ? `?status=${filter}` : ""}`, 30_000);
  const selected = Number(params.get("id")) || null;
  const creating = params.get("new") === "1";
  const select = (id: number | null) => setParams(id ? { id: String(id) } : {});

  return (
    <div>
      <PageHeader title="Serwis" subtitle="Zgłoszenia awarii, przeglądy i montaże."
        actions={<Button variant="primary" onClick={() => setParams({ new: "1" })}><Plus size={16} /> Nowe zgłoszenie</Button>} />
      <div className="mb-4">
        <Tabs value={filter} onChange={setFilter} items={[
          { id: "active", label: "Otwarte" }, { id: "open", label: "Nowe" }, { id: "in_progress", label: "W toku" },
          { id: "waiting", label: "Czekają" }, { id: "closed", label: "Zamknięte" }, { id: "", label: "Wszystkie" },
        ]} />
      </div>
      <ErrorNote error={error} />
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
        <Card pad={false}>
          {!tickets?.length ? <div className="p-4"><Empty title="Brak zgłoszeń" /></div> : (
            <ul className="flex flex-col divide-y divide-[var(--border)]">
              {tickets.map((t) => (
                <li key={t.id}>
                  <button onClick={() => select(t.id)}
                    className={clsx("flex w-full flex-col gap-1 px-4 py-3 text-left transition hover:bg-[var(--surface-2)]",
                      t.id === selected && "bg-[var(--surface-2)] shadow-[inset_3px_0_0_var(--accent)]")}>
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-[var(--muted)]">#{t.id}</span>
                      <span className="min-w-0 flex-1 truncate font-semibold">{t.title}</span>
                      <Badge tone={PRIORITY_TONE[t.priority]}>{TICKET_PRIORITY[t.priority]}</Badge>
                      <Badge tone={STATUS_TONE[t.status]}>{TICKET_STATUS[t.status]}</Badge>
                    </div>
                    <div className="text-sm text-[var(--muted)]">
                      {TICKET_CATEGORY[t.category]} · {t.venue_name ?? "—"}{t.board_name && ` · ${t.board_name}`} · {ago(t.created_at)}
                      {t.assignee && ` · ${t.assignee}`}
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Card>
        {selected ? <TicketDetail key={selected} id={selected} onChanged={reload} /> : (
          <Card><Empty title="Wybierz zgłoszenie">Kliknij zgłoszenie na liście, żeby zobaczyć szczegóły i historię.</Empty></Card>
        )}
      </div>
      {creating && (
        <TicketForm
          initial={{ board_id: params.get("board") ?? "", venue_id: params.get("venue") ?? "", title: params.get("title") ?? "",
            priority: params.get("priority") ?? "normal", reporter: authorName() }}
          onClose={() => setParams({})}
          onSaved={(t) => { reload(); select(t.id); }} />
      )}
    </div>
  );
}

function TicketDetail({ id, onChanged }: { id: number; onChanged: () => void }) {
  const { data: t, error, setData } = useApi<Ticket>(`/api/fleet/tickets/${id}`);
  const [text, setText] = useState("");
  const [author, setAuthor] = useState(authorName());
  const update = useAction(async (body: Record<string, unknown>) => {
    setData(await api.patch<Ticket>(`/api/fleet/tickets/${id}`, { ...body, author }));
    onChanged();
  });
  const comment = useAction(async () => {
    saveAuthor(author);
    setData(await api.post<Ticket>(`/api/fleet/tickets/${id}/comments`, { text, author }));
    setText("");
    onChanged();
  });
  if (error) return <ErrorNote error={error} />;
  if (!t) return null;
  return (
    <Card className="xl:sticky xl:top-6 xl:self-start">
      <div className="flex flex-col gap-4">
        <div>
          <div className="text-sm text-[var(--muted)]">#{t.id} · {TICKET_CATEGORY[t.category]} · zgłoszone {dateTime(t.created_at)}{t.reporter && ` przez ${t.reporter}`}</div>
          <h2 className="mt-1 font-display text-2xl font-bold">{t.title}</h2>
          <div className="mt-1 text-sm">
            {t.venue_id && <Link className="hover:text-[var(--accent)]" to={`/operator/venues/${t.venue_id}`}>{t.venue_name}</Link>}
            {t.board_id && <> · <Link className="hover:text-[var(--accent)]" to={`/operator/boards/${t.board_id}`}>{t.board_name}</Link></>}
          </div>
        </div>
        {t.description && <p className="whitespace-pre-wrap rounded-xl bg-[var(--surface-2)] p-3 text-sm">{t.description}</p>}
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          <label className="flex flex-col gap-1 text-sm">
            <span className="font-medium text-[var(--muted)]">Status</span>
            <select className={inputCls} value={t.status} onChange={(e) => update.run({ status: e.target.value })}>
              {Object.entries(TICKET_STATUS).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-sm">
            <span className="font-medium text-[var(--muted)]">Priorytet</span>
            <select className={inputCls} value={t.priority} onChange={(e) => update.run({ priority: e.target.value })}>
              {Object.entries(TICKET_PRIORITY).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
            </select>
          </label>
          <label className="col-span-2 flex flex-col gap-1 text-sm sm:col-span-1">
            <span className="font-medium text-[var(--muted)]">Przypisane do</span>
            <input className={inputCls} defaultValue={t.assignee} placeholder="technik"
              onBlur={(e) => e.target.value !== t.assignee && update.run({ assignee: e.target.value })} />
          </label>
        </div>
        <ErrorNote error={update.error} />
        <div>
          <div className="mb-2 text-sm font-semibold">Historia</div>
          {!t.comments?.length ? <div className="text-sm text-[var(--muted)]">Brak wpisów.</div> : (
            <ol className="flex flex-col gap-3 border-l-2 border-[var(--border)] pl-4">
              {t.comments.map((c) => (
                <li key={c.id} className="text-sm">
                  <div className="text-xs text-[var(--muted)]">{c.author || "—"} · {dateTime(c.created_at)}</div>
                  {c.status_change && <div className="font-semibold text-[var(--accent)]">{statusChange(c.status_change)}</div>}
                  {c.text && <div className="whitespace-pre-wrap">{c.text}</div>}
                </li>
              ))}
            </ol>
          )}
        </div>
        <form className="flex flex-col gap-2" onSubmit={(e) => { e.preventDefault(); if (text.trim()) comment.run(); }}>
          <textarea className={inputCls} rows={2} value={text} onChange={(e) => setText(e.target.value)} placeholder="Dodaj komentarz…" />
          <div className="flex gap-2">
            <input className={clsx(inputCls, "flex-1")} value={author} onChange={(e) => setAuthor(e.target.value)} placeholder="Twoje imię" />
            <Button variant="primary" disabled={!text.trim() || comment.busy}><Send size={15} /> Dodaj</Button>
          </div>
          <ErrorNote error={comment.error} />
        </form>
      </div>
    </Card>
  );
}
