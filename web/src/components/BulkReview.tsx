import { Check, Clock, Undo2, X } from "lucide-react";
import { type ReactNode, useCallback, useEffect, useRef, useState } from "react";
import { api, type BulkRequest, type BulkResult, type Candidate, type InboxFilter, type InboxGroup } from "../api";
import { Button, Modal, plural, useToast } from "./ui";

/** Inbox bulk review (F9): filters, selection, batch actions with one Undo, and keys (j/k move, x select, a accept,
 * r reject). Every decision still goes through the server one item at a time, with the same rules as a click. */

export const KIND_LABEL: Record<string, string> = {
  evidence: "Evidence",
  deadline: "Deadlines",
  pipeline: "Pipeline ideas",
  letter: "Letter writers",
  update: "Updates",
  metric: "Metrics",
  context: "Notes",
};

export function matchesFilter(c: Candidate, f: InboxFilter, groupOf: (c: Candidate) => string): boolean {
  if (f.group && groupOf(c) !== f.group) return false;
  if (f.kind && c.kind !== f.kind) return false;
  if (f.text && !`${c.title} ${c.summary}`.toLowerCase().includes(f.text.toLowerCase())) return false;
  return true;
}

/** The selection, with shift-click ranges over the order the cards are shown in. */
export function useSelection(order: string[]) {
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const last = useRef<string | null>(null);
  const toggle = useCallback(
    (id: string, range: boolean) => {
      const anchor = last.current; // read now: the update below runs later, after this is overwritten
      setPicked((prev) => {
        const next = new Set(prev);
        if (range && anchor && order.includes(anchor)) {
          const [a, b] = [order.indexOf(anchor), order.indexOf(id)].sort((x, y) => x - y);
          const on = !prev.has(id);
          order.slice(a, b + 1).forEach((x) => (on ? next.add(x) : next.delete(x)));
        } else if (next.has(id)) next.delete(id);
        else next.add(id);
        return next;
      });
      last.current = id;
    },
    [order],
  );
  const setMany = useCallback((ids: string[], on: boolean) => {
    setPicked((prev) => {
      const next = new Set(prev);
      ids.forEach((x) => (on ? next.add(x) : next.delete(x)));
      return next;
    });
  }, []);
  const clear = useCallback(() => setPicked(new Set()), []);
  return { picked, toggle, setMany, clear };
}

export function SelectRow({ id, checked, onToggle, focused, children }: { id: string; checked: boolean; onToggle: (id: string, range: boolean) => void; focused: boolean; children: ReactNode }) {
  return (
    <div className={`flex items-start border-b border-line last:border-b-0 ${focused ? "outline-2 -outline-offset-2 outline-ink" : ""}`} data-row={id}>
      <label className="flex shrink-0 cursor-pointer items-center px-3 pt-7 md:pl-5" title="Select (shift-click for a range)">
        <input
          type="checkbox"
          className="size-4 accent-[var(--ink)]"
          checked={checked}
          aria-label="Select for bulk review"
          onChange={() => undefined}
          onClick={(e) => onToggle(id, (e as React.MouseEvent).shiftKey)}
        />
      </label>
      <div className="min-w-0 flex-1 [&>article]:border-b-0 [&>article]:pl-1 md:[&>article]:pl-1">{children}</div>
    </div>
  );
}

export function GroupCheckbox({ ids, picked, setMany }: { ids: string[]; picked: Set<string>; setMany: (ids: string[], on: boolean) => void }) {
  const all = ids.length > 0 && ids.every((x) => picked.has(x));
  const some = !all && ids.some((x) => picked.has(x));
  return (
    <input
      type="checkbox"
      className="size-4 accent-[var(--ink)]"
      aria-label={all ? "Unselect this group" : "Select this group"}
      checked={all}
      ref={(el) => {
        if (el) el.indeterminate = some;
      }}
      onChange={() => setMany(ids, !all)}
    />
  );
}

