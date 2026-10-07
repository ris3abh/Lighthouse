/** Chip input logic (C12), kept pure so it's tested without a browser: turning typed or pasted text into
 * chips, and what each key does. */

/** "a; b" or a pasted list (one per line, bullets or numbers allowed) -> ["a", "b"]. Commas stay: titles have them. */
export function splitChips(text: string): string[] {
  return text
    .split(/[;\n\r]+/)
    .map((s) => s.replace(/^\s*(?:[-*•·]|\d+[.)])\s+/, "").trim())
    .filter(Boolean);
}

export type ChipState = { chips: string[]; draft: string; editing: number | null };

export type ChipKey = { key: string; shift?: boolean };

/** What a key press in the text field does. Returns the new state and whether the key was handled. */
export function onFieldKey(s: ChipState, k: ChipKey): { state: ChipState; handled: boolean } {
  if (k.key === "Enter" || k.key === ";") {
    if (!s.draft.trim()) return { state: s, handled: k.key === ";" };
    return { state: commit(s), handled: true };
  }
  if (k.key === "Backspace" && s.draft === "" && s.chips.length && s.editing === null)
    return { state: { ...s, chips: s.chips.slice(0, -1) }, handled: true };
  return { state: s, handled: false };
}

/** The draft becomes a chip (or replaces the one being edited); the field is empty again. */
export function commit(s: ChipState): ChipState {
  const added = splitChips(s.draft);
  if (s.editing !== null) {
    const chips = [...s.chips];
    chips.splice(s.editing, 1, ...added);
    return { chips, draft: "", editing: null };
  }
  return { chips: [...s.chips, ...added], draft: "", editing: null };
}

/** Pasting text with separators adds every item as a chip at once. */
export function onPaste(s: ChipState, text: string): { state: ChipState; handled: boolean } {
  if (!/[;\n]/.test(text)) return { state: s, handled: false };
  return { state: commit({ ...s, draft: s.draft + text }), handled: true };
}

/** Click (or Enter on) a chip: its text goes back into the field for editing. */
export function edit(s: ChipState, index: number): ChipState {
  const base = s.draft.trim() ? commit(s) : s;
  return { ...base, draft: base.chips[index] ?? "", editing: index };
}

export function remove(s: ChipState, index: number): ChipState {
  return { ...s, chips: s.chips.filter((_, i) => i !== index), editing: null };
}

/** Everything as a list, including a draft not yet turned into a chip (so Save never drops it). */
export function finalList(s: ChipState): string[] {
  return s.draft.trim() ? commit(s).chips : s.chips;
}
