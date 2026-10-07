import { ArrowLeft, ArrowRight, Check, FileText, MessageSquare, Pencil, RotateCw, Search, SkipForward, Upload } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { api, type OnboardingLookup, type OnboardingQuestion, type OnboardingView } from "../api";
import ChipInput from "../components/ChipInput";
import DropZone from "../components/DropZone";
import { Button, Chip, cx, plural, Segmented, useToast } from "../components/ui";
import { useTheme, type ThemeMode } from "../hooks";
import { Monitor, Moon, Sun } from "lucide-react";

/** Onboarding (ADR 0008): one ask at a time, the profile filling in beside it, nothing guessed, no web without a Yes. */

const STEPS = [
  { id: "linkedin", label: "LinkedIn" },
  { id: "questions", label: "Your profile" },
  { id: "lookups", label: "Find your work" },
  { id: "chats", label: "Chat history" },
  { id: "tour", label: "Tour" },
] as const;

const THEMES: { value: ThemeMode; label: ReactNode; title: string }[] = [
  { value: "system", label: <Monitor aria-label="System" />, title: "Theme: follow the system" },
  { value: "light", label: <Sun aria-label="Light" />, title: "Theme: light" },
  { value: "dark", label: <Moon aria-label="Dark" />, title: "Theme: dark" },
];

