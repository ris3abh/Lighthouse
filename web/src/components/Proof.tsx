import { Check, Link2, Minus, Upload, X } from "lucide-react";
import { useState } from "react";
import { api, type EvidenceCriterion, type ProofChecklist, type ProofItem } from "../api";
import { useLoad, useScrollTo } from "../hooks";
import { Button, Card, Chip, cx, plural, useToast } from "./ui";

export interface ProofUpload {
  anchor: string;
  item: string;
  label: string;
  evidence_type: string | null;
  stage: string | null;
}

/** Proof recipes (ADR 0017): for each accepted / completed / granted / published activity, the proof worth saving
 * while it's still easy to get. An item is done only when an exhibit preserves it, or you mark it not applicable. */
export default function ProofPanel({
  criteria,
  focus,
  version,
  onUpload,
  onChanged,
}: {
  criteria: EvidenceCriterion[];
  focus: string | null;
  version: number;
  onUpload: (crit: EvidenceCriterion, proof: ProofUpload) => void;
  onChanged: () => void;
}) {
  const view = useLoad(() => api.proof(), [version]);
  useScrollTo(focus ? `proof-${focus}` : null, !!view.data);
  const lists = view.data?.checklists ?? [];
  if (!lists.length) return null;
  const open = lists.filter((c) => c.missing).length;
  return (
    <Card
      title={`Proof to save · ${open ? plural(open, "activity", "activities") + " with gaps" : "all saved"}`}
      className="mb-8"
      panel="proof"
      actions={<span className="font-mono text-[11px] tracking-[0.06em] text-muted uppercase">Suggestions, not legal requirements</span>}
    >
      <ul className="divide-y divide-line">
        {lists.map((c) => (
          <Checklist
            key={c.anchor}
            c={c}
            crit={criteria.find((x) => x.id === c.criterion)}
            open={focus ? focus === c.anchor : c === lists.find((x) => x.missing)}
            onUpload={onUpload}
            onChanged={() => {
              view.reload();
              onChanged();
            }}
          />
        ))}
      </ul>
    </Card>
  );
}

function Checklist({
  c,
  crit,
  open,
  onUpload,
  onChanged,
}: {
  c: ProofChecklist;
  crit: EvidenceCriterion | undefined;
  open: boolean;
  onUpload: (crit: EvidenceCriterion, proof: ProofUpload) => void;
  onChanged: () => void;
}) {
  const done = c.items.filter((i) => i.status === "done" || i.status === "waived").length;
  return (
    <li id={`proof-${c.anchor}`}>
      <details open={open} className="group">
        <summary className="flex cursor-pointer list-none flex-wrap items-center gap-x-3 gap-y-1 px-5 py-3.5 hover:bg-sunken">
          <span className="font-medium">{c.title}</span>
          <Chip>{c.stage}</Chip>
          <span className="font-mono text-[11px] tracking-[0.06em] text-muted uppercase">
            {crit ? crit.short_label || crit.label : c.criterion} · {c.date}
          </span>
          <span className={cx("ml-auto font-mono text-xs", c.missing ? "text-ink" : "text-muted")}>
            {done}/{c.items.length} saved{c.missing ? ` · ${c.missing} to save` : ""}
          </span>
        </summary>
        <ul className="border-t border-line bg-surface">
          {c.items.map((i) => (
            <Item key={i.id} c={c} i={i} crit={crit} onUpload={onUpload} onChanged={onChanged} />
          ))}
        </ul>
      </details>
    </li>
  );
}

