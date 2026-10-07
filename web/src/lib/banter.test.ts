// Run with: node --test web/src/lib/   (Node strips the types; no browser needed)
import assert from "node:assert/strict";
import { test } from "node:test";
import { banterAllowed, banterText, SERIOUS_PAGES } from "./banter.ts";

const ok = { insideSerious: false, seriousOnScreen: false, seriousPage: false, earlierShown: 0 };

test("never on or near a serious surface, and one per screen", () => {
  assert.equal(banterAllowed(ok), true);
  assert.equal(banterAllowed({ ...ok, insideSerious: true }), false);
  assert.equal(banterAllowed({ ...ok, seriousOnScreen: true }), false);
  assert.equal(banterAllowed({ ...ok, seriousPage: true }), false);
  assert.equal(banterAllowed({ ...ok, earlierShown: 1 }), false);
  for (const page of ["overview", "evidence", "calendar", "knowledge", "agent"]) assert.ok(SERIOUS_PAGES.has(page));
  for (const page of ["inbox", "pipeline", "letters", "settings"]) assert.ok(!SERIOUS_PAGES.has(page));
});

test("lines come from the shared file, with values filled in", () => {
  assert.equal(banterText("empty_inbox"), "Nothing to review. The skies are clear.");
  assert.equal(banterText("signal_verified", { what: "a judging call" }), "New signal detected: a judging call, verified.");
});
