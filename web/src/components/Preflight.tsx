import { ClipboardCheck } from "lucide-react";
import { useState } from "react";
import { api, type PreflightIssue, type PreflightReport } from "../api";
import { useLoad } from "../hooks";
import { Button, Card, Chip, cx, Empty, plural, useToast } from "./ui";

const KIND: Record<string, string> = {
  superseded_cited: "Outdated value cited",
  unsupported_cited: "Unsupported claim cited",
  conflicting_facts: "Facts disagree",
  metric_mismatch: "Metric differs",
  invited_not_completed: "Invited, not completed",
  capture_without_primary: "No primary copy",
  claim_without_exhibit: "Fact without an exhibit",
  undated_exhibit: "No document date",
};

/** Evidence preflight (ADR 0018): what a reviewer would notice, before they do. It never blocks anything; the
 * review packet carries the open issues. Severity is about noticeability, never about approval. */
export default function PreflightPanel({ version }: { version: number }) {
  const toast = useToast();
  const saved = useLoad(() => api.preflight(), [version]);
  const [report, setReport] = useState<PreflightReport | null>(null);
  const [busy, setBusy] = useState(false);
  const [showDismissed, setShowDismissed] = useState(false);
  const [showLow, setShowLow] = useState(false);
  const r = report ?? saved.data?.report ?? null;
  const run = async () => {
    setBusy(true);
    try {
      setReport((await api.runPreflight()).report);
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setBusy(false);
    }
  };
  const open = r ? r.issues.filter((i) => !i.dismissed) : [];
  const low = open.filter((i) => i.severity === "low");
  const shown = showLow ? open : open.filter((i) => i.severity !== "low");
  const dismissed = r ? r.issues.filter((i) => i.dismissed) : [];
  return (
    <Card
      title={r ? `Preflight · ${plural(open.length, "open issue")}` : "Preflight"}
      className="mb-8"
      panel="preflight"
      actions={
        <>
          {r && <span className="font-mono text-[11px] tracking-[0.06em] text-muted uppercase">Run {new Date(r.run_at).toLocaleString()}</span>}
          <Button size="sm" variant="primary" onClick={run} disabled={busy}>
            <ClipboardCheck /> {busy ? "Checking…" : r ? "Run again" : "Run preflight"}
          </Button>
        </>
      }
    >
      {!r ? (
        <Empty>
          Checks every exhibit, letter and draft for what a reviewer would notice: outdated or unsupported values, facts that disagree, invitations without
          proof they happened, captures without a primary copy, undated exhibits. Nothing is blocked; the review packet lists what's open.
        </Empty>
      ) : (
        <>
          <div className="flex flex-wrap gap-x-6 gap-y-1 border-b border-line px-5 py-3 font-mono text-xs text-ink-2">
            <span>
              <span className={cx(r.counts.high > 0 && "text-alert")}>{r.counts.high}</span> high
            </span>
            <span>{r.counts.medium} medium</span>
            <span>{r.counts.low} low</span>
            <span className="text-muted">
              {plural(r.exhibits, "exhibit")} · {plural(r.claims, "claim")} checked
            </span>
          </div>
          {open.length === 0 ? (
            <Empty>No open issues.</Empty>
          ) : (
            <>
              <ul className="divide-y divide-line">
                {shown.map((i) => (
                  <Issue key={i.id} i={i} onDismissed={(rep) => setReport(rep)} />
                ))}
              </ul>
              {low.length > 0 && (
                <div className="border-t border-line px-5 py-3">
                  <button className="link text-xs" onClick={() => setShowLow(!showLow)}>
                    {showLow ? "Hide" : "Show"} {plural(low.length, "low-severity issue")}
                  </button>
                </div>
              )}
            </>
          )}
          {dismissed.length > 0 && (
            <div className="border-t border-line px-5 py-3">
              <button className="link text-xs" onClick={() => setShowDismissed(!showDismissed)}>
                {showDismissed ? "Hide" : "Show"} {plural(dismissed.length, "dismissed issue")}
              </button>
              {showDismissed && (
                <ul className="mt-2 space-y-1 text-xs text-ink-2">
                  {dismissed.map((i) => (
                    <li key={i.id}>
                      {i.title} — <span className="text-muted">{i.dismissed_note}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </>
      )}
    </Card>
  );
}

function Issue({ i, onDismissed }: { i: PreflightIssue; onDismissed: (r: PreflightReport) => void }) {
  const toast = useToast();
  const [dismissing, setDismissing] = useState(false);
  const [allRefs, setAllRefs] = useState(false);
  const refs = allRefs ? i.refs : i.refs.slice(0, 5);
  const [note, setNote] = useState("");
  return (
    <li className="px-5 py-4">
      <div className="flex flex-wrap items-center gap-2">
        <Chip tone={i.severity === "high" ? "alert" : i.severity === "medium" ? "outline" : "muted"}>{i.severity}</Chip>
        <span className="font-mono text-[10.5px] tracking-[0.06em] text-muted uppercase">{KIND[i.kind] ?? i.kind}</span>
      </div>
      <p className="mt-1.5 font-medium">{i.title}</p>
      <p className="text-sm text-ink-2">{i.detail}</p>
      <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs">
        {refs.map((ref) => (
          <li key={`${ref.type}:${ref.id}`}>
            <span className="font-mono text-[10.5px] tracking-[0.06em] text-muted uppercase">{ref.type}</span>{" "}
            {ref.link ? (
              <a className="link" href={ref.link}>
                {ref.label}
              </a>
            ) : (
              ref.label
            )}
            {ref.value !== undefined && ref.value !== null && <span className="text-ink-2"> = {String(ref.value)}</span>}
            {ref.date && <span className="text-muted"> ({ref.date})</span>}
          </li>
        ))}
        {i.refs.length > refs.length && (
          <li>
            <button className="link text-muted" onClick={() => setAllRefs(true)}>
              +{i.refs.length - refs.length} more
            </button>
          </li>
        )}
      </ul>
      {dismissing ? (
        <form
          className="mt-3 flex flex-wrap items-center gap-2"
          onSubmit={async (e) => {
            e.preventDefault();
            try {
              onDismissed((await api.dismissPreflight(i.id, note)).report);
              toast("Dismissed");
            } catch (err) {
              toast((err as Error).message, "error");
            }
          }}
        >
          <input className="input h-8 max-w-sm text-sm" autoFocus required placeholder="Why it isn't a problem" value={note} onChange={(e) => setNote(e.target.value)} />
          <Button size="sm" type="submit">
            Dismiss
          </Button>
          <Button size="sm" variant="ghost" type="button" onClick={() => setDismissing(false)}>
            Cancel
          </Button>
        </form>
      ) : (
        <button className="link mt-2 text-xs text-muted" onClick={() => setDismissing(true)}>
          Not a problem…
        </button>
      )}
    </li>
  );
}
