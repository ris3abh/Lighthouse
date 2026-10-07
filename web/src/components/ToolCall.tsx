import { useState } from "react";
import { Chip, cx } from "./ui";

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

function describe(t: ToolView): { icon: string; text: React.ReactNode } {
  const n = t.name;
  if (n === "WebSearch" || n === "web_search") return { icon: "🔍", text: <>Searched the web: “{str(t.input.query)}”</> };
  if (n === "read_page") {
    const url = str(t.input.url);
    return {
      icon: "🌐",
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
    const what = n.replace("propose_", "").replace("_", " ");
    return { icon: "✚", text: <>Proposed {what}: {str(t.input.title) || str(t.input.name)}</> };
  }
  return { icon: "📄", text: <>{n.replace(/_/g, " ")}</> };
}

/** One tool call, as shown in the chat panel and on the Agent page. */
export default function ToolCall({ t }: { t: ToolView }) {
  const [open, setOpen] = useState(false);
  const { icon, text } = describe(t);
  const running = t.ok === undefined || t.ok === null;
  return (
    <div className={cx("border px-2 py-1.5 text-xs", t.ok === false ? "border-alert" : "border-line")}>
      <button type="button" onClick={() => setOpen(!open)} className="flex w-full items-start gap-1.5 text-left" aria-expanded={open}>
        <span aria-hidden>{icon}</span>
        <span className="min-w-0 flex-1">{text}</span>
        <span className={cx("shrink-0", running ? "animate-pulse text-muted" : t.ok ? "text-ink" : "text-alert")}>
          {running ? "…" : t.ok ? "✓" : "✗"}
        </span>
      </button>
      {t.touches && t.touches.length > 0 && (
        <div className="mt-1 flex flex-wrap gap-1 pl-5">
          <span className="text-[11px] text-muted">{t.read_only === false ? "wrote" : "read"}</span>
          {t.touches.map((f) => (
            <Chip key={f}>{f}</Chip>
          ))}
        </div>
      )}
      {t.proposals && t.proposals.length > 0 && t.name.startsWith("propose_") && t.ok && (
        <a href="#/inbox" className="link mt-1 ml-5 inline-block text-[11px]">
          Review in the Inbox →
        </a>
      )}
      {open && (
        <div className="mt-1.5 space-y-1 pl-5">
          <pre className="max-h-40 overflow-auto bg-sunken p-1.5 text-[11px] whitespace-pre-wrap">{JSON.stringify(t.input, null, 2)}</pre>
          {t.summary && <p className="text-[11px] whitespace-pre-wrap text-muted">{t.summary}</p>}
        </div>
      )}
    </div>
  );
}
