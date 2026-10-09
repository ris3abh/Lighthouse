import { useCallback, useEffect, useRef, useState } from "react";
import { bindBackToClose } from "./lib/nav";

/** Load data on mount; `reload()` re-fetches without clearing what's on screen. */
export function useLoad<T>(fn: () => Promise<T>, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [loading, setLoading] = useState(true);

  const reload = useCallback(() => {
    setLoading(true);
    return fn()
      .then((d) => {
        setData(d);
        setError(null);
      })
      .catch((e: Error) => setError(e))
      .finally(() => setLoading(false));
  }, deps);

  useEffect(() => {
    reload();
  }, [reload]);

  return { data, error, loading, reload };
}

/** Minimal hash router: "#/evidence?c=judging" -> { page: "evidence", params }. */
export function useRoute() {
  const parse = () => {
    const raw = window.location.hash.replace(/^#\/?/, "");
    const [page, query = ""] = raw.split("?");
    return { page: page || "overview", params: new URLSearchParams(query) };
  };
  const [route, setRoute] = useState(parse);
  useEffect(() => {
    const onChange = () => setRoute(parse());
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return route;
}

export type ThemeMode = "system" | "light" | "dark";

function systemDark() {
  return !!window.matchMedia?.("(prefers-color-scheme: dark)").matches;
}

function applyTheme(mode: ThemeMode) {
  document.documentElement.classList.toggle("dark", mode === "dark" || (mode === "system" && systemDark()));
}

/** System / Light / Dark, remembered per browser; System follows the OS setting live. */
export function useTheme() {
  const [mode, setModeState] = useState<ThemeMode>(() => {
    try {
      const saved = localStorage.getItem("lh-theme");
      return saved === "light" || saved === "dark" ? saved : "system";
    } catch {
      return "system";
    }
  });
  useEffect(() => {
    applyTheme(mode);
    if (mode !== "system") return;
    const mq = window.matchMedia?.("(prefers-color-scheme: dark)");
    const on = () => applyTheme("system");
    mq?.addEventListener("change", on);
    return () => mq?.removeEventListener("change", on);
  }, [mode]);
  const setMode = (next: ThemeMode) => {
    try {
      localStorage.setItem("lh-theme", next);
    } catch {
      /* storage unavailable */
    }
    setModeState(next);
  };
  return { mode, setMode };
}

/** Local calendar date as YYYY-MM-DD. */
export function today(offsetDays = 0) {
  const d = new Date();
  d.setDate(d.getDate() + offsetDays);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}


/** While ``open``, the browser's Back closes the dialog (and stays on the page). */
export function useBackToClose(open: boolean, onClose: () => void) {
  const close = useRef(onClose);
  close.current = onClose;
  useEffect(() => {
    if (!open) return;
    return bindBackToClose(window.history, window, () => close.current());
  }, [open]);
}

/** Actions that cost money or send something run once at a time (B3): `run(key, fn)` ignores a second call with
 * the same key while the first is in flight (a ref, so a double click can't slip in before the re-render), and
 * `busy(key)` disables its button. The server dedupes too (idempotency keys), for other tabs and retries. */
export function useOnce() {
  const inflight = useRef(new Set<string>());
  const [, setTick] = useState(0);
  const run = useCallback(async <T,>(key: string, fn: () => Promise<T>): Promise<T | undefined> => {
    if (inflight.current.has(key)) return undefined;
    inflight.current.add(key);
    setTick((t) => t + 1);
    try {
      return await fn();
    } finally {
      inflight.current.delete(key);
      setTick((t) => t + 1);
    }
  }, []);
  const busy = useCallback((key: string) => inflight.current.has(key), []);
  return { run, busy };
}

/** Scroll to an element by id once it exists, and keep it in place while the page around it is still loading (panels
 * that arrive later push it down): re-aims for up to three seconds, and stops as soon as the person scrolls (B7). */
export function useScrollTo(id: string | null, ready: boolean) {
  useEffect(() => {
    if (!id || !ready) return;
    let stop = false;
    let timer = 0;
    const cancel = () => {
      stop = true;
    };
    const events = ["wheel", "touchstart", "keydown", "mousedown"] as const;
    events.forEach((e) => window.addEventListener(e, cancel, { passive: true }));
    const started = performance.now();
    let first = true;
    const tick = () => {
      if (stop) return;
      const el = document.getElementById(id);
      if (el && (first || Math.abs(el.getBoundingClientRect().top) > 4)) { // a panel above that finishes loading moves it a little too
        el.scrollIntoView({ behavior: first ? "smooth" : "auto", block: "start" });
        first = false;
      }
      if (performance.now() - started < 3000) timer = window.setTimeout(tick, 200);
    };
    tick();
    return () => {
      stop = true;
      window.clearTimeout(timer);
      events.forEach((e) => window.removeEventListener(e, cancel));
    };
  }, [id, ready]);
}