export default function Welcome({ view, onChange }: { view: OnboardingView; onChange: (v: OnboardingView) => void }) {
  const toast = useToast();
  const { mode, setMode } = useTheme();
  const [busy, setBusy] = useState(false);
  const step = view.state.step;
  const stepIndex = Math.max(0, STEPS.findIndex((s) => s.id === step));

  const run = async (fn: () => Promise<OnboardingView>) => {
    setBusy(true);
    try {
      onChange(await fn());
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex min-h-full flex-col bg-paper">
      <header className="flex h-14 shrink-0 items-center gap-4 border-b border-frame bg-surface px-4 lg:h-16 lg:px-8">
        <span className="display text-2xl uppercase lg:text-[28px]">Lighthouse</span>
        <ol className="ml-4 hidden items-center gap-1.5 md:flex" aria-label="Setup steps">
          {STEPS.map((s, i) => {
            const reachable = !!view.nav?.steps.find((x) => x.id === s.id)?.reachable && i !== stepIndex;
            const inner = (
              <>
                <span className={cx("h-1.5 w-8 border border-ink transition-colors duration-300", i < stepIndex ? "bg-ink" : i === stepIndex ? "bg-ink-2" : "bg-transparent")} />
                <span className={cx("font-mono text-[10.5px] tracking-[0.08em] uppercase", i === stepIndex ? "text-ink" : "text-muted", reachable && "group-hover:text-ink")}>{s.label}</span>
              </>
            );
            return (
              <li key={s.id} aria-current={i === stepIndex ? "step" : undefined}>
                {reachable ? (
                  <button type="button" className="group flex items-center gap-1.5" disabled={busy} onClick={() => run(() => api.onboardingGoto(s.id))} title={`Back to ${s.label}`}>
                    {inner}
                  </button>
                ) : (
                  <span className="flex items-center gap-1.5">{inner}</span>
                )}
              </li>
            );
          })}
        </ol>
        <div className="ml-auto flex items-center gap-3">
          <span className="hidden sm:block">
            <Segmented label="Theme" size="sm" value={mode} onChange={setMode} options={THEMES} />
          </span>
          <Button size="sm" variant="ghost" disabled={busy} onClick={() => run(() => api.onboardingStep("skip_all"))}>
            Skip setup
          </Button>
        </div>
      </header>

      <main className="@container mx-auto w-full max-w-[1280px] flex-1 px-4 py-6 md:px-10 md:py-10">
        <div className="mb-6 h-8">
          {view.nav?.back && (
            <Button size="sm" variant="ghost" className="-ml-3" disabled={busy} onClick={() => run(() => api.onboardingGoto(view.nav.back!.step, view.nav.back!.question))}>
              <ArrowLeft /> Back
            </Button>
          )}
        </div>
        {step === "linkedin" && <LinkedInStep busy={busy} run={run} hasAnswers={view.panel.some((l) => l.status !== "pending")} />}
        {step === "questions" && <QuestionStep view={view} busy={busy} run={run} />}
        {step === "lookups" && <LookupStep view={view} busy={busy} run={run} onChange={onChange} />}
        {step === "chats" && <ChatsStep busy={busy} run={run} />}
      </main>
    </div>
  );
}

type Run = (fn: () => Promise<OnboardingView>) => Promise<void>;

function LinkedInStep({ busy, run, hasAnswers }: { busy: boolean; run: Run; hasAnswers: boolean }) {
  return (
    <div className="mx-auto max-w-3xl animate-rise">
      <p className="eyebrow">Step 1 · LinkedIn</p>
      <h1 className="display mt-4 text-5xl md:text-7xl">Let's start with your LinkedIn profile as a PDF</h1>
      <div className="mt-10">
        <DropZone
          busy={busy}
          accept="application/pdf"
          label="Upload your LinkedIn PDF"
          onFiles={(files) => files[0] && run(() => api.onboardingLinkedin(files[0]))}
        >
          <Upload className="size-6" strokeWidth={1.5} aria-hidden />
          <p className="display text-3xl">{busy ? "Reading it…" : "Drop the PDF here, or click to choose"}</p>
          <p className="font-mono text-[11px] text-muted uppercase">Read on this computer · emails and phone numbers removed first</p>
        </DropZone>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-4">
        <p className="text-[15px] text-ink-2">On LinkedIn: Profile &gt; More &gt; Save to PDF.</p>
        {hasAnswers ? (
          <Button variant="primary" disabled={busy} onClick={() => run(() => api.onboardingGoto("questions"))}>
            Keep my answers and continue <ArrowRight />
          </Button>
        ) : (
          <Button variant="ghost" disabled={busy} onClick={() => run(() => api.onboardingStep("skip_linkedin"))}>
            <SkipForward /> Skip
          </Button>
        )}
      </div>
    </div>
  );
}

function asText(v: string | string[] | undefined) {
  return Array.isArray(v) ? v.join("; ") : (v ?? "");
}

function QuestionStep({ view, busy, run }: { view: OnboardingView; busy: boolean; run: Run }) {
  const q = view.question;
  const turns = view.state.transcript ?? [];
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => {
    end.current?.scrollIntoView({ block: "nearest" });
  }, [turns.length, q?.id]);
  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-8 @4xl:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
      <section className="card flex min-w-0 flex-col self-start" aria-label="Getting to know you">
        <header className="flex items-center justify-between gap-3 border-b border-line px-5 py-3">
          <h1 className="eyebrow text-ink">Getting to know you</h1>
          {view.state.source && (
            <span className="truncate font-mono text-[10.5px] text-muted uppercase">
              {view.state.source.filename} · {plural(view.state.source.redactions, "contact detail")} removed
            </span>
          )}
        </header>
        <div className="flex max-h-[min(62vh,640px)] flex-col gap-3 overflow-y-auto px-5 py-5" aria-live="polite">
          {turns.map((turn, i) => (
            <Bubble key={i} who={turn.who} first={i === 0 || turns[i - 1].who !== turn.who}>
              {turn.text}
            </Bubble>
          ))}
          {q && (
            <Bubble key={q.id} who="lighthouse" first={turns.at(-1)?.who !== "lighthouse"} current>
              {q.text}
              {q.quote && !q.text.includes(q.quote) && (
                <span className="mt-2 flex items-start gap-1.5 text-xs text-ink-2">
                  <FileText className="mt-0.5 size-3.5 shrink-0" strokeWidth={1.5} aria-hidden />
                  From your PDF: “{q.quote}”
                </span>
              )}
            </Bubble>
          )}
          {!q && <p className="text-sm text-ink-2">All set.</p>}
          <div ref={end} />
        </div>
        {q && <Answer key={q.id} q={q} busy={busy} run={run} labels={labels(view)} />}
      </section>
      <ProfilePanel view={view} />
    </div>
  );
}

