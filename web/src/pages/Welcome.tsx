import { ArrowRight, Check, FileText, MessageSquare, Pencil, Search, SkipForward, Upload } from "lucide-react";
import { useState, type ReactNode } from "react";
import { api, type OnboardingLookup, type OnboardingQuestion, type OnboardingView } from "../api";
import DropZone from "../components/DropZone";
import { Button, cx, plural, Segmented, useToast } from "../components/ui";
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
          {STEPS.map((s, i) => (
            <li key={s.id} className="flex items-center gap-1.5" aria-current={i === stepIndex ? "step" : undefined}>
              <span className={cx("h-1.5 w-8 border border-ink transition-colors duration-300", i < stepIndex ? "bg-ink" : i === stepIndex ? "bg-ink-2" : "bg-transparent")} />
              <span className={cx("font-mono text-[10.5px] tracking-[0.08em] uppercase", i === stepIndex ? "text-ink" : "text-muted")}>{s.label}</span>
            </li>
          ))}
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

      <main className="@container mx-auto w-full max-w-[1280px] flex-1 px-4 py-10 md:px-10 md:py-16">
        {step === "linkedin" && <LinkedInStep busy={busy} run={run} />}
        {step === "questions" && <QuestionStep view={view} busy={busy} run={run} />}
        {step === "lookups" && <LookupStep view={view} busy={busy} run={run} />}
        {step === "chats" && <ChatsStep busy={busy} run={run} />}
      </main>
    </div>
  );
}

type Run = (fn: () => Promise<OnboardingView>) => Promise<void>;

function LinkedInStep({ busy, run }: { busy: boolean; run: Run }) {
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
        <Button variant="ghost" disabled={busy} onClick={() => run(() => api.onboardingStep("skip_linkedin"))}>
          <SkipForward /> Skip
        </Button>
      </div>
    </div>
  );
}

function asText(v: string | string[] | undefined) {
  return Array.isArray(v) ? v.join("; ") : (v ?? "");
}

function QuestionStep({ view, busy, run }: { view: OnboardingView; busy: boolean; run: Run }) {
  const q = view.question;
  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-10 @4xl:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
      <div className="min-w-0">
        <p className="eyebrow">Step 2 · Your profile</p>
        {q ? <QuestionCard key={q.id} q={q} busy={busy} run={run} source={view.state.source?.filename} /> : <p className="mt-6 text-ink-2">All set.</p>}
        {view.state.source && (
          <p className="mt-6 font-mono text-[10.5px] text-muted uppercase">
            Read locally from {view.state.source.filename} · {plural(view.state.source.redactions, "contact detail")} removed before anything else saw it
          </p>
        )}
      </div>
      <ProfilePanel view={view} />
    </div>
  );
}

