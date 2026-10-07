/** Chat as a modal (C13): which dashboard panels a tool call changed, and the open-chat shortcut. Pure, so it's
 * tested without a browser. Panels carry data-panel="inbox deadlines" naming what they show. */

const PANELS: [prefix: string, panels: string[]][] = [
  ["data/inbox.json", ["inbox"]],
  ["data/deadlines.json", ["deadlines"]],
  ["data/pipeline.json", ["pipeline"]],
  ["data/letters.json", ["letters"]],
  ["data/metrics.csv", ["metrics"]],
  ["data/briefing.json", ["briefing"]],
  ["data/exhibits.json", ["scoreboard"]],
];

/** The panels to un-blur and highlight after a tool call. Reads change nothing, so they highlight nothing. */
export function panelsFor(touches: string[] | undefined, readOnly: boolean | undefined): string[] {
  if (readOnly !== false || !touches?.length) return [];
  const out = new Set<string>();
  for (const t of touches) for (const [prefix, panels] of PANELS) if (t.startsWith(prefix)) panels.forEach((p) => out.add(p));
  return [...out];
}

/** Cmd+K on a Mac, Ctrl+K elsewhere; never while typing with other modifiers. */
export function isAskShortcut(e: { key: string; metaKey: boolean; ctrlKey: boolean; altKey: boolean; shiftKey: boolean }): boolean {
  return e.key.toLowerCase() === "k" && (e.metaKey || e.ctrlKey) && !e.altKey && !e.shiftKey;
}

/** The CSS selector for panels showing any of ``panels``. */
export function panelSelector(panels: string[]): string {
  return panels.map((p) => `[data-panel~="${p.replace(/[^a-z-]/g, "")}"]`).join(", ");
}
