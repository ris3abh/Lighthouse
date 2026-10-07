import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import type { CriterionStatus } from "../api";

export function cx(...parts: (string | false | null | undefined)[]) {
  return parts.filter(Boolean).join(" ");
}

type Variant = "primary" | "secondary" | "ghost" | "danger";

const VARIANTS: Record<Variant, string> = {
  primary: "bg-zinc-900 text-white hover:bg-zinc-700 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-white",
  secondary:
    "border border-zinc-300 bg-white hover:bg-zinc-50 dark:border-zinc-700 dark:bg-zinc-900 dark:hover:bg-zinc-800",
  ghost: "hover:bg-zinc-100 dark:hover:bg-zinc-800",
  danger: "text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-950",
};

export function Button({
  variant = "secondary",
  size = "md",
  className,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: "sm" | "md" }) {
  return (
    <button
      {...props}
      className={cx(
        "inline-flex items-center justify-center gap-1.5 rounded-md font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50",
        size === "sm" ? "px-2 py-1 text-xs" : "px-3 py-1.5 text-sm",
        VARIANTS[variant],
        className,
      )}
    />
  );
}

export const STATUS_STYLE: Record<CriterionStatus, { dot: string; chip: string; label: string }> = {
  banked: {
    dot: "bg-emerald-500",
    chip: "bg-emerald-50 text-emerald-800 ring-emerald-600/20 dark:bg-emerald-950 dark:text-emerald-300 dark:ring-emerald-400/30",
    label: "Banked",
  },
  building: {
    dot: "bg-amber-500",
    chip: "bg-amber-50 text-amber-800 ring-amber-600/20 dark:bg-amber-950 dark:text-amber-300 dark:ring-amber-400/30",
    label: "Building",
  },
  gap: {
    dot: "bg-zinc-300 dark:bg-zinc-600",
    chip: "bg-zinc-50 text-zinc-600 ring-zinc-500/20 dark:bg-zinc-900 dark:text-zinc-400 dark:ring-zinc-500/30",
    label: "Gap",
  },
  dropped: {
    dot: "bg-zinc-200 dark:bg-zinc-700",
    chip: "bg-transparent text-zinc-400 ring-zinc-400/20 line-through dark:text-zinc-500",
    label: "Dropped",
  },
};

export function StatusBadge({ status }: { status: CriterionStatus }) {
  const s = STATUS_STYLE[status];
  return (
    <span className={cx("inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset", s.chip)}>
      <span className={cx("size-1.5 rounded-full", s.dot)} />
      {s.label}
    </span>
  );
}

export function Chip({ children, tone = "zinc" }: { children: ReactNode; tone?: "zinc" | "amber" | "emerald" | "red" }) {
  const tones = {
    red: "bg-red-100 text-red-900 dark:bg-red-900/40 dark:text-red-200",
    zinc: "bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300",
    amber: "bg-amber-100 text-amber-900 dark:bg-amber-900/40 dark:text-amber-200",
    emerald: "bg-emerald-100 text-emerald-900 dark:bg-emerald-900/40 dark:text-emerald-200",
  };
  return <span className={cx("inline-flex items-center rounded px-1.5 py-0.5 font-mono text-[11px]", tones[tone])}>{children}</span>;
}

export function Card({ title, actions, children, className }: { title?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={cx("card", className)}>
      {(title || actions) && (
        <header className="flex items-center justify-between gap-2 border-b border-zinc-100 px-4 py-2.5 dark:border-zinc-800">
          <h2 className="text-sm font-semibold">{title}</h2>
          {actions}
        </header>
      )}
      {children}
    </section>
  );
}

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
        {subtitle && <p className="mt-0.5 text-sm text-zinc-500 dark:text-zinc-400">{subtitle}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="px-4 py-8 text-center text-sm text-zinc-500 dark:text-zinc-400">{children}</div>;
}

export function Loading() {
  return <div className="p-8 text-sm text-zinc-500">Loading…</div>;
}

export function ErrorBox({ error, retry }: { error: Error; retry?: () => void }) {
  return (
    <div className="card border-red-200 p-4 text-sm text-red-700 dark:border-red-900 dark:text-red-300">
      <p className="font-medium">Couldn't load this page.</p>
      <p className="mt-1">{error.message}</p>
      {retry && (
        <Button className="mt-3" size="sm" onClick={retry}>
          Retry
        </Button>
      )}
    </div>
  );
}

export function fmt(n: number | null | undefined) {
  if (n === null || n === undefined) return "—";
  return Number.isInteger(n) ? n.toLocaleString() : n.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

export function Delta({ value }: { value: number | null }) {
  if (value === null) return <span className="text-zinc-400">—</span>;
  const tone = value > 0 ? "text-emerald-600 dark:text-emerald-400" : value < 0 ? "text-red-600 dark:text-red-400" : "text-zinc-400";
  return (
    <span className={cx("tabular-nums", tone)}>
      {value > 0 ? "+" : ""}
      {fmt(value)}
    </span>
  );
}

export function Modal({ title, onClose, children, wide }: { title: string; onClose: () => void; children: ReactNode; wide?: boolean }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-zinc-950/40 p-4 pt-[10vh] backdrop-blur-sm" onMouseDown={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className={cx("card w-full p-0", wide ? "max-w-4xl" : "max-w-lg")}
        onMouseDown={(e) => e.stopPropagation()}
      >
        <header className="flex items-center justify-between border-b border-zinc-100 px-4 py-3 dark:border-zinc-800">
          <h2 className="text-sm font-semibold">{title}</h2>
          <Button variant="ghost" size="sm" onClick={onClose} aria-label="Close">
            ✕
          </Button>
        </header>
        <div className="p-4">{children}</div>
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
      <div className="pointer-events-none fixed right-4 bottom-4 z-50 flex flex-col gap-2" aria-live="polite">
        {toasts.map((t) => (
          <div
            key={t.id}
            className={cx(
              "pointer-events-auto max-w-sm rounded-lg px-3 py-2 text-sm shadow-lg",
              t.tone === "error" ? "bg-red-600 text-white" : "bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900",
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
