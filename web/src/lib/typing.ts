/** How a new agent message arrives in onboarding (C15): a short beat of typing dots, then the words appear,
 * whole words at a time, faster for long messages so none takes more than MAX_TYPE_MS. */

export const DOTS_MS = 450;
export const MS_PER_CHAR = 14;
export const MAX_TYPE_MS = 1600;

export function typeDuration(text: string): number {
  return Math.min(MAX_TYPE_MS, text.length * MS_PER_CHAR);
}

/** The part of `text` showing `elapsed` ms after the words started, cut at a word boundary. */
export function typedPrefix(text: string, elapsed: number): string {
  const total = typeDuration(text);
  if (elapsed >= total) return text;
  if (elapsed <= 0) return "";
  const n = Math.floor((text.length * elapsed) / total);
  const space = text.indexOf(" ", n);
  return space < 0 ? text : text.slice(0, space);
}
