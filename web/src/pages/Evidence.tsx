import { Check, Upload } from "lucide-react";
import { useEffect, useState } from "react";
import { api, type EvidenceCriterion, type Exhibit, STAGES, stageCounts } from "../api";
import ClaimsPanel, { StageChip } from "../components/Claims";
import DropZone, { useFileDrop } from "../components/DropZone";
import { useRefresh } from "../App";
import { Button, Card, Chip, CriterionName, cx, Empty, ErrorBox, Loading, Modal, PageHeader, plural, StatusBadge, useToast } from "../components/ui";
import { today, useLoad } from "../hooks";

export default function Evidence({ focus }: { focus: string | null }) {
  const { version, bump } = useRefresh();
  const view = useLoad(() => api.evidence(), [version]);
  const [uploadFor, setUploadFor] = useState<EvidenceCriterion | null>(null);
  const [preview, setPreview] = useState<Exhibit | null>(null);
  const [sending, setSending] = useState(false);
  const toast = useToast();

  /** Dropped files go to the Inbox (snapshotted in memory/); accepting there files them as exhibits. */
  const sendToInbox = async (files: File[], criterion?: string) => {
    setSending(true);
    try {
      const cands = await api.uploadToInbox(files, criterion);
      const unsorted = cands.filter((c) => !c.proposed_criterion).length;
      toast(`${cands.length} file${cands.length > 1 ? "s" : ""} sent to the Inbox${unsorted ? ` — ${unsorted} need a criterion` : ""}`);
      bump();
      window.location.hash = "#/inbox";
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setSending(false);
    }
  };

  useEffect(() => {
    if (focus && view.data) document.getElementById(`crit-${focus}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [focus, view.data]);

  if (view.error) return <ErrorBox error={view.error} retry={view.reload} />;
  if (!view.data) return <Loading />;
  const { criteria, naming_issues, other_exhibits } = view.data;

  return (
    <div>
      <PageHeader
        eyebrow={`${plural(criteria.reduce((n, c) => n + c.exhibit_count, 0), "exhibit")} · ${plural(criteria.filter((c) => c.status === "banked").length, "criterion")} banked`}
        title="Evidence"
        subtitle="Accepted exhibits per criterion. Files live in evidence/<criterion>/ in your workspace."
      />

      <DropZone onFiles={(f) => sendToInbox(f)} busy={sending}>
        <Upload className="size-6" strokeWidth={1.5} aria-hidden />
        <p className="display text-3xl">{sending ? "Uploading…" : "Drop certificates, letters, screenshots or PDFs"}</p>
        <p className="max-w-xl text-sm text-ink-2">
          or click to choose. They go to your Inbox with a suggested criterion and stage; nothing is filed until you accept. Drop
          onto a criterion below to propose it there.
        </p>
      </DropZone>

      {naming_issues.length > 0 && (
        <div className="mb-8 border border-alert bg-surface p-5 text-sm">
          <p className="eyebrow text-alert">Naming check · {plural(naming_issues.length, "issue")}</p>
          <ul className="mt-3 space-y-1 font-mono text-xs text-ink-2">
            {naming_issues.map((i) => (
              <li key={i.file}>
                <code>{i.file}</code> — {i.problem.replace("_", " ")}: {i.detail}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="flex flex-col gap-8">
        {criteria.map((c) => (
          <CriterionSection
            key={c.id}
            c={c}
            highlighted={focus === c.id}
            allCriteria={criteria}
            onUpload={() => setUploadFor(c)}
            onDropFiles={(files) => sendToInbox(files, c.id)}
            onPreview={setPreview}
            onChanged={bump}
          />
        ))}
        {other_exhibits.length > 0 && (
          <Card title="Filed under criteria outside this profile">
            <ul className="divide-y divide-line">
              {other_exhibits.map((e) => (
                <li key={e.id} className="px-5 py-3 text-sm">
                  {e.title} <Chip>{e.criterion}</Chip>
                </li>
              ))}
            </ul>
          </Card>
        )}
      </div>

      {uploadFor && <UploadModal crit={uploadFor} onClose={() => setUploadFor(null)} onDone={bump} />}
      {preview && <PreviewModal exhibit={preview} onClose={() => setPreview(null)} />}
    </div>
  );
}

function CriterionSection({
  c,
  highlighted,
  allCriteria,
  onUpload,
  onDropFiles,
  onPreview,
  onChanged,
}: {
  c: EvidenceCriterion;
  highlighted: boolean;
  allCriteria: EvidenceCriterion[];
  onUpload: () => void;
  onDropFiles: (files: File[]) => void;
  onPreview: (e: Exhibit) => void;
  onChanged: () => void;
}) {
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const signalLabel = Object.fromEntries(c.strength_signals.map((s) => [s.id, s.label]));
  const need = c.bank;
  const { over, bind } = useFileDrop(onDropFiles);

  const override = async (status: "dropped" | "gap" | null) => {
    setBusy(true);
    try {
      await api.setOverride(c.id, status);
      toast(status ? `Marked ${status}` : "Override cleared — rules decide again");
      onChanged();
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setBusy(false);
    }
  };

  const remap = async (e: Exhibit, criterion: string) => {
    try {
      await api.remap(e.id, criterion);
      toast("Re-mapped — file moved and renamed");
      onChanged();
    } catch (err) {
      toast((err as Error).message, "error");
    }
  };

  return (
    <section
      id={`crit-${c.id}`}
      {...bind}
      className={cx("card relative animate-rise scroll-mt-6", (highlighted || over) && "outline-2 outline-offset-2 outline-ink")}
    >
      {over && (
        <div className="display pointer-events-none absolute inset-0 z-10 flex items-center justify-center bg-sunken/95 text-3xl text-ink">
          Drop to propose under {c.short_label || c.label}
        </div>
      )}
      <header className="flex flex-wrap items-start gap-x-6 gap-y-3 border-b border-line px-6 py-5">
        <div className="min-w-0 flex-1">
          <StatusBadge status={c.status} />
          <h2 className="display mt-2 text-4xl md:text-5xl">
            <CriterionName c={c} />
          </h2>
          {c.short_label && c.short_label !== c.label && <p className="mt-1 text-sm text-ink-2">{c.label}</p>}
        </div>
        <span className="num self-center text-xs text-ink-2 uppercase">
          have {c.exhibit_count}
          {need && ` / need ${need.min_exhibits}`}
          {need && need.min_signals > 0 && ` · signals ${c.matched_signals.length}/${need.min_signals}`}
          {c.in_progress_count > 0 && ` · ${c.in_progress_count} in progress`}
        </span>
        <div className="flex gap-1.5 self-center">
          <Button size="sm" variant="primary" onClick={onUpload}>
            <Upload /> Upload
          </Button>
          {c.overridden ? (
            <Button size="sm" disabled={busy} onClick={() => override(null)}>
              Clear override
            </Button>
          ) : (
            <>
              <Button size="sm" variant="ghost" disabled={busy} onClick={() => override("gap")} title="Treat as a known gap regardless of evidence">
                Mark gap
              </Button>
              <Button size="sm" variant="ghost" disabled={busy} onClick={() => override("dropped")} title="You decided not to pursue this criterion">
                Drop
              </Button>
            </>
          )}
        </div>
      </header>
      <p className="px-6 pt-4 text-sm text-ink-2">{c.reason}</p>
      {c.strength_signals.length > 0 && (
        <div className="flex flex-wrap gap-1.5 px-6 pt-3 pb-5">
          {c.strength_signals.map((s) => (
            <span
              key={s.id}
              title={s.id}
              className={cx(
                "inline-flex items-center gap-1 border px-2 py-0.5 font-mono text-[10.5px] uppercase",
                c.matched_signals.includes(s.id) ? "border-ink bg-ink text-on-ink" : "border-line text-muted",
              )}
            >
              {c.matched_signals.includes(s.id) && <Check className="size-3" aria-hidden />}
              {s.label}
            </span>
          ))}
        </div>
      )}
      {c.exhibits.length > 0 ? (
        <ul className="border-t border-line">
          {c.exhibits.map((e) => (
            <li key={e.id} className={cx("flex flex-wrap items-center gap-3 border-b border-line px-6 py-4 last:border-b-0", !stageCounts(e.stage) && "bg-sunken/60")}>
              <div className="min-w-0 flex-1">
                <p className="truncate text-[15px]">
                  {e.source_url ? (
                    <a className="link" href={e.source_url} target="_blank" rel="noreferrer">
                      {e.title}
                    </a>
                  ) : (
                    e.title
                  )}
                </p>
                <p className="mt-1.5 flex flex-wrap items-center gap-1.5 text-xs text-muted">
                  <span className="num">{e.date}</span>
                  <Chip>{e.evidence_type}</Chip>
                  <StageChip stage={e.stage} />
                  {!stageCounts(e.stage) && <span className="font-mono text-[10.5px] text-ink uppercase">not counted until completed</span>}
                  {e.signals.map((s) => (
                    <Chip key={s} tone="ink">
                      {signalLabel[s] ?? s}
                    </Chip>
                  ))}
                </p>
                <ClaimsPanel ids={e.claim_ids} verb="Cites" />
              </div>
              <Button size="sm" variant="ghost" onClick={() => onPreview(e)} title={e.file}>
                Preview
              </Button>
              <select
                aria-label="Re-map to another criterion"
                className="input h-8 w-auto py-0 font-mono text-[11px]"
                value=""
                onChange={(ev) => ev.target.value && remap(e, ev.target.value)}
              >
                <option value="">Re-map…</option>
                {allCriteria
                  .filter((x) => x.id !== c.id)
                  .map((x) => (
                    <option key={x.id} value={x.id}>
                      {x.label}
                    </option>
                  ))}
              </select>
            </li>
          ))}
        </ul>
      ) : (
        <div className="border-t border-line">
          <Empty>
            No exhibits yet. Accepts types: {c.evidence_types.map((t) => <Chip key={t}>{t}</Chip>)}
          </Empty>
        </div>
      )}
    </section>
  );
}

function UploadModal({ crit, onClose, onDone }: { crit: EvidenceCriterion; onClose: () => void; onDone: () => void }) {
  const toast = useToast();
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [type, setType] = useState(crit.evidence_types[0] ?? "");
  const [stage, setStage] = useState(/invite/.test(crit.evidence_types[0] ?? "") ? "invited" : "");
  const [date, setDate] = useState(today());
  const [summary, setSummary] = useState("");
  const [signals, setSignals] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) return;
    const form = new FormData();
    form.append("file", file);
    form.append("criterion", crit.id);
    form.append("evidence_type", type);
    form.append("title", title || file.name.replace(/\.[^.]+$/, ""));
    form.append("date", date);
    form.append("summary", summary);
    form.append("signals", signals.join(","));
    form.append("stage", stage);
    setBusy(true);
    try {
      const ex = await api.upload(form);
      toast(`Filed as ${ex.file}`);
      onDone();
      onClose();
    } catch (err) {
      toast((err as Error).message, "error");
      setBusy(false);
    }
  };

  return (
    <Modal title="Upload exhibit" onClose={onClose}>
      <p className="eyebrow -mt-1 mb-4">{crit.short_label || crit.label}</p>
      <form onSubmit={submit} className="grid gap-3">
        <label>
          <span className="label">File (PDF, image, letter…)</span>
          <input type="file" required className="input" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        </label>
        <label>
          <span className="label">Title — becomes the file name slug</span>
          <input className="input" value={title} placeholder="e.g. HackMIT 2026 judge invitation" onChange={(e) => setTitle(e.target.value)} />
        </label>
        <div className="grid grid-cols-2 gap-3">
          <label>
            <span className="label">Evidence type</span>
            <select
              className="input"
              value={type}
              onChange={(e) => {
                setType(e.target.value);
                if (/invite/.test(e.target.value) && !stage) setStage("invited");
              }}
            >
              {crit.evidence_types.map((t) => (
                <option key={t}>{t}</option>
              ))}
            </select>
          </label>
          <label>
            <span className="label">Date</span>
            <input type="date" className="input" value={date} onChange={(e) => setDate(e.target.value)} />
          </label>
        </div>
        <label>
          <span className="label">Stage — an invitation isn't a completion; only completed / published / granted count</span>
          <select className="input" value={stage} onChange={(e) => setStage(e.target.value)}>
            <option value="">Not an activity (e.g. a certificate, a pay stub)</option>
            {STAGES.map((s) => (
              <option key={s} value={s}>
                {s}
                {stageCounts(s) ? " — counts" : ""}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span className="label">Summary</span>
          <textarea className="input" rows={2} value={summary} onChange={(e) => setSummary(e.target.value)} />
        </label>
        {crit.strength_signals.length > 0 && (
          <fieldset>
            <legend className="label">Strength signals this document shows</legend>
            <div className="flex flex-col gap-1">
              {crit.strength_signals.map((s) => (
                <label key={s.id} className="flex items-center gap-2.5 text-sm">
                  <input
                    type="checkbox"
                    className="size-4 accent-[var(--ink)]"
                    checked={signals.includes(s.id)}
                    onChange={(e) => setSignals(e.target.checked ? [...signals, s.id] : signals.filter((x) => x !== s.id))}
                  />
                  {s.label}
                </label>
              ))}
            </div>
          </fieldset>
        )}
        <div className="mt-2 flex justify-end gap-2 border-t border-line pt-4">
          <Button type="button" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" variant="primary" disabled={!file || busy}>
            {busy ? "Uploading…" : "File exhibit"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}

function PreviewModal({ exhibit, onClose }: { exhibit: Exhibit; onClose: () => void }) {
  const url = api.fileUrl(exhibit.file);
  const ext = exhibit.file.split(".").pop()?.toLowerCase() ?? "";
  const [text, setText] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const isText = ["md", "txt", "csv", "json"].includes(ext);
  const isImage = ["png", "jpg", "jpeg", "gif", "webp", "svg"].includes(ext);

  useEffect(() => {
    if (!isText) return;
    fetch(url)
      .then((r) => (r.ok ? r.text() : Promise.reject(new Error(r.statusText))))
      .then(setText)
      .catch((e: Error) => setError(e.message));
  }, [url, isText]);

  return (
    <Modal title={exhibit.title} onClose={onClose} wide>
      <p className="mb-3 font-mono text-xs text-muted">{exhibit.file}</p>
      {isText ? (
        error ? (
          <p className="text-sm text-alert">{error}</p>
        ) : (
          <pre className="max-h-[60vh] overflow-auto bg-sunken p-3 text-xs whitespace-pre-wrap">{text ?? "Loading…"}</pre>
        )
      ) : isImage ? (
        <img src={url} alt={exhibit.title} className="max-h-[65vh]" />
      ) : ext === "pdf" ? (
        <iframe src={url} title={exhibit.title} className="h-[65vh] w-full border border-line" />
      ) : (
        <Empty>No preview for .{ext} files.</Empty>
      )}
      <div className="mt-3 text-right">
        <a href={url} target="_blank" rel="noreferrer" className="link text-sm">
          Open in new tab
        </a>
      </div>
    </Modal>
  );
}
