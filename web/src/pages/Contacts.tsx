import { Check, Mail, Plus, RefreshCw, Send, Trash2, UserRound, X } from "lucide-react";
import { useEffect, useState } from "react";
import { api, type ContactFields, type ContactView, type OutreachDraftView, type OutreachView, type Relationship } from "../api";
import { useRefresh } from "../App";
import ChipInput from "../components/ChipInput";
import MailView from "../components/MailView";
import { Button, Card, Chip, cx, Empty, ErrorBox, Loading, PageHeader, plural, Segmented, useToast } from "../components/ui";
import { today, useLoad, useRoute } from "../hooks";

const RELATIONSHIPS: Relationship[] = ["recommender", "collaborator", "organizer", "editor", "mentor", "employer", "other"];

/** Contacts (E4, ADR 0014 §4): the people your case runs through, with what you asked, when you last spoke and
 * when to follow up. Letter writers appear here until you add them. Tracking only: never evidence. */
export default function Contacts() {
  const { version, bump } = useRefresh();
  const toast = useToast();
  const data = useLoad(() => api.contacts(), [version]);
  const mail = useLoad(() => api.outreach(), [version]);
  const [writing, setWriting] = useState<ContactView | null>(null);
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState<string | null>(null);
  const { params } = useRoute();
  const tab = params.get("view") === "mail" ? "mail" : "people";
  const go = (view: "people" | "mail", contact = "") => {
    window.location.hash = view === "mail" ? `#/contacts?view=mail${contact ? `&contact=${encodeURIComponent(contact)}` : ""}` : "#/contacts";
  };
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
            <Segmented
              label="Contacts or mail"
              value={tab}
              onChange={(v) => go(v)}
              options={[
                { value: "people", label: "People" },
                { value: "mail", label: <><Mail /> Mail</> },
              ]}
            />
            {tab === "people" && <Button onClick={() => save(async () => toast((await api.syncGmail()).lines.join(" ")), "Threads refreshed")}>
              <RefreshCw /> Refresh threads
            </Button>}
            {tab === "people" && <Button variant="primary" onClick={() => setAdding(true)}>
              <Plus /> Add a contact
            </Button>}
          </div>
        }
      />
      {tab === "mail" ? (
        <MailView contacts={contacts} contact={params.get("contact") ?? ""} setContact={(id) => go("mail", id)} />
      ) : (
      <>
      {mail.data && <Outreach view={mail.data} onChange={bump} />}
      {writing && (
        <Card title={`Email to ${writing.name}`} className="mb-8">
          <Composer
            to={writing.emails[0]}
            onSave={(subject, body) => save(async () => { await api.draftEmail(writing.id, subject, body); setWriting(null); }, "Draft saved; it waits for your approval above")}
            onCancel={() => setWriting(null)}
          />
        </Card>
      )}
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
                <ContactRow key={c.id} c={c} onEdit={() => setEditing(c.id)} onWrite={!c.virtual && c.emails.length ? () => setWriting(c) : undefined} onMail={!c.virtual && c.emails.length ? () => go("mail", c.id) : undefined} />
              ),
            )}
          </ul>
        )}
      </Card>
      </>
      )}
    </div>
  );
}

