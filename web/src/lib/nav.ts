/** Back and forth (C11): one URL per onboarding step and question, and the browser's Back closing dialogs
 * before it leaves a page. Pure functions over an injectable history, so they're tested without a browser. */

export type OnboardingPlace = { step: string; question?: string | null };

const STEPS = new Set(["linkedin", "questions", "ai", "lookups", "chats", "mail", "tour"]);

/** "#/welcome/questions/role" for { step: "questions", question: "role" }. */
export function onboardingHash(place: OnboardingPlace): string {
  return `#/welcome/${place.step}${place.step === "questions" && place.question ? `/${encodeURIComponent(place.question)}` : ""}`;
}

/** The place a hash points at, or null when it isn't an onboarding hash. */
export function parseOnboardingHash(hash: string): OnboardingPlace | null {
  const m = /^#\/welcome\/([a-z]+)(?:\/([^/?#]+))?\/?$/.exec(hash);
  if (!m || !STEPS.has(m[1])) return null;
  return { step: m[1], question: m[1] === "questions" && m[2] ? decodeURIComponent(m[2]) : null };
}

export function samePlace(a: OnboardingPlace | null, b: OnboardingPlace | null): boolean {
  return !!a && !!b && a.step === b.step && (a.question ?? null) === (b.question ?? null);
}

export interface HistoryLike {
  readonly state: unknown;
  pushState(data: unknown, unused: string, url?: string | null): void;
  back(): void;
}
export interface Events {
  addEventListener(type: "popstate", fn: () => void): void;
  removeEventListener(type: "popstate", fn: () => void): void;
}

let counter = 0;

/** While a dialog is open it owns one history entry: the browser's Back closes it (and stays on the page);
 * closing it any other way removes that entry again, so Back never "re-closes" or leaves unexpectedly.
 * Returns the cleanup to call when the dialog closes. Nested dialogs close innermost first. */
export function bindBackToClose(history: HistoryLike, events: Events, onClose: () => void): () => void {
  const id = `d${++counter}`;
  const base = history.state && typeof history.state === "object" ? (history.state as Record<string, unknown>) : {};
  history.pushState({ ...base, lhDialog: id, lhDepth: depth(history.state) + 1 }, "");
  let poppedHere = false;
  const onPop = () => {
    // Our entry is gone when the current entry is shallower than ours.
    if (!poppedHere && depth(history.state) < myDepth) {
      poppedHere = true;
      onClose();
    }
  };
  const myDepth = depth(history.state);
  events.addEventListener("popstate", onPop);
  return () => {
    events.removeEventListener("popstate", onPop);
    if (!poppedHere && (history.state as Record<string, unknown> | null)?.lhDialog === id) history.back();
  };
}

function depth(state: unknown): number {
  const d = state && typeof state === "object" ? (state as Record<string, unknown>).lhDepth : 0;
  return typeof d === "number" ? d : 0;
}
