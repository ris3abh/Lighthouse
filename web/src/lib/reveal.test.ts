import assert from "node:assert/strict";
import { test } from "node:test";
import { isAskShortcut, panelSelector, panelsFor } from "./reveal.ts";

test("a write that lands in the Inbox highlights the Inbox panels; reads highlight nothing", () => {
  assert.deepEqual(panelsFor(["data/inbox.json"], false), ["inbox"]);
  assert.deepEqual(panelsFor(["data/inbox.json", "data/pipeline.json", "data/deadlines.json"], false), ["inbox", "pipeline", "deadlines"]);
  assert.deepEqual(panelsFor(["data/inbox.json"], true), []); // list_inbox reads it
  assert.deepEqual(panelsFor(["memory/sources/"], false), []); // nothing on screen shows it
  assert.deepEqual(panelsFor(undefined, false), []);
});

test("Cmd/Ctrl+K opens the chat, nothing else does", () => {
  const k = { key: "k", metaKey: false, ctrlKey: false, altKey: false, shiftKey: false };
  assert.ok(isAskShortcut({ ...k, metaKey: true }));
  assert.ok(isAskShortcut({ ...k, ctrlKey: true, key: "K" }));
  assert.ok(!isAskShortcut(k));
  assert.ok(!isAskShortcut({ ...k, metaKey: true, shiftKey: true }));
});

test("selectors only ever name known panel words", () => {
  assert.equal(panelSelector(["inbox", 'x"]']), '[data-panel~="inbox"], [data-panel~="x"]');
});
