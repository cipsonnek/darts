import { Check, Copy, MapPin, Search } from "lucide-react";
import { useState } from "react";
import { Button, ErrorNote, Field, inputCls, Modal, Toggle } from "@/components/ui";
import { useAction, useApi } from "@/hooks/useApi";
import { api } from "@/lib/api";
import {
  BOARD_STATUS, TICKET_CATEGORY, TICKET_PRIORITY, VENUE_KIND, type Board, type Ticket, type Venue, type VenueRow,
} from "./lib";
import { LocationPicker } from "./VenueMap";

const EMPTY_VENUE: Partial<Venue> = {
  name: "", kind: "bar", address: "", city: "", postal_code: "", lat: null, lng: null, contact_name: "", phone: "",
  email: "", opening_hours: "", price_per_game: 5, venue_share_pct: 50, notes: "", active: true,
};

/** Create or edit a venue. Location: click the map, or look the address up in OpenStreetMap. */
export function VenueForm({ venue, onClose, onSaved }: { venue?: Venue; onClose: () => void; onSaved: (v: Venue) => void }) {
  const [f, setF] = useState<Partial<Venue>>(venue ?? EMPTY_VENUE);
  const [found, setFound] = useState<string | null>(null);
  const set = <K extends keyof Venue>(k: K, v: Venue[K] | null) => setF((cur) => ({ ...cur, [k]: v }));
  const save = useAction(async () => {
    const body = { ...f, price_per_game: Number(f.price_per_game), venue_share_pct: Number(f.venue_share_pct) };
    onSaved(venue ? await api.patch<Venue>(`/api/fleet/venues/${venue.id}`, body) : await api.post<Venue>("/api/fleet/venues", body));
  });
  const geocode = useAction(async () => {
    const q = [f.address, f.postal_code, f.city, "Polska"].filter(Boolean).join(", ");
    const res = await fetch(`https://nominatim.openstreetmap.org/search?format=json&limit=1&q=${encodeURIComponent(q)}`, {
      headers: { "Accept-Language": "pl" },
    });
    const hits = (await res.json()) as { lat: string; lon: string; display_name: string }[];
    if (!hits.length) throw new Error("Nie znaleziono adresu — zaznacz miejsce na mapie.");
    setF((cur) => ({ ...cur, lat: Number(Number(hits[0].lat).toFixed(5)), lng: Number(Number(hits[0].lon).toFixed(5)) }));
    setFound(hits[0].display_name);
  });
  const share = Number(f.venue_share_pct ?? 0);
  return (
    <Modal open onClose={onClose} title={venue ? `Edycja: ${venue.name}` : "Nowy lokal"} wide>
      <form className="grid gap-5 lg:grid-cols-2" onSubmit={(e) => { e.preventDefault(); save.run(); }}>
        <div className="flex flex-col gap-3">
          <div className="grid grid-cols-[1fr_150px] gap-3">
            <Field label="Nazwa lokalu"><input className={inputCls} required maxLength={120} value={f.name ?? ""} onChange={(e) => set("name", e.target.value)} /></Field>
            <Field label="Rodzaj">
              <select className={inputCls} value={f.kind} onChange={(e) => set("kind", e.target.value)}>
                {Object.entries(VENUE_KIND).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
              </select>
            </Field>
          </div>
          <Field label="Ulica i numer"><input className={inputCls} value={f.address ?? ""} onChange={(e) => set("address", e.target.value)} /></Field>
          <div className="grid grid-cols-[120px_1fr] gap-3">
            <Field label="Kod pocztowy"><input className={inputCls} value={f.postal_code ?? ""} onChange={(e) => set("postal_code", e.target.value)} placeholder="00-000" /></Field>
            <Field label="Miasto"><input className={inputCls} value={f.city ?? ""} onChange={(e) => set("city", e.target.value)} /></Field>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Osoba kontaktowa"><input className={inputCls} value={f.contact_name ?? ""} onChange={(e) => set("contact_name", e.target.value)} /></Field>
            <Field label="Telefon"><input className={inputCls} value={f.phone ?? ""} onChange={(e) => set("phone", e.target.value)} /></Field>
            <Field label="E-mail"><input className={inputCls} type="email" value={f.email ?? ""} onChange={(e) => set("email", e.target.value)} /></Field>
            <Field label="Godziny otwarcia"><input className={inputCls} value={f.opening_hours ?? ""} onChange={(e) => set("opening_hours", e.target.value)} placeholder="pn–nd 16:00–02:00" /></Field>
          </div>
          <div className="rounded-xl border border-[var(--border)] bg-[var(--surface-2)] p-3">
            <div className="mb-2 text-sm font-semibold">Warunki rozliczenia</div>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Cena gry (zł)"><input className={inputCls} type="number" min={0} step={0.5} value={f.price_per_game ?? 0} onChange={(e) => set("price_per_game", Number(e.target.value))} /></Field>
              <Field label="Udział lokalu (%)"><input className={inputCls} type="number" min={0} max={100} step={1} value={f.venue_share_pct ?? 0} onChange={(e) => set("venue_share_pct", Number(e.target.value))} /></Field>
            </div>
            <div className="mt-2 text-xs text-[var(--muted)]">
              Z każdej gry lokal dostaje {share}%, operator {100 - share}%. Nowe stawki dotyczą tylko gier rozegranych od zapisania zmiany.
            </div>
          </div>
          <Field label="Notatki"><textarea className={inputCls} rows={2} value={f.notes ?? ""} onChange={(e) => set("notes", e.target.value)} /></Field>
          {venue && <Toggle checked={!!f.active} onChange={(v) => set("active", v)} label="Lokal aktywny (współpraca trwa)" />}
        </div>
        <div className="flex flex-col gap-2">
          <div className="flex items-center justify-between gap-2">
            <div className="text-sm font-medium text-[var(--muted)]">Lokalizacja — kliknij na mapie</div>
            <Button type="button" size="sm" onClick={() => geocode.run()} disabled={geocode.busy || !(f.city || f.address)}><Search size={14} /> Znajdź adres</Button>
          </div>
          <LocationPicker lat={f.lat ?? null} lng={f.lng ?? null} onPick={(lat, lng) => setF((c) => ({ ...c, lat, lng }))} className="h-80 rounded-xl lg:h-full lg:min-h-80" />
          <div className="flex items-center gap-1.5 text-xs text-[var(--muted)]">
            <MapPin size={13} /> {f.lat != null ? `${f.lat}, ${f.lng}` : "brak współrzędnych"}{found && <span className="truncate"> · {found}</span>}
          </div>
          <ErrorNote error={geocode.error} />
        </div>
        <div className="flex flex-col gap-2 lg:col-span-2">
          <ErrorNote error={save.error} />
          <div className="flex justify-end gap-2">
            <Button type="button" onClick={onClose}>Anuluj</Button>
            <Button variant="primary" disabled={save.busy}>{venue ? "Zapisz zmiany" : "Dodaj lokal"}</Button>
          </div>
        </div>
      </form>
    </Modal>
  );
}

function CopyBox({ text, label }: { text: string; label: string }) {
  const [ok, setOk] = useState(false);
  return (
    <div>
      <div className="mb-1 text-sm font-medium text-[var(--muted)]">{label}</div>
      <div className="flex items-start gap-2 rounded-lg border border-[var(--border)] bg-black/30 p-2">
        <pre className="flex-1 overflow-x-auto font-mono text-xs whitespace-pre-wrap break-all">{text}</pre>
        <Button type="button" size="sm" onClick={() => { navigator.clipboard?.writeText(text).then(() => setOk(true)).catch(() => {}); }}>
          {ok ? <Check size={14} /> : <Copy size={14} />}
        </Button>
      </div>
    </div>
  );
}

/** Shows a freshly generated board key once, with the config to paste on the board. */
export function KeyModal({ board, apiKey, onClose }: { board: { name: string }; apiKey: string; onClose: () => void }) {
  const url = location.origin.replace(/:5173$/, ":8100");
  return (
    <Modal open onClose={onClose} title={`Klucz tarczy ${board.name}`}>
      <div className="flex flex-col gap-4 text-sm">
        <div className="rounded-lg border border-[var(--warn)]/50 bg-[color-mix(in_oklab,var(--warn)_12%,transparent)] p-3 text-[var(--warn)]">
          Klucz jest pokazywany tylko teraz. Jeśli go zgubisz, wygeneruj nowy (stary przestanie działać).
        </div>
        <CopyBox label="Klucz API" text={apiKey} />
        <CopyBox label="Wklej na komputerze tarczy do configs/local.yaml" text={`fleet:\n  url: ${url}\n  board_key: ${apiKey}\n`} />
        <div className="text-[var(--muted)]">Po zapisaniu pliku uruchom ponownie DartSense na tarczy. Pierwszy sygnał pojawi się w ciągu minuty.</div>
        <Button variant="primary" onClick={onClose}>Gotowe</Button>
      </div>
    </Modal>
  );
}

/** Register a board (then show its key) or edit one. */
export function BoardForm({ board, venueId, onClose, onSaved }: {
  board?: Board; venueId?: string; onClose: () => void; onSaved: (b: Board) => void;
}) {
  const { data: venues } = useApi<VenueRow[]>("/api/fleet/venues");
  const [f, setF] = useState({ name: board?.name ?? "", serial: board?.serial ?? "", venue_id: board?.venue_id ?? venueId ?? "",
    status: board?.status ?? "active", notes: board?.notes ?? "" });
  const [created, setCreated] = useState<Board | null>(null);
  const save = useAction(async () => {
    const body = { ...f, venue_id: f.venue_id || null };
    if (board) onSaved(await api.patch<Board>(`/api/fleet/boards/${board.id}`, body));
    else setCreated(await api.post<Board>("/api/fleet/boards", body));
  });
  if (created) return <KeyModal board={created} apiKey={created.api_key!} onClose={() => onSaved(created)} />;
  return (
    <Modal open onClose={onClose} title={board ? `Edycja: ${board.name}` : "Nowa tarcza"}>
      <form className="flex flex-col gap-3" onSubmit={(e) => { e.preventDefault(); save.run(); }}>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Nazwa"><input className={inputCls} required maxLength={80} value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} placeholder="np. KRA-01-1" /></Field>
          <Field label="Numer seryjny"><input className={inputCls} value={f.serial} onChange={(e) => setF({ ...f, serial: e.target.value })} /></Field>
        </div>
        <Field label="Lokal" hint="Zmiana lokalu ustawia nową datę montażu. Gry bez lokalu są darmowe.">
          <select className={inputCls} value={f.venue_id} onChange={(e) => setF({ ...f, venue_id: e.target.value })}>
            <option value="">— magazyn / bez lokalu —</option>
            {venues?.filter((v) => v.active || v.id === f.venue_id).map((v) => <option key={v.id} value={v.id}>{v.name} ({v.city})</option>)}
          </select>
        </Field>
        {board && (
          <Field label="Status">
            <select className={inputCls} value={f.status} onChange={(e) => setF({ ...f, status: e.target.value })}>
              {Object.entries(BOARD_STATUS).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
            </select>
          </Field>
        )}
        <Field label="Notatki"><textarea className={inputCls} rows={2} value={f.notes} onChange={(e) => setF({ ...f, notes: e.target.value })} /></Field>
        <ErrorNote error={save.error} />
        <div className="flex justify-end gap-2">
          <Button type="button" onClick={onClose}>Anuluj</Button>
          <Button variant="primary" disabled={save.busy}>{board ? "Zapisz" : "Dodaj i wygeneruj klucz"}</Button>
        </div>
      </form>
    </Modal>
  );
}

export function TicketForm({ initial, onClose, onSaved }: { initial?: Partial<Ticket>; onClose: () => void; onSaved: (t: Ticket) => void }) {
  const { data: boards } = useApi<Board[]>("/api/fleet/boards");
  const { data: venues } = useApi<VenueRow[]>("/api/fleet/venues");
  const [f, setF] = useState({ title: initial?.title ?? "", description: initial?.description ?? "", category: initial?.category ?? "fault",
    priority: initial?.priority ?? "normal", board_id: initial?.board_id ?? "", venue_id: initial?.venue_id ?? "",
    assignee: initial?.assignee ?? "", reporter: initial?.reporter ?? "" });
  const save = useAction(async () => {
    onSaved(await api.post<Ticket>("/api/fleet/tickets", { ...f, board_id: f.board_id || null, venue_id: f.venue_id || null }));
  });
  return (
    <Modal open onClose={onClose} title="Nowe zgłoszenie">
      <form className="flex flex-col gap-3" onSubmit={(e) => { e.preventDefault(); save.run(); }}>
        <Field label="Tytuł"><input className={inputCls} required maxLength={200} value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} /></Field>
        <Field label="Opis"><textarea className={inputCls} rows={3} value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} /></Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Rodzaj">
            <select className={inputCls} value={f.category} onChange={(e) => setF({ ...f, category: e.target.value })}>
              {Object.entries(TICKET_CATEGORY).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
            </select>
          </Field>
          <Field label="Priorytet">
            <select className={inputCls} value={f.priority} onChange={(e) => setF({ ...f, priority: e.target.value })}>
              {Object.entries(TICKET_PRIORITY).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
            </select>
          </Field>
          <Field label="Tarcza">
            <select className={inputCls} value={f.board_id} onChange={(e) => setF({ ...f, board_id: e.target.value })}>
              <option value="">—</option>
              {boards?.map((b) => <option key={b.id} value={b.id}>{b.name}{b.venue_name ? ` · ${b.venue_name}` : ""}</option>)}
            </select>
          </Field>
          <Field label="Lokal" hint={f.board_id ? "Z tarczy, jeśli puste" : undefined}>
            <select className={inputCls} value={f.venue_id} onChange={(e) => setF({ ...f, venue_id: e.target.value })}>
              <option value="">—</option>
              {venues?.map((v) => <option key={v.id} value={v.id}>{v.name} ({v.city})</option>)}
            </select>
          </Field>
          <Field label="Przypisane do"><input className={inputCls} value={f.assignee} onChange={(e) => setF({ ...f, assignee: e.target.value })} placeholder="technik" /></Field>
          <Field label="Zgłaszający"><input className={inputCls} value={f.reporter} onChange={(e) => setF({ ...f, reporter: e.target.value })} /></Field>
        </div>
        <ErrorNote error={save.error} />
        <div className="flex justify-end gap-2">
          <Button type="button" onClick={onClose}>Anuluj</Button>
          <Button variant="primary" disabled={save.busy}>Utwórz zgłoszenie</Button>
        </div>
      </form>
    </Modal>
  );
}
