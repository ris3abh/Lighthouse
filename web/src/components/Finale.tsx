import { ArrowRight, Sparkles } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useReducedMotion } from "../lib/motion";
import { Button, plural } from "./ui";
import Banter from "./Banter";

const duration = 380; // ms, ADR 0007

/** The end of onboarding: one full moment, then the Ask button flies to its place in the header and stays there. */
export default function Finale({ name, todos, onDone }: { name: string; todos: number; onDone: () => void }) {
  const reduced = useReducedMotion();
  const ask = useRef<HTMLButtonElement>(null);
  const [leaving, setLeaving] = useState(false);

  const dock = () => {
    if (leaving) return;
    const from = ask.current?.getBoundingClientRect();
    const to = document.querySelector("[data-ask-anchor]")?.getBoundingClientRect();
    if (reduced || !from || !to || !ask.current?.animate) return onDone();
    setLeaving(true);
    const dx = to.left + to.width / 2 - (from.left + from.width / 2);
    const dy = to.top + to.height / 2 - (from.top + from.height / 2);
    const scale = Math.max(to.height / from.height, 0.3);
    ask.current
      .animate([{ transform: "none" }, { transform: `translate(${dx}px, ${dy}px) scale(${scale})` }], {
        duration,
        easing: "cubic-bezier(0.22, 1, 0.36, 1)",
        fill: "forwards",
      })
      .finished.then(onDone, onDone);
  };

  useEffect(() => {
    ask.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && dock();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  return (
    <div role="dialog" aria-modal="true" aria-label="Setup finished" className="fixed inset-0 z-50 flex items-center justify-center">
      <div className={`absolute inset-0 bg-paper transition-opacity duration-[380ms] ${leaving ? "opacity-0" : "opacity-100"}`} />
      <div className="relative mx-auto w-full max-w-4xl px-6">
        <div className={`transition-opacity duration-200 ${leaving ? "opacity-0" : "animate-rise"}`}>
          <p className="eyebrow">{name ? `All set, ${name}` : "All set"}</p>
          <Banter id="finish" className="display mt-5 text-6xl md:text-8xl" fallback="That's it. I'm one click away, and at your service." />
          <p className="mt-6 max-w-xl text-lg leading-relaxed text-ink-2">
            {todos
              ? `${plural(todos, "next step")} from what you told me ${todos === 1 ? "is" : "are"} waiting on your Overview. Ask me anything, any time, from the button at the top.`
              : "Ask me anything, any time, from the button at the top."}
          </p>
        </div>
        <div className="mt-10 flex flex-wrap items-center gap-3">
          <Button ref={ask} variant="primary" className="h-14 px-7 text-base" onClick={dock}>
            <Sparkles strokeWidth={1.5} /> Ask
          </Button>
          <Button variant="ghost" className={`h-14 px-5 transition-opacity duration-200 ${leaving ? "opacity-0" : ""}`} onClick={dock}>
            Open my dashboard <ArrowRight />
          </Button>
        </div>
      </div>
    </div>
  );
}
