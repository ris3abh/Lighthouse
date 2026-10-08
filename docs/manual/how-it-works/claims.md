# Claims and provenance

Every fact Area O1 holds is a claim that quotes its source exactly, so you can always trace it back to what was read.

## Observations

When a connector reads something (a GitHub API response, an email, a page, a file you uploaded), Area O1 saves it unchanged as an **observation**:

- the content goes to `memory/sources/<sha256>.<ext>`, named by its SHA-256 hash, so the same content is stored once;
- a line in `memory/observations.jsonl` records the connector, the source URL, when it was captured, the hash, and the source's tier.

The tier says how far a source can be trusted on its own:

| Tier | Meaning |
|---|---|
| `tier1`, `tier2`, `tier3` | Official rule sources in the knowledge vault: primary law and agency pages, adjudication, secondary. |
| `platform` | A service's own API, such as GitHub or Hugging Face. |
| `user` | A document you filed. |
| `self_reported` | Your own words, such as imported chat history or a note from an AI tool. Useful for trackers, never proof. |

## Claims

A **claim** is one fact drawn from an observation. Each claim has:

- `subject`: what it's about, an entity id such as `artifact:github:mayachen/fastgrad`,
- `predicate` and `value`: for example `stars` and `1340`,
- `stage` for activities: `invited`, `completed`, `submitted`, `published`... (see [Invited vs completed](invited-vs-completed.md)),
- `excerpt`: the exact words from the snapshot that support it,
- `excerpt_start` and `excerpt_end`: where those words sit in the snapshot, by character offset,
- `valid_from`: when it became true in the world, and `recorded_at`: when Area O1 learned it,
- `extracted_by`: the connector, model or person that read it, and a `confidence` of high, medium or low.

Area O1 refuses a claim whose excerpt isn't found word for word in its snapshot. `areao1 validate` re-checks every claim: it confirms each excerpt is still at its offsets and each snapshot still matches its hash, so an edited snapshot is caught.

## Append-only memory

The memory files in `memory/` only grow. Nothing is edited or deleted in place:

| File | Holds |
|---|---|
| `observations.jsonl` | Raw captures. |
| `entities.jsonl` | People, artifacts, organizations, venues, events. |
| `claims.jsonl` | One fact per line, with its excerpt and offsets. |
| `edges.jsonl` | Links between them. |
| `decisions.jsonl` | Your approve and reject decisions. |

Lines append cleanly in Git, so the history of your case is easy to diff. A SQLite index in `.areao1/cache/` speeds up queries; it can be deleted and is rebuilt from these files. See [ADR 0004](https://github.com/ris3abh/areao1/blob/main/docs/adr/0004-append-only-claim-memory.md).

## Links between claims

Edges connect the pieces. The ones you'll see most:

| Edge | Meaning |
|---|---|
| `DERIVED_FROM` | A claim came from this observation. |
| `ABOUT` | A claim is about this entity. |
| `SUPERSEDES` | A newer claim replaces an older one on the same subject and predicate. |
| `CONTRADICTS` | Two claims disagree. The Memory page shows them in red. |
| `REVIEWED_BY` | A claim has a review decision. |
| `CITES` | An exhibit relies on this claim. |

When a source says something new (fastgrad went from 1,200 to 1,340 stars), Area O1 appends a new claim with a higher version that `SUPERSEDES` the old one. The old claim stays, so the history is kept. When a second, independent connector reports the same value, the claim is **corroborated**.

## Review status

A claim's status is worked out from the files, not stored on it:

- **approved** or **rejected**: your latest decision, made when you accepted or rejected the Inbox item that rests on it,
- **corroborated**: no decision yet, but two independent connectors saw the same value,
- **proposed**: everything else.

Approval records your decision. It doesn't certify that the fact is true or legally sufficient. Agents are told to draft only from claims that are approved and current (nothing supersedes them), and the Letters page enforces it.

## As-of queries

Because each claim has both `valid_from` and `recorded_at`, you can ask what Area O1 believed on a given day: what was true by then **and** already known by then. This answers questions like "what were my metrics on filing day?" and powers the trend charts and "what changed since my last session". MCP clients ask it with `query_claims(entity, as_of)` (see [MCP tools](../mcp/tools.md#query_claims)).

## W3C PROV

The model maps onto [W3C PROV](https://www.w3.org/TR/prov-overview/), the standard vocabulary for provenance: a source is a `prov:Entity`, extraction and review are `prov:Activity`, and connectors, models and you are `prov:Agent`. `DERIVED_FROM` corresponds to `prov:wasDerivedFrom`. The `get_provenance` MCP tool returns a small `prov` block in these terms.

## The Memory page

The [Memory page](../tour/memory.md) draws every claim as a star, one cluster per criterion. Brighter stars are higher confidence, solid ones are approved, rings are waiting for your review, faded ones are superseded, and red ones are in a conflict. You can filter by criterion, entity, status and date, and replay the case over time.

Click a star to open its trail: the claim, the verified excerpt, the raw source, the reviews, earlier versions and the exhibits that cite it.

![The Memory page](../assets/shots/memory-light.webp#only-light)
![The Memory page](../assets/shots/memory-dark.webp#only-dark)