/** Real titles for list items (a paper's arXiv link), known only after a lookup the person said Yes to. */
function labels(view: OnboardingView): Record<string, string> {
  return Object.assign({}, ...view.state.lookups.map((l) => l.resolved ?? {}));
}

function Bubble({ who, first, current, children }: { who: "lighthouse" | "you"; first: boolean; current?: boolean; children: ReactNode }) {
  const me = who === "you";
  return (
    <div className={cx("flex animate-rise flex-col", me ? "items-end" : "items-start")}>
      {first && <span className="mb-1 font-mono text-[10px] tracking-[0.12em] text-muted uppercase">{me ? "You" : "Lighthouse"}</span>}
      <p
        className={cx(
          "max-w-[85%] border px-4 py-2.5 text-[15px] leading-relaxed",
          me ? "border-ink bg-ink text-on-ink" : current ? "border-ink bg-surface text-ink" : "border-line bg-paper text-ink",
        )}
      >
        {children}
      </p>
    </div>
  );
}

/** The reply area under the conversation: Yes / No, let me fix it / Skip, a choice, or a month. */
function Answer({ q, busy, run, labels }: { q: OnboardingQuestion; busy: boolean; run: Run; labels: Record<string, string> }) {
  const [fixing, setFixing] = useState(false);
  const [lists, setLists] = useState<Record<string, string[]>>(() =>
    Object.fromEntries(q.keys.filter((k) => Array.isArray(q.values[k])).map((k) => [k, q.values[k] as string[]])),
  );
  const [draft, setDraft] = useState<Record<string, string>>(() => Object.fromEntries(q.keys.map((k) => [k, asText(q.values[k])])));
  const skip = (
    <Button type="button" variant="ghost" disabled={busy} onClick={() => run(() => api.onboardingAnswer(q.id, "skip"))}>
      Skip
    </Button>
  );
  let body: ReactNode;
  if (q.kind === "month")
    body = (
      <form
        className="flex flex-wrap items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (draft.when) run(() => api.onboardingAnswer(q.id, "yes", draft.when));
        }}
      >
        <label className="min-w-0 flex-1 basis-48">
          <span className="label">Month</span>
          <input id="when" type="month" className="input" value={draft.when ?? ""} onChange={(e) => setDraft({ when: e.target.value })} />
        </label>
        <Button type="submit" variant="primary" disabled={busy || !draft.when}>
          <Check /> Save
        </Button>
        {skip}
      </form>
    );
  else if (q.kind === "choice")
    body = (
      <div className="flex flex-wrap gap-2">
        {q.options.map((o) => (
          <Button key={o.value} disabled={busy} onClick={() => run(() => api.onboardingAnswer(q.id, "yes", o.value))}>
            {o.label}
          </Button>
        ))}
        {skip}
      </div>
    );
  else if (fixing)
    body = (
      <form
        className="grid gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          const all: Record<string, string | string[]> = { ...draft, ...lists };
          run(() => api.onboardingAnswer(q.id, "fix", q.keys.length === 1 ? all[q.keys[0]] : all));
        }}
      >
        {q.keys.map((k) =>
          Array.isArray(q.values[k]) ? (
            <div key={k}>
              <span className="label" id={`fix-${k}-label`}>
                {k}
              </span>
              <ChipInput id={`fix-${k}`} label={k} value={lists[k] ?? []} labels={labels} onChange={(items) => setLists({ ...lists, [k]: items })} />
              <span className="mt-1 block font-mono text-[10.5px] text-muted uppercase">; or Enter adds one · paste a list · Backspace removes the last · click one to edit</span>
            </div>
          ) : (
            <label key={k}>
              <span className="label">{k}</span>
              <input className="input" id={`fix-${k}`} autoFocus={k === q.keys[0]} value={draft[k] ?? ""} onChange={(e) => setDraft({ ...draft, [k]: e.target.value })} />
            </label>
          ),
        )}
        <div className="flex flex-wrap gap-2">
          <Button type="submit" variant="primary" disabled={busy}>
            <Check /> Save
          </Button>
          <Button type="button" variant="ghost" onClick={() => setFixing(false)}>
            Cancel
          </Button>
        </div>
      </form>
    );
  else
    body = (
      <div className="flex flex-wrap gap-2">
        <Button variant="primary" disabled={busy} onClick={() => run(() => api.onboardingAnswer(q.id, "yes"))}>
          <Check /> Yes
        </Button>
        <Button disabled={busy} onClick={() => setFixing(true)}>
          <Pencil /> No, let me fix it
        </Button>
        {skip}
      </div>
    );
  return <div className="border-t border-line bg-sunken/40 px-5 py-4">{body}</div>;
}

