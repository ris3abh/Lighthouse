import { useState } from "react";
import { api, type Candidate } from "../api";
import ClaimsPanel, { StageChip } from "./Claims";
import RuleCheckView, { blocking } from "./RuleCheck";
import { Button, Chip, useToast } from "./ui";
import { today } from "../hooks";

export const TRACKER_LABEL = {
  deadline: "Deadlines",
  pipeline: "Pipeline",
  letter: "Letter writers",
  update: "Tracker updates",
  metric: "Metrics",
} as const;
const ADD_TO = {
  deadline: "Add to deadlines",
  pipeline: "Add to pipeline",
  letter: "Add to letters",
  update: "Apply update",
  metric: "Record metric",
} as const;
const PIPELINE_STAGES = ["idea", "applied", "waiting", "done"];
const LETTER_STATUSES = ["prospect", "asked", "drafting", "sent", "signed", "declined"];
const RELATIONSHIPS = ["employer", "independent", "coauthor"];

type Proposal = Record<string, string | boolean | null | undefined>;

/** A self-reported tracker candidate (from imported chats): becomes a deadline / pipeline item / letter writer. */
export default function TrackerCard({ c, onDone }: { c: Candidate; onDone: () => void }) {
  const toast = useToast();
  const kind = c.kind as keyof typeof TRACKER_LABEL;
  const [p, setP] = useState<Proposal>(c.proposal as Proposal);
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const set = (k: string, v: string) => setP({ ...p, [k]: v });

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
  const add = () =>
    act(async () => {
      if (editing) await api.editCandidate(c.id, { proposal: p } as Partial<Candidate>);
      await api.accept(c.id, {});
    }, `${ADD_TO[kind].replace("Add to", "Added to")}`);

  return (
    <article className="card p-3">
      <div className="flex flex-wrap items-start gap-2">
        <div className="min-w-0 flex-1">
          <h3 className="text-sm font-medium">{kind === "letter" ? String(p.name) : kind === "update" || kind === "metric" ? c.title : String(p.title)}</h3>
          {kind === "update" && (
            <p className="mt-0.5 text-xs text-zinc-500">
              {String(p.target_type).replace("_", " ")}:{" "}
              {Object.entries((p.changes as unknown as Record<string, unknown>) ?? {})
                .map(([k, v]) => `${k} → ${String(v)}`)
                .join(", ")}
            </p>
          )}
          <p className="mt-0.5 flex flex-wrap items-center gap-1.5 text-xs text-zinc-500">
            {kind === "deadline" && <span className="font-medium tabular-nums text-zinc-700 dark:text-zinc-200">due {String(p.due)}</span>}
            {kind === "pipeline" && <Chip>pipeline: {String(p.stage)}</Chip>}
            {kind === "letter" && (
              <>
                <Chip>{String(p.relationship)}</Chip>
                <Chip>{String(p.status)}</Chip>
              </>
            )}
            <StageChip stage={c.stage} />
            {c.source_tier === "self_reported" ? <Chip tone="amber">self-reported</Chip> : c.source.startsWith("agent:") ? <Chip>from the agent</Chip> : null}
          </p>
          <p className="mt-1.5 text-xs text-zinc-600 dark:text-zinc-400">{c.summary}</p>
          <ClaimsPanel ids={c.claim_ids} verb="Adding approves" />
        </div>
      </div>

      {editing && (
        <div className="mt-3 grid gap-2 border-t border-zinc-100 pt-3 sm:grid-cols-2 dark:border-zinc-800">
          {kind !== "letter" && (
            <label className="sm:col-span-2">
              <span className="label">Title</span>
              <input className="input" value={String(p.title ?? "")} onChange={(e) => set("title", e.target.value)} />
            </label>
          )}
          {kind === "deadline" && (
            <label>
              <span className="label">Due</span>
              <input type="date" className="input" min={today(-365)} value={String(p.due ?? "")} onChange={(e) => set("due", e.target.value)} />
            </label>
          )}
          {kind === "pipeline" && (
            <label>
              <span className="label">Stage</span>
              <select className="input" value={String(p.stage)} onChange={(e) => set("stage", e.target.value)}>
                {PIPELINE_STAGES.map((s) => (
                  <option key={s}>{s}</option>
                ))}
              </select>
            </label>
          )}
          {kind === "letter" && (
            <>
              <label>
                <span className="label">Name</span>
                <input className="input" value={String(p.name ?? "")} onChange={(e) => set("name", e.target.value)} />
              </label>
              <label>
                <span className="label">Relationship</span>
                <select className="input" value={String(p.relationship)} onChange={(e) => set("relationship", e.target.value)}>
                  {RELATIONSHIPS.map((s) => (
                    <option key={s}>{s}</option>
                  ))}
                </select>
              </label>
              <label>
                <span className="label">Status</span>
                <select className="input" value={String(p.status)} onChange={(e) => set("status", e.target.value)}>
                  {LETTER_STATUSES.map((s) => (
                    <option key={s}>{s}</option>
                  ))}
                </select>
              </label>
            </>
          )}
        </div>
      )}

      <RuleCheckView check={c.rule_check} onRecheck={() => api.recheckCandidate(c.id).then(onDone).catch((e: Error) => toast(e.message, "error"))} />
      {blocking(c.rule_check).length > 0 && (
        <p className="mt-2 text-xs text-amber-800 dark:text-amber-300">States rules the knowledge vault doesn't confirm; it can't be added as written.</p>
      )}
      <div className="mt-3 flex flex-wrap gap-2">
        <Button variant="primary" size="sm" disabled={busy} onClick={add}>
          {editing ? `Save & ${ADD_TO[kind].toLowerCase()}` : ADD_TO[kind]}
        </Button>
        {kind !== "update" && kind !== "metric" && (
          <Button size="sm" disabled={busy} onClick={() => setEditing(!editing)}>
            {editing ? "Cancel edit" : "Edit"}
          </Button>
        )}
        <Button size="sm" variant="ghost" disabled={busy} onClick={() => act(() => api.snooze(c.id, today(7)), "Snoozed for 7 days")}>
          Snooze 7d
        </Button>
        <Button size="sm" variant="danger" disabled={busy} onClick={() => act(() => api.reject(c.id), "Dismissed. It won't come back on re-import.")}>
          Dismiss
        </Button>
      </div>
    </article>
  );
}
