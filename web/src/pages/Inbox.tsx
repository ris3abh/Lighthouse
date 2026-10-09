import { useCallback, useEffect, useState } from "react";
import { api, type Candidate, DATE_SOURCE, type Profile } from "../api";
import { useRefresh } from "../App";
import ClaimsPanel, { StageChip } from "../components/Claims";
import RuleCheckView, { blocking } from "../components/RuleCheck";
import TrackerCard, { TRACKER_LABEL } from "../components/TrackerCard";
import { Paperclip, Upload } from "lucide-react";
import DropZone from "../components/DropZone";
import { BulkBar, Filters, GroupCheckbox, KeyAcceptConfirm, KIND_LABEL, matchesFilter, SelectRow, UndoBanner, useInboxKeys, useSelection } from "../components/BulkReview";
import type { InboxFilter } from "../api";
import { Button, Card, Chip, Empty, ErrorBox, Loading, PageHeader, useToast } from "../components/ui";
import { today, useLoad, useRoute } from "../hooks";
import Banter, { banterOk } from "../components/Banter";
import { banterText } from "../lib/banter";

export default function Inbox() {
  const { version, bump } = useRefresh();
  const inbox = useLoad(() => Promise.all([api.inbox(), api.profile(), api.inboxGroups()]), [version]);
  const [filter, setFilter] = useState<InboxFilter>({});
  const [last, setLast] = useState<{ batch: string; label: string } | null>(null);
  const [more, setMore] = useState<Record<string, boolean>>({});
  const toast = useToast();
  const [sending, setSending] = useState(false);
  const drop = async (files: File[]) => {
    setSending(true);
    try {
      const cands = await api.uploadToInbox(files);
      toast(`${cands.length} file${cands.length > 1 ? "s" : ""} added for review`);
      bump();
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setSending(false);
    }
  };
  const focus = useRoute().params.get("candidate"); // from the Mail view: "In Inbox"
  useEffect(() => {
    if (focus && inbox.data) document.querySelector(`[data-candidate="${CSS.escape(focus)}"]`)?.scrollIntoView({ block: "center" });
  }, [focus, inbox.data]);
  const all = inbox.data?.[0] ?? [];
  const candidates = all.filter((c) => matchesFilter(c, filter, (x) => x.group ?? ""));
  const order = orderOf(candidates, inbox.data?.[1]);
  const sel = useSelection(order);
  // a / r from the keyboard: one decision, through the bulk door so it has a batch, with Undo in its toast.
  // Accepting evidence asks first (it files an exhibit).
  const [keyConfirm, setKeyConfirm] = useState<Candidate | null>(null);
  const [keyBusy, setKeyBusy] = useState(false);
  const runKey = useCallback(
    async (c: Candidate, action: "accept" | "reject", confirm_evidence = false) => {
      setKeyBusy(true);
      try {
        const r = await api.bulkInbox({ action, ids: [c.id], confirm_evidence });
        if (r.batch) {
          const batch = r.batch;
          const label = `${action === "accept" ? "Accepted" : c.kind === "evidence" ? "Rejected" : "Dismissed"}: ${c.title}`;
          toast(label, "ok", {
            label: "Undo",
            run: async () => {
              try {
                await api.undoBatch(batch);
                toast(`Undone: ${c.title} is back in the Inbox`);
              } catch (e) {
                toast((e as Error).message, "error");
              }
              bump();
            },
          });
        } else toast(r.failed[0]?.why ?? "Nothing changed", "error");
        bump();
      } catch (e) {
        toast((e as Error).message, "error");
      } finally {
        setKeyBusy(false);
        setKeyConfirm(null);
      }
    },
    [toast, bump],
  );
  const decide = useCallback(
    (id: string, action: "accept" | "reject") => {
      const c = all.find((x) => x.id === id);
      if (!c) return;
      if (action === "accept" && c.kind === "evidence") setKeyConfirm(c);
      else runKey(c, action);
    },
    [all, runKey],
  );
  const cursor = useInboxKeys(order, sel.toggle, decide);
  if (inbox.error) return <ErrorBox error={inbox.error} retry={inbox.reload} />;
  if (!inbox.data) return <Loading />;
  const [, profile, groupList] = inbox.data;
  const row = (c: Candidate, card: React.ReactNode) => (
    <SelectRow key={c.id} id={c.id} checked={sel.picked.has(c.id)} onToggle={sel.toggle} focused={cursor === c.id}>
      {card}
    </SelectRow>
  );
  const LIMIT = 50;
  const page = <T extends Candidate>(key: string, list: T[]) => (more[key] ? list : list.slice(0, LIMIT));
  const showMore = (key: string, list: Candidate[]) =>
    list.length > LIMIT && !more[key] ? (
      <div className="border-t border-line px-5 py-3">
        <Button size="sm" variant="ghost" onClick={() => setMore({ ...more, [key]: true })}>
          Show {list.length - LIMIT} more
        </Button>
      </div>
    ) : null;

  const labels: Record<string, string> = { "": "Needs a criterion", ...Object.fromEntries(profile.criteria.map((c) => [c.id, c.short_label || c.label])) };
  const full: Record<string, string> = Object.fromEntries(profile.criteria.map((c) => [c.id, c.label]));
  const { groups, criteriaOrder, trackerGroups } = grouped(candidates, profile);

  return (
    <div>
      <PageHeader
        eyebrow={`${candidates.length} to review`}
        title="Inbox"
        subtitle="Connectors and the agent propose; you decide. Nothing becomes evidence until you accept it, and accepting records your decision. It doesn't certify legal sufficiency."
      />
      <DropZone onFiles={drop} busy={sending} label="Add files or emails to the Inbox">
        <p className="flex items-center gap-2 text-sm text-ink-2">
          <Upload className="size-4" strokeWidth={1.5} aria-hidden />
          {sending ? "Adding…" : "Drop files or emails (.eml) here, or click to choose. Emails are checked for a verified sender."}
        </p>
      </DropZone>
      {all.length > 0 && <Filters groups={groupList} filter={filter} setFilter={setFilter} total={all.length} shown={candidates.length} />}
      <UndoBanner
        last={last}
        onUndone={() => {
          setLast(null);
          bump();
        }}
      />
      {keyConfirm && (
        <KeyAcceptConfirm candidate={keyConfirm} busy={keyBusy} onCancel={() => setKeyConfirm(null)} onConfirm={() => runKey(keyConfirm, "accept", true)} />
      )}
      <BulkBar
        picked={sel.picked}
        matching={order}
        filter={filter}
        candidates={candidates}
        onClear={sel.clear}
        onSelectMatching={() => sel.setMany(order, true)}
        onDone={(r, label) => {
          sel.clear();
          if (r.batch) setLast({ batch: r.batch, label });
          else toast(label, "error");
          bump();
        }}
      />
      {all.length > 0 && (
        <p className="-mt-3 mb-6 font-mono text-[10.5px] tracking-[0.04em] text-muted">
          Keys: j / k move · x select · a accept · r reject · shift-click a checkbox for a range
        </p>
      )}
      {candidates.length === 0 && all.length > 0 ? (
        <Card panel="inbox">
          <Empty>Nothing matches these filters.</Empty>
        </Card>
      ) : candidates.length === 0 ? (
        <Card panel="inbox">
          <Empty>
            <Banter id="empty_inbox" as="span" fallback="Nothing to review." /> New candidates arrive when you{" "}
            <a href="#/sources" className="link">
              add or sync a source
            </a>
            .
          </Empty>
        </Card>
      ) : (
        <div className="flex flex-col gap-8">
          {criteriaOrder.map((crit) => (
            <Card
              key={crit}
              panel="inbox"
              title={
                <span className="flex items-center gap-3" title={full[crit]}>
                  <GroupCheckbox ids={groups.get(crit)!.map((c) => c.id)} picked={sel.picked} setMany={sel.setMany} />
                  {labels[crit] ?? crit}
                  <span className="num text-ink-2">{groups.get(crit)!.length}</span>
                </span>
              }
              actions={!labels[crit] && <Chip tone="outline">not in the {profile.name} profile</Chip>}
            >
              {page(crit, groups.get(crit)!).map((c) => row(c, <CandidateCard c={c} profile={profile} onDone={bump} />))}
              {showMore(crit, groups.get(crit)!)}
            </Card>
          ))}
          {trackerGroups.map(([kind, list]) =>
            kind === "context" ? (
              <details key={kind} className="card group" open={filter.kind === "context"}>
                <summary className="flex min-h-12 cursor-pointer list-none flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-2.5 hover:bg-sunken">
                  <span className="eyebrow flex items-center gap-3 text-ink">
                    <span onClick={(e) => e.stopPropagation()}>
                      <GroupCheckbox ids={list.map((c) => c.id)} picked={sel.picked} setMany={sel.setMany} />
                    </span>
                    {KIND_LABEL.context} from your chats and tools
                    <span className="num text-ink-2">{list.length}</span>
                  </span>
                  <span className="font-mono text-[10.5px] text-muted uppercase">Low priority · self-reported · never evidence</span>
                </summary>
                {page(kind, list).map((c) => row(c, <TrackerCard c={c} onDone={bump} />))}
                {showMore(kind, list)}
              </details>
            ) : (
              <Card
                key={kind}
                panel="inbox"
                title={
                  <span className="flex items-center gap-3">
                    <GroupCheckbox ids={list.map((c) => c.id)} picked={sel.picked} setMany={sel.setMany} />
                    {TRACKER_LABEL[kind]}
                    <span className="num text-ink-2">{list.length}</span>
                  </span>
                }
                actions={<span className="font-mono text-[10.5px] text-muted uppercase">Tracker · never counts toward a criterion</span>}
              >
                {page(kind, list).map((c) => row(c, <TrackerCard c={c} onDone={bump} />))}
                {showMore(kind, list)}
              </Card>
            ),
          )}
          {trackerGroups.length > 0 && (
            <p className="max-w-3xl text-sm leading-relaxed text-ink-2">
              Tracker suggestions come from your chats and the agent. Adding them updates your deadlines, pipeline, letters and metrics;
              they never count toward a criterion. For evidence, upload the underlying document on the{" "}
              <a href="#/evidence" className="link">
                Evidence
              </a>{" "}
              page.
            </p>
          )}
        </div>
      )}
    </div>
  );
}

