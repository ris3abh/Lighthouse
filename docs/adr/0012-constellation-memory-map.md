# 0012. The constellation memory map

- Status: accepted
- Date: 2026-10-08
- Builds on: ADR 0004 (append-only claim memory), ADR 0007 (design system), ADR 0010 §4 (banter)

## Context

Every fact in a case is a claim that quotes its source, with a review status, versions (SUPERSEDES) and
contradictions (CONTRADICTS). The pages show claims next to the things they support, but nothing shows the whole
memory at once: how much is known per criterion, what's approved, what's waiting, what conflicts, how it grew. A
case with a few years of work has thousands of claims, so a list doesn't do it.

## Decision

A **Memory** page draws the memory as a night sky.

- **Layout.** Each criterion of the active profile is a cluster (plus "Other" for claims not tied to one); clusters
  sit on a ring, and inside a cluster stars spiral out in date order (golden angle), so the oldest are at the center
  and replaying the case grows each cluster outward. A claim's criterion comes from what cites it (an exhibit's
  criterion), else an Inbox candidate resting on it, else its predicate.
- **Encoding.** Every claim is a star. Brightness and size follow confidence (high / medium / low). Approved claims
  are solid, pending ones (proposed, corroborated) are hollow rings, superseded ones fade, and a claim in a
  CONTRADICTS edge glows red. Rejected claims are hidden unless the status filter asks for them.
- **Provenance.** Clicking a star opens its trail: the claim, the verified excerpt, the raw source (the snapshot and
  its URL), the reviews, earlier versions and the exhibits that cite it. On the sky, the trail draws as an animated
  path from the star to its source and to any citing exhibit.
- **Filters.** Criterion, entity (search), status, and a date range; a time slider replays the case in date order.
- **Rendering.** One `<canvas>`, drawn only while something moves (a glide, a fade, the twinkle, a replay); a spatial
  grid for hit-testing, so 2,000+ claims stay smooth. Touch: drag to pan, pinch to zoom; the trail opens as a sheet
  on phones. A list view of the same stars serves screen readers and keyboards.
- **Motion.** Stars fade in on load; only pending stars twinkle; zoom and pan glide (eased); the trail draws as a
  path; "Aligning the stars..." (the banter line for this place) shows while loading. With reduced motion there's no
  twinkle, fade or glide, and replay jumps to the end.
- **Look.** A dark sky in both themes (the page is the one place the light theme stays dark), with the design
  system's type and controls around it.

## Consequences

- The memory files are unchanged: the page reads claims, decisions and edges through one endpoint
  (`/api/memory/constellation`) and the existing provenance chain (`/api/claims/{id}/provenance`).
- Layout and hit-testing are pure functions (`web/src/lib/constellation.ts`) with their own tests, including a
  3,000-claim timing test.
