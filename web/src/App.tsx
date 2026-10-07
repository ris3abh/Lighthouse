import {
  BookOpen,
  Cable,
  CalendarDays,
  ChartLine,
  FileStack,
  Gauge,
  Inbox as InboxIcon,
  Kanban,
  Mail,
  Menu,
  Monitor,
  Moon,
  Settings as SettingsIcon,
  Sparkles,
  Sun,
  X,
  type LucideIcon,
} from "lucide-react";
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api } from "./api";
import ChatPanel from "./components/ChatPanel";
import { Button, cx, Segmented, ToastProvider, useToast } from "./components/ui";
import { useLoad, useRoute, useTheme, type ThemeMode } from "./hooks";
import Agent from "./pages/Agent";
import Calendar from "./pages/Calendar";
import Evidence from "./pages/Evidence";
import Inbox from "./pages/Inbox";
import Knowledge from "./pages/Knowledge";
import Letters from "./pages/Letters";
import Metrics from "./pages/Metrics";
import OverviewPage from "./pages/Overview";
import Pipeline from "./pages/Pipeline";
import Settings from "./pages/Settings";
import Sources from "./pages/Sources";

/** Bumping `version` makes every page and the shell re-fetch after a write. */
const RefreshCtx = createContext<{ version: number; bump: () => void }>({ version: 0, bump: () => {} });
export const useRefresh = () => useContext(RefreshCtx);

const NAV: { id: string; label: string; icon: LucideIcon }[] = [
  { id: "overview", label: "Overview", icon: Gauge },
  { id: "inbox", label: "Inbox", icon: InboxIcon },
  { id: "evidence", label: "Evidence", icon: FileStack },
  { id: "metrics", label: "Metrics", icon: ChartLine },
  { id: "pipeline", label: "Pipeline", icon: Kanban },
  { id: "letters", label: "Letters", icon: Mail },
  { id: "calendar", label: "Calendar", icon: CalendarDays },
  { id: "agent", label: "Agent", icon: Sparkles },
  { id: "knowledge", label: "Knowledge", icon: BookOpen },
  { id: "sources", label: "Sources", icon: Cable },
  { id: "settings", label: "Settings", icon: SettingsIcon },
];

