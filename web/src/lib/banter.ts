/** Banter (ADR 0010 §4): the lines live in areao1/banter.json; this decides whether one may show. Never inside
 * a serious surface (marked data-serious: deadlines, countdowns, rule-check warnings, conflicts, refusals, errors,
 * status, RFEs, filing), never on a serious page, and at most one per screen (the first one in reading order). */
import lines from "../../../areao1/banter.json" with { type: "json" };

export type BanterKey = Exclude<keyof typeof lines, "_note">;

export function banterText(key: BanterKey, values: Record<string, string> = {}): string {
  return lines[key].text.replace(/\{(\w+)\}/g, (_, k: string) => values[k] ?? "");
}

/** Pages that are about status, deadlines, rule checks or refusals as a whole. */
export const SERIOUS_PAGES = new Set(["overview", "evidence", "calendar", "knowledge", "agent", "contacts", "merits"]); // contacts: follow-up dates

export function banterAllowed(s: { insideSerious: boolean; seriousOnScreen: boolean; seriousPage: boolean; earlierShown: number }): boolean {
  return !s.insideSerious && !s.seriousOnScreen && !s.seriousPage && s.earlierShown === 0;
}