export function Filters({ groups, filter, setFilter, total, shown }: { groups: InboxGroup[]; filter: InboxFilter; setFilter: (f: InboxFilter) => void; total: number; shown: number }) {
  const kinds = Object.keys(KIND_LABEL);
  return (
    <div className="mb-6 flex flex-wrap items-end gap-3 border border-frame bg-surface px-4 py-3" role="search" aria-label="Filter the Inbox">
      <label>
        <span className="label">From</span>
        <select className="input h-9 py-0" value={filter.group ?? ""} onChange={(e) => setFilter({ ...filter, group: e.target.value || undefined })}>
          <option value="">Everywhere ({total})</option>
          {groups.map((g) => (
            <option key={g.key} value={g.key}>
              {g.label} ({g.count})
            </option>
          ))}
        </select>
      </label>
      <label>
        <span className="label">Kind</span>
        <select className="input h-9 py-0" value={filter.kind ?? ""} onChange={(e) => setFilter({ ...filter, kind: e.target.value || undefined })}>
          <option value="">Any</option>
          {kinds.map((k) => (
            <option key={k} value={k}>
              {KIND_LABEL[k]}
            </option>
          ))}
        </select>
      </label>
      <label className="min-w-48 flex-1">
        <span className="label">Contains</span>
        <input className="input h-9" type="search" placeholder="A name, an event, a word" value={filter.text ?? ""} onChange={(e) => setFilter({ ...filter, text: e.target.value || undefined })} />
      </label>
      <span className="pb-2 font-mono text-[11px] tracking-[0.06em] text-muted uppercase">
        {shown === total ? plural(total, "item") : `${shown} of ${total} shown`}
      </span>
      {(filter.group || filter.kind || filter.text) && (
        <Button size="sm" variant="ghost" onClick={() => setFilter({})}>
          Clear filters
        </Button>
      )}
    </div>
  );
}

export function BulkBar({
  picked,
  matching,
  filter,
  candidates,
  onClear,
  onSelectMatching,
  onDone,
}: {
  picked: Set<string>;
  matching: string[];
  filter: InboxFilter;
  candidates: Candidate[];
  onClear: () => void;
  onSelectMatching: () => void;
  onDone: (r: BulkResult, label: string) => void;
}) {
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState<Candidate[] | null>(null);
  const filtered = !!(filter.group || filter.kind || filter.text);
  const allMatching = filtered && picked.size === matching.length && matching.every((x) => picked.has(x));
  const run = async (action: BulkRequest["action"], confirm_evidence = false) => {
    setBusy(true);
    try {
      const body: BulkRequest = allMatching
        ? { action, filter, expect: matching.length, confirm_evidence }
        : { action, ids: [...picked], confirm_evidence };
      if (action === "snooze") body.until = undefined;
      const r = await api.bulkInbox(body);
      const verb = { accept: "Accepted", reject: "Rejected", snooze: "Snoozed" }[action];
      onDone(r, `${verb} ${plural(r.done.length, "item")}${r.failed.length ? ` · ${r.failed.length} not: ${r.failed[0].why}` : ""}`);
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setBusy(false);
      setConfirm(null);
    }
  };
  const accept = () => {
    const evidence = candidates.filter((c) => picked.has(c.id) && c.kind === "evidence");
    if (evidence.length) setConfirm(evidence);
    else run("accept");
  };
  if (!picked.size && !filtered) return null;
  return (
    <div className="sticky top-0 z-20 mb-6 flex flex-wrap items-center gap-2 border border-ink bg-ink px-4 py-2.5 text-on-ink" role="toolbar" aria-label="Bulk review">
      <span className="mr-2 font-mono text-[11px] tracking-[0.06em] uppercase">{picked.size ? `${picked.size} selected` : "None selected"}</span>
      {filtered && !allMatching && matching.length > 0 && (
        <button className="mr-2 text-xs underline underline-offset-2" onClick={onSelectMatching}>
          Select all {matching.length} matching
        </button>
      )}
      <span className="flex-1" />
      <Button size="sm" className="border-on-ink bg-on-ink text-ink hover:bg-paper disabled:bg-transparent disabled:text-on-ink" disabled={!picked.size || busy} onClick={accept}>
        <Check /> Accept
      </Button>
      <Button size="sm" className="border-on-ink text-on-ink hover:bg-ink-2" disabled={!picked.size || busy} onClick={() => run("reject")}>
        <X /> Reject
      </Button>
      <Button size="sm" className="border-on-ink text-on-ink hover:bg-ink-2" disabled={!picked.size || busy} onClick={() => run("snooze")}>
        <Clock /> Snooze 7d
      </Button>
      {picked.size > 0 && (
        <Button size="sm" variant="ghost" className="text-on-ink hover:bg-ink-2" onClick={onClear}>
          Clear
        </Button>
      )}
      {confirm && (
        <Modal title="Accept as evidence?" onClose={() => setConfirm(null)}>
          <p className="text-sm text-ink-2">
            {plural(confirm.length, "selected item")} will be filed as exhibits under their criteria, and the claims behind them approved. The rest of the
            selection is added to your trackers. You can undo the whole batch.
          </p>
          <ul className="mt-3 max-h-60 list-disc overflow-y-auto pl-5 text-sm">
            {confirm.slice(0, 30).map((c) => (
              <li key={c.id}>{c.title}</li>
            ))}
          </ul>
          <div className="mt-4 flex justify-end gap-2 border-t border-line pt-4">
            <Button onClick={() => setConfirm(null)}>Cancel</Button>
            <Button variant="primary" disabled={busy} onClick={() => run("accept", true)}>
              File {plural(confirm.length, "exhibit")}
            </Button>
          </div>
        </Modal>
      )}
    </div>
  );
}

