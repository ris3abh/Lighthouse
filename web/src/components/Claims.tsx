import { useState } from "react";
import { api, type Claim, stageCounts } from "../api";
import { Chip, cx } from "./ui";

const STATUS_TONE: Record<Claim["status"], string> = {
  proposed: "text-zinc-500",
  corroborated: "text-sky-600 dark:text-sky-400",
  approved: "text-emerald-600 dark:text-emerald-400",
  rejected: "text-red-600 dark:text-red-400",
};

/** Stage chip: completed stages are green; earlier ones (invited, preprint…) are amber and don't count yet. */
export function StageChip({ stage }: { stage: string | null }) {
  if (!stage) return null;
  return (
    <span title={stageCounts(stage) ? "Completed — counts toward the criterion" : "Not completed — doesn't count yet"}>
      <Chip tone={stageCounts(stage) ? "emerald" : "amber"}>stage: {stage}</Chip>
    </span>
  );
}

/** Expandable list of the memory claims behind a candidate or exhibit, each with its verbatim source quote. */
export default function ClaimsPanel({ ids, verb = "Accepting approves" }: { ids: string[]; verb?: string }) {
  const [open, setOpen] = useState(false);
  const [claims, setClaims] = useState<Claim[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  if (!ids.length) return null;

  const toggle = () => {
    setOpen(!open);
    if (!claims)
      api
        .claims(ids)
        .then(setClaims)
        .catch((e: Error) => setError(e.message));
  };

  return (
    <div className="mt-2">
      <button type="button" onClick={toggle} className="text-xs text-zinc-500 hover:text-zinc-900 dark:hover:text-white" aria-expanded={open}>
        {open ? "▾" : "▸"} {verb} {ids.length} sourced claim{ids.length > 1 ? "s" : ""}
      </button>
      {open && (
        <div className="mt-1.5 overflow-hidden rounded-md border border-zinc-200 dark:border-zinc-800">
          {error && <p className="p-2 text-xs text-red-600">{error}</p>}
          {!claims && !error && <p className="p-2 text-xs text-zinc-500">Loading…</p>}
          {claims?.map((c) => (
            <div key={c.id} className="border-b border-zinc-100 px-3 py-2 text-xs last:border-b-0 dark:border-zinc-800">
              <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
                <span className="font-medium">
                  {c.predicate.replace(/_/g, " ")} = <span className="tabular-nums">{String(c.value)}</span>
                </span>
                <span className={cx("font-medium", STATUS_TONE[c.status])}>{c.status}</span>
                <span className="text-zinc-400">
                  confidence {c.confidence} · v{c.version}
                  {c.valid_from && ` · valid from ${c.valid_from}`}
                </span>
              </div>
              <code className="mt-1 block truncate rounded bg-zinc-50 px-1.5 py-0.5 text-[11px] text-zinc-700 dark:bg-zinc-950 dark:text-zinc-300" title={c.excerpt}>
                {c.excerpt}
              </code>
              <p className="mt-0.5 truncate text-[11px] text-zinc-400" title={c.source_url ?? ""}>
                quoted from {c.source_url} · captured {c.captured_at?.slice(0, 10)} via {c.connector}
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
