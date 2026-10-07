import { X } from "lucide-react";
import { useRef, useState } from "react";
import { edit, finalList, onFieldKey, onPaste, remove, type ChipState } from "../lib/chips";
import { cx } from "./ui";

/** One shared list input (C12): ";", Enter or a pasted list turns text into chips; Backspace on an empty field
 * removes the last chip; click a chip (or Enter on it) to edit it; Delete removes a focused chip. ``labels`` shows
 * a better name for a chip (a paper's real title, once a lookup the person said Yes to found it). */
export default function ChipInput({
  id,
  label,
  value,
  onChange,
  labels = {},
  placeholder = "Type, then ; or Enter",
}: {
  id: string;
  label: string;
  value: string[];
  onChange: (items: string[]) => void;
  labels?: Record<string, string>;
  placeholder?: string;
}) {
  const [s, setS] = useState<ChipState>({ chips: value, draft: "", editing: null });
  const field = useRef<HTMLInputElement>(null);
  const chipRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const update = (next: ChipState) => {
    setS(next);
    onChange(finalList(next));
  };
  const focusField = () => requestAnimationFrame(() => field.current?.focus());

  const fieldEl = (
    <input
      ref={field}
      id={id}
      className={cx("min-w-[12ch] flex-1 bg-transparent py-1 text-base outline-none", s.editing !== null && "border-b border-ink")}
      value={s.draft}
      placeholder={s.chips.length ? "" : placeholder}
      aria-label={s.editing !== null ? `Editing item ${s.editing + 1} of ${label}` : `Add to ${label}`}
      onChange={(e) => update({ ...s, draft: e.target.value })}
      onPaste={(e) => {
        const r = onPaste(s, e.clipboardData.getData("text"));
        if (r.handled) {
          e.preventDefault();
          update(r.state);
        }
      }}
      onKeyDown={(e) => {
        if (e.key === "ArrowLeft" && !s.draft && s.chips.length) {
          chipRefs.current[s.chips.length - 1]?.focus();
          return;
        }
        if (e.key === "Escape" && s.editing !== null) {
          e.preventDefault();
          e.stopPropagation();
          update({ ...s, draft: "", editing: null });
          return;
        }
        const r = onFieldKey(s, { key: e.key });
        if (r.handled) {
          e.preventDefault();
          update(r.state);
        }
      }}
    />
  );

  return (
    <div
      role="group"
      aria-label={label}
      className="input flex h-auto min-h-12 flex-wrap items-center gap-1.5 py-1.5"
      onClick={(e) => e.target === e.currentTarget && field.current?.focus()}
    >
      {s.chips.map((chip, i) =>
        s.editing === i ? (
          <span key="editing" className="contents">{fieldEl}</span>
        ) : (
          <span key={`${chip}-${i}`} className="inline-flex max-w-full animate-flash items-stretch border border-ink bg-sunken text-sm">
            <button
              type="button"
              ref={(el) => {
                chipRefs.current[i] = el;
              }}
              className="max-w-[48ch] truncate px-2 py-1 text-left hover:bg-ink hover:text-on-ink"
              title={labels[chip] ? `${labels[chip]} (${chip})` : `Edit: ${chip}`}
              aria-label={`Edit ${labels[chip] ?? chip}`}
              onClick={() => {
                update(edit(s, i));
                focusField();
              }}
              onKeyDown={(e) => {
                if (e.key === "Delete" || e.key === "Backspace") {
                  e.preventDefault();
                  update(remove(s, i));
                  (chipRefs.current[i - 1] ?? field.current)?.focus();
                } else if (e.key === "ArrowLeft") chipRefs.current[i - 1]?.focus();
                else if (e.key === "ArrowRight") (chipRefs.current[i + 1] ?? field.current)?.focus();
              }}
            >
              {labels[chip] ?? chip}
            </button>
            <button
              type="button"
              className="border-l border-ink px-1.5 hover:bg-ink hover:text-on-ink"
              aria-label={`Remove ${labels[chip] ?? chip}`}
              onClick={() => {
                update(remove(s, i));
                focusField();
              }}
            >
              <X className="size-3.5" aria-hidden />
            </button>
          </span>
        ),
      )}
      {s.editing === null && fieldEl}
    </div>
  );
}
