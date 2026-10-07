import { useCallback, useEffect, useState } from "react";

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
