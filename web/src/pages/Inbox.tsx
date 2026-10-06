import { useState } from "react";
import { api, type Candidate, type Profile } from "../api";
import { useRefresh } from "../App";
import ClaimsPanel, { StageChip } from "../components/Claims";
import { Button, Card, Chip, cx, Empty, ErrorBox, Loading, PageHeader, useToast } from "../components/ui";
import { today, useLoad } from "../hooks";

export default function Inbox() {
  const { version, bump } = useRefresh();
  const inbox = useLoad(() => Promise.all([api.inbox(), api.profile()]), [version]);
  if (inbox.error) return <ErrorBox error={inbox.error} retry={inbox.reload} />;
  if (!inbox.data) return <Loading />;
  const [candidates, profile] = inbox.data;

  const labels = Object.fromEntries(profile.criteria.map((c) => [c.id, c.label]));
  const groups = new Map<string, Candidate[]>();
  for (const c of candidates) groups.set(c.proposed_criterion, [...(groups.get(c.proposed_criterion) ?? []), c]);
  const order = [...groups.keys()].sort(
    (a, b) => profile.criteria.findIndex((c) => c.id === a) - profile.criteria.findIndex((c) => c.id === b),
  );

  return (
    <div className="mx-auto max-w-5xl">
      <PageHeader
        title="Inbox"
        subtitle="Connectors propose; you decide. Nothing becomes evidence until you accept it — and accepting records your decision, it doesn't certify legal sufficiency."
      />
      {candidates.length === 0 ? (
        <Card>
          <Empty>
            Inbox zero. New candidates arrive when you <a href="#/sources" className="link">add or sync a source</a>.
          </Empty>
        </Card>
      ) : (
        <div className="flex flex-col gap-5">
          {order.map((crit) => (
            <section key={crit}>
              <h2 className="mb-2 flex items-center gap-2 text-sm font-semibold">
                {labels[crit] ?? crit}
                <span className="rounded-full bg-zinc-200 px-1.5 text-xs tabular-nums dark:bg-zinc-800">{groups.get(crit)!.length}</span>
                {!labels[crit] && <span className="text-xs font-normal text-amber-600">not in the {profile.name} profile</span>}
              </h2>
              <div className="flex flex-col gap-2">
                {groups.get(crit)!.map((c) => (
                  <CandidateCard key={c.id} c={c} profile={profile} onDone={bump} />
                ))}
              </div>
            </section>
          ))}
        </div>
      )}
    </div>
  );
}

function Confidence({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-zinc-500" title="How sure the connector is that this is evidence">
      <span className="h-1.5 w-12 overflow-hidden rounded-full bg-zinc-200 dark:bg-zinc-800">
        <span className={cx("block h-full rounded-full", pct >= 65 ? "bg-emerald-500" : pct >= 45 ? "bg-amber-500" : "bg-zinc-400")} style={{ width: `${pct}%` }} />
      </span>
      {pct}%
    </span>
  );
}

function CandidateCard({ c, profile, onDone }: { c: Candidate; profile: Profile; onDone: () => void }) {
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({
    proposed_criterion: c.proposed_criterion,
    evidence_type: c.evidence_type,
    title: c.title,
    summary: c.summary,
    date: today(),
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
      setBusy(false);
    }
  };

  const edits = () => ({
    proposed_criterion: form.proposed_criterion,
    evidence_type: form.evidence_type,
    title: form.title,
    summary: form.summary,
  });
  const accept = () =>
    act(() => api.accept(c.id, { ...(editing ? edits() : {}), date: form.date }), "Accepted — exhibit filed and scoreboard updated");

  return (
    <article className="card p-4">
      <div className="flex flex-wrap items-start gap-3">
        <div className="min-w-0 flex-1">
          <h3 className="text-sm font-medium">
            {c.raw_url ? (
              <a href={c.raw_url} target="_blank" rel="noreferrer" className="link">
                {c.title}
              </a>
            ) : (
              c.title
            )}
          </h3>
          <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-300">{c.summary}</p>
          <div className="mt-2 flex flex-wrap items-center gap-1.5">
            <Chip>{c.evidence_type}</Chip>
            <StageChip stage={c.stage} />
            {c.signals.map((s) => (
              <Chip key={s} tone="emerald">
                {s}
              </Chip>
            ))}
            <span className="text-xs text-zinc-400">from {c.source}</span>
            {c.status === "snoozed" && <Chip tone="amber">snooze ended {c.snoozed_until}</Chip>}
          </div>
          <ClaimsPanel ids={c.claim_ids} />
        </div>
        <Confidence value={c.confidence} />
      </div>

      {editing && (
        <div className="mt-3 grid gap-3 border-t border-zinc-100 pt-3 sm:grid-cols-2 dark:border-zinc-800">
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
            <span className="label">Exhibit date</span>
            <input type="date" className="input" value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} />
          </label>
        </div>
      )}

      <div className="mt-3 flex flex-wrap gap-2">
        <Button variant="primary" size="sm" disabled={busy} onClick={accept}>
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
