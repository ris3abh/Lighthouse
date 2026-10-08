import {
  BookOpen, Orbit,
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
  Users,
  X,
  type LucideIcon,
} from "lucide-react";
import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { api, type OnboardingView } from "./api";
import ChatPanel from "./components/ChatPanel";
import Finale from "./components/Finale";
import { onboardingHash, parseOnboardingHash, samePlace, type OnboardingPlace } from "./lib/nav";
import { isAskShortcut, panelSelector } from "./lib/reveal";
import Tour from "./components/Tour";
import { Button, cx, Segmented, ToastProvider, useToast } from "./components/ui";
import { useBackToClose, useLoad, useRoute, useTheme, type ThemeMode } from "./hooks";
import Agent from "./pages/Agent";
import Calendar from "./pages/Calendar";
import Evidence from "./pages/Evidence";
import Inbox from "./pages/Inbox";
import Knowledge from "./pages/Knowledge";
import Memory from "./pages/Memory";
import Letters from "./pages/Letters";
import Contacts from "./pages/Contacts";
import Metrics from "./pages/Metrics";
import OverviewPage from "./pages/Overview";
import Pipeline from "./pages/Pipeline";
import Settings from "./pages/Settings";
import Sources from "./pages/Sources";
import Welcome from "./pages/Welcome";
import { PRODUCT } from "./names";
import Banter, { banterOk } from "./components/Banter";
import { banterText, SERIOUS_PAGES } from "./lib/banter";
import NotFound from "./pages/NotFound";

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
  { id: "contacts", label: "Contacts", icon: Users },
  { id: "calendar", label: "Calendar", icon: CalendarDays },
  { id: "agent", label: "Agent", icon: Sparkles },
  { id: "memory", label: "Memory", icon: Orbit },
  { id: "knowledge", label: "Knowledge", icon: BookOpen },
  { id: "sources", label: "Sources", icon: Cable },
  { id: "settings", label: "Settings", icon: SettingsIcon },
];

const THEMES: { value: ThemeMode; label: ReactNode; title: string }[] = [
  { value: "system", label: <Monitor aria-label="System" />, title: "Theme: follow the system" },
  { value: "light", label: <Sun aria-label="Light" />, title: "Theme: light" },
  { value: "dark", label: <Moon aria-label="Dark" />, title: "Theme: dark" },
];

/** Visitor mode (O-1A) / Resident mode (EB-1A): control labels that keep the legal names (ADR 0010 §4). */
function profileLabel(id: string): ReactNode {
  const short = id === "o1a" ? "O-1A" : id === "eb1a" ? "EB-1A" : id;
  const mode = id === "o1a" ? "Visitor mode" : id === "eb1a" ? "Resident mode" : "";
  return mode ? (
    <>
      <span className="hidden xl:inline">
        {mode} ({short})
      </span>
      <span className="xl:hidden">{short}</span>
    </>
  ) : (
    short
  );
}

