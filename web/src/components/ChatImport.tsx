import { FolderOpen, MessageSquare, Upload } from "lucide-react";
import { useMemo, useRef, useState } from "react";
import { api, type ChatMatch, type ChatScan } from "../api";
import DropZone, { filePath } from "./DropZone";
import { Button, Chip, cx, plural, useToast } from "./ui";

/** Chat-history import (C14): drop anything (an export .zip, .json files, a folder), see what matters for your
 * case with the reason each matched, tick what to bring in. Scoring runs on this computer; only the ticked items
 * reach the workspace, and only those are read by a model. */
export default function ChatImport({ onDone, compact }: { onDone: (summary: string) => void; compact?: boolean }) {
  const toast = useToast();
  const [scan, setScan] = useState<ChatScan | null>(null);
  const [ticked, setTicked] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState<"scan" | "import" | null>(null);
  const [showAll, setShowAll] = useState(false);
  const folder = useRef<HTMLInputElement>(null);

  const read = async (files: File[]) => {
    setBusy("scan");
    try {
      const s = await api.scanChats(files, filePath);
      setScan(s);
      setTicked(new Set(s.items.filter((i) => i.ticked).map((i) => i.id)));
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setBusy(null);
    }
  };
  const bring = async () => {
    if (!scan) return;
    setBusy("import");
    try {
      const r = await api.importScan(scan.id, [...ticked]);
      setScan(null);
      onDone(r.summary);
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setBusy(null);
    }
  };

  const matched = useMemo(() => scan?.items.filter((i) => i.reasons.length) ?? [], [scan]);
  const rest = useMemo(() => scan?.items.filter((i) => !i.reasons.length) ?? [], [scan]);

  if (!scan)
    return (
      <div>
        {!compact && (
          <p className="mb-4 max-w-2xl text-[15px] leading-relaxed text-ink-2">
            When you export, <strong className="font-semibold text-ink">choose the longest range you can</strong>. Lighthouse sorts it on this computer
            first, shows you what looks related to your case and why, and brings in only what you tick.
          </p>
        )}
        <DropZone busy={busy === "scan"} multiple label="Upload a chat export" onFiles={read}>
          <Upload className="size-6" strokeWidth={1.5} aria-hidden />
          <p className={cx("display", compact ? "text-2xl" : "text-3xl")}>{busy === "scan" ? "Reading on this computer…" : "Drop your export here"}</p>
          <p className="font-mono text-[11px] text-muted uppercase">the .zip, its .json files, or the whole folder · Claude or ChatGPT</p>
        </DropZone>
        <div className="-mt-5 mb-6 flex justify-center">
          <Button size="sm" variant="ghost" disabled={!!busy} onClick={() => folder.current?.click()}>
            <FolderOpen /> Choose a folder
          </Button>
          <input
            ref={folder}
            type="file"
            hidden
            multiple
            // @ts-expect-error: a non-standard attribute every major browser supports for picking folders
            webkitdirectory=""
            onChange={(e) => {
              const files = Array.from(e.target.files ?? []);
              e.target.value = "";
              if (files.length) read(files);
            }}
          />
        </div>
      </div>
    );

  const toggle = (id: string) =>
    setTicked((s) => {
      const n = new Set(s);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });
  const row = (m: ChatMatch) => (
    <li key={m.id}>
      <label className={cx("flex cursor-pointer items-start gap-3 border-b border-line px-4 py-3 hover:bg-sunken", ticked.has(m.id) && "bg-surface")}>
        <input type="checkbox" className="mt-1 size-4 shrink-0 accent-[var(--ink)]" checked={ticked.has(m.id)} onChange={() => toggle(m.id)} />
        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-center gap-2">
            {m.kind === "project" && <Chip tone="ink">Project</Chip>}
            <span className="text-[15px] leading-snug">{m.title}</span>
          </span>
          <span className="mt-0.5 block font-mono text-[10.5px] tracking-[0.04em] text-muted uppercase">
            {m.provider === "chatgpt" ? "ChatGPT" : "Claude"} · {m.date ?? "no date"} · {m.kind === "project" ? plural(m.messages, "file") : plural(m.messages, "message")}
          </span>
          {m.reasons.length > 0 && <span className="mt-1 block text-sm text-ink-2">{m.reasons.join(" · ")}</span>}
        </span>
      </label>
    </li>
  );
  return (
    <div className="card" aria-label="Pick what to import">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-4 py-3">
        <div>
          <p className="eyebrow text-ink">Found {scan.summary}</p>
          <p className="mt-1 text-sm text-ink-2">
            {plural(matched.length, "item")} look related to your case; {ticked.size} ticked. Read on this computer; nothing is saved until you import.
          </p>
        </div>
        <span className="flex gap-1">
          <Button size="sm" variant="ghost" onClick={() => setTicked(new Set(matched.map((m) => m.id)))}>
            Tick all matches
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setTicked(new Set())}>
            None
          </Button>
        </span>
      </header>
      {scan.unread.length > 0 && (
        <p className="border-b border-alert bg-alert-soft px-4 py-2.5 text-xs text-ink" role="status">
          <span className="text-alert">Couldn't read {plural(scan.unread.length, "file")}:</span>{" "}
          {scan.unread.slice(0, 6).map((u) => `${u.file} (${u.why})`).join("; ")}
          {scan.unread.length > 6 ? " …" : ""}
        </p>
      )}
      <ul className={cx("overflow-y-auto", compact ? "max-h-[46vh]" : "max-h-[60vh]")}>
        {matched.map(row)}
        {rest.length > 0 && !showAll && (
          <li>
            <button type="button" className="w-full px-4 py-3 text-left font-mono text-[11px] tracking-[0.08em] text-ink-2 uppercase hover:text-ink" onClick={() => setShowAll(true)}>
              {plural(rest.length, "more conversation")} with no case signals · show
            </button>
          </li>
        )}
        {showAll && rest.map(row)}
      </ul>
      <footer className="flex flex-wrap items-center justify-between gap-3 border-t border-line px-4 py-3">
        <p className="flex items-center gap-2 font-mono text-[10.5px] text-muted uppercase">
          <MessageSquare className="size-3.5" strokeWidth={1.5} aria-hidden /> Self-reported · never counts toward a criterion
        </p>
        <span className="flex gap-2">
          <Button
            variant="ghost"
            disabled={!!busy}
            onClick={() => {
              api.discardScan(scan.id).catch(() => undefined);
              setScan(null);
            }}
          >
            Cancel
          </Button>
          <Button variant="primary" disabled={!!busy || ticked.size === 0} onClick={bring}>
            {busy === "import" ? "Importing…" : `Import ${plural(ticked.size, "item")}`}
          </Button>
        </span>
      </footer>
    </div>
  );
}
