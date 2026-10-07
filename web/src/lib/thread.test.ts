// Run with: node --test web/src/lib/   (Node strips the types; no browser needed)
import assert from "node:assert/strict";
import { test } from "node:test";
import type { OnboardingView } from "../api";
import { buildThread, CHATS_ASK, initiallySeen, LINKEDIN_ASK, LOOKUPS_ASK, typingIndex } from "./thread.ts";

function view(step: OnboardingView["state"]["step"], extra: Partial<OnboardingView["state"]> = {}, question: OnboardingView["question"] = null) {
  return {
    needed: true,
    state: { status: "in_progress", step, source: { filename: "profile.pdf", chars: 900, redactions: 1, parser: "rules" }, lookups: [],
      transcript: [], target_profile: null, tour: "pending", chats: "pending", ...extra },
    question,
    nav: { back: null, reached: step, steps: [] },
    panel: [],
    person: { name: "", field: "", location: "" },
  } as OnboardingView;
}
const q = (id: string, text: string) => ({ id, text, keys: [id], kind: "confirm" as const, values: {}, options: [], quote: "" });
const opening = { who: "lighthouse" as const, text: "Nice to meet you, Maya!" };

test("the thread starts with the PDF ask and keeps every earlier step above the current one", () => {
  assert.deepEqual(buildThread(view("linkedin")).map((m) => [m.who, m.text, m.widget]), [["lighthouse", LINKEDIN_ASK, "linkedin"]]);
  const chats = buildThread(view("chats", { transcript: [opening], lookups: [{ id: "a", kind: "papers", prompt: "", targets: [], status: "declined", result: "" }] }));
  assert.deepEqual(chats.map((m) => m.text), [LINKEDIN_ASK, "Here's my profile: profile.pdf", opening.text, LOOKUPS_ASK, "That's all for now.", CHATS_ASK]);
  // no lookups offered: that step leaves nothing in the thread
  assert.ok(!buildThread(view("chats", { transcript: [opening] })).some((m) => m.text === LOOKUPS_ASK));
  // skipped the PDF
  assert.equal(buildThread(view("questions", { source: null })).at(1)?.text, "I'll skip the PDF for now.");
});

test("an answered question keeps its key, so it isn't typed again", () => {
  const asking = buildThread(view("questions", { transcript: [opening] }, q("name", "Is your name Maya Chen?")));
  const answered = buildThread(view("questions", {
    transcript: [opening, { who: "lighthouse", text: "Is your name Maya Chen?" }, { who: "you", text: "Yes" }],
  }, q("role", "You're a staff engineer?")));
  const key = asking.at(-1)!.key;
  assert.ok(answered.some((m) => m.key === key));
  const seen = new Set(asking.map((m) => m.key));
  assert.equal(answered[typingIndex(answered, seen)].text, "You're a staff engineer?"); // only the new question types
});

test("repeated lines get their own keys", () => {
  const t = buildThread(view("questions", { transcript: [opening, { who: "you", text: "Yes" }, { who: "you", text: "Yes" }] }));
  assert.equal(new Set(t.map((m) => m.key)).size, t.length);
});

test("on opening, only our last message types; a reload doesn't replay the history", () => {
  const t = buildThread(view("questions", { transcript: [opening] }, q("name", "Is your name Maya Chen?")));
  const seen = initiallySeen(t);
  assert.equal(typingIndex(t, seen), t.length - 1);
  const mine = buildThread(view("chats", { transcript: [opening, { who: "you", text: "Yes" }] })).slice(0, -1);
  assert.equal(typingIndex(mine, initiallySeen(mine)), -1); // last message is the person's: nothing types
});
