import assert from "node:assert/strict";
import { test } from "node:test";
import { commit, edit, finalList, onFieldKey, onPaste, remove, splitChips, type ChipState } from "./chips.ts";

const s0: ChipState = { chips: ["Award A"], draft: "", editing: null };

test("semicolons, new lines and pasted lists become chips; commas stay inside titles", () => {
  assert.deepEqual(splitChips("Best Paper, ICML 2025; Dean's List"), ["Best Paper, ICML 2025", "Dean's List"]);
  assert.deepEqual(splitChips("- one\n• two\n3) three\n\n"), ["one", "two", "three"]);
});

test("Enter or ; turns the text into a chip and leaves a fresh field", () => {
  for (const key of ["Enter", ";"]) {
    const { state, handled } = onFieldKey({ ...s0, draft: "Award B" }, { key });
    assert.ok(handled);
    assert.deepEqual(state, { chips: ["Award A", "Award B"], draft: "", editing: null });
  }
  assert.equal(onFieldKey({ ...s0, draft: "  " }, { key: "Enter" }).state.chips.length, 1); // nothing empty
});

test("Backspace on an empty field removes the last chip, and only then", () => {
  assert.deepEqual(onFieldKey(s0, { key: "Backspace" }).state.chips, []);
  assert.equal(onFieldKey({ ...s0, draft: "x" }, { key: "Backspace" }).handled, false);
});

test("pasting a list adds every item at once", () => {
  const { state, handled } = onPaste(s0, "Paper one\nPaper two; Paper three");
  assert.ok(handled);
  assert.deepEqual(state.chips, ["Award A", "Paper one", "Paper two", "Paper three"]);
  assert.equal(onPaste(s0, "just text").handled, false); // ordinary typing-paste is left alone
});

test("clicking a chip edits it in place", () => {
  let s = edit({ chips: ["a", "b", "c"], draft: "", editing: null }, 1);
  assert.deepEqual(s, { chips: ["a", "b", "c"], draft: "b", editing: 1 });
  s = commit({ ...s, draft: "B" });
  assert.deepEqual(s.chips, ["a", "B", "c"]);
  assert.deepEqual(remove(s, 0).chips, ["B", "c"]);
});

test("Save keeps a draft that wasn't turned into a chip yet", () => {
  assert.deepEqual(finalList({ chips: ["a"], draft: "b", editing: null }), ["a", "b"]);
});
