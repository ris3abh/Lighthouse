import { ArrowLeft, ArrowRight, X } from "lucide-react";
import { useEffect, useState } from "react";
import type { Overview } from "../api";
import { Button, plural } from "./ui";

type Step = { page: string; title: string; text: (o: Overview | null) => string };

/** A guided tour of each page, written from the person's own data. */
const STEPS: Step[] = [
  {
    page: "overview",
    title: "Where your case stands",
    text: (o) => {
      if (!o) return "Your criteria, tasks and deadlines at a glance.";
      const who = o.person.name ? `${o.person.name.split(" ")[0]}, ` : "";
      const b = o.scoreboard;
      return b.banked
        ? `${who}${plural(b.banked, "criterion", "criteria")} banked of the ${b.threshold} needed for ${b.profile_name}. The bars fill as evidence is accepted.`
        : `${who}nothing is banked yet, which is normal on day one. ${b.profile_name} needs ${b.threshold} criteria; each bar fills as you accept evidence.`;
    },
  },
  {
    page: "inbox",
    title: "Everything waits here first",
    text: (o) =>
      o && o.inbox_pending ? `${plural(o.inbox_pending, "suggestion")} from your setup ${o.inbox_pending === 1 ? "is" : "are"} waiting. Nothing counts until you accept it.` : "Finds from your sources and the agent land here. Nothing counts until you accept it.",
  },
  { page: "evidence", title: "Your evidence, by criterion", text: () => "Accepted items are filed here. Drop certificates, letters and PDFs on any criterion." },
  {
    page: "calendar",
    title: "Deadlines and follow-ups",
    text: (o) => (o && o.deadlines.length ? `${plural(o.deadlines.length, "deadline")} coming up. Drag one to another day to move it.` : "Add deadlines here, or drag them to move them."),
  },
  { page: "sources", title: "Connect your work", text: () => "GitHub, Hugging Face, Semantic Scholar, OpenAlex, arXiv, ORCID or any web page. Connectors only read." },
  { page: "agent", title: "The agent's work, in the open", text: () => "Every run, what it read, what it proposed and what it cost. Ask it anything from any page." },
];

/** Each tour step has its own URL (#/inbox?tour=2), so the browser's back and forward move through it too. */
function tourIndex(): number {
  const n = Number(new URLSearchParams(window.location.hash.split("?")[1] ?? "").get("tour"));
  return Number.isInteger(n) && n >= 1 && n <= STEPS.length ? n - 1 : 0;
}

export default function Tour({ overview, onDone, onBack }: { overview: Overview | null; onDone: (skipped: boolean) => void; onBack?: () => void }) {
  const [i, setI] = useState(tourIndex);
  const step = STEPS[i];
  useEffect(() => {
    const want = `#/${step.page}?tour=${i + 1}`;
    if (window.location.hash !== want) window.location.hash = want;
  }, [step.page, i]);
  useEffect(() => {
    const onHash = () => {
      if (/[?&]tour=\d/.test(window.location.hash)) setI(tourIndex());
    };
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
  return (
    <div role="dialog" aria-label="Guided tour" className="fixed right-4 bottom-4 left-4 z-50 animate-rise border border-ink bg-surface sm:left-auto sm:w-[400px]">
      <div className="flex items-center justify-between border-b border-line px-5 py-3">
        <span className="eyebrow text-ink">
          Tour · {i + 1} of {STEPS.length}
        </span>
        <Button size="sm" variant="ghost" className="px-2" aria-label="Skip the tour" onClick={() => onDone(true)}>
          <X />
        </Button>
      </div>
      <div className="px-5 py-5">
        <p className="display text-3xl">{step.title}</p>
        <p className="mt-3 text-[15px] leading-relaxed text-ink-2">{step.text(overview)}</p>
      </div>
      <div className="flex items-center justify-between border-t border-line px-5 py-3">
        <Button size="sm" variant="ghost" disabled={i === 0 && !onBack} onClick={() => (i === 0 ? onBack?.() : setI(i - 1))}>
          <ArrowLeft /> Back
        </Button>
        {i < STEPS.length - 1 ? (
          <Button size="sm" variant="primary" onClick={() => setI(i + 1)}>
            Next <ArrowRight />
          </Button>
        ) : (
          <Button size="sm" variant="primary" onClick={() => onDone(false)}>
            Finish
          </Button>
        )}
      </div>
    </div>
  );
}