function ProfilePanel({ view }: { view: OnboardingView }) {
  const lines = view.panel.filter((l) => l.status !== "pending");
  return (
    <aside className="card self-start" aria-label="Your profile so far">
      <header className="border-b border-line px-5 py-3">
        <h2 className="eyebrow text-ink">Your profile so far</h2>
      </header>
      {lines.length === 0 ? (
        <p className="px-5 py-8 text-sm text-ink-2">Each answer fills a line here. Skipped ones stay blank.</p>
      ) : (
        <dl>
          {lines.map((l) => (
            <div key={l.key} className="animate-rise border-b border-line px-5 py-3 last:border-b-0">
              <dt className="eyebrow">{l.label}</dt>
              <dd className={cx("mt-1 text-[15px] leading-snug", l.status === "skipped" ? "text-muted" : "text-ink")}>
                {l.status === "skipped" ? "Skipped" : Array.isArray(l.value) ? l.value.map((v) => labels(view)[v] ?? v).join("; ") : asText(l.value)}
                {l.status === "fixed" && <span className="ml-2 font-mono text-[10px] text-muted uppercase">edited</span>}
              </dd>
            </div>
          ))}
        </dl>
      )}
    </aside>
  );
}

function LookupStep({ view, busy, run, onChange }: { view: OnboardingView; busy: boolean; run: Run; onChange: (v: OnboardingView) => void }) {
  const open = view.state.lookups.some((l) => l.status === "offered");
  const searching = view.state.lookups.some((l) => l.status === "searching" || l.status === "accepted");
  useEffect(() => {
    if (!searching) return;
    const id = setInterval(() => api.onboarding().then(onChange, () => {}), 2500); // web lookups run in the background
    return () => clearInterval(id);
  }, [searching, onChange]);
  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-10 @4xl:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
      <div className="min-w-0">
        <p className="eyebrow">Step 3 · Find your work</p>
        <h1 className="display mt-4 text-4xl md:text-6xl">Want me to look these up?</h1>
        <p className="mt-4 max-w-xl text-[15px] leading-relaxed text-ink-2">
          Only for what you confirmed. Anything I find goes to your Inbox for you to check first, and finds that may belong to someone with the
          same name are marked. Web searches use your AI, usually a few cents each.
        </p>
        <div className="mt-8 flex flex-col gap-3">
          {view.state.lookups.map((l) => (
            <LookupCard key={l.id} l={l} busy={busy} run={run} />
          ))}
        </div>
        <Button className="mt-6" variant={open ? "ghost" : "primary"} disabled={busy && open} onClick={() => run(() => api.onboardingStep("lookups_done"))}>
          {open ? "Not now, continue" : searching ? "Continue (searches finish in the background)" : "Continue"}
        </Button>
      </div>
      <ProfilePanel view={view} />
    </div>
  );
}

const LOOKUP_STATUS: Record<OnboardingLookup["status"], { label: string; tone: "ink" | "outline" | "muted" | "alert" }> = {
  offered: { label: "", tone: "muted" },
  declined: { label: "Skipped", tone: "muted" },
  searching: { label: "Searching", tone: "outline" },
  accepted: { label: "Searching", tone: "outline" },
  found: { label: "Found", tone: "ink" },
  done: { label: "Done", tone: "ink" },
  nothing_found: { label: "Nothing found", tone: "muted" },
  unreachable: { label: "Couldn't reach the site", tone: "alert" },
  blocked: { label: "Blocked by the site", tone: "alert" },
  failed: { label: "Didn't work", tone: "alert" },
};
const RETRYABLE = new Set(["nothing_found", "unreachable", "blocked", "failed"]);