const THEMES: { value: ThemeMode; label: ReactNode; title: string }[] = [
  { value: "system", label: <Monitor aria-label="System" />, title: "Theme: follow the system" },
  { value: "light", label: <Sun aria-label="Light" />, title: "Theme: light" },
  { value: "dark", label: <Moon aria-label="Dark" />, title: "Theme: dark" },
];

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
  const { mode, setMode } = useTheme();
  const toast = useToast();
  const overview = useLoad(() => api.overview(), [version]);
  const [switching, setSwitching] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [chatOpen, setChatOpen] = useState(() => {
    try {
      return localStorage.getItem("lh-chat-open") === "1";
    } catch {
      return false;
    }
  });
  useEffect(() => setMenuOpen(false), [page]);
  const toggleChat = (open: boolean) => {
    setChatOpen(open);
    try {
      localStorage.setItem("lh-chat-open", open ? "1" : "0");
    } catch {
      /* storage unavailable */
    }
  };
  const ov = overview.data;

  const switchProfile = async (id: string) => {
    if (id === ov?.profile) return;
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
    case "pipeline":
      content = <Pipeline />;
      break;
    case "letters":
      content = <Letters />;
      break;
    case "agent":
      content = <Agent focus={params.get("run")} />;
      break;
    case "knowledge":
      content = <Knowledge />;
      break;
    case "calendar":
      content = <Calendar />;
      break;
    case "settings":
      content = <Settings />;
      break;
    default:
      content = <OverviewPage data={ov} error={overview.error} retry={overview.reload} />;
  }

  const nav = (
    <nav className="flex flex-col" aria-label="Main">
      {NAV.map((n) => {
        const Icon = n.icon;
        const active = page === n.id;
        return (
          <a
            key={n.id}
            href={`#/${n.id}`}
            aria-current={active ? "page" : undefined}
            className={cx(
              "group flex h-11 items-center gap-3 border-b border-line px-5 text-[15px] transition-colors duration-150",
              active ? "bg-ink text-on-ink" : "text-ink-2 hover:bg-sunken hover:text-ink",
            )}
          >
            <Icon className="size-[18px] shrink-0" strokeWidth={1.5} aria-hidden />
            {n.label}
            {n.id === "inbox" && !!ov?.inbox_pending && (
              <span className={cx("num ml-auto text-xs", active ? "text-on-ink" : "text-ink")}>{ov.inbox_pending}</span>
            )}
          </a>
        );
      })}
    </nav>
  );

  const profileSwitch = ov && ov.profiles.length > 1 && (
    <Segmented
      label="Criteria profile"
      size="sm"
      value={ov.profile}
      onChange={(id) => !switching && switchProfile(id)}
      options={ov.profiles.map((p) => ({ value: p.id, label: p.id === "o1a" ? "O-1A" : p.id === "eb1a" ? "EB-1A" : p.id, title: p.name }))}
    />
  );

  return (
    <div className="flex h-full min-h-0">
      <aside className="hidden w-60 shrink-0 flex-col border-r border-frame bg-surface lg:flex">
        <a href="#/overview" className="flex h-16 items-center gap-3 border-b border-frame px-5">
          <img src="./favicon.svg" alt="" className="size-6" />
          <span className="display text-[28px] tracking-tight uppercase">Lighthouse</span>
        </a>
        {nav}
        <div className="mt-auto border-t border-line p-5 font-mono text-[10.5px] leading-relaxed tracking-[0.06em] text-muted uppercase">
          Local only · 127.0.0.1
          <br />
          Every change is a file in your workspace
        </div>
      </aside>

      {menuOpen && (
        <div className="fixed inset-0 z-50 flex flex-col overflow-y-auto bg-surface lg:hidden" role="dialog" aria-label="Menu">
          <div className="flex h-14 items-center justify-between border-b border-frame px-4">
            <span className="display text-2xl uppercase">Lighthouse</span>
            <Button variant="ghost" size="sm" onClick={() => setMenuOpen(false)} aria-label="Close menu" className="px-2">
              <X />
            </Button>
          </div>
          {nav}
          <div className="flex flex-wrap items-center gap-3 p-4">
            {profileSwitch}
            <Segmented label="Theme" size="sm" value={mode} onChange={setMode} options={THEMES} />
          </div>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center gap-3 border-b border-frame bg-surface px-4 lg:h-16 lg:px-8">
          <Button variant="ghost" size="sm" className="px-2 lg:hidden" onClick={() => setMenuOpen(true)} aria-label="Open menu">
            <Menu />
          </Button>
          <a href="#/overview" className="display text-2xl uppercase lg:hidden">
            Lighthouse
          </a>
          <div className="hidden min-w-0 items-baseline gap-3 truncate lg:flex">
            <span className="text-[15px] font-semibold">{ov?.person.name || "Your case"}</span>
            {ov?.person.field && <span className={cx("truncate font-mono text-xs text-muted", chatOpen && "hidden 2xl:inline")}>{ov.person.field}</span>}
          </div>
          <div className="ml-auto flex items-center gap-2 md:gap-3">
            <div className="hidden md:block">{profileSwitch}</div>
            <div className="hidden sm:block">
              <Segmented label="Theme" size="sm" value={mode} onChange={setMode} options={THEMES} />
            </div>
            <Button variant={chatOpen ? "primary" : "secondary"} size="sm" onClick={() => toggleChat(!chatOpen)} aria-pressed={chatOpen} title="Chat with the agent">
              <Sparkles strokeWidth={1.5} />
              Ask
            </Button>
          </div>
        </header>

        <main className="min-h-0 flex-1 overflow-x-hidden overflow-y-auto">
          <div className="@container mx-auto w-full max-w-[1440px] px-4 py-8 md:px-10 md:py-12">{content}</div>
          <footer className="mx-auto max-w-[1440px] border-t border-line px-4 py-5 font-mono text-[10.5px] leading-relaxed text-muted md:px-10">
            Lighthouse is not legal advice and is not affiliated with USCIS. Criteria profiles are community-maintained summaries of public
            regulations (8 CFR 214.2(o), 8 CFR 204.5(h)). Always confirm strategy with an immigration attorney.
          </footer>
        </main>
      </div>
      {chatOpen && <ChatPanel page={page} onClose={() => toggleChat(false)} />}
    </div>
  );
}
