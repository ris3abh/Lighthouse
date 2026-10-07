# 0007. Design system: "Brutalism 2.0"

- Status: accepted; amended 2026-10-07 (status palette, decision 2)
- Date: 2026-10-07
- Phase: build Part B (B1–B4)

## Context

The dashboard grew page by page with Tailwind's default palette: zinc grays, an amber accent, emerald and red
for status, rounded cards with soft shadows and emoji-like glyphs for icons. Color carried too many meanings:
amber meant both "brand" and "in progress", and red meant "negative delta" as well as "needs you". Panels were
small and dense. Dark mode was mostly `dark:` inversions of the light classes.

The product is a calm command center for a long, high-stakes case. People should see at a glance what needs
attention, and nothing else should compete for it.

## Decision

1. **Tokens, not palette classes.** Colors are semantic CSS variables set on `:root` and redefined under
   `.dark`:

   | Token | Light | Dark | Use |
   |---|---|---|---|
   | `paper` | `#f3f1eb` | `#0d0d0c` | page background |
   | `surface` | `#faf9f5` | `#151514` | framed panels |
   | `sunken` | `#ebe8e0` | `#1d1d1b` | wells, hover, selected rows |
   | `ink` | `#0b0b0a` | `#eceae4` | text, frames, primary blocks |
   | `ink-2` | `#45443f` | `#b9b7b0` | secondary text |
   | `muted` | `#67655f` | `#8f8d87` | labels, hints |
   | `line` | `#d6d3ca` | `#2e2d2a` | interior grid lines |
   | `frame` | `#0b0b0a` | `#4a4945` | panel frames |
   | `alert`, `alert-soft` | `#a8372b`, `#f3dcd6` | `#e2705f`, `#3a1d18` | status: attention (red) |
   | `building`, `building-soft` | `#855600`, `#f4e6c8` | `#e3a53c`, `#36280e` | status: building (amber) |
   | `banked`, `banked-soft` | `#2f6b3a`, `#d4ead7` | `#6cc07e`, `#17301c` | status: banked (green) |
   | `on-ink`, `on-alert`, `on-status` | | | text on solid ink / red / green / amber blocks |

   Every text token meets WCAG AA (4.5:1) on paper, surface and sunken in both themes, and each status color
   meets it on its soft badge background and under its `on-` text (tested).

   Tailwind's `@theme` maps them to utilities (`bg-paper`, `text-ink`, `border-line`, `text-alert`). Pages
   don't use raw palette colors (zinc, amber, emerald, red), and a test enforces it.
2. **Monochrome plus three status colors, used only for status** (amended 2026-10-07; first accepted as
   monochrome plus one red). Green means banked, amber means building, and red means attention: conflicts,
   overdue items, refused actions, errors and stale rules. They appear on scoreboard bars, criterion markers,
   status badges and deadline countdowns, never as decoration, branding or chart color. A positive or
   negative metric delta is not status, so both stay ink. Fill still carries the meaning without color:
   banked is solid, building is half-filled, gap is hollow, and dropped is struck through. A test allows
   exactly these three hues among the tokens and keeps green and amber inside the status components.
3. **Structure from lines, not shadows.** Panels are square, framed with a 1px border, and have no shadows.
   Interior grid lines (`line`) separate rows and cells. Primary actions are solid ink blocks. Secondary
   actions are outlined, and ghost actions are text.
4. **Type.** Archivo Variable for headlines, set condensed (`font-stretch: 68%`, weight 700, large sizes,
   tight leading) and for body text at normal width. JetBrains Mono Variable for labels (uppercase, tracked),
   numbers, dates, ids and data. Both are self-hosted from `@fontsource-variable` packages. The dashboard
   stays local and makes no font requests.
5. **Space.** Fewer, larger panels; a 12-column page grid; generous padding (24–32px in panels at laptop
   width). Phone width stacks to one column with 16px gutters and no horizontal scroll.
6. **Dark is designed, not inverted.** Near-black paper, off-white ink, and dark-gray frames, because ink
   frames are too loud on black. The red is lightened to keep its contrast ratio. Primary blocks invert to
   off-white with black text.
7. **Theme choice.** A System / Light / Dark switch in the header, defaulting to System and remembered per
   browser (`lh-theme`). System follows `prefers-color-scheme` live. The saved choice is applied before
   first paint, so the page never flashes the wrong theme.
8. **Icons.** Lucide line icons (1.5px stroke) replace every emoji and glyph.
9. **Motion** is used for data and state changes only, never for decoration:
   - Charts draw in left to right and morph between ranges.
   - Numbers count up, and deltas slide in.
   - Sparklines draw when scrolled into view.
   - Scoreboard bars fill, and status changes get a short transition.
   - Calendar moves and view switches animate (View Transitions API where available).
   - Durations are 150–400ms with ease-out curves. Motion never blocks input, and nothing loops except a
     running tool call's pulse.
   - `prefers-reduced-motion: reduce` makes everything instant. It is checked once in `useReducedMotion()`
     and in a CSS media query.

## Consequences

- Every page is re-laid out, and the chat panel and dialogs are restyled (B2).
- Recharts stays for full charts, styled through tokens. Sparklines, count-ups and progress are small
  in-house components, so no animation library is added.
- New dependencies: `lucide-react`, `@fontsource-variable/archivo`, `@fontsource-variable/jetbrains-mono`.
- The guard test fails on raw palette classes in pages, so the system can't drift back.
