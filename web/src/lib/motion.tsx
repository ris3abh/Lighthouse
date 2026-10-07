import { useEffect, useRef, useState, type RefObject } from "react";
import { flushSync } from "react-dom";

/** Motion rules (ADR 0007): data and state changes only, 150–400ms, eased, never blocking; reduced motion = instant. */

const QUERY = "(prefers-reduced-motion: reduce)";

export function prefersReducedMotion() {
  return typeof window !== "undefined" && !!window.matchMedia?.(QUERY).matches;
}

export function useReducedMotion() {
  const [reduced, setReduced] = useState(prefersReducedMotion);
  useEffect(() => {
    const mq = window.matchMedia?.(QUERY);
    if (!mq) return;
    const on = () => setReduced(mq.matches);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);
  return reduced;
}

/** True once the element has scrolled into view (stays true). */
export function useInView<T extends Element>(ref: RefObject<T | null>, margin = "0px 0px -10% 0px") {
  const [seen, setSeen] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el || seen) return;
    if (typeof IntersectionObserver === "undefined") return setSeen(true);
    const io = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          setSeen(true);
          io.disconnect();
        }
      },
      { rootMargin: margin },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [ref, seen, margin]);
  return seen;
}

export const easeOutCubic = (t: number) => 1 - Math.pow(1 - t, 3);

/** Counts from the previous value (0 on first view) to `value`. */
export function useCountUp(value: number, { duration = 400, start = true } = {}) {
  const reduced = useReducedMotion();
  const [shown, setShown] = useState(reduced || !start ? (start ? value : 0) : 0);
  const from = useRef(0);
  useEffect(() => {
    if (!start) return;
    if (reduced) {
      setShown(value);
      from.current = value;
      return;
    }
    const begin = from.current;
    const t0 = performance.now();
    let raf = 0;
    const step = (now: number) => {
      const t = Math.min(1, (now - t0) / duration);
      setShown(begin + (value - begin) * easeOutCubic(t));
      if (t < 1) raf = requestAnimationFrame(step);
      else from.current = value;
    };
    raf = requestAnimationFrame(step);
    return () => {
      cancelAnimationFrame(raf);
      from.current = value;
    };
  }, [value, start, reduced, duration]);
  return shown;
}

function format(n: number, decimals: number) {
  return n.toLocaleString(undefined, { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}

/** A number that counts up to its value the first time it's on screen. */
export function CountUp({ value, decimals, className }: { value: number; decimals?: number; className?: string }) {
  const ref = useRef<HTMLSpanElement>(null);
  const seen = useInView(ref);
  const d = decimals ?? (Number.isInteger(value) ? 0 : 2);
  const shown = useCountUp(value, { start: seen });
  return (
    <span ref={ref} className={className} aria-label={format(value, d)}>
      <span aria-hidden>{format(seen ? shown : 0, d)}</span>
    </span>
  );
}

type DocWithVT = Document & { startViewTransition?: (cb: () => void) => { finished: Promise<void> } };

/** Run a state update inside a view transition when the browser supports it (and motion is allowed). */
export function withViewTransition(update: () => void) {
  const doc = document as DocWithVT;
  if (!doc.startViewTransition || prefersReducedMotion()) {
    update();
    return;
  }
  doc.startViewTransition(() => flushSync(update));
}
