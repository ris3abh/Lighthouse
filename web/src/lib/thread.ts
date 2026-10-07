/** Onboarding as one conversation (C15): every step so far, in order, as messages in a single thread. Steps the
 * person has passed stay above (so the chat scrolls up as it grows); the current step's message carries its
 * widget (the PDF drop, the lookups, the chat import). Pure, so it's tested without a browser. */

import type { OnboardingView } from "../api";
import { PRODUCT } from "../names.ts";

export type Widget = "linkedin" | "ai" | "lookups" | "chats" | "mail";
export type Msg = { key: string; who: "areao1" | "you"; text: string; quote?: string; widget?: Widget };

const ORDER = ["linkedin", "questions", "ai", "lookups", "chats", "mail", "tour"];

export const LINKEDIN_ASK =
  `Hi, I'm ${PRODUCT}. I'll help you build your case, one piece at a time. Let's start with your LinkedIn profile as a PDF ` +
  "(on LinkedIn: Profile > More > Save to PDF). I read it on this computer and remove emails and phone numbers first.";
export const AI_ASK =
  "One more thing before I look anything up: connect your AI. Chat and web lookups need it; everything else works " +
  "without one. Paste an Anthropic API key (console.anthropic.com > API keys); I check it with a free request, and " +
  "it stays in this computer's keychain, never in your workspace.";
const AI_REPLY = { login: "", key: "Use my API key.", skipped: "Later.", pending: "" };
export const LOOKUPS_ASK =
  "Want me to look these up? Only what you confirmed. Anything I find goes to your Inbox for you to check first, and finds " +
  "that may belong to someone with the same name are marked. Web searches use your AI, usually a few cents each.";
export const CHATS_ASK =
  "Quick story: the person who built me kept his context spread across Claude and ChatGPT. If you're like him, drop those " +
  "exports here and I'll pick up where they left off. Choose the longest range you can when you export: I sort it on this " +
  "computer first, show you what looks related to your case and why, and bring in only what you tick.";
export const MAIL_ASK =
  "Last one, and optional: connect Gmail so I can keep up with your letter writers and organizers and draft follow-ups. " +
  "All it takes is your address and an app password. I only read: case mail (invites, judging, reviews, letters, press, " +
  "awards) sorted on Contacts > Mail, keeping who, when and the subject, never the rest. I send nothing until you press Approve & send.";
const MAIL_REPLY = { pending: "", connected: "Connected my Gmail.", skipped: "Later." };

/** The thread for where onboarding is now. Keys are stable across updates (who, text and which repeat), so an
 * answered question keeps its place and a message is never typed twice. */
export function buildThread(view: OnboardingView): Msg[] {
  const s = view.state;
  const at = Math.max(0, ORDER.indexOf(s.step));
  const raw: Omit<Msg, "key">[] = [{ who: "areao1", text: LINKEDIN_ASK, widget: "linkedin" }];
  if (at >= 1) {
    raw.push({ who: "you", text: s.source ? `Here's my profile: ${s.source.filename}` : "I'll skip the PDF for now." });
    raw.push(...(s.transcript ?? []));
    if (at === 1 && view.question) {
      const q = view.question;
      raw.push({ who: "areao1", text: q.text, quote: q.quote && !q.text.includes(q.quote) ? q.quote : undefined });
    }
  }
  if (at >= 2) {
    raw.push({ who: "areao1", text: AI_ASK, widget: "ai" });
    if (at > 2 && AI_REPLY[s.ai ?? "pending"]) raw.push({ who: "you", text: AI_REPLY[s.ai] });
  }
  if (at >= 3 && s.lookups.length) {
    raw.push({ who: "areao1", text: LOOKUPS_ASK, widget: "lookups" });
    if (at > 3) raw.push({ who: "you", text: "That's all for now." });
  }
  if (at >= 4) raw.push({ who: "areao1", text: CHATS_ASK, widget: "chats" });
  if (at >= 5) {
    raw.push({ who: "areao1", text: MAIL_ASK, widget: "mail" });
    if (at > 5 && MAIL_REPLY[s.mail ?? "pending"]) raw.push({ who: "you", text: MAIL_REPLY[s.mail ?? "pending"] });
  }
  const seen = new Map<string, number>();
  return raw.map((m) => {
    const base = `${m.who}:${m.text}`;
    const n = seen.get(base) ?? 0;
    seen.set(base, n + 1);
    return { ...m, key: `${base}#${n}` };
  });
}

/** Messages already on screen when the thread first opens show at once; only the last one types, if it's ours
 * (so a fresh start or a reload greets you, and a long history doesn't replay). */
export function initiallySeen(msgs: Msg[]): Set<string> {
  const seen = new Set(msgs.map((m) => m.key));
  const last = msgs.at(-1);
  if (last?.who === "areao1") seen.delete(last.key);
  return seen;
}

/** Index of the message typing now: the first of ours not yet shown. Everything after it waits. -1 when none. */
export function typingIndex(msgs: Msg[], seen: Set<string>): number {
  return msgs.findIndex((m) => m.who === "areao1" && !seen.has(m.key));
}