const TRACKER_KINDS = ["deadline", "pipeline", "letter", "update", "metric", "context"] as const;

/** Evidence by criterion (profile order), then trackers by kind, notes last. */
function grouped(candidates: Candidate[], profile: Profile) {
  const groups = new Map<string, Candidate[]>();
  for (const c of candidates.filter((x) => x.kind === "evidence")) groups.set(c.proposed_criterion, [...(groups.get(c.proposed_criterion) ?? []), c]);
  const criteriaOrder = [...groups.keys()].sort(
    (a, b) => profile.criteria.findIndex((c) => c.id === a) - profile.criteria.findIndex((c) => c.id === b),
  );
  const trackerGroups = TRACKER_KINDS.map((k) => [k, candidates.filter((c) => c.kind === k)] as const).filter(([, list]) => list.length);
  return { groups, criteriaOrder, trackerGroups };
}

/** The order cards are shown in (for shift-click ranges and j / k). */
function orderOf(candidates: Candidate[], profile: Profile | undefined): string[] {
  if (!profile) return [];
  const { groups, criteriaOrder, trackerGroups } = grouped(candidates, profile);
  return [...criteriaOrder.flatMap((k) => groups.get(k)!.map((c) => c.id)), ...trackerGroups.flatMap(([, list]) => list.map((c) => c.id))];
}

