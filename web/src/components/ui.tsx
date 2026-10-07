import { ArrowDownRight, ArrowUpRight, Minus, X } from "lucide-react";
import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import type { CriterionStatus } from "../api";
import { useBackToClose } from "../hooks";
import { CountUp, useInView, useReducedMotion } from "../lib/motion";

/** Brutalism 2.0 primitives (ADR 0007). Pages use these and the semantic tokens, never raw palette colors. */

export function cx(...parts: (string | false | null | undefined)[]) {
  return parts.filter(Boolean).join(" ");
}

type Variant = "primary" | "secondary" | "ghost" | "danger";

const VARIANTS: Record<Variant, string> = {
  primary: "border border-ink bg-ink text-on-ink hover:bg-ink-2 hover:border-ink-2",
  secondary: "border border-ink bg-transparent text-ink hover:bg-sunken",
  ghost: "border border-transparent text-ink-2 hover:bg-sunken hover:text-ink",
  // Destructive but not "attention": monochrome. Red is reserved for conflicts, overdue and refusals.
  danger: "border border-line text-ink-2 hover:border-ink hover:text-ink",
};

export function Button({
  variant = "secondary",
  size = "md",
  className,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: "sm" | "md"; ref?: React.Ref<HTMLButtonElement> }) {
  return (
    <button
      {...props}
      className={cx(
        "inline-flex items-center justify-center gap-2 font-medium whitespace-nowrap transition-colors duration-150 disabled:cursor-not-allowed disabled:opacity-40 [&_svg]:size-4 [&_svg]:shrink-0",
        size === "sm" ? "h-8 px-3 text-xs" : "h-10 px-4 text-sm",
        VARIANTS[variant],
        className,
      )}
    />
  );
}

/** Status by fill and by the status palette (ADR 0007): banked solid green, building half amber, gap hollow ink,
 * dropped struck through. Fill still carries the meaning without color. */
export const STATUS_STYLE: Record<CriterionStatus, { label: string; mark: string; text: string }> = {
  banked: { label: "Banked", mark: "bg-banked border-banked", text: "text-banked" },
  building: { label: "Building", mark: "border-building bg-[linear-gradient(90deg,var(--building)_50%,transparent_50%)]", text: "text-building" },
  gap: { label: "Gap", mark: "border-ink bg-transparent", text: "text-ink-2" },
  dropped: { label: "Dropped", mark: "border-muted bg-transparent", text: "text-muted line-through" },
};

export function StatusMark({ status, className }: { status: CriterionStatus; className?: string }) {
  return <span aria-hidden className={cx("inline-block size-2.5 shrink-0 border transition-[background] duration-300", STATUS_STYLE[status].mark, className)} />;
}

export function StatusBadge({ status }: { status: CriterionStatus }) {
  const s = STATUS_STYLE[status];
  // Keyed by status so a change (gap -> building -> banked) replays the short flash.
  return (
    <span key={status} className={cx("inline-flex animate-flash items-center gap-1.5 font-mono text-[11px] tracking-[0.1em] uppercase", s.text)}>
      <StatusMark status={status} />
      {s.label}
    </span>
  );
}

type Tone = "ink" | "outline" | "muted" | "alert" | "banked" | "building";

/** Tag. Monochrome: "ink" = solid, "outline" = framed (notice), "muted" = quiet. Status only: "banked" (green),
 * "building" (amber), "alert" (red: conflicts, overdue, refused). */
export function Chip({ children, tone = "muted", className }: { children: ReactNode; tone?: Tone; className?: string }) {
  const tones: Record<Tone, string> = {
    ink: "border-ink bg-ink text-on-ink",
    outline: "border-ink text-ink",
    muted: "border-line text-ink-2",
    alert: "border-alert text-alert",
    banked: "border-banked bg-banked-soft text-banked",
    building: "border-building bg-building-soft text-building",
  };
  return (
    <span className={cx("inline-flex h-5 items-center gap-1 border px-1.5 font-mono text-[10.5px] tracking-[0.06em] whitespace-nowrap uppercase [&_svg]:size-3", tones[tone], className)}>
      {children}
    </span>
  );
}

/** A criterion's short name ("Awards") with its full regulatory wording on hover. */
export function CriterionName({ c, className }: { c: { label: string; short_label?: string }; className?: string }) {
  const short = c.short_label || c.label;
  return (
    <span className={className} title={short !== c.label ? c.label : undefined}>
      {short}
    </span>
  );
}