function LookupCard({ l, busy, run }: { l: OnboardingLookup; busy: boolean; run: Run }) {
  const s = LOOKUP_STATUS[l.status];
  const searching = l.status === "searching" || l.status === "accepted";
  return (
    <div className="card animate-rise p-5" data-lookup={l.id} data-status={l.status}>
      <div className="flex items-start gap-3">
        <Search className={cx("mt-1 size-5 shrink-0", searching && "animate-tool-pulse")} strokeWidth={1.5} aria-hidden />
        <div className="min-w-0 flex-1">
          <p className="text-[17px] leading-snug">{l.prompt}</p>
          <p className="mt-1 truncate font-mono text-[11px] text-muted">{l.targets.join(" · ")}</p>
          {s.label && (
            <p className="mt-3 flex flex-wrap items-center gap-2" role="status">
              <Chip tone={s.tone}>{s.label}</Chip>
              {l.result && <span className={cx("text-sm", s.tone === "alert" ? "text-alert" : "text-ink-2")}>{l.result}</span>}
            </p>
          )}
        </div>
      </div>
      {(l.status === "offered" || RETRYABLE.has(l.status)) && (
        <div className="mt-4 flex gap-2 pl-8">
          <Button variant={l.status === "offered" ? "primary" : "secondary"} disabled={busy} onClick={() => run(() => api.onboardingLookup(l.id, true))}>
            {l.status === "offered" ? "Yes, look" : <><RotateCw /> Retry</>}
          </Button>
          {l.status === "offered" && (
            <Button variant="ghost" disabled={busy} onClick={() => run(() => api.onboardingLookup(l.id, false))}>
              No thanks
            </Button>
          )}
        </div>
      )}
    </div>
  );
}

function ChatsStep({ busy, run }: { busy: boolean; run: Run }) {
  const toast = useToast();
  const [importing, setImporting] = useState(false);
  const drop = async (files: File[]) => {
    if (!files[0]) return;
    setImporting(true);
    try {
      const r = await api.importChats(files[0]);
      toast(r.summary);
      await run(() => api.onboardingStep("chats_done"));
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setImporting(false);
    }
  };
  return (
    <div className="mx-auto max-w-3xl animate-rise">
      <p className="eyebrow">Step 4 · Chat history</p>
      <h1 className="display mt-4 text-4xl md:text-6xl">Bring your chats along</h1>
      <p className="mt-5 text-lg leading-relaxed text-ink-2">
        Quick story: the person who built me kept his context spread across Claude and ChatGPT. If you're like him, drop those exports here and
        I'll pick up where they left off.
      </p>
      <div className="mt-8 grid gap-px border border-frame bg-line sm:grid-cols-2">
        <div className="bg-surface p-5">
          <p className="flex items-center gap-2 text-[15px] font-medium">
            <MessageSquare className="size-4" strokeWidth={1.5} aria-hidden /> Claude
          </p>
          <p className="mt-2 text-sm text-ink-2">Settings &gt; Privacy &gt; Export data, then drop the .zip from the email.</p>
        </div>
        <div className="bg-surface p-5">
          <p className="flex items-center gap-2 text-[15px] font-medium">
            <MessageSquare className="size-4" strokeWidth={1.5} aria-hidden /> ChatGPT
          </p>
          <p className="mt-2 text-sm text-ink-2">Settings &gt; Data controls &gt; Export, then drop the .zip from the email.</p>
        </div>
      </div>
      <div className="mt-6">
        <DropZone busy={busy || importing} label="Upload a chat export" onFiles={drop}>
          <Upload className="size-6" strokeWidth={1.5} aria-hidden />
          <p className="display text-3xl">{importing ? "Reading your chats…" : "Drop an export here"}</p>
          <p className="font-mono text-[11px] text-muted uppercase">conversations.json or the export .zip · stays on this computer · never counts as evidence</p>
        </DropZone>
      </div>
      <div className="flex justify-end">
        <Button variant="ghost" disabled={busy || importing} onClick={() => run(() => api.onboardingStep("chats_skip"))}>
          <SkipForward /> Skip for now
        </Button>
      </div>
    </div>
  );
}
