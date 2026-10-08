# 0011. The vault without babysitting

- Status: accepted
- Date: 2026-10-07
- Builds on: ADR 0006 (the knowledge vault)

## Context

The vault keeps official sources fresh with timers: every fact kind has a freshness window (fees 7 days, policy 30),
and a source past its window is re-fetched. That works for eCFR and the Federal Register, which answer automated
requests, but uscis.gov and travel.state.gov usually block them. Those sources are "manual": the person saves the
page and imports it, and a reminder arrives every time the window lapses, even when nothing changed. That's
babysitting: weekly chores that almost never matter.

## Decision

### 1. Change signals instead of timers (G1)

The manifest gets `signals`: named topics (`o1`, `eb1`, `fees`, `forms`) with search terms, CFR parts and eCFR
sections. A source can name its `signal`. The vault-watch job checks two official change feeds, both public APIs:

- the **Federal Register** (`/api/v1/documents.json`): final rules from USCIS / DHS, matched to a signal by their CFR
  references or terms; a rule counts once it's in effect (`effective_on` on or before today);
- **eCFR** (`/api/versioner/v1/versions/title-8.json`): the latest amendment date of each watched section.

For a source with a signal, "fresh" means **no relevant change in effect since the copy was taken** (as long as the
signals were checked in the last three days; otherwise its timer applies, so being offline never makes stale facts
look fresh). So a blocked USCIS page is flagged only when a relevant rule actually changed, and the reminder names the
change. Sources with no change signal (processing times, the Visa Bulletin) keep their timers.

### 2. A zero-click capture extension (G2)

`extension/` is a Chrome extension (Manifest V3). It never browses on its own: when the person visits a page, it
compares the URL with the vault's source list (from the local app) and, only on a match, sends the page's HTML to the
local Area O1, which imports it like a saved copy. Pairing is a one-time code shown in Settings > Knowledge,
exchanged for a capture token kept in the extension; the app accepts captures only with that token, only from the
extension, only for listed URLs, and only on 127.0.0.1. Its host permissions are the vault's official domains and
127.0.0.1, nothing else.

### 3. A community snapshot library (G3)

`community-vault/` holds the contents of a separate public repository: a manifest of snapshots of public-domain U.S.
government pages (17 U.S.C. § 105), each with its URL, source id, capture date and SHA-256, the snapshot files, and a
CI workflow that validates URL (listed official domains only), hash and structure. Installs pull the manifest on
vault-watch and import a snapshot for a manual source only when it's newer than the local copy and its hash matches.
Sharing is opt-in (`vault.share_captures`): captures of Tier 1 pages are written to a local outbox with the exact
manifest entry and file to contribute; nothing is uploaded automatically.

### 4. One notification, only when it matters (G4)

A reminder is sent only when a relevant page changed (a signal, or a lapsed timer for sources without one) **and** no
newer snapshot exists anywhere (not from the extension, not in the community library): one notification per lapse,
with a direct link to the page.

## Consequences

- Most weeks, nothing asks the person for anything. When a fee rule takes effect, one message says which page to
  open; with the extension installed, opening it is enough.
- The extension is a second piece of software to install and keep in sync with the app's pairing; it is optional.
- The community library depends on volunteers sharing; hash checks mean a bad snapshot is ignored, not trusted.
