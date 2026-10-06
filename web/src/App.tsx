import { createContext, useCallback, useContext, useState, type ReactNode } from "react";
import { api } from "./api";
import { Button, cx, ToastProvider, useToast } from "./components/ui";
import { useLoad, useRoute, useTheme } from "./hooks";
import Evidence from "./pages/Evidence";
import Inbox from "./pages/Inbox";
import Metrics from "./pages/Metrics";
import OverviewPage from "./pages/Overview";
import Settings from "./pages/Settings";
import Sources from "./pages/Sources";

/** Bumping `version` makes every page and the shell re-fetch after a write. */
const RefreshCtx = createContext<{ version: number; bump: () => void }>({ version: 0, bump: () => {} });
export const useRefresh = () => useContext(RefreshCtx);

const NAV = [
  { id: "overview", label: "Overview", icon: "◎" },
  { id: "inbox", label: "Inbox", icon: "⇣" },
  { id: "evidence", label: "Evidence", icon: "▤" },
  { id: "metrics", label: "Metrics", icon: "∿" },
  { id: "sources", label: "Sources", icon: "⛁" },
  { id: "settings", label: "Settings", icon: "⚙" },
] as const;

export default function App() {
  const [version, setVersion] = useState(0);
  const bump = useCallback(() => setVersion((v) => v + 1), []);
  return (
    <RefreshCtx.Provider value={{ version, bump }}>
      <ToastProvider>
        <Shell />
      </ToastProvider>
    </RefreshCtx.Provider>
  );
}

function Shell() {
  const { page, params } = useRoute();
  const { version, bump } = useRefresh();
  const { dark, toggle } = useTheme();
  const toast = useToast();
  const overview = useLoad(() => api.overview(), [version]);
  const [switching, setSwitching] = useState(false);
  const ov = overview.data;

  const switchProfile = async (id: string) => {
    setSwitching(true);
    try {
      const board = await api.setProfile(id);
      toast(`Re-scored for ${board.profile_name}: ${board.banked} banked`);
      bump();
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setSwitching(false);
    }
  };

  let content: ReactNode;
  switch (page) {
    case "inbox":
      content = <Inbox />;
      break;
    case "evidence":
      content = <Evidence focus={params.get("c")} />;
      break;
    case "metrics":
      content = <Metrics focus={params.get("item")} />;
      break;
    case "sources":
      content = <Sources />;
      break;
    case "settings":
      content = <Settings />;
      break;
    default:
      content = <OverviewPage data={ov} error={overview.error} retry={overview.reload} />;
  }

  return (
    <div className="flex h-full min-h-0">
      <aside className="hidden w-52 shrink-0 flex-col border-r border-zinc-200 bg-white md:flex dark:border-zinc-800 dark:bg-zinc-900">
        <a href="#/overview" className="flex items-center gap-2 px-4 py-4">
          <img src="./favicon.svg" alt="" className="size-7" />
          <span className="font-semibold tracking-tight">Lighthouse</span>
        </a>
        <nav className="flex flex-col gap-0.5 px-2" aria-label="Main">
          {NAV.map((n) => (
            <a
              key={n.id}
              href={`#/${n.id}`}
              aria-current={page === n.id ? "page" : undefined}
              className={cx(
                "flex items-center gap-2.5 rounded-md px-2.5 py-1.5 text-sm",
                page === n.id
                  ? "bg-zinc-100 font-medium text-zinc-900 dark:bg-zinc-800 dark:text-white"
                  : "text-zinc-600 hover:bg-zinc-50 dark:text-zinc-400 dark:hover:bg-zinc-800/60",
              )}
            >
              <span className="w-4 text-center text-zinc-400" aria-hidden>
                {n.icon}
              </span>
              {n.label}
              {n.id === "inbox" && !!ov?.inbox_pending && (
                <span className="ml-auto rounded-full bg-amber-500 px-1.5 text-[11px] font-semibold text-white tabular-nums">
                  {ov.inbox_pending}
                </span>
              )}
            </a>
          ))}
        </nav>
        <div className="mt-auto p-4 text-[11px] leading-snug text-zinc-400">
          Local only · 127.0.0.1
          <br />
          Every change is a file in your workspace.
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center gap-3 border-b border-zinc-200 bg-white/80 px-4 py-2 backdrop-blur md:px-6 dark:border-zinc-800 dark:bg-zinc-900/80">
          <nav className="flex gap-1 md:hidden" aria-label="Main (mobile)">
            {NAV.map((n) => (
              <a key={n.id} href={`#/${n.id}`} className={cx("rounded px-2 py-1 text-xs", page === n.id && "bg-zinc-100 dark:bg-zinc-800")}>
                {n.label}
              </a>
            ))}
          </nav>
          <div className="hidden min-w-0 truncate text-sm md:block">
            <span className="font-medium">{ov?.person.name || "Your case"}</span>
            {ov?.person.field && <span className="text-zinc-500 dark:text-zinc-400"> · {ov.person.field}</span>}
          </div>
          <div className="ml-auto flex items-center gap-2">
            {ov && (
              <div className="flex rounded-md border border-zinc-300 p-0.5 dark:border-zinc-700" role="group" aria-label="Criteria profile">
                {ov.profiles.map((p) => (
                  <button
                    key={p.id}
                    disabled={switching}
                    onClick={() => p.id !== ov.profile && switchProfile(p.id)}
                    aria-pressed={p.id === ov.profile}
                    title={p.name}
                    className={cx(
                      "rounded px-2.5 py-1 text-xs font-medium uppercase",
                      p.id === ov.profile ? "bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900" : "text-zinc-500 hover:text-zinc-900 dark:hover:text-white",
                    )}
                  >
                    {p.id === "o1a" ? "O-1A" : p.id === "eb1a" ? "EB-1A" : p.id}
                  </button>
                ))}
              </div>
            )}
            <Button variant="ghost" size="sm" onClick={toggle} aria-label="Toggle dark mode" title="Toggle theme">
              {dark ? "☀" : "☾"}
            </Button>
          </div>
        </header>

        <main className="min-h-0 flex-1 overflow-y-auto px-4 py-5 md:px-6">{content}</main>

        <footer className="border-t border-zinc-200 px-4 py-2 text-[11px] text-zinc-500 md:px-6 dark:border-zinc-800 dark:text-zinc-500">
          Lighthouse is not legal advice and is not affiliated with USCIS. Criteria profiles are community-maintained summaries of
          public regulations (8 CFR 214.2(o), 8 CFR 204.5(h)). Always confirm strategy with an immigration attorney.
        </footer>
      </div>
    </div>
  );
}