function ContactRow({ c, onEdit, onWrite, onMail }: { c: ContactView; onEdit: () => void; onWrite?: () => void; onMail?: () => void }) {
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
        <span className="flex gap-1">
          {onMail && (
            <Button size="sm" variant="ghost" onClick={onMail}>
              <Mail /> Mail
            </Button>
          )}
          {onWrite && (
            <Button size="sm" variant="ghost" onClick={onWrite}>
              <Send /> Write
            </Button>
          )}
          <Button size="sm" variant="ghost" onClick={onEdit}>
            Edit
          </Button>
        </span>
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

/** Emails waiting for your approval (ADR 0014 §5): nothing is sent until you press Approve & send. */
function Outreach({ view, onChange }: { view: OutreachView; onChange: () => void }) {
  const toast = useToast();
  const waiting = view.drafts.filter((d) => d.status === "draft");
  const queued = view.drafts.filter((d) => d.status === "queued");
  const sent = view.drafts.filter((d) => d.status === "sent").slice(0, 5);
  const failed = view.failures ?? [];
  if (!waiting.length && !queued.length && !sent.length && !failed.length) return null;
  const act = async (fn: () => Promise<unknown>, msg: string) => {
    try {
      await fn();
      toast(msg);
      onChange();
    } catch (e) {
      toast((e as Error).message, "error");
    }
  };
  return (
    <Card
      title={`Emails waiting for your approval · ${waiting.length}`}
      className="mb-8"
      panel="outreach"
      actions={<span className="font-mono text-[10.5px] text-muted uppercase">{view.sent_today} of {view.daily_limit} sent today</span>}
    >
      {failed.length > 0 && (
        <div role="alert" className="border-b border-alert bg-alert-soft px-5 py-4 md:px-6" data-send-failures>
          <p className="font-mono text-[10.5px] text-alert uppercase">{plural(failed.length, "send")} didn't go out (last 7 days)</p>
          <ul className="mt-2 grid gap-1.5 text-sm">
            {failed.map((f) => (
              <li key={`${f.draft_id}-${f.at}`}>
                <span className="font-mono text-[11px] text-ink-2">{f.at.slice(0, 16).replace("T", " ")}</span> · To {f.contact ? `${f.contact} <${f.to}>` : f.to} · {f.subject}
                <span className="block text-ink-2">{f.error}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {queued.length > 0 && (
        <ul>
          {queued.map((d) => (
            <QueuedRow key={d.id} d={d} seconds={view.undo_seconds} onUndo={() => act(() => api.undoSend(d.id), "Undone: nothing was sent. It's a draft again.")} onDone={onChange} />
          ))}
        </ul>
      )}
      {waiting.length === 0 && !queued.length && <Empty>Nothing waiting. Drafts from you, the agent or a follow-up land here first.</Empty>}
      <ul>
        {waiting.map((d) => (
          <DraftRow key={d.id} d={d} canSend={view.can_send} act={act} />
        ))}
      </ul>
      {sent.length > 0 && (
        <p className="border-t border-line px-5 py-3 font-mono text-[10.5px] leading-relaxed text-muted uppercase md:px-6">
          Sent: {sent.map((d) => `${d.contact || d.to} · ${d.subject}`).join(" | ")}
        </p>
      )}
    </Card>
  );
}

/** Approved and waiting out the undo window: a countdown and Undo send. The server sends it when the time is up. */
function QueuedRow({ d, seconds, onUndo, onDone }: { d: OutreachDraftView; seconds: number; onUndo: () => void; onDone: () => void }) {
  const until = (d.queued_at ? Date.parse(d.queued_at) : Date.now()) + seconds * 1000;
  const [left, setLeft] = useState(() => Math.max(0, Math.ceil((until - Date.now()) / 1000)));
  useEffect(() => {
    const tick = setInterval(() => {
      const s = Math.max(0, Math.ceil((until - Date.now()) / 1000));
      setLeft(s);
      if (until - Date.now() < -1500) {
        clearInterval(tick);
        onDone(); // sent by now (or refused, which shows above)
      }
    }, 250);
    return () => clearInterval(tick);
  }, [until, onDone]);
  return (
    <li className="flex flex-wrap items-center justify-between gap-3 border-b border-line bg-sunken px-5 py-4 md:px-6" data-queued={d.id}>
      <p className="min-w-0 text-sm">
        <span className="font-mono text-[10.5px] text-muted uppercase">{left > 0 ? `Sending in ${left}s` : "Sending…"}</span>
        <span className="block truncate">
          To {d.contact || d.to} · {d.subject}
        </span>
      </p>
      <Button variant="primary" disabled={left <= 0} onClick={onUndo}>
        <X /> Undo send
      </Button>
    </li>
  );
}

function DraftRow({ d, canSend, act }: { d: OutreachDraftView; canSend: boolean; act: (fn: () => Promise<unknown>, msg: string) => Promise<void> }) {
  const [subject, setSubject] = useState(d.subject);
  const [sending, setSending] = useState(false); // Gmail can take seconds: one click, one email
  const [body, setBody] = useState(d.body);
  const edited = subject !== d.subject || body !== d.body;
  const who = d.drafted_by === "user" ? "you" : d.drafted_by === "follow-up" ? "a follow-up (7 quiet days)" : "the agent";
  return (
    <li className="grid gap-3 border-b border-line px-5 py-5 last:border-b-0 md:px-6" data-draft={d.id}>
      <p className="font-mono text-[10.5px] text-muted uppercase">
        To {d.contact ? `${d.contact} <${d.to}>` : d.to} · drafted by {who}
      </p>
      <input className="input" value={subject} onChange={(e) => setSubject(e.target.value)} aria-label="Subject" />
      <textarea className="input min-h-32" value={body} onChange={(e) => setBody(e.target.value)} aria-label="Message" />
      <div className="flex flex-wrap items-center gap-2">
        <Button
          variant="primary"
          disabled={!canSend || edited || sending}
          title={!canSend ? "Connect Gmail in Settings > Gmail" : edited ? "Save your edits first" : undefined}
          onClick={() => {
            setSending(true);
            act(() => api.sendDraft(d.id), `Approved: sending to ${d.to} in a few seconds. You can still undo it.`).finally(() => setSending(false));
          }}
        >
          <Check /> {sending ? "Sending…" : "Approve & send"}
        </Button>
        {edited && (
          <Button onClick={() => act(() => api.editDraft(d.id, { subject, body }), "Saved")}>
            Save edits
          </Button>
        )}
        <Button variant="ghost" onClick={() => act(() => api.rejectDraft(d.id), "Rejected; nothing was sent")}>
          <X /> Reject
        </Button>
        {!canSend && <span className="text-xs text-ink-2">Sending is off: connect Gmail in Settings &gt; Gmail.</span>}
      </div>
    </li>
  );
}

function Composer({ to, onSave, onCancel }: { to: string; onSave: (subject: string, body: string) => void; onCancel: () => void }) {
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  return (
    <form
      className="grid gap-3 p-5 md:p-6"
      onSubmit={(e) => {
        e.preventDefault();
        onSave(subject, body);
      }}
    >
      <p className="font-mono text-[10.5px] text-muted uppercase">To {to} · saved as a draft; nothing is sent until you approve it</p>
      <input className="input" placeholder="Subject" value={subject} onChange={(e) => setSubject(e.target.value)} required />
      <textarea className="input min-h-32" placeholder="Message" value={body} onChange={(e) => setBody(e.target.value)} required />
      <div className="flex gap-2">
        <Button type="submit" variant="primary">
          Save draft
        </Button>
        <Button type="button" variant="ghost" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