function Item({
  c,
  i,
  crit,
  onUpload,
  onChanged,
}: {
  c: ProofChecklist;
  i: ProofItem;
  crit: EvidenceCriterion | undefined;
  onUpload: (crit: EvidenceCriterion, proof: ProofUpload) => void;
  onChanged: () => void;
}) {
  const toast = useToast();
  const [linking, setLinking] = useState(false);
  const [waiving, setWaiving] = useState(false);
  const [note, setNote] = useState("");
  const act = async (fn: () => Promise<unknown>, ok: string) => {
    try {
      await fn();
      toast(ok);
      setLinking(false);
      setWaiving(false);
      onChanged();
    } catch (e) {
      toast((e as Error).message, "error");
    }
  };
  const others = (crit?.exhibits ?? []).filter((e) => `exhibit:${e.id}` !== c.anchor && !i.suggestions.some((s) => s.id === e.id));
  const missing = i.status === "missing" || i.status === "self_reported";
  return (
    <li className="grid gap-2 px-5 py-3 sm:grid-cols-[1.5rem_1fr_auto] sm:items-start" data-proof-item={`${c.anchor}#${i.id}`}>
      <span aria-hidden className="mt-0.5">
        {i.status === "done" ? <Check className="size-4 text-ink" /> : i.status === "waived" ? <Minus className="size-4 text-muted" /> : <span className="inline-block size-3.5 border border-dashed border-ink-2" title="Not saved yet" />}
      </span>
      <div className="min-w-0">
        <p className={cx("text-sm", i.status === "waived" && "text-muted line-through")}>
          {i.label}
          {i.optional && <span className="ml-2 font-mono text-[10.5px] tracking-[0.06em] text-muted uppercase">if available</span>}
        </p>
        <p className="text-xs text-ink-2">{i.why}</p>
        {i.exhibit_title && (
          <p className="mt-1 text-xs">
            {i.via === "anchor" ? "This exhibit: " : "Saved as: "}
            <span className="font-medium">{i.exhibit_title}</span>
            {i.status === "self_reported" && (
              <Chip tone="outline" className="ml-2">
                Self-reported, doesn't count
              </Chip>
            )}
          </p>
        )}
        {i.status === "waived" && <p className="mt-1 text-xs text-ink-2">Not applicable: {i.note}</p>}
        {linking && (
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <select
              className="input h-8 max-w-sm text-sm"
              defaultValue=""
              aria-label={`Exhibit that preserves: ${i.label}`}
              onChange={(e) => e.target.value && act(() => api.proofLink(c.anchor, i.id, e.target.value), "Linked")}
            >
              <option value="">Choose an exhibit…</option>
              {i.suggestions.length > 0 && (
                <optgroup label="Looks like a match">
                  {i.suggestions.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.title}
                    </option>
                  ))}
                </optgroup>
              )}
              <optgroup label="Other exhibits">
                {others.map((e) => (
                  <option key={e.id} value={e.id}>
                    {e.title}
                  </option>
                ))}
              </optgroup>
            </select>
            <Button size="sm" variant="ghost" onClick={() => setLinking(false)}>
              Cancel
            </Button>
          </div>
        )}
        {waiving && (
          <form
            className="mt-2 flex flex-wrap items-center gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              act(() => api.proofWaive(c.anchor, i.id, note), "Marked not applicable");
            }}
          >
            <input className="input h-8 max-w-sm text-sm" autoFocus required placeholder="Why it doesn't apply" value={note} onChange={(e) => setNote(e.target.value)} />
            <Button size="sm" type="submit">
              Save
            </Button>
            <Button size="sm" variant="ghost" type="button" onClick={() => setWaiving(false)}>
              Cancel
            </Button>
          </form>
        )}
      </div>
      <div className="flex flex-wrap gap-1.5 sm:justify-end">
        {missing && !linking && !waiving && (
          <>
            {crit && (
              <Button size="sm" onClick={() => onUpload(crit, { anchor: c.anchor, item: i.id, label: i.label, ...i.preset })}>
                <Upload /> Upload
              </Button>
            )}
            <Button size="sm" variant="ghost" onClick={() => setLinking(true)} disabled={!i.suggestions.length && !others.length}>
              <Link2 /> Link{i.suggestions.length ? ` (${i.suggestions.length} likely)` : ""}
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setWaiving(true)}>
              Not applicable
            </Button>
          </>
        )}
        {(i.via === "linked" || i.status === "waived") && (
          <Button size="sm" variant="ghost" onClick={() => act(() => api.proofUnlink(c.anchor, i.id), "Removed")}>
            <X /> {i.status === "waived" ? "Undo" : "Unlink"}
          </Button>
        )}
      </div>
    </li>
  );
}
