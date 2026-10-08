# 0016. The daily opportunity job

- Status: accepted
- Date: 2026-10-07
- Builds on: ADR 0014 (Gmail, the Mail view, .eml and forwards), ADR 0015 (the OpenAI engine), ADR 0010 §4 (banter)

## Context

Invitations to judge, review, speak or apply arrive by email, often in Promotions, sometimes forwarded from a work
account. The weekly scout searches the web; nothing yet turns the person's own mail into tracked opportunities, and
nothing checks that an invitation is real before it reaches the Inbox. Phishing that imitates hackathons and
journals is common, so "verified" has to mean something.

## Decision

### 1. Searches are capped per run

`agent.max_searches` (default 8) in `areao1.yaml`. The engine refuses searches past the cap with a reason the model
sees ("finish with what you found and say so"), and each hosted search sub-request is limited to one search
(`max_tool_calls: 1`), so the count is exact. If the answer doesn't mention the cap, the runner appends a line
saying it was reached.

### 2. A daily job, off by default

`opportunities.enabled` (Settings > Gmail > Daily opportunity check) turns on the `daily-opportunities` job, every
24 hours (`schedules`). Each run:

1. refreshes the Mail view with its rules (contacts, organizer domains, keywords, Promotions / Social filtered),
   the model only if model sorting is on;
2. takes new mail in the opportunity categories (invites, judging, reviewer requests, press, awards), including a
   forward's attached original (sorted and authenticated as the original); dropped .eml files already went to the
   Inbox and are skipped;
3. reads each message's text in memory (PEEK), and keeps only facts (sender, dates mentioned, links, event name)
   and one quoted sentence; the stage follows the .eml rule: `completed` only on explicit completion, else
   `invited`;
4. proposes an evidence candidate to the Inbox with that stage, the sender check, and a verification status.

### 3. Verification

A find is **verified** only when both hold:

- **the sender check passed** (DMARC pass, or DKIM pass aligned with the From domain, from the receiving server's
  `Authentication-Results`), and
- **the event is confirmed on the web**: a page on the sender's organizational domain, or on Devpost or MLH,
  mentions the event and at least one date from the email. Links in the email are tried first (only those on
  those domains); otherwise one guarded web search restricted to those domains, on the mundane tier, counted in
  the run's cost. Pages are read with the same fetcher as the agent's `read_page` (no private addresses).

Otherwise the find is **unconfirmed**. If the sender check didn't fail outright, a short confirmation reply to the
organizer is drafted behind Approve & send (the organizer is added to Contacts as `organizer`, marked as added by
the job), and the item stays unconfirmed until a later message from that sender arrives, which marks it
**confirmed (they replied)**. If the sender check failed (spoofing, a DMARC fail, a look-alike domain with no
authentication), the find is **suspicious**: no reply is drafted, so nothing confirms a phisher's address.

Because anyone can register a domain with working DMARC and a copied page, two more signals make a find suspicious
before any page is fetched: a **look-alike** sender domain (a near miss of the event's own name or of a known
organizer or platform: digits for letters, `rn` for `m`, one or two characters off; an event's own domain may be
hyphenated, a known one may not), and a **hidden domain** (`examplehacks.org.evil.example`). A free mail address
can't be confirmed by a page on the organizer's site (only Devpost / MLH count for it).

### 4. De-duplication and notifications

A find is skipped when the Inbox (pending or snoozed, scout leads included), the pipeline or an earlier find
already has it: same official URL, or a title that matches after normalizing (case, punctuation, years, "Re:" /
"Fwd:"), by token overlap. Each new find sends one notification on the `opportunity` event: verified ones use the
banter line "New signal detected: {what}, verified."; the rest use "Unidentified signal. Couldn't confirm the
sender, so I drafted a check-in." (or, for a suspicious find, a plain warning with no drafted reply). Tests run a set
of phishing fixtures (display-name spoofing, look-alike domains, DMARC fail, links to other domains, an
authenticated sender whose page doesn't mention the event) and require that none comes out verified.

## Consequences

- One more job, off by default; with it on, the cost is mail reading (free) plus at most one cheap search per
  unconfirmed find with no usable link.
- "Verified" is conservative: real invitations without dates, or from an organizer whose site doesn't list the event
  yet, stay unconfirmed until the person approves the drafted check-in and the organizer answers.
