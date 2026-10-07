import { Mail, Plus, RefreshCw, Trash2, UserRound } from "lucide-react";
import { useState } from "react";
import { api, type ContactFields, type ContactView, type Relationship } from "../api";
import { useRefresh } from "../App";
import ChipInput from "../components/ChipInput";
import { Button, Card, Chip, cx, Empty, ErrorBox, Loading, PageHeader, plural, useToast } from "../components/ui";
import { today, useLoad } from "../hooks";

const RELATIONSHIPS: Relationship[] = ["recommender", "collaborator", "organizer", "editor", "mentor", "employer", "other"];

/** Contacts (E4, ADR 0014 §4): the people your case runs through, with what you asked, when you last spoke and
 * when to follow up. Letter writers appear here until you add them. Tracking only: never evidence. */
export default function Contacts() {
  const { version, bump } = useRefresh();
  const toast = useToast();
  const data = useLoad(() => api.contacts(), [version]);
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState<string | null>(null);
  if (data.error) return <ErrorBox error={data.error} retry={data.reload} />;
  if (!data.data) return <Loading />;
  const contacts = data.data;
  const due = contacts.filter((c) => c.next_follow_up && c.next_follow_up <= today()).length;

  const save = async (fn: () => Promise<unknown>, msg: string) => {
    try {
      await fn();
      toast(msg);
      setAdding(false);
      setEditing(null);
      bump();
    } catch (e) {
      toast((e as Error).message, "error");
    }
  };

  return (
    <div>
      <PageHeader
        eyebrow={`${plural(contacts.length, "contact")}${due ? ` · ${due} to follow up` : ""}`}
        title="Contacts"
        subtitle="Letter writers, organizers, editors and collaborators: what you asked, when you last spoke, when to follow up. Tracking only; never evidence."
        actions={
          <div className="flex flex-wrap gap-2">
            <Button onClick={() => save(async () => toast((await api.syncGmail()).lines.join(" ")), "Threads refreshed")}>
              <RefreshCw /> Refresh threads
            </Button>
            <Button variant="primary" onClick={() => setAdding(true)}>
              <Plus /> Add a contact
            </Button>
          </div>
        }
      />
      {adding && (
        <Card title="New contact" className="mb-8">
          <ContactForm onSave={(f) => save(() => api.addContact(f), `${f.name} added`)} onCancel={() => setAdding(false)} />
        </Card>
      )}
      <Card panel="contacts">
        {contacts.length === 0 ? (
          <Empty>No contacts yet. Letter writers show up here on their own; add anyone else your case runs through.</Empty>
        ) : (
          <ul>
            {contacts.map((c) =>
              editing === c.id ? (
                <li key={c.id} className="border-b border-line last:border-b-0">
                  <ContactForm
                    start={c}
                    onSave={(f) => save(() => api.updateContact(c.id, f), `${c.name} saved`)}
                    onCancel={() => setEditing(null)}
                    onDelete={c.virtual ? undefined : () => save(() => api.deleteContact(c.id), `${c.name} removed`)}
                  />
                </li>
              ) : (
                <ContactRow key={c.id} c={c} onEdit={() => setEditing(c.id)} />
              ),
            )}
          </ul>
        )}
      </Card>
    </div>
  );
}

