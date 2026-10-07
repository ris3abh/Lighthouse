import { ChevronDown } from "lucide-react";
import { useState } from "react";
import { api, type Claim, stageCounts } from "../api";
import { Chip, cx } from "./ui";

const STATUS_TONE: Record<Claim["status"], string> = {
  proposed: "text-ink-2",
  corroborated: "text-ink",
  approved: "text-ink font-semibold",
  rejected: "text-muted line-through",
};

/** Stage chip: completed stages are green; earlier ones (invited, preprint…) are amber and don't count yet. */
export function StageChip({ stage }: { stage: string | null }) {
  if (!stage) return null;
  return (
    <span title={stageCounts(stage) ? "Completed — counts toward the criterion" : "Not completed — doesn't count yet"}>
      <Chip tone={stageCounts(stage) ? "ink" : "outline"}>stage: {stage}</Chip>
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
      <button type="button" onClick={toggle} className="inline-flex items-center gap-1.5 font-mono text-[11px] text-ink-2 uppercase hover:text-ink" aria-expanded={open}>
        <ChevronDown className={cx("size-3.5 transition-transform duration-200", !open && "-rotate-90")} aria-hidden /> {verb} {ids.length} sourced claim{ids.length > 1 ? "s" : ""}
      </button>
      {open && (
        <div className="mt-2 animate-rise overflow-hidden border border-line">
          {error && <p className="p-2 text-xs text-alert">{error}</p>}
          {!claims && !error && <p className="p-2 text-xs text-muted">Loading…</p>}
          {claims?.map((c) => (
            <div key={c.id} className="border-b border-line px-4 py-3 text-xs last:border-b-0">
              <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
                <span className="font-medium text-ink">
                  {c.predicate.replace(/_/g, " ")} = <span className="tabular-nums">{String(c.value)}</span>
                </span>
                <span className={cx("font-mono text-[11px] uppercase", STATUS_TONE[c.status])}>{c.status}</span>
                <span className="font-mono text-[11px] text-muted">
                  confidence {c.confidence} · v{c.version}
                  {c.valid_from && ` · valid from ${c.valid_from}`}
                </span>
              </div>
              <code className="mt-2 block truncate border-l-2 border-ink bg-sunken px-2 py-1 font-mono text-[11px] text-ink" title={c.excerpt}>
                {c.excerpt}
              </code>
              <p className="mt-1 truncate font-mono text-[10.5px] text-muted" title={c.source_url ?? ""}>
                quoted from {c.source_url} · captured {c.captured_at?.slice(0, 10)} via {c.connector}
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
