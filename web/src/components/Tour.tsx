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
    text: (o) =>
      o ? `${plural(o.scoreboard.banked, "criterion", "criteria")} banked of the ${o.scoreboard.threshold} needed for ${o.scoreboard.profile_name}. The bars fill as evidence is accepted.` : "Your criteria, tasks and deadlines at a glance.",
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

export default function Tour({ overview, onDone }: { overview: Overview | null; onDone: (skipped: boolean) => void }) {
  const [i, setI] = useState(0);
  const step = STEPS[i];
  useEffect(() => {
    window.location.hash = `#/${step.page}`;
  }, [step.page]);
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
        <Button size="sm" variant="ghost" disabled={i === 0} onClick={() => setI(i - 1)}>
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