export function UndoBanner({ last, onUndone }: { last: { batch: string; label: string } | null; onUndone: () => void }) {
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  if (!last) return null;
  return (
    <div className="mb-6 flex flex-wrap items-center justify-between gap-3 border border-frame bg-surface px-4 py-3 text-sm" role="status">
      <span>{last.label}</span>
      <Button
        size="sm"
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          try {
            const r = await api.undoBatch(last.batch);
            toast(`Undone: ${plural(r.undone.length, "item")} back in the Inbox${r.left.length ? `; ${r.left.length} left (${r.left[0].why})` : ""}`);
            onUndone();
          } catch (e) {
            toast((e as Error).message, "error");
          } finally {
            setBusy(false);
          }
        }}
      >
        <Undo2 /> Undo batch
      </Button>
    </div>
  );
}

/** j / k move between cards, x selects, a accepts, r rejects the focused card. Not while typing. */
export function useInboxKeys(order: string[], toggle: (id: string, range: boolean) => void) {
  const [cursor, setCursor] = useState<string | null>(null);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (e.metaKey || e.ctrlKey || e.altKey || ["INPUT", "TEXTAREA", "SELECT"].includes(t.tagName) || t.isContentEditable) return;
      if (document.querySelector("[role=dialog][aria-modal=true]")) return;
      const i = cursor ? order.indexOf(cursor) : -1;
      const move = (j: number) => {
        const id = order[Math.max(0, Math.min(order.length - 1, j))];
        if (!id) return;
        setCursor(id);
        document.querySelector(`[data-row="${CSS.escape(id)}"]`)?.scrollIntoView({ block: "nearest" });
      };
      const press = (label: RegExp) => {
        if (!cursor) return;
        const row = document.querySelector(`[data-row="${CSS.escape(cursor)}"]`);
        const b = [...(row?.querySelectorAll("button") ?? [])].find((x) => label.test(x.textContent?.trim() ?? ""));
        (b as HTMLButtonElement | undefined)?.click();
      };
      if (e.key === "j") move(i + 1);
      else if (e.key === "k") move(i - 1);
      else if (e.key === "x" && cursor) toggle(cursor, false);
      else if (e.key === "a") press(/^(Accept|Add|Keep)/);
      else if (e.key === "r") press(/^(Reject|Dismiss)/);
      else return;
      e.preventDefault();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [cursor, order, toggle]);
  return cursor;
}
