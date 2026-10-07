// Run with: node --test web/src/lib/   (Node strips the types; no browser needed)
import assert from "node:assert/strict";
import { test } from "node:test";
import { MAX_TYPE_MS, typeDuration, typedPrefix } from "./typing.ts";

test("words appear whole, from nothing to the full message", () => {
  const text = "Let's start with your name as it should appear on your case.";
  assert.equal(typedPrefix(text, 0), "");
  const total = typeDuration(text);
  let last = "";
  for (let t = 1; t <= total; t += 37) {
    const p = typedPrefix(text, t);
    assert.ok(text.startsWith(p) && p.length >= last.length, "only ever grows");
    assert.ok(p === text || text[p.length] === " ", `cut mid-word: "${p}"`);
    last = p;
  }
  assert.equal(typedPrefix(text, total), text);
});

test("a long message never takes longer than the cap", () => {
  assert.equal(typeDuration("x".repeat(5000)), MAX_TYPE_MS);
  assert.equal(typedPrefix("word ".repeat(1000), MAX_TYPE_MS), "word ".repeat(1000));
});
