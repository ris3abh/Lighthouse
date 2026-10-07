import { useLayoutEffect, useReducer, useRef } from "react";
import { banterAllowed, banterText, SERIOUS_PAGES, type BanterKey } from "../lib/banter";

function seriousPage(): boolean {
  const page = window.location.hash.replace(/^#\/?/, "").split(/[/?]/)[0] || "overview";
  return SERIOUS_PAGES.has(page);
}

/** The screen an element is on: a modal dialog is a screen of its own (the onboarding finish covers the page). */
function screenOf(el: Element | null): ParentNode {
  return el?.closest('[role="dialog"][aria-modal="true"]') ?? document;
}

const TOAST_MS = 3500; // how long a plain toast stays (ui.tsx)
let claimedUntil = 0;

/** Whether a toast may carry a line right now (not on a serious page, nothing serious on screen). If so, the toast
 * takes the screen's one slot while it's up: other lines step aside until it goes. */
export function banterOk(): boolean {
  const ok = banterAllowed({
    insideSerious: false,
    seriousOnScreen: !!document.querySelector("[data-serious]"),
    seriousPage: seriousPage(),
    earlierShown: 0,
  });
  if (ok) {
    claimedUntil = Date.now() + TOAST_MS;
    nudge();
    window.setTimeout(nudge, TOAST_MS + 50);
  }
  return ok;
}

// Every mounted line re-checks when another appears or goes, so "the first in reading order wins" holds even when
// a page's content loads after its footer.
const recheck = new Set<() => void>();
const nudge = () => queueMicrotask(() => recheck.forEach((f) => f()));

/** One tagged line of banter. It hides itself where the rules say it can't be (ADR 0010 §4). */
export default function Banter({
  id,
  className,
  as: Tag = "p",
  fallback,
}: {
  id: BanterKey;
  className?: string;
  as?: "p" | "span";
  fallback?: string; // the plain words to show where the line can't be
}) {
  const ref = useRef<HTMLElement>(null);
  const [, tick] = useReducer((n: number) => n + 1, 0);
  useLayoutEffect(() => {
    recheck.add(tick);
    nudge();
    return () => {
      recheck.delete(tick);
      nudge();
    };
  }, []);
  const el = ref.current;
  let show = false;
  if (el) {
    const screen = screenOf(el);
    const own = screen !== document;
    const lines = [...screen.querySelectorAll("[data-banter]")];
    show = banterAllowed({
      insideSerious: !!el.closest("[data-serious]"),
      seriousOnScreen: !!screen.querySelector("[data-serious]"),
      seriousPage: !own && seriousPage(),
      earlierShown: lines.indexOf(el) + (!own && Date.now() < claimedUntil ? 1 : 0), // a toast holds the slot
    });
  }
  useLayoutEffect(() => {
    if (!el) tick(); // first render: decide once the element exists
  });
  return (
    <>
      <Tag ref={ref as never} data-banter={id} hidden={!show} className={className}>
        {banterText(id)}
      </Tag>
      {!show && fallback && <Tag className={className}>{fallback}</Tag>}
    </>
  );
}
