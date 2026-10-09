# How it works

Area O1 turns what it reads into sourced facts, asks you about each one, and counts only what you accepted.

## The flow

```text
sources ──> observations ──> claims ──> Inbox candidates ──> your review ──> exhibits ──> scoreboard
```

1. **Sources.** Connectors read the places your work lives: GitHub, Hugging Face, scholarly sites, websites, Gmail, `.eml` files, chat exports, and files you upload. See [Connectors](../connectors/index.md).
2. **Observations.** Each thing a connector reads is saved as-is, as a snapshot in `memory/sources/`, named by its SHA-256 hash. That's the record of what the source said on that day.
3. **Claims.** From each observation, Area O1 draws claims: single facts such as "fastgrad has 1,340 stars" or "Maya Chen was invited to judge Northwind Hacks". Every claim quotes the snapshot word for word, with the character offsets of the quote. See [Claims and provenance](claims.md).
4. **Inbox candidates.** Claims that might be evidence are grouped into a candidate in the [Inbox](../tour/inbox.md), with a suggested criterion, an evidence type, a stage (invited, completed...) and the claims behind it. The in-app agent, the daily opportunity check and MCP tools add candidates here too.
5. **Your review.** You accept, edit, snooze or reject each one. Nothing skips this step. See [Review in the Inbox](review.md).
6. **Exhibits.** Accepting files an exhibit: a file under `evidence/<criterion>/` and an entry in `data/exhibits.json`. Your decision is recorded against the claims.
7. **Scoreboard.** The criteria engine counts accepted exhibits against the profile's rules and shows each criterion as banked, building, gap or dropped. An invitation doesn't count until it's completed. See [Invited vs completed](invited-vs-completed.md).

## Around the flow

- **The rule check.** Anything the agent writes about the rules (fees, forms, criteria wording) is checked against official sources in the knowledge vault before it can enter your records. See [Rule check and the knowledge vault](rule-check.md).
- **The capture extension.** Some official sites block automated reading. An optional browser extension saves those pages to your vault when you visit them. See [Capture extension and community vault](extension.md).
- **Proof recipes.** When an activity is done, its criterion's recipe lists what to save. See [Proof recipes](proof-recipes.md).
- **Preflight.** Checks your exhibits, letters and facts for gaps and inconsistencies, without blocking anything. See [Evidence preflight](preflight.md).
- **The review packet.** Your case in order for your attorney, every fact matched to its page. See [The review packet](review-packet.md).
- **The daily opportunity check.** If you turn it on, invitations in your Gmail become Inbox candidates, each marked verified, unconfirmed or suspicious. See [Daily opportunity check](opportunities.md).

## Where things live

Everything is plain files in your workspace folder. The files are the source of truth; the app's indexes under `.areao1/cache/` can be deleted and rebuilt. See [ADR 0001](https://github.com/ris3abh/areao1/blob/main/docs/adr/0001-files-are-the-source-of-truth.md) and [Architecture](../reference/architecture.md).

| Step | Files |
|---|---|
| Observations | `memory/observations.jsonl`, `memory/sources/` |
| Claims, links, reviews | `memory/claims.jsonl`, `memory/edges.jsonl`, `memory/decisions.jsonl`, `memory/entities.jsonl` |
| Candidates | `data/inbox.json` |
| Exhibits | `data/exhibits.json`, `evidence/<criterion>/` |
| Scoreboard | `data/criteria.json` (generated) |
| Every change you or an agent made | `data/changes.jsonl` |