export function Card({
  title,
  actions,
  children,
  className,
  bodyClassName,
}: {
  title?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
}) {
  return (
    <section className={cx("card animate-rise", className)}>
      {(title || actions) && (
        <header className="flex min-h-12 flex-wrap items-center justify-between gap-x-3 gap-y-2 border-b border-line px-5 py-2.5">
          <h2 className="eyebrow text-ink">{title}</h2>
          {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
        </header>
      )}
      {bodyClassName ? <div className={bodyClassName}>{children}</div> : children}
    </section>
  );
}

export function PageHeader({ title, subtitle, actions, eyebrow }: { title: string; subtitle?: ReactNode; actions?: ReactNode; eyebrow?: ReactNode }) {
  return (
    <div className="mb-8 flex flex-wrap items-end justify-between gap-x-6 gap-y-4 border-b border-frame pb-5">
      <div className="min-w-0">
        {eyebrow && <p className="eyebrow mb-3">{eyebrow}</p>}
        <h1 className="display text-5xl break-words md:text-7xl">{title}</h1>
        {subtitle && <p className="mt-3 max-w-2xl text-[15px] leading-relaxed text-ink-2">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

/** A big number with a mono label; counts up on first view. */
export function Stat({ label, value, sub, alert, decimals }: { label: ReactNode; value: number | null | undefined; sub?: ReactNode; alert?: boolean; decimals?: number }) {
  return (
    <div className="min-w-0">
      <p className="eyebrow">{label}</p>
      <p className={cx("display mt-2 text-5xl md:text-6xl", alert && "text-alert")}>
        {value === null || value === undefined ? "—" : <CountUp value={value} decimals={decimals} />}
      </p>
      {sub && <div className="mt-2 font-mono text-xs text-ink-2">{sub}</div>}
    </div>
  );
}

/** Fills to its level the first time it's on screen. */
export function Progress({ value, max, alert, label }: { value: number; max: number; alert?: boolean; label?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const seen = useInView(ref);
  const pct = max > 0 ? Math.min(100, (value / max) * 100) : 0;
  return (
    <div ref={ref} className="h-2 w-full border border-ink" role="progressbar" aria-valuemin={0} aria-valuemax={max} aria-valuenow={value} aria-label={label}>
      <div className={cx("h-full transition-[width] duration-[400ms] ease-out", alert ? "bg-alert" : "bg-ink")} style={{ width: seen ? `${pct}%` : 0 }} />
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="px-5 py-12 text-center text-sm text-ink-2">{children}</div>;
}

export function Loading() {
  return (
    <div className="flex items-center gap-3 p-10 font-mono text-xs tracking-[0.14em] text-muted uppercase">
      <span className="size-2 animate-tool-pulse bg-ink" />
      Loading
    </div>
  );
}

export function ErrorBox({ error, retry }: { error: Error; retry?: () => void }) {
  return (
    <div className="border border-alert bg-surface p-5 text-sm">
      <p className="eyebrow text-alert">Couldn't load this page</p>
      <p className="mt-2 text-ink-2">{error.message}</p>
      {retry && (
        <Button className="mt-4" size="sm" onClick={retry}>
          Retry
        </Button>
      )}
    </div>
  );
}

const IRREGULAR: Record<string, string> = { criterion: "criteria", entry: "entries" };

/** "1 candidate", "12 candidates", "3 criteria" (the last word of a phrase is pluralized). */
export function plural(n: number, word: string, many?: string) {
  if (n === 1) return `1 ${word}`;
  if (!many) {
    const parts = word.split(" ");
    const last = parts.pop()!;
    parts.push(IRREGULAR[last] ?? last + (/(s|x|ch|sh)$/.test(last) ? "es" : "s"));
    many = parts.join(" ");
  }
  return `${n.toLocaleString()} ${many}`;
}

export function fmt(n: number | null | undefined) {
  if (n === null || n === undefined) return "—";
  return Number.isInteger(n) ? n.toLocaleString() : n.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

/** Change since the last snapshot. Not an alert, so ink either way; slides in. */
export function Delta({ value }: { value: number | null }) {
  if (value === null) return <span className="font-mono text-muted">—</span>;
  const Icon = value > 0 ? ArrowUpRight : value < 0 ? ArrowDownRight : Minus;
  return (
    <span className={cx("inline-flex animate-slide-in items-center gap-0.5 font-mono tabular-nums", value === 0 ? "text-muted" : "text-ink")}>
      <Icon className="size-3.5" aria-hidden />
      {value > 0 ? "+" : ""}
      {fmt(value)}
    </span>
  );
}

/** Segmented control (mono, framed). */
export function Segmented<T extends string>({
  value,
  options,
  onChange,
  label,
  size = "md",
}: {
  value: T;
  options: { value: T; label: ReactNode; title?: string }[];
  onChange: (v: T) => void;
  label: string;
  size?: "sm" | "md";
}) {
  return (
    <div className="inline-flex border border-ink" role="group" aria-label={label}>
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          title={o.title}
          aria-pressed={o.value === value}
          onClick={() => onChange(o.value)}
          className={cx(
            "inline-flex items-center gap-1.5 font-mono tracking-[0.08em] whitespace-nowrap uppercase transition-colors duration-150 [&_svg]:size-3.5",
            size === "sm" ? "h-7 px-2 text-[10.5px]" : "h-8 px-3 text-[11px]",
            o.value === value ? "bg-ink text-on-ink" : "text-ink-2 hover:bg-sunken hover:text-ink",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function Modal({ title, onClose, children, wide }: { title: string; onClose: () => void; children: ReactNode; wide?: boolean }) {
  useBackToClose(true, onClose); // the browser's Back closes the dialog, not the page
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-paper/85 p-4 pt-[8vh]" onMouseDown={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className={cx("card w-full animate-rise", wide ? "max-w-4xl" : "max-w-xl")}
        onMouseDown={(e) => e.stopPropagation()}
      >
        <header className="flex items-center justify-between border-b border-frame px-5 py-3">
          <h2 className="display text-3xl">{title}</h2>
          <Button variant="ghost" size="sm" onClick={onClose} aria-label="Close" className="px-2">
            <X />
          </Button>
        </header>
        <div className="p-5">{children}</div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- toasts

type Toast = { id: number; text: string; tone: "ok" | "error" };
const ToastCtx = createContext<(text: string, tone?: Toast["tone"]) => void>(() => {});

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const push = useCallback((text: string, tone: Toast["tone"] = "ok") => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t, { id, text, tone }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), tone === "error" ? 7000 : 3500);
  }, []);
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="pointer-events-none fixed right-4 bottom-4 z-[60] flex flex-col gap-2" aria-live="polite">
        {toasts.map((t) => (
          <div
            key={t.id}
            className={cx(
              "pointer-events-auto max-w-sm animate-rise border px-4 py-3 text-sm",
              t.tone === "error" ? "border-alert bg-alert text-on-alert" : "border-ink bg-ink text-on-ink",
            )}
          >
            {t.text}
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}

export const useToast = () => useContext(ToastCtx);

export { useReducedMotion };
