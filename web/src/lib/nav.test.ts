// Run with: node --test web/src/lib/   (Node strips the types; no browser needed)
import assert from "node:assert/strict";
import { test } from "node:test";
import { bindBackToClose, onboardingHash, parseOnboardingHash, samePlace, type Events, type HistoryLike } from "./nav.ts";

test("every onboarding step and question has its own URL", () => {
  assert.equal(onboardingHash({ step: "questions", question: "role" }), "#/welcome/questions/role");
  assert.equal(onboardingHash({ step: "lookups" }), "#/welcome/lookups");
  assert.equal(onboardingHash({ step: "lookups", question: "role" }), "#/welcome/lookups"); // only questions carry one
  for (const place of [{ step: "linkedin" }, { step: "questions", question: "when" }, { step: "chats" }, { step: "tour" }])
    assert.ok(samePlace(parseOnboardingHash(onboardingHash(place)), { question: null, ...place }));
  assert.equal(parseOnboardingHash("#/overview"), null);
  assert.equal(parseOnboardingHash("#/welcome/nowhere"), null);
});

/** A fake browser history with a back stack, firing popstate like the real one. */
function fakeBrowser() {
  const entries: unknown[] = [null];
  let index = 0;
  const listeners = new Set<() => void>();
  const history: HistoryLike & { length: number; forward(): void } = {
    get state() {
      return entries[index];
    },
    get length() {
      return entries.length;
    },
    pushState(data) {
      entries.splice(index + 1);
      entries.push(data);
      index += 1;
    },
    back() {
      if (index > 0) {
        index -= 1;
        listeners.forEach((fn) => fn());
      }
    },
    forward() {
      if (index < entries.length - 1) {
        index += 1;
        listeners.forEach((fn) => fn());
      }
    },
  };
  const events: Events = { addEventListener: (_t, fn) => listeners.add(fn), removeEventListener: (_t, fn) => listeners.delete(fn) };
  return { history, events, at: () => index, listeners };
}

test("Back closes an open dialog instead of leaving the page", () => {
  const b = fakeBrowser();
  let closed = 0;
  const cleanup = bindBackToClose(b.history, b.events, () => closed++);
  assert.equal(b.at(), 1);
  b.history.back(); // the browser's Back
  assert.equal(closed, 1);
  assert.equal(b.at(), 0); // still on the page's own entry
  cleanup(); // React unmounts the dialog; nothing more happens
  assert.equal(b.at(), 0);
  assert.equal(b.listeners.size, 0);
});

test("closing a dialog with its button removes its history entry", () => {
  const b = fakeBrowser();
  let closed = 0;
  const cleanup = bindBackToClose(b.history, b.events, () => closed++);
  cleanup(); // Esc or the close button
  assert.equal(b.at(), 0);
  assert.equal(closed, 0); // onClose isn't called again for a dialog already closing
  b.history.back(); // the next Back would leave the page as usual: nothing of ours is left
  assert.equal(closed, 0);
});

test("nested dialogs close innermost first", () => {
  const b = fakeBrowser();
  const closed: string[] = [];
  const outer = bindBackToClose(b.history, b.events, () => closed.push("outer"));
  const inner = bindBackToClose(b.history, b.events, () => closed.push("inner"));
  b.history.back();
  assert.deepEqual(closed, ["inner"]);
  inner();
  b.history.back();
  assert.deepEqual(closed, ["inner", "outer"]);
  outer();
  assert.equal(b.at(), 0);
});