function QuestionCard({ q, busy, run, source }: { q: OnboardingQuestion; busy: boolean; run: Run; source?: string }) {
  const [fixing, setFixing] = useState(false);
  const [draft, setDraft] = useState<Record<string, string>>(() => Object.fromEntries(q.keys.map((k) => [k, asText(q.values[k])])));
  if (q.kind === "month")
    return (
      <form
        className="mt-4 animate-rise"
        onSubmit={(e) => {
          e.preventDefault();
          if (draft.when) run(() => api.onboardingAnswer(q.id, "yes", draft.when));
        }}
      >
        <h1 className="display text-4xl md:text-6xl">{q.text}</h1>
        <label className="mt-8 block max-w-xs">
          <span className="label">Month</span>
          <input id="when" type="month" className="input h-12 text-base" value={draft.when ?? ""} onChange={(e) => setDraft({ when: e.target.value })} />
        </label>
        <div className="mt-6 flex flex-wrap gap-2">
          <Button type="submit" variant="primary" className="h-12 px-6" disabled={busy || !draft.when}>
            <Check /> Save
          </Button>
          <Button type="button" variant="ghost" className="h-12 px-6" disabled={busy} onClick={() => run(() => api.onboardingAnswer(q.id, "skip"))}>
            Skip
          </Button>
        </div>
      </form>
    );
  if (q.kind === "choice")
    return (
      <div className="mt-4 animate-rise">
        <h1 className="display text-4xl md:text-6xl">{q.text}</h1>
        <div className="mt-8 flex flex-col gap-2">
          {q.options.map((o) => (
            <button
              key={o.value}
              type="button"
              disabled={busy}
              onClick={() => run(() => api.onboardingAnswer(q.id, "yes", o.value))}
              className="group flex items-center justify-between border border-ink bg-surface px-5 py-4 text-left text-[15px] transition-colors hover:bg-ink hover:text-on-ink"
            >
              {o.label}
              <ArrowRight className="size-4 transition-transform group-hover:translate-x-1" aria-hidden />
            </button>
          ))}
        </div>
        <Button className="mt-4" variant="ghost" disabled={busy} onClick={() => run(() => api.onboardingAnswer(q.id, "skip"))}>
          Skip
        </Button>
      </div>
    );
  return (
    <div className="mt-4 animate-rise">
      <h1 className="display text-4xl leading-[0.95] md:text-6xl">{q.text}</h1>
      {q.quote && (
        <p className="mt-5 flex items-start gap-2 border-l-2 border-ink pl-3 text-sm text-ink-2">
          <FileText className="mt-0.5 size-4 shrink-0" strokeWidth={1.5} aria-hidden />
          <span>
            From your PDF{source ? ` (${source})` : ""}
            {q.text.includes(q.quote) ? "" : `: “${q.quote}”`}
          </span>
        </p>
      )}
      {fixing ? (
        <form
          className="mt-8 grid gap-4"
          onSubmit={(e) => {
            e.preventDefault();
            const value = q.keys.length === 1 ? draft[q.keys[0]] : draft;
            run(() => api.onboardingAnswer(q.id, "fix", value));
          }}
        >
          {q.keys.map((k) => (
            <label key={k}>
              <span className="label">{k}</span>
              <input className="input h-12 text-base" id={`fix-${k}`} autoFocus={k === q.keys[0]} value={draft[k] ?? ""} onChange={(e) => setDraft({ ...draft, [k]: e.target.value })} />
              {Array.isArray(q.values[k]) && <span className="mt-1 block font-mono text-[10.5px] text-muted uppercase">Separate items with ;</span>}
            </label>
          ))}
          <div className="flex flex-wrap gap-2">
            <Button type="submit" variant="primary" disabled={busy}>
              <Check /> Save
            </Button>
            <Button type="button" variant="ghost" onClick={() => setFixing(false)}>
              Cancel
            </Button>
          </div>
        </form>
      ) : (
        <div className="mt-8 flex flex-wrap gap-2">
          <Button variant="primary" className="h-12 px-6" disabled={busy} onClick={() => run(() => api.onboardingAnswer(q.id, "yes"))}>
            <Check /> Yes
          </Button>
          <Button className="h-12 px-6" disabled={busy} onClick={() => setFixing(true)}>
            <Pencil /> No, let me fix it
          </Button>
          <Button variant="ghost" className="h-12 px-6" disabled={busy} onClick={() => run(() => api.onboardingAnswer(q.id, "skip"))}>
            Skip
          </Button>
        </div>
      )}
    </div>
  );
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
                {l.status === "skipped" ? "Skipped" : asText(l.value)}
                {l.status === "fixed" && <span className="ml-2 font-mono text-[10px] text-muted uppercase">edited</span>}
              </dd>
            </div>
          ))}
        </dl>
      )}
    </aside>
  );
}

function LookupStep({ view, busy, run }: { view: OnboardingView; busy: boolean; run: Run }) {
  const open = view.state.lookups.some((l) => l.status === "offered");
  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-10 @4xl:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
      <div className="min-w-0">
        <p className="eyebrow">Step 3 · Find your work</p>
        <h1 className="display mt-4 text-4xl md:text-6xl">Want me to look these up?</h1>
        <p className="mt-4 max-w-xl text-[15px] leading-relaxed text-ink-2">
          Only for what you confirmed. Anything I find goes to your Inbox for you to check first, and finds that may belong to someone with the
          same name are marked.
        </p>
        <div className="mt-8 flex flex-col gap-3">
          {view.state.lookups.map((l) => (
            <LookupCard key={l.id} l={l} busy={busy} run={run} />
          ))}
        </div>
        {open && (
          <Button className="mt-6" variant="ghost" disabled={busy} onClick={() => run(() => api.onboardingStep("lookups_done"))}>
            Not now, continue
          </Button>
        )}
      </div>
      <ProfilePanel view={view} />
    </div>
  );
}

function LookupCard({ l, busy, run }: { l: OnboardingLookup; busy: boolean; run: Run }) {
  return (
    <div className="card animate-rise p-5">
      <div className="flex items-start gap-3">
        <Search className={cx("mt-1 size-5 shrink-0", l.status === "accepted" && "animate-tool-pulse")} strokeWidth={1.5} aria-hidden />
        <div className="min-w-0 flex-1">
          <p className="text-[17px] leading-snug">{l.prompt}</p>
          <p className="mt-1 truncate font-mono text-[11px] text-muted">{l.targets.join(" · ")}</p>
          {l.result && <p className={cx("mt-3 text-sm", l.status === "failed" ? "text-alert" : "text-ink-2")}>{l.result}</p>}
        </div>
      </div>
      {l.status === "offered" ? (
        <div className="mt-4 flex gap-2 pl-8">
          <Button variant="primary" disabled={busy} onClick={() => run(() => api.onboardingLookup(l.id, true))}>
            Yes, look
          </Button>
          <Button variant="ghost" disabled={busy} onClick={() => run(() => api.onboardingLookup(l.id, false))}>
            No thanks
          </Button>
        </div>
      ) : (
        <p className="mt-3 pl-8 font-mono text-[10.5px] text-muted uppercase">{l.status === "declined" ? "Skipped" : l.status === "done" ? "Done · check your Inbox" : l.status}</p>
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