function ContactRow({ c, onEdit }: { c: ContactView; onEdit: () => void }) {
  const overdue = !!c.next_follow_up && c.next_follow_up <= today();
  return (
    <li className="grid gap-3 border-b border-line px-5 py-5 last:border-b-0 md:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)_auto] md:px-6" data-contact={c.id}>
      <div className="min-w-0">
        <p className="flex flex-wrap items-center gap-2">
          <UserRound className="size-4 text-ink-2" strokeWidth={1.5} aria-hidden />
          <span className="text-[17px] font-medium">{c.name}</span>
          <Chip>{c.relationship}</Chip>
          {c.virtual && <Chip tone="muted">from Letters</Chip>}
        </p>
        <p className="mt-1 truncate font-mono text-[11px] text-muted">{[c.org, ...c.emails].filter(Boolean).join(" · ") || "No email yet"}</p>
        {(c.letters.length > 0 || c.pipeline.length > 0) && (
          <p className="mt-2 flex flex-wrap gap-1.5 text-xs">
            {c.letters.map((l) => (
              <a key={l.id} href="#/letters" className="link">
                Letter: {l.status}
              </a>
            ))}
            {c.pipeline.map((p) => (
              <a key={p.id} href="#/pipeline" className="link">
                {p.title} ({p.stage})
              </a>
            ))}
          </p>
        )}
        {c.asks.length > 0 && <p className="mt-2 text-sm text-ink-2">Asked: {c.asks.join("; ")}</p>}
      </div>
      <div className="min-w-0 text-sm">
        {c.threads.length > 0 ? (
          <p className="flex items-start gap-1.5 text-ink-2">
            <Mail className="mt-0.5 size-3.5 shrink-0" strokeWidth={1.5} aria-hidden />
            <span className="min-w-0">
              <span className="block truncate text-ink">{c.threads[0].subject || "(no subject)"}</span>
              <span className="font-mono text-[10.5px] text-muted uppercase">
                {plural(c.threads.length, "thread")} · last from {c.threads[0].last_from} · {c.threads[0].last_at.slice(0, 10)}
              </span>
            </span>
          </p>
        ) : (
          <p className="text-muted">No threads{c.emails.length ? "" : " (add an email to match Gmail)"}</p>
        )}
      </div>
      <div className="flex flex-wrap items-start gap-3 font-mono text-[11px] uppercase md:flex-col md:items-end">
        <span className="text-muted">Last touch {c.last_touch ?? "—"}</span>
        <span className={cx(overdue ? "text-alert" : "text-ink-2")}>Follow up {c.next_follow_up ?? "—"}</span>
        <Button size="sm" variant="ghost" onClick={onEdit}>
          Edit
        </Button>
      </div>
    </li>
  );
}

function ContactForm({ start, onSave, onCancel, onDelete }: { start?: ContactView; onSave: (f: ContactFields) => void; onCancel: () => void; onDelete?: () => void }) {
  const [f, setF] = useState<ContactFields>(() => ({
    name: start?.name ?? "",
    emails: start?.emails ?? [],
    org: start?.org ?? "",
    relationship: start?.relationship ?? "other",
    notes: start?.notes ?? "",
    asks: start?.asks ?? [],
    next_follow_up: start?.next_follow_up ?? null,
  }));
  return (
    <form
      className="grid gap-4 p-5 md:grid-cols-2 md:p-6"
      onSubmit={(e) => {
        e.preventDefault();
        onSave({ ...f, next_follow_up: f.next_follow_up || null });
      }}
    >
      <label>
        <span className="label">Name</span>
        <input className="input" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} required />
      </label>
      <label>
        <span className="label">Relationship</span>
        <select className="input" value={f.relationship} onChange={(e) => setF({ ...f, relationship: e.target.value as Relationship })}>
          {RELATIONSHIPS.map((r) => (
            <option key={r}>{r}</option>
          ))}
        </select>
      </label>
      <div>
        <span className="label" id="emails-label">
          Emails
        </span>
        <ChipInput id="emails" label="Emails" value={f.emails ?? []} onChange={(emails) => setF({ ...f, emails })} />
      </div>
      <label>
        <span className="label">Organization</span>
        <input className="input" value={f.org} onChange={(e) => setF({ ...f, org: e.target.value })} />
      </label>
      <div>
        <span className="label" id="asks-label">
          What you've asked
        </span>
        <ChipInput id="asks" label="What you've asked" value={f.asks ?? []} onChange={(asks) => setF({ ...f, asks })} />
      </div>
      <label>
        <span className="label">Next follow-up</span>
        <input className="input" type="date" value={f.next_follow_up ?? ""} onChange={(e) => setF({ ...f, next_follow_up: e.target.value || null })} />
      </label>
      <label className="md:col-span-2">
        <span className="label">Notes</span>
        <input className="input" value={f.notes} onChange={(e) => setF({ ...f, notes: e.target.value })} />
      </label>
      <div className="flex flex-wrap gap-2 md:col-span-2">
        <Button type="submit" variant="primary">
          Save
        </Button>
        <Button type="button" variant="ghost" onClick={onCancel}>
          Cancel
        </Button>
        {onDelete && (
          <Button type="button" variant="ghost" className="ml-auto" onClick={onDelete}>
            <Trash2 /> Remove
          </Button>
        )}
      </div>
    </form>
  );
}