function placeOf(v: OnboardingView): OnboardingPlace {
  return { step: v.state.step, question: v.state.step === "questions" ? (v.question?.id ?? null) : null };
}

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
  const [chatDocked, setChatDocked] = useState(() => {
    try {
      return localStorage.getItem("lh-chat-dock") === "1";
    } catch {
      return false;
    }
  });
  useEffect(() => setMenuOpen(false), [page]);
  useBackToClose(menuOpen, () => setMenuOpen(false));
  const [onboarding, setOnboarding] = useState<OnboardingView | null>(null);
  // Onboarding is a conversation over the dashboard (C15): the dashboard shows blurred behind it, and Ask waits.
  const welcoming = !!onboarding?.needed && onboarding.state.step !== "tour";
  const chatModal = chatOpen && !chatDocked && !welcoming;
  const [finished, setFinished] = useState(false); // the closing moment is showing
  const [docked, setDocked] = useState(false); // the Ask button just landed in the header
  useEffect(() => {
    if (!docked) return;
    const t = setTimeout(() => setDocked(false), 2600);
    return () => clearTimeout(t);
  }, [docked]);
  useEffect(() => {
    api
      .onboarding()
      .then(setOnboarding)
      .catch(() => setOnboarding(null));
  }, [version]);
  // Onboarding has a URL per step and question (#/welcome/questions/role), so back / forward move through it.
  useEffect(() => {
    if (!onboarding) return;
    const here = parseOnboardingHash(window.location.hash);
    if (!onboarding.needed) {
      if (here) window.history.replaceState(null, "", "#/overview");
      return;
    }
    if (onboarding.state.step === "tour") return; // the tour keeps its own URLs
    const want = placeOf(onboarding);
    if (samePlace(here, want)) return;
    if (here) window.location.hash = onboardingHash(want);
    else window.history.replaceState(window.history.state, "", onboardingHash(want)); // first load: no extra entry
  }, [onboarding]);
  const onboardingNow = useRef(onboarding);
  onboardingNow.current = onboarding;
  useEffect(() => {
    const onHash = () => {
      const place = parseOnboardingHash(window.location.hash);
      const current = onboardingNow.current;
      if (!place || !current?.needed || samePlace(place, placeOf(current))) return;
      api.onboardingGoto(place.step, place.question).then(setOnboarding, () => {
        window.history.replaceState(window.history.state, "", onboardingHash(placeOf(current))); // not reached yet
      });
    };
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
  const toggleChat = (open: boolean) => {
    setChatOpen(open);
    try {
      localStorage.setItem("lh-chat-open", open ? "1" : "0");
    } catch {
      /* storage unavailable */
    }
  };
  const pinChat = (docked: boolean) => {
    setChatDocked(docked);
    try {
      localStorage.setItem("lh-chat-dock", docked ? "1" : "0");
    } catch {
      /* storage unavailable */
    }
  };
  useBackToClose(chatModal, () => toggleChat(false));
  const chatOpenNow = useRef(chatOpen);
  chatOpenNow.current = chatOpen;
  useEffect(() => {
    // Cmd/Ctrl+K opens (or closes) the chat; Esc closes it.
    const onKey = (e: KeyboardEvent) => {
      if (isAskShortcut(e)) {
        if (onboardingNow.current?.needed && onboardingNow.current.state.step !== "tour") return;
        e.preventDefault();
        toggleChat(!chatOpenNow.current);
      } else if (e.key === "Escape" && chatOpenNow.current && !document.querySelector('[role="dialog"]:not([aria-label^="Chat"])')) {
        toggleChat(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  useEffect(() => {
    // A tool call changed something: those panels refresh, and while the chat is open over them (everything
    // behind stays evenly blurred) a crisp outline and label on top of the blur show where. Docked, the panel
    // itself flashes.
    const onChanged = (e: Event) => {
      const panels = (e as CustomEvent<string[]>).detail;
      bump();
      const found = [...document.querySelectorAll<HTMLElement>(panelSelector(panels))];
      const outer = found.filter((el) => !found.some((o) => o !== el && o.contains(el))); // one mark per area
      for (const el of outer) {
        if (!document.querySelector(".lh-chat-modal")) {
          el.classList.remove("lh-reveal");
          void el.offsetWidth; // restart the flash
          el.classList.add("lh-reveal");
          window.setTimeout(() => el.classList.remove("lh-reveal"), 1800);
          continue;
        }
        const r = el.getBoundingClientRect();
        if (r.bottom < 0 || r.top > window.innerHeight || !r.width) continue;
        const mark = document.createElement("div");
        mark.className = "lh-mark";
        mark.setAttribute("aria-hidden", "true");
        Object.assign(mark.style, { left: `${r.left}px`, top: `${r.top}px`, width: `${r.width}px`, height: `${r.height}px` });
        const label = document.createElement("span");
        label.textContent = `Changed: ${(el.dataset.panel ?? "").split(" ").filter((p) => panels.includes(p)).join(", ")}`;
        const chat = document.querySelector('aside[aria-label^="Chat"]')?.getBoundingClientRect();
        if (chat && r.right > chat.right && r.left > chat.left) Object.assign(label.style, { left: "auto", right: "-3px" }); // the side you can see
        mark.appendChild(label);
        document.body.appendChild(mark);
        window.setTimeout(() => mark.remove(), 1800);
      }
    };
    window.addEventListener("lh:changed", onChanged);
    return () => window.removeEventListener("lh:changed", onChanged);
  }, [bump]);
  const ov = overview.data;

  const switchProfile = async (id: string) => {
    if (id === ov?.profile) return;
    setSwitching(true);
    try {
      const board = await api.setProfile(id);
      const plain = `Re-scored for ${board.profile_name}: ${board.banked} banked`;
      let first = false;
      try {
        first = id === "eb1a" && !localStorage.getItem("lh-eb1a-hello");
      } catch {
        /* storage unavailable */
      }
      if (first && banterOk()) {
        toast(`${banterText("eb1a_first_switch")} ${plain}.`);
        try {
          localStorage.setItem("lh-eb1a-hello", "1");
        } catch {
          /* storage unavailable */
        }
      } else toast(plain);
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
    case "contacts":
      content = <Contacts />;
      break;
    case "agent":
      content = <Agent focus={params.get("run")} />;
      break;
    case "knowledge":
      content = <Knowledge />;
      break;
    case "memory":
      content = <Memory />;
      break;
    case "calendar":
      content = <Calendar />;
      break;
    case "settings":
      content = <Settings />;
      break;
    case "overview":
    case "welcome":
    case "":
      content = <OverviewPage data={ov} error={overview.error} retry={overview.reload} />;
      break;
    default:
      content = <NotFound />;
  }

  const touring = !!onboarding?.needed && onboarding.state.step === "tour";
  const endTour = async (skipped: boolean) => {
    try {
      setOnboarding(await api.onboardingStep(skipped ? "tour_skip" : "tour_done"));
      setFinished(true);
      window.location.hash = "#/overview";
      bump();
    } catch (e) {
      toast((e as Error).message, "error");
    }
  };

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
      options={[...ov.profiles]
        .sort((a, b) => (a.id === "o1a" ? -1 : b.id === "o1a" ? 1 : 0)) // Visitor before Resident
        .map((p) => ({ value: p.id, label: profileLabel(p.id), title: p.name }))}
    />
  );

  return (
    <div className={cx("lh-shell flex h-full min-h-0", (chatModal || welcoming) && "lh-chat-modal")}>
      <aside inert={welcoming} className="lh-nav hidden w-60 shrink-0 flex-col border-r border-frame bg-surface lg:flex">
        <a href="#/overview" className="flex h-16 items-center gap-3 border-b border-frame px-5">
          <img src="./favicon.svg" alt="" className="size-6" />
          <span className="display text-[28px] tracking-tight uppercase">{PRODUCT}</span>
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
            <span className="display text-2xl uppercase">{PRODUCT}</span>
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

      <div inert={welcoming} className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center gap-3 border-b border-frame bg-surface px-4 lg:h-16 lg:px-8">
          <Button variant="ghost" size="sm" className="px-2 lg:hidden" onClick={() => setMenuOpen(true)} aria-label="Open menu">
            <Menu />
          </Button>
          <a href="#/overview" className="display text-2xl uppercase lg:hidden">
            {PRODUCT}
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
            <Button
              variant={chatOpen ? "primary" : "secondary"}
              size="sm"
              onClick={() => {
                setDocked(false);
                toggleChat(!chatOpen);
              }}
              aria-pressed={chatOpen}
              title="Ask the agent (Cmd+K or Ctrl+K)"
              data-ask-anchor
              className={cx("transition-[outline-offset] duration-300", docked && "outline-2 outline-offset-4 outline-ink")}
            >
              <Sparkles strokeWidth={1.5} />
              Ask
            </Button>
          </div>
        </header>

        <main className="min-h-0 flex-1 overflow-x-hidden overflow-y-auto">
          <div className="lh-content @container mx-auto w-full max-w-[1440px] px-4 py-8 md:px-10 md:py-12" data-serious={SERIOUS_PAGES.has(page) || undefined}>
            {content}
          </div>
          <footer className="mx-auto max-w-[1440px] border-t border-line px-4 py-5 font-mono text-[10.5px] leading-relaxed text-muted md:px-10">
            {PRODUCT} is not legal advice and is not affiliated with USCIS. Criteria profiles are community-maintained summaries of public
            regulations (8 CFR 214.2(o), 8 CFR 204.5(h)). Always confirm strategy with an immigration attorney.
            <Banter id="disclaimer" as="span" className="ml-1" />
          </footer>
        </main>
      </div>
      {welcoming && onboarding && (
        <>
          <div className="lh-scrim fixed inset-0 z-40 bg-paper/35" aria-hidden />
          <Welcome
            view={onboarding}
            onChange={(v) => {
              setOnboarding(v);
              if (!v.needed) setFinished(v.state.status === "done");
              bump();
            }}
          />
        </>
      )}
      {chatOpen && chatDocked && !welcoming && <ChatPanel page={page} docked onPin={pinChat} onClose={() => toggleChat(false)} />}
      {chatModal && (
        <>
          <div className="lh-scrim fixed inset-0 z-40 bg-paper/35" aria-hidden onMouseDown={() => toggleChat(false)} />
          <ChatPanel page={page} onPin={pinChat} onClose={() => toggleChat(false)} />
        </>
      )}
      {touring && <Tour overview={ov} onDone={endTour} onBack={() => api.onboardingGoto("chats").then(setOnboarding, (e) => toast((e as Error).message, "error"))} />}
      {finished && (
        <Finale
          name={(ov?.person.name ?? "").split(" ")[0]}
          todos={(ov?.tasks ?? []).filter((t) => t.kind === "todo").length}
          onDone={() => {
            setFinished(false);
            setDocked(true);
          }}
        />
      )}
    </div>
  );
}