function Confidence({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  return (
    <span className="hidden w-24 shrink-0 flex-col items-end gap-1.5 @2xl:flex" title="How sure the connector is that this is evidence">
      <span className="display text-3xl leading-none">
        {pct}
        <span className="text-muted">%</span>
      </span>
      <span className="eyebrow">confidence</span>
    </span>
  );
}

function CandidateCard({ c, profile, onDone }: { c: Candidate; profile: Profile; onDone: () => void }) {
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState(!c.proposed_criterion);
  const [form, setForm] = useState({
    proposed_criterion: c.proposed_criterion,
    evidence_type: c.evidence_type,
    title: c.title,
    summary: c.summary,
    date: c.document_date ?? "", // the document's own date (B2); empty when nothing says, never today by default
  });
  const crit = profile.criteria.find((x) => x.id === form.proposed_criterion);

  const act = async (fn: () => Promise<unknown>, msg: string) => {
    setBusy(true);
    try {
      await fn();
      toast(msg);
      onDone();
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setBusy(false); // a card that stays (Save without accepting) must be usable again (B1)
    }
  };

  const edits = () => ({
    proposed_criterion: form.proposed_criterion,
    evidence_type: form.evidence_type,
    title: form.title,
    summary: form.summary,
  });
  const accept = () =>
    act(async () => {
      const banked = (o: { scoreboard: { criteria: { id: string; status: string }[] } }) =>
        new Set(o.scoreboard.criteria.filter((x) => x.status === "banked").map((x) => x.id));
      const before = banked(await api.overview());
      await api.accept(c.id, { ...(editing ? edits() : {}), ...(editing && form.date ? { date: form.date } : {}) });
      const now = banked(await api.overview());
      if ([...now].some((id) => !before.has(id)) && banterOk()) toast(`${banterText("banked")} A criterion is now banked.`); // ADR 0010 §4
    }, "Accepted — exhibit filed and scoreboard updated");

  return (
    <article className="animate-rise border-b border-line px-5 py-6 last:border-b-0 md:px-6" data-candidate={c.id}>
      <div className="flex items-start gap-6">
        <div className="min-w-0 flex-1">
          <h3 className="text-lg leading-snug font-medium">
            {c.raw_url ? (
              <a href={c.raw_url} target="_blank" rel="noreferrer" className="link">
                {c.title}
              </a>
            ) : (
              c.title
            )}
          </h3>
          <p className="mt-2 max-w-3xl text-[15px] leading-relaxed text-ink-2">{c.summary}</p>
          {c.kind === "evidence" && (
            <p className="mt-1.5 font-mono text-[11px] tracking-[0.04em] text-muted">
              {c.document_date ? `Dated ${c.document_date}, ${DATE_SOURCE[c.date_source ?? "source"]}` : "No document date found: Edit to set it, or it's filed as date unconfirmed"}
            </p>
          )}
          <div className="mt-3 flex flex-wrap items-center gap-1.5">
            <Chip>{c.evidence_type}</Chip>
            <StageChip stage={c.stage} />
            {c.verification && <VerificationChip v={c.verification} note={c.verification_note ?? ""} />}
            {c.signals.map((s) => (
              <Chip key={s} tone="ink">
                {s}
              </Chip>
            ))}
            <span className="ml-1 font-mono text-[11px] text-muted">FROM {c.source}</span>
            <span className="font-mono text-[11px] text-muted @2xl:hidden">· {Math.round(c.confidence * 100)}% CONFIDENCE</span>
            {c.status === "snoozed" && <Chip tone="outline">snooze ended {c.snoozed_until}</Chip>}
          </div>
          {c.attachment && (
            <a href={api.attachmentUrl(c.attachment)} target="_blank" rel="noreferrer" className="link mt-3 inline-flex items-center gap-1.5 text-sm">
              <Paperclip className="size-4" strokeWidth={1.5} aria-hidden /> Preview the uploaded file
            </a>
          )}
          <ClaimsPanel ids={c.claim_ids} />
        </div>
        <Confidence value={c.confidence} />
      </div>

      {editing && (
        <div className="mt-5 grid gap-4 border-t border-line pt-5 sm:grid-cols-2">
          <label>
            <span className="label">Criterion</span>
            <select
              className="input"
              value={form.proposed_criterion}
              onChange={(e) => {
                const next = profile.criteria.find((x) => x.id === e.target.value);
                setForm({ ...form, proposed_criterion: e.target.value, evidence_type: next?.evidence_types.includes(form.evidence_type) ? form.evidence_type : (next?.evidence_types[0] ?? form.evidence_type) });
              }}
            >
              {!form.proposed_criterion && <option value="">Choose a criterion…</option>}
              {profile.criteria.map((x) => (
                <option key={x.id} value={x.id}>
                  {x.label}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span className="label">Evidence type</span>
            <select className="input" value={form.evidence_type} onChange={(e) => setForm({ ...form, evidence_type: e.target.value })}>
              {[...new Set([...(crit?.evidence_types ?? []), form.evidence_type])].map((t) => (
                <option key={t}>{t}</option>
              ))}
            </select>
          </label>
          <label className="sm:col-span-2">
            <span className="label">Title (used in the exhibit file name)</span>
            <input className="input" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
          </label>
          <label className="sm:col-span-2">
            <span className="label">Summary</span>
            <textarea className="input" rows={2} value={form.summary} onChange={(e) => setForm({ ...form, summary: e.target.value })} />
          </label>
          <label>
            <span className="label">Exhibit date — the date the document shows</span>
            <input type="date" className="input" value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} />
            <span className="mt-1 block text-xs text-ink-2">
              {c.document_date && form.date === c.document_date
                ? `Read ${DATE_SOURCE[c.date_source ?? "source"]}.`
                : form.date
                  ? "Set by you."
                  : "No date found. Enter the date the document shows, or accept it as date unconfirmed and set it later."}
            </span>
          </label>
        </div>
      )}

      <RuleCheckView check={c.rule_check} onRecheck={() => api.recheckCandidate(c.id).then(onDone).catch((e: Error) => toast(e.message, "error"))} />
      {blocking(c.rule_check).length > 0 && !editing && (
        <p className="mt-3 max-w-3xl font-mono text-[11px] leading-relaxed text-alert">
          This states rules the knowledge vault doesn't confirm, so it can't become an exhibit as written. Re-check after
          the vault refreshes, or edit the text into your own words.
        </p>
      )}
      <div className="mt-5 flex flex-wrap gap-2">
        <Button variant="primary" size="sm" disabled={busy || !form.proposed_criterion || (blocking(c.rule_check).length > 0 && !editing)} onClick={accept}>
          {editing ? "Save & accept" : "Accept"}
        </Button>
        <Button size="sm" disabled={busy} onClick={() => setEditing(!editing)}>
          {editing ? "Cancel edit" : "Edit"}
        </Button>
        {editing && (
          <Button
            size="sm"
            disabled={busy}
            onClick={() => act(() => api.editCandidate(c.id, edits()), "Saved")}
          >
            Save without accepting
          </Button>
        )}
        <Button size="sm" variant="ghost" disabled={busy} onClick={() => act(() => api.snooze(c.id, today(7)), "Snoozed for 7 days")}>
          Snooze 7d
        </Button>
        <Button size="sm" variant="danger" disabled={busy} onClick={() => act(() => api.reject(c.id), "Rejected — it won't come back on re-import")}>
          Reject
        </Button>
      </div>
    </article>
  );
}

const VERIFICATION: Record<string, { label: string; tone: "ink" | "muted" | "outline"; alert?: boolean }> = {
  verified: { label: "verified", tone: "ink" },
  confirmed: { label: "confirmed by reply", tone: "ink" },
  unconfirmed: { label: "unconfirmed", tone: "outline" },
  suspicious: { label: "suspicious sender", tone: "outline", alert: true },
};

/** A mail find's verification (ADR 0016): sender check + official page, a drafted check-in, or a failed check. */
function VerificationChip({ v, note }: { v: string; note: string }) {
  const s = VERIFICATION[v] ?? { label: v, tone: "muted" as const };
  return (
    <span title={note} className={s.alert ? "text-alert" : undefined}>
      <Chip tone={s.tone} className={s.alert ? "border-alert text-alert" : undefined}>
        {s.label}
      </Chip>
    </span>
  );
}
