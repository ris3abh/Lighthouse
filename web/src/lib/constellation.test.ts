// Run with: node --test web/src/lib/
import assert from "node:assert/strict";
import { test } from "node:test";
import { DEFAULT_STATUSES, fit, glide, Grid, layout, partial, toScreen, toWorld, trail, visible, zoomAt, type Star } from "./constellation.ts";

function star(i: number, extra: Partial<Star> = {}): Star {
  const day = String(1 + (i % 28)).padStart(2, "0");
  const month = String(1 + ((i / 28) | 0) % 12).padStart(2, "0");
  return { id: `clm_${String(i).padStart(5, "0")}`, criterion: ["judging", "awards", "press"][i % 3], entity: `event:e${i % 40}`,
    entity_name: `Event ${i % 40}`, predicate: "judged", value: i, stage: null, date: `2026-${month}-${day}`, confidence: [0.33, 0.66, 1][i % 3],
    band: "medium", status: (["approved", "pending", "superseded"] as const)[i % 3], review: null, conflict: i % 50 === 0, source: `obs_${i % 90}`,
    source_url: null, connector: "github", exhibits: i % 7 === 0 ? [`exh_${i % 5}`] : [], ...extra };
}
const clusters = [{ id: "judging", label: "Judging" }, { id: "awards", label: "Awards" }, { id: "press", label: "Press" }];

test("clusters sit on a ring, stars spiral out of their cluster in date order", () => {
  const l = layout(clusters, [star(2, { date: "2026-03-01" }), star(5, { date: "2026-01-01" }), star(8, { date: "2026-02-01" })]);
  const c = l.centers.get("press")!;
  const d = (id: string) => Math.hypot(l.byId.get(id)!.x - c.x, l.byId.get(id)!.y - c.y);
  assert.ok(d("clm_00005") < d("clm_00008") && d("clm_00008") < d("clm_00002")); // oldest nearest the center
  assert.deepEqual(l.dates, ["2026-01-01", "2026-02-01", "2026-03-01"]);
  assert.equal(l.byId.get("clm_00005")!.order, 0);
});

test("brighter means bigger, and filters by criterion, entity, status and date", () => {
  const l = layout(clusters, [star(0), star(1), star(2)]);
  assert.ok(l.byId.get("clm_00002")!.r > l.byId.get("clm_00000")!.r);
  const f = { criterion: "all", entity: "", statuses: new Set(DEFAULT_STATUSES), from: null, until: null };
  assert.ok(visible(star(0), f) && !visible(star(0, { status: "rejected" }), f));
  assert.ok(!visible(star(0), { ...f, criterion: "awards" }) && visible(star(1), { ...f, criterion: "awards" }));
  assert.ok(visible(star(3), { ...f, entity: "event 3" }) && !visible(star(4), { ...f, entity: "event 3" }));
  assert.ok(!visible(star(0, { date: "2026-05-01" }), { ...f, until: "2026-04-30" }));
});

test("picking, zooming and gliding", () => {
  const l = layout(clusters, Array.from({ length: 300 }, (_, i) => star(i)));
  const p = l.placed[123];
  const g = new Grid(l.placed);
  assert.equal(g.nearest(p.x + 0.1, p.y - 0.1, 3)?.star.id, p.star.id);
  assert.equal(g.nearest(p.x + 0.1, p.y, 3, (q) => q.star.id !== p.star.id)?.star.id !== p.star.id, true);
  const cam = fit(l.bounds, 800, 600);
  const { sx, sy } = toScreen(cam, 800, 600, p.x, p.y);
  const z = zoomAt(cam, 800, 600, sx, sy, 3);
  const back = toWorld(z, 800, 600, sx, sy);
  assert.ok(Math.abs(back.x - p.x) < 1e-6 && Math.abs(back.y - p.y) < 1e-6); // the point under the pointer stays put
  let c = cam;
  let done = false;
  for (let i = 0; i < 200 && !done; i++) [c, done] = glide(c, z, 16);
  assert.ok(done && c === z);
});

test("the provenance trail runs star, source, citing exhibits, and draws partway", () => {
  const l = layout(clusters, [star(7)]);
  const pts = trail(l, "clm_00007");
  assert.equal(pts.length, 3);
  const half = partial(pts, 0.5);
  assert.ok(half.length >= 2 && half.length <= 3);
  assert.deepEqual(partial(pts, 1), pts);
});

test("3,000 claims lay out and pick fast", () => {
  const stars = Array.from({ length: 3000 }, (_, i) => star(i));
  const t0 = performance.now();
  const l = layout(clusters, stars);
  const g = new Grid(l.placed);
  for (let i = 0; i < 1000; i++) g.nearest(l.placed[i].x, l.placed[i].y, 4);
  const ms = performance.now() - t0;
  assert.equal(l.placed.length, 3000);
  assert.ok(ms < 400, `${ms.toFixed(0)} ms`);
});
