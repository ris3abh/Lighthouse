import { ArrowUpRight, Download, Inbox as InboxIcon, Mail, RefreshCw, ShieldAlert, ShieldCheck, Upload } from "lucide-react";
import { useEffect, useState } from "react";
import { api, type ContactView, type MailCategory, type MailItemView, type MailText, type MailView as MailData } from "../api";
import DropZone from "./DropZone";
import { Button, Card, Chip, cx, Empty, ErrorBox, Loading, Modal, plural, useToast } from "./ui";

const MOVE_HIDE = "hide";

/** The Mail view on Contacts: case-relevant mail only, read-only. Inbox-wide by category, or one contact's threads
 * (sent and received). Opening a message fetches its text from Gmail; nothing is saved and nothing changes in Gmail. */
export default function MailView({ contacts, contact, setContact }: { contacts: ContactView[]; contact: string; setContact: (id: string) => void }) {
  const toast = useToast();
  const [data, setData] = useState<MailData | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [cat, setCat] = useState<MailCategory | "all">("all");
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState<MailItemView | null>(null);
  const load = () => api.mail().then(setData, setError);
  useEffect(() => {
    load();
  }, []);
  if (error) return <ErrorBox error={error} retry={load} />;
  if (!data) return <Loading />;

  const refresh = async () => {
    setBusy(true);
    try {
      const r = await api.syncMail();
      setData(r);
      toast((r.lines ?? []).join(" ") || "Mail refreshed");
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setBusy(false);
    }
  };
  const move = async (item: MailItemView, to: MailCategory | "hide") => {
    try {
      setData(await api.moveMail(item.id, to));
      toast(to === MOVE_HIDE ? `Hidden. Mail from ${item.from_addr} won't show again.` : `Moved. Mail from ${item.from_addr} goes there from now on.`);
    } catch (e) {
      toast((e as Error).message, "error");
    }
  };

  const dropEml = async (files: File[]) => {
    const emails = files.filter((f) => f.name.toLowerCase().endsWith(".eml"));
    if (!emails.length) return toast("Only .eml files here. Other files go on the Evidence page.", "error");
    setBusy(true);
    try {
      const cands = await api.uploadToInbox(emails);
      toast(`${plural(cands.length, "email")} sent to the Inbox for review`);
      await load();
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setBusy(false);
    }
  };
  const importOriginal = async (item: MailItemView) => {
    try {
      await api.importForwarded(item.id);
      toast("The attached original is in your Inbox, with its sender check. Its file is kept.");
      await load();
    } catch (e) {
      toast((e as Error).message, "error");
    }
  };

  const labels = Object.fromEntries(data.categories.map((c) => [c.id, c.label])) as Record<MailCategory, string>;
  const person = contacts.find((c) => c.id === contact);
  const mine = person ? data.items.filter((i) => i.contact_ids.includes(person.id)) : data.items;
  const shown = cat === "all" ? mine : mine.filter((i) => i.category === cat);
  const counts = (id: MailCategory) => mine.filter((i) => i.category === id).length;
  const withMail = contacts.filter((c) => !c.virtual && c.emails.length);

  return (
    <div className="grid gap-6" data-mail-view>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <label className="min-w-0">
          <span className="label">Showing</span>
          <select className="input" value={contact} onChange={(e) => setContact(e.target.value)} aria-label="Whose mail">
            <option value="">All case mail</option>
            {withMail.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </label>
        <div className="flex flex-wrap items-center gap-3">
          <span className="font-mono text-[10.5px] text-muted uppercase">{data.synced_at ? `Read ${data.synced_at.slice(0, 16).replace("T", " ")}` : "Not read yet"}</span>
          <Button onClick={refresh} disabled={busy || !data.connected} title={data.connected ? undefined : "Connect Gmail in Settings > Gmail"}>
            <RefreshCw /> {busy ? "Reading…" : "Refresh mail"}
          </Button>
        </div>
      </div>

      <div className="flex flex-wrap gap-1.5" role="group" aria-label="Categories">
        <CatButton on={cat === "all"} onClick={() => setCat("all")} label="All" count={mine.length} />
        {data.categories.map((c) => (
          <CatButton key={c.id} on={cat === c.id} onClick={() => setCat(c.id)} label={c.label} count={counts(c.id)} />
        ))}
      </div>

      <DropZone onFiles={dropEml} busy={busy} accept=".eml,message/rfc822" multiple label="Drop .eml emails">
        <p className="flex items-center gap-2 text-sm text-ink-2">
          <Upload className="size-4" strokeWidth={1.5} aria-hidden />
          Drop emails saved as .eml (from another account), or click to choose. Each one is checked for a verified sender and goes to your
          Inbox; its file is kept.
        </p>
      </DropZone>

      <Card panel="mail">
        {!data.connected && !data.items.length ? (
          <Empty>
            Connect Gmail in <a className="link" href="#/settings">Settings &gt; Gmail</a> to see case mail here.
          </Empty>
        ) : shown.length === 0 ? (
          <Empty>{data.synced_at ? "Nothing in this category." : "Press Refresh mail to read your recent mail."}</Empty>
        ) : person ? (
          <Threads items={shown} labels={labels} onOpen={setOpen} onMove={move} onImport={importOriginal} />
        ) : (
          <ul>
            {shown.map((i) => (
              <Row key={i.id} i={i} labels={labels} onOpen={() => setOpen(i)} onMove={(to) => move(i, to)} onImport={() => importOriginal(i)} />
            ))}
          </ul>
        )}
      </Card>
      {data.unsorted > 0 && (
        <p className="text-sm text-ink-2" data-mail-unsorted>
          {plural(data.unsorted, "new message")} no rule could sort {data.unsorted === 1 ? "isn't" : "aren't"} shown or kept.
          {data.model_sorting ? " No model was available to sort them." : <> Turn on <a className="link" href="#/settings">model sorting</a> in Settings &gt; Gmail to sort them, or move similar mail to teach the rules.</>}
        </p>
      )}
      <p className="font-mono text-[10.5px] leading-relaxed text-muted uppercase">
        Read-only: nothing is marked read, moved, labelled or deleted in Gmail · only case mail is kept (who, when, the subject) · a message's text is
        fetched when you open it and never saved · moving a message teaches the sorting rules
      </p>
      {open && <Reader item={open} onClose={() => setOpen(null)} />}
    </div>
  );
}

function CatButton({ on, onClick, label, count }: { on: boolean; onClick: () => void; label: string; count: number }) {
  return (
    <button
      type="button"
      aria-pressed={on}
      onClick={onClick}
      className={cx(
        "inline-flex h-8 items-center gap-2 border px-3 font-mono text-[11px] tracking-[0.06em] uppercase transition-colors duration-150",
        on ? "border-ink bg-ink text-on-ink" : "border-line text-ink-2 hover:border-ink hover:text-ink",
      )}
    >
      {label}
      <span className={cx("tabular-nums", on ? "text-on-ink" : "text-muted")}>{count}</span>
    </button>
  );
}

/** One contact's mail as threads, newest first; each thread lists its messages, sent and received. */
function Threads({ items, labels, onOpen, onMove, onImport }: { items: MailItemView[]; labels: Record<MailCategory, string>; onOpen: (i: MailItemView) => void; onMove: (i: MailItemView, to: MailCategory | "hide") => void; onImport: (i: MailItemView) => void }) {
  const threads = new Map<string, MailItemView[]>();
  for (const i of items) threads.set(i.thread_id, [...(threads.get(i.thread_id) ?? []), i]);
  return (
    <ul>
      {[...threads.entries()].map(([tid, msgs]) => (
        <li key={tid} className="border-b border-line last:border-b-0" data-thread={tid}>
          <p className="flex flex-wrap items-center gap-2 px-5 pt-4 font-mono text-[10.5px] text-muted uppercase md:px-6">
            <Mail className="size-3.5" strokeWidth={1.5} aria-hidden />
            {plural(msgs.length, "message")} · {msgs.filter((m) => m.outgoing).length} sent · {msgs.filter((m) => !m.outgoing).length} received
          </p>
          <ul>
            {msgs.map((i) => (
              <Row key={i.id} i={i} labels={labels} onOpen={() => onOpen(i)} onMove={(to) => onMove(i, to)} onImport={() => onImport(i)} nested />
            ))}
          </ul>
        </li>
      ))}
    </ul>
  );
}

function Row({ i, labels, onOpen, onMove, onImport, nested }: { i: MailItemView; labels: Record<MailCategory, string>; onOpen: () => void; onMove: (to: MailCategory | "hide") => void; onImport: () => void; nested?: boolean }) {
  const who = i.outgoing ? `To ${i.contacts[0] ?? i.to[0] ?? ""}` : i.from_name || i.from_addr;
  return (
    <li className={cx("grid gap-2 px-5 py-4 md:grid-cols-[minmax(0,1fr)_auto] md:items-center md:px-6", !nested && "border-b border-line last:border-b-0")} data-mail={i.id}>
      <button type="button" onClick={onOpen} className="min-w-0 text-left">
        <span className="flex min-w-0 flex-wrap items-baseline gap-x-2">
          <span className="truncate font-medium">{who}</span>
          <span className="font-mono text-[10.5px] text-muted uppercase">{i.outgoing ? "Sent · " : ""}{i.at.slice(0, 10)}</span>
        </span>
        <span className="block truncate text-sm text-ink-2 hover:text-ink">{i.subject || "(no subject)"}</span>
        <span className="mt-1 block font-mono text-[10px] text-muted uppercase">
          {i.source === "eml" ? "Dropped .eml · " : ""}
          {i.by === "model" ? "Sorted by the model" : i.by === "you" ? "You moved it" : i.why}
        </span>
        <AuthBadge auth={i.auth} />
      </button>
      <div className="flex flex-wrap items-center gap-2">
        <Chip tone={i.category === "contacts" ? "muted" : "ink"}>{labels[i.category]}</Chip>
        {i.forwarded_part && (
          <Button size="sm" variant="ghost" onClick={onImport} title="Fetch the attached original and send it to the Inbox, with its sender check">
            <Download /> Import original
          </Button>
        )}
        {i.candidate && (
          <a className="link inline-flex items-center gap-1 font-mono text-[10.5px] uppercase" href={`#/inbox?candidate=${encodeURIComponent(i.candidate.id)}`} title={i.candidate.title}>
            <InboxIcon className="size-3.5" aria-hidden /> In Inbox <ArrowUpRight className="size-3" aria-hidden />
          </a>
        )}
        <select
          className="input h-8 w-auto py-0 text-xs"
          aria-label="Move to"
          value=""
          onChange={(e) => e.target.value && onMove(e.target.value as MailCategory | "hide")}
        >
          <option value="">Move to…</option>
          {(Object.keys(labels) as MailCategory[])
            .filter((k) => k !== i.category)
            .map((k) => (
              <option key={k} value={k}>
                {labels[k]}
              </option>
            ))}
          <option value={MOVE_HIDE}>Not case mail (hide)</option>
        </select>
      </div>
    </li>
  );
}

/** The receiving server's sender check, from the original headers (ADR 0014, amendment). */
function AuthBadge({ auth }: { auth: MailItemView["auth"] }) {
  if (!auth) return null;
  const how = auth.dmarc === "pass" ? "DMARC passed" : auth.dkim_domain ? `DKIM ${auth.dkim} for ${auth.dkim_domain}` : `DKIM ${auth.dkim ?? "none"}`;
  const by = auth.by ? `, checked by ${auth.by}` : "";
  if (auth.verdict === "verified")
    return (
      <span className="mt-1 inline-flex items-center gap-1 font-mono text-[10px] text-ink-2 uppercase" title={`${how}${by}`}>
        <ShieldCheck className="size-3" aria-hidden /> Verified sender
      </span>
    );
  return (
    <span className={cx("mt-1 inline-flex items-center gap-1 font-mono text-[10px] uppercase", auth.verdict === "failed" ? "text-alert" : "text-muted")} title={`${how}${by}`}>
      <ShieldAlert className="size-3" aria-hidden /> {auth.verdict === "failed" ? "Sender check failed" : "Sender not verified"}
    </span>
  );
}

/** A message's text, fetched from Gmail when opened (with PEEK, so it stays unread there) and kept only here. */
function Reader({ item, onClose }: { item: MailItemView; onClose: () => void }) {
  const [msg, setMsg] = useState<MailText | null>(null);
  const [error, setError] = useState<Error | null>(null);
  useEffect(() => {
    api.mailText(item.id).then(setMsg, setError);
  }, [item.id]);
  return (
    <Modal title={item.subject || "(no subject)"} onClose={onClose} wide>
      {error ? (
        <ErrorBox error={error} />
      ) : !msg ? (
        <Loading />
      ) : (
        <div className="grid gap-4">
          <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1 font-mono text-[11px] text-ink-2">
            <dt className="text-muted uppercase">From</dt>
            <dd className="break-words">{msg.from}</dd>
            <dt className="text-muted uppercase">To</dt>
            <dd className="break-words">{msg.to}</dd>
            {msg.cc && (
              <>
                <dt className="text-muted uppercase">Cc</dt>
                <dd className="break-words">{msg.cc}</dd>
              </>
            )}
            <dt className="text-muted uppercase">Date</dt>
            <dd>{msg.date}</dd>
          </dl>
          <div className="max-h-[60vh] overflow-y-auto border-t border-line pt-4 text-sm leading-relaxed break-words whitespace-pre-wrap">{msg.text || "(no text)"}</div>
          <p className="font-mono text-[10.5px] text-muted uppercase">Fetched from Gmail just now · not saved · still unread in Gmail</p>
        </div>
      )}
    </Modal>
  );
}
