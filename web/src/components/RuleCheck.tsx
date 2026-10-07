import { useState } from "react";
import type { RuleCheck, RuleClaim, RuleStatus } from "../api";
import { ChevronDown, ShieldCheck } from "lucide-react";
import { Button, Chip, cx } from "./ui";

const TONE: Record<RuleStatus, "ink" | "outline" | "alert"> = { verified: "ink", unverified: "alert", stale: "outline", conflict: "alert" };

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
    <div className="mt-3 border border-line text-xs" data-serious>
      <div className="flex items-center gap-2 px-3 py-2">
        <button type="button" className="flex flex-1 items-center gap-2 text-left" onClick={() => setOpen(!open)} aria-expanded={open}>
          <ShieldCheck className="size-3.5 text-ink-2" aria-hidden />
          <span className="eyebrow text-ink-2">Rule check</span>
          <span className="font-mono text-[11px] text-ink-2">{summary.join(" · ") || check.note}</span>
          <ChevronDown className={cx("ml-auto size-3.5 text-muted transition-transform duration-200", !open && "-rotate-90")} aria-hidden />
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
        <ul className="divide-y divide-line border-t border-line">
          {check.claims.map((c) => (
            <ClaimRow key={c.id} c={c} />
          ))}
          {check.note && check.note !== "no rule statements" && <li className="px-3 py-2 text-ink-2">{check.note}</li>}
        </ul>
      )}
    </div>
  );
}

function ClaimRow({ c }: { c: RuleClaim }) {
  return (
    <li className="px-3 py-3">
      <div className="flex items-start gap-2">
        <Chip tone={TONE[c.status]}>{c.status}</Chip>
        <p className="min-w-0 flex-1 text-[13px] leading-snug text-ink">{c.sentence}</p>
      </div>
      {c.reason && <p className={cx("mt-1 font-mono text-[11px]", c.status === "verified" ? "text-ink-2" : "text-alert")}>{c.reason}</p>}
      {c.citations.map((x, i) => (
        <blockquote key={i} className={cx("mt-2 border-l-2 pl-3", x.verdict === "contradicts" ? "border-alert" : "border-ink", !x.fresh && "opacity-60")}>
          <p className="text-[13px] text-ink-2">“{x.quote}”</p>
          <p className="mt-1 font-mono text-[10.5px] text-muted">
            {x.verdict === "contradicts" ? "contradicted by " : ""}Tier {x.tier} ·{" "}
            <a className="link hover:text-ink" href={x.url} target="_blank" rel="noreferrer">
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
