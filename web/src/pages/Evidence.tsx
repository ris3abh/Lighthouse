import { useEffect, useState } from "react";
import { api, type EvidenceCriterion, type Exhibit, STAGES, stageCounts } from "../api";
import ClaimsPanel, { StageChip } from "../components/Claims";
import { useRefresh } from "../App";
import { Button, Card, Chip, cx, Empty, ErrorBox, Loading, Modal, PageHeader, StatusBadge, useToast } from "../components/ui";
import { today, useLoad } from "../hooks";

export default function Evidence({ focus }: { focus: string | null }) {
  const { version, bump } = useRefresh();
  const view = useLoad(() => api.evidence(), [version]);
  const [uploadFor, setUploadFor] = useState<EvidenceCriterion | null>(null);
  const [preview, setPreview] = useState<Exhibit | null>(null);

  useEffect(() => {
    if (focus && view.data) document.getElementById(`crit-${focus}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [focus, view.data]);

  if (view.error) return <ErrorBox error={view.error} retry={view.reload} />;
  if (!view.data) return <Loading />;
  const { criteria, naming_issues, other_exhibits } = view.data;

  return (
    <div className="mx-auto max-w-5xl">
      <PageHeader title="Evidence" subtitle="Accepted exhibits per criterion. Files live in evidence/<criterion>/ in your workspace." />

      {naming_issues.length > 0 && (
        <div className="card mb-4 border-amber-300 p-3 text-sm dark:border-amber-800">
          <p className="font-medium text-amber-800 dark:text-amber-300">Naming check: {naming_issues.length} issue(s)</p>
          <ul className="mt-1 list-disc pl-5 text-xs text-zinc-600 dark:text-zinc-400">
            {naming_issues.map((i) => (
              <li key={i.file}>
                <code>{i.file}</code> — {i.problem.replace("_", " ")}: {i.detail}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="flex flex-col gap-3">
        {criteria.map((c) => (
          <CriterionSection
            key={c.id}
            c={c}
            highlighted={focus === c.id}
            allCriteria={criteria}
            onUpload={() => setUploadFor(c)}
            onPreview={setPreview}
            onChanged={bump}
          />
        ))}
        {other_exhibits.length > 0 && (
          <Card title="Filed under criteria outside this profile">
            <ul className="divide-y divide-zinc-100 dark:divide-zinc-800">
              {other_exhibits.map((e) => (
                <li key={e.id} className="px-4 py-2 text-sm">
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
  onPreview,
  onChanged,
}: {
  c: EvidenceCriterion;
  highlighted: boolean;
  allCriteria: EvidenceCriterion[];
  onUpload: () => void;
  onPreview: (e: Exhibit) => void;
  onChanged: () => void;
}) {
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const signalLabel = Object.fromEntries(c.strength_signals.map((s) => [s.id, s.label]));
  const need = c.bank;

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
    <section id={`crit-${c.id}`} className={cx("card scroll-mt-4", highlighted && "ring-2 ring-amber-400")}>
      <header className="flex flex-wrap items-center gap-3 px-4 py-3">
        <StatusBadge status={c.status} />
        <h2 className="min-w-0 flex-1 text-sm font-semibold">{c.label}</h2>
        <span className="text-xs text-zinc-500 tabular-nums">
          have {c.exhibit_count}
          {need && ` / need ${need.min_exhibits}`}
          {need && need.min_signals > 0 && ` · signals ${c.matched_signals.length}/${need.min_signals}`}
          {c.in_progress_count > 0 && ` · ${c.in_progress_count} in progress`}
        </span>
        <div className="flex gap-1">
          <Button size="sm" variant="primary" onClick={onUpload}>
            Upload
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
      <p className="px-4 pb-2 text-xs text-zinc-500 dark:text-zinc-400">{c.reason}</p>
      {c.strength_signals.length > 0 && (
        <div className="flex flex-wrap gap-1.5 px-4 pb-3">
          {c.strength_signals.map((s) => (
            <span
              key={s.id}
              title={s.id}
              className={cx(
                "rounded-full px-2 py-0.5 text-[11px]",
                c.matched_signals.includes(s.id)
                  ? "bg-emerald-100 text-emerald-900 dark:bg-emerald-900/40 dark:text-emerald-200"
                  : "bg-zinc-100 text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400",
              )}
            >
              {c.matched_signals.includes(s.id) ? "✓ " : ""}
              {s.label}
            </span>
          ))}
        </div>
      )}
      {c.exhibits.length > 0 ? (
        <ul className="divide-y divide-zinc-100 border-t border-zinc-100 dark:divide-zinc-800 dark:border-zinc-800">
          {c.exhibits.map((e) => (
            <li key={e.id} className={cx("flex flex-wrap items-center gap-3 px-4 py-2", !stageCounts(e.stage) && "bg-amber-50/50 dark:bg-amber-950/20")}>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm">
                  {e.source_url ? (
                    <a className="link" href={e.source_url} target="_blank" rel="noreferrer">
                      {e.title}
                    </a>
                  ) : (
                    e.title
                  )}
                </p>
                <p className="mt-0.5 flex flex-wrap items-center gap-1.5 text-xs text-zinc-500">
                  <span className="tabular-nums">{e.date}</span>
                  <Chip>{e.evidence_type}</Chip>
                  <StageChip stage={e.stage} />
                  {!stageCounts(e.stage) && <span className="text-amber-700 dark:text-amber-400">not counted until completed</span>}
                  {e.signals.map((s) => (
                    <Chip key={s} tone="emerald">
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
                className="input w-auto py-1 text-xs"
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
        <div className="border-t border-zinc-100 dark:border-zinc-800">
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
    <Modal title={`Upload exhibit — ${crit.label}`} onClose={onClose}>
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
                <label key={s.id} className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={signals.includes(s.id)}
                    onChange={(e) => setSignals(e.target.checked ? [...signals, s.id] : signals.filter((x) => x !== s.id))}
                  />
                  {s.label}
                </label>
              ))}
            </div>
          </fieldset>
        )}
        <div className="flex justify-end gap-2">
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
      <p className="mb-3 font-mono text-xs text-zinc-500">{exhibit.file}</p>
      {isText ? (
        error ? (
          <p className="text-sm text-red-600">{error}</p>
        ) : (
          <pre className="max-h-[60vh] overflow-auto rounded-md bg-zinc-50 p-3 text-xs whitespace-pre-wrap dark:bg-zinc-950">{text ?? "Loading…"}</pre>
        )
      ) : isImage ? (
        <img src={url} alt={exhibit.title} className="max-h-[65vh] rounded-md" />
      ) : ext === "pdf" ? (
        <iframe src={url} title={exhibit.title} className="h-[65vh] w-full rounded-md border border-zinc-200 dark:border-zinc-800" />
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
