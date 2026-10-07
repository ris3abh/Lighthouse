// Run with: node --test web/src/lib/   (Node strips the types; no browser needed)
import assert from "node:assert/strict";
import { test } from "node:test";
import { usageLine } from "./usage.ts";

test("never 0 tokens next to a cost", () => {
  assert.equal(usageLine(0, 0.01), "$0.01");
  assert.equal(usageLine(undefined, 0.096), "$0.10");
  assert.equal(usageLine(10_040, 0.096), "10k tokens · $0.10");
  assert.equal(usageLine(1200, 0), "1.2k tokens");
  assert.equal(usageLine(0, 0), "$0.00".replace("$0.00", "<$0.01"));
  assert.ok(!/\b0 tokens/.test([usageLine(0, 0.5), usageLine(null, 0.002)].join(" ")));
});
