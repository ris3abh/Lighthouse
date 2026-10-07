import { useState } from "react";
import type { RuleCheck, RuleClaim, RuleStatus } from "../api";
import { Button, Chip, cx } from "./ui";

const TONE: Record<RuleStatus, "emerald" | "amber" | "red"> = { verified: "emerald", unverified: "amber", stale: "amber", conflict: "red" };

export const blocking = (check?: RuleCheck | null) => (check?.claims ?? []).filter((c) => c.status !== "verified");

/** Rule claims in agent-written text and how each was checked against the knowledge vault (SPEC 5a). */
export default function RuleCheckView({
  check,
  onRecheck,
  compact,
}: {
  check?: RuleCheck | null;
  onRecheck?: () => Promise<unknown>;
  compact?: boolean;
}) {
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(!compact);
  if (!check || (!check.claims.length && !check.note?.startsWith("rule-check couldn't"))) return null;
  const counts = check.claims.reduce<Record<string, number>>((acc, c) => ({ ...acc, [c.status]: (acc[c.status] ?? 0) + 1 }), {});
  const summary = (["verified", "unverified", "stale", "conflict"] as RuleStatus[]).filter((s) => counts[s]).map((s) => `${counts[s]} ${s}`);
  return (
    <div className="mt-2 rounded-md border border-zinc-200 text-xs dark:border-zinc-800">
      <div className="flex items-center gap-2 px-2.5 py-1.5">
        <button type="button" className="flex flex-1 items-center gap-2 text-left" onClick={() => setOpen(!open)} aria-expanded={open}>
          <span className="font-medium text-zinc-600 dark:text-zinc-300">Rule check</span>
          <span className="text-zinc-500">{summary.join(" · ") || check.note}</span>
          <span className="ml-auto text-zinc-400">{open ? "▾" : "▸"}</span>
        </button>
        {onRecheck && (
          <Button
            size="sm"
            variant="ghost"
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              try {
                await onRecheck();
              } finally {
                setBusy(false);
              }
            }}
          >
            {busy ? "Checking…" : "Re-check"}
          </Button>
        )}
      </div>
      {open && (
        <ul className="divide-y divide-zinc-100 border-t border-zinc-100 dark:divide-zinc-800 dark:border-zinc-800">
          {check.claims.map((c) => (
            <ClaimRow key={c.id} c={c} />
          ))}
          {check.note && check.note !== "no rule statements" && <li className="px-2.5 py-1.5 text-zinc-500">{check.note}</li>}
        </ul>
      )}
    </div>
  );
}

function ClaimRow({ c }: { c: RuleClaim }) {
  return (
    <li className="px-2.5 py-2">
      <div className="flex items-start gap-2">
        <Chip tone={TONE[c.status]}>{c.status}</Chip>
        <p className="min-w-0 flex-1 text-zinc-700 dark:text-zinc-200">{c.sentence}</p>
      </div>
      {c.reason && <p className="mt-0.5 pl-1 text-zinc-500">{c.reason}</p>}
      {c.citations.map((x, i) => (
        <blockquote key={i} className={cx("mt-1.5 border-l-2 pl-2", x.verdict === "contradicts" ? "border-red-400" : "border-emerald-400", !x.fresh && "opacity-60")}>
          <p className="text-zinc-600 dark:text-zinc-300">“{x.quote}”</p>
          <p className="mt-0.5 text-[11px] text-zinc-400">
            {x.verdict === "contradicts" ? "contradicted by " : ""}Tier {x.tier} ·{" "}
            <a className="underline hover:text-zinc-700 dark:hover:text-zinc-200" href={x.url} target="_blank" rel="noreferrer">
              {x.title}
            </a>{" "}
            · checked {new Date(x.checked_at).toLocaleDateString()}
            {!x.fresh && " · stale"}
          </p>
        </blockquote>
      ))}
    </li>
  );
}
