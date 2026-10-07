import {
  Ban,
  BookOpen,
  CalendarDays,
  ChevronDown,
  FilePlus2,
  FileText,
  Gauge,
  Globe,
  Inbox,
  ListChecks,
  Mail,
  Search,
  type LucideIcon,
  Undo2,
  X,
} from "lucide-react";
import { useState } from "react";
import { api } from "../api";
import { useRefresh } from "../App";
import { Button, Chip, cx, useToast } from "./ui";

export type ToolView = {
  id: string;
  name: string;
  input: Record<string, unknown>;
  touches?: string[];
  read_only?: boolean;
  ok?: boolean | null;
  summary?: string;
  proposals?: string[];
};

const str = (v: unknown) => (typeof v === "string" ? v : "");

function describe(t: ToolView): { icon: LucideIcon; text: React.ReactNode } {
  const n = t.name;
  if (n === "WebSearch" || n === "web_search") return { icon: Search, text: <>Searched the web: “{str(t.input.query)}”</> };
  if (n === "decline") return { icon: Ban, text: <>Declined: {str(t.input.reason)}</> };
  if (n === "search_vault") return { icon: BookOpen, text: <>Searched the knowledge vault: “{str(t.input.query)}”</> };
  if (n === "read_page") {
    const url = str(t.input.url);
    return {
      icon: Globe,
      text: (
        <>
          Read page:{" "}
          <a className="link break-all" href={url} target="_blank" rel="noreferrer">
            {url}
          </a>
        </>
      ),
    };
  }
  if (n.startsWith("propose_")) {
    const what = n.replace("propose_", "").replace(/_/g, " ");
    return { icon: FilePlus2, text: <>Proposed {what}: {str(t.input.title) || str(t.input.name)}</> };
  }
  const direct = /^(add|update|delete)_(deadline|pipeline_item|letter_writer)$|^update_todo$/.exec(n);
  if (direct) {
    const verb = { add: "Added", update: "Changed", delete: "Deleted" }[n.split("_")[0]] ?? "Changed";
    const what = n === "update_todo" ? "to-do" : n.replace(/^(add|update|delete)_/, "").replace(/_/g, " ");
    const icon = n.includes("deadline") ? CalendarDays : n.includes("letter") ? Mail : ListChecks;
    // Once it ran, its own words name the record ("Moved MLH Fall hackathon"); before that, what was asked.
    const said = t.ok && t.summary ? t.summary.split(". It's on the page")[0] : "";
    if (said) return { icon, text: <>{said}</> };
    const name = str(t.input.title) || str(t.input.name) || str(t.input.id);
    return { icon, text: <>{verb} {what}: {name}</> };
  }
  if (/deadline|calendar/.test(n)) return { icon: CalendarDays, text: <>{n.replace(/_/g, " ")}</> };
  if (/inbox|candidate/.test(n)) return { icon: Inbox, text: <>{n.replace(/_/g, " ")}</> };
  if (/letter/.test(n)) return { icon: Mail, text: <>{n.replace(/_/g, " ")}</> };
  if (/scoreboard|gaps|criteria/.test(n)) return { icon: Gauge, text: <>{n.replace(/_/g, " ")}</> };
  if (/pipeline|tracker/.test(n)) return { icon: ListChecks, text: <>{n.replace(/_/g, " ")}</> };
  return { icon: FileText, text: <>{n.replace(/_/g, " ")}</> };
}

/** A checkmark that draws itself in (instant with reduced motion). */
export function DrawnCheck({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={cx("size-4", className)} fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="square" aria-label="Done">
      <path d="M4 12.5l5 5L20 6.5" pathLength={1} strokeDasharray="1" className="animate-draw" />
    </svg>
  );
}

/** One tool call, as shown in the chat panel and on the Agent page. The icon pulses while it runs; a check draws
 * in when it succeeds. */
/** The change id a direct page action reports ("undo: chg_…"), so the chat can offer Undo right there. */
export function undoId(summary?: string): string | null {
  return /\bundo: (\S+)/.exec(summary ?? "")?.[1] ?? null;
}

function UndoButton({ id }: { id: string }) {
  const toast = useToast();
  const { bump } = useRefresh();
  const [done, setDone] = useState(false);
  return done ? (
    <span className="mt-2 ml-6 inline-block font-mono text-[10.5px] text-muted uppercase">Undone</span>
  ) : (
    <Button
      size="sm"
      variant="ghost"
      className="mt-1 ml-4"
      onClick={() =>
        api
          .undoChange(id)
          .then(() => {
            setDone(true);
            bump();
          })
          .catch((e: Error) => toast(e.message, "error"))
      }
    >
      <Undo2 /> Undo
    </Button>
  );
}

export default function ToolCall({ t }: { t: ToolView }) {
  const [open, setOpen] = useState(false);
  const undo = t.ok ? undoId(t.summary) : null;
  const { icon: Icon, text } = describe(t);
  const running = t.ok === undefined || t.ok === null;
  return (
    <div className={cx("animate-rise border px-3 py-2 text-xs", t.ok === false ? "border-alert" : "border-line")}>
      <button type="button" onClick={() => setOpen(!open)} className="flex w-full items-start gap-2.5 text-left" aria-expanded={open} aria-busy={running}>
        <Icon className={cx("mt-px size-4 shrink-0", running ? "animate-tool-pulse text-ink" : "text-ink-2")} strokeWidth={1.5} aria-hidden />
        <span className="min-w-0 flex-1 leading-relaxed">{text}</span>
        <span className="flex shrink-0 items-center gap-1.5">
          {running ? (
            <span className="font-mono text-[10px] text-muted uppercase">running</span>
          ) : t.ok ? (
            <DrawnCheck className="text-ink" />
          ) : (
            <X className="size-4 text-alert" aria-label="Failed" />
          )}
          <ChevronDown className={cx("size-3.5 text-muted transition-transform duration-200", !open && "-rotate-90")} aria-hidden />
        </span>
      </button>
      {t.touches && t.touches.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1 pl-6">
          <span className="font-mono text-[10px] text-muted uppercase">{t.read_only === false ? "wrote" : "read"}</span>
          {t.touches.map((f) => (
            <Chip key={f}>{f}</Chip>
          ))}
        </div>
      )}
      {t.proposals && t.proposals.length > 0 && t.name.startsWith("propose_") && t.ok && (
        <a href="#/inbox" className="link mt-2 ml-6 inline-block font-mono text-[10.5px] uppercase">
          Review in the Inbox
        </a>
      )}
      {undo && <UndoButton id={undo} />}
      {open && (
        <div className="mt-2 animate-rise space-y-1.5 pl-6">
          <pre className="max-h-40 overflow-auto bg-sunken p-2 font-mono text-[11px] whitespace-pre-wrap">{JSON.stringify(t.input, null, 2)}</pre>
          {t.summary && <p className="text-[11px] whitespace-pre-wrap text-ink-2">{t.summary}</p>}
        </div>
      )}
    </div>
  );
}
