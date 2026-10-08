# Daily opportunity check

Once a day, Area O1 can turn invitations in your Gmail into Inbox items, and check each one before you trust it.

Invitations to judge, review, speak or apply often land in Promotions, or get forwarded from a work account. Phishing that imitates hackathons and journals is common too. The daily opportunity check finds those messages and marks each find **verified**, **unconfirmed** or **suspicious**. The design is in [ADR 0016](https://github.com/ris3abh/areao1/blob/main/docs/adr/0016-daily-opportunities.md).

## Turn it on

It's off by default, and it needs Gmail connected (see [Gmail](../connectors/gmail.md)).

1. Open **Settings**, then the **Gmail** card.
2. Next to **Daily opportunity check**, click **Off** to switch it **On**.
3. To try it straight away, click **Check now**.

When it's on, the `daily-opportunities` job runs once a day (by default at 08:30; see `schedules` in [Configuration](../reference/configuration.md)). In `areao1.yaml` the setting is `opportunities.enabled`. You can also run it by hand with `areao1 run daily-opportunities`.

## What each run does

1. Refreshes the Mail view with its rules (contacts, organizer domains, keywords; Promotions and Social are filtered).
2. Takes new mail in the opportunity categories: invites, judging, reviewer requests, press and awards. For a forward, it uses the attached original, sorted and checked as the original.
3. Skips mail that isn't really about the opportunity its category implies. A judging find must mention judging, a reviewer request must mention reviewing, an invitation must mention speaking or a panel. A hackathon's participant notices or a platform's digest aren't invitations.
4. Reads each message in memory and keeps only facts (sender, dates mentioned, links, event name) and one quoted sentence.
5. Sets the stage the same way as for `.eml` files: `completed` only when the message says so explicitly, otherwise `invited`. See [Invited vs completed](invited-vs-completed.md).
6. Proposes an evidence candidate to your Inbox, with the stage, the sender check and a verification status.

A run adds at most 20 finds. `.eml` files you dropped in already went to the Inbox and are skipped.

## Verified, unconfirmed, suspicious

| Status | When |
|---|---|
| **verified** | The sender check passed **and** the event is confirmed on the web. |
| **unconfirmed** | Either check didn't pass, and the sender check didn't fail outright. A check-in to the organizer is drafted. |
| **confirmed by reply** | Was unconfirmed; then a later message arrived from that sender. |
| **suspicious sender** | The sender check failed, or the sender looks like an imitation. No reply is drafted. |

**The sender check** passes on DMARC pass, or DKIM pass aligned with the From domain, read from your mail server's `Authentication-Results`.

**Confirmed on the web** means a page on the sender's organization's domain, or on Devpost or MLH, mentions the event and at least one date from the email. Links in the email are tried first, but only those on those domains. Otherwise one web search restricted to those domains runs on the cheap model tier, and its cost counts toward your budget. To skip the web step, set `opportunities.verify_on_web: false`; finds then stay unconfirmed (or suspicious).

A free mail address (gmail.com, outlook.com and the like) can't be confirmed by a page on an organizer's site; only Devpost or MLH count for it.

**Suspicious before any page is read.** Anyone can register a domain with working DMARC and copy a page, so two more signals mark a find suspicious:

- a **look-alike** domain: a near miss of the event's name or of a known organizer or platform (digits for letters, `rn` for `m`, one or two characters off),
- a **hidden** domain, such as `examplehacks.org.evil.example`.

"Verified" is strict on purpose. A real invitation with no dates, or from an organizer whose site doesn't list the event yet, stays unconfirmed until the organizer answers your check-in.

## The check-in draft

For an unconfirmed find, Area O1 drafts a short, polite reply to the organizer asking for the event page and the details (dates and your role). It also adds the organizer to Contacts as an `organizer`, marked as added by the job.

Nothing is sent. The draft waits on the [Contacts page](../tour/contacts.md) until you press **Approve & send**, or edit or reject it. When the organizer writes back, the find is marked confirmed by reply.

For a suspicious find, no reply is drafted, so nothing confirms an address to a phisher.

## No duplicates

A find is skipped when it's already somewhere: a pending or snoozed Inbox item (scout leads included), a pipeline item, or an earlier find. Two items match when they share the same official URL, or when their titles match after ignoring case, punctuation, years and "Re:" / "Fwd:".

## Notifications

Each new find sends one notification on the `opportunity` event, through the channels you routed it to in Settings. A verified find says so; an unconfirmed one says a check-in was drafted; a suspicious one is a plain warning, with no drafted reply.

## The weekly opportunity scout

The scout is a different thing: a scheduled agent mission that searches the web, not your mail.

- Turn it on in **Settings > Missions > Weekly opportunity scout**. It's off by default.
- Once a week (Fridays at 09:00 by default), it looks for current opportunities for your weakest criteria and proposes pipeline items and deadlines to your Inbox, or applies them where you turned on autopilot.
- It runs on the missions model, inside your monthly budget. Results show on the Agent page and as a notification.

## Search caps

Every agent run, the scout included, has a cap on web searches: `agent.max_searches` in `areao1.yaml`, 8 by default. At the cap, the run finishes with what it found and says so. Each search request is limited to one search, so the count is exact. See [Costs and budget caps](../getting-started/costs.md).

## Your Inbox decides

A find is only a candidate. Being verified means the sender and the event checked out; it doesn't make the item evidence, and an invitation doesn't count toward a criterion until it's completed. Accept, edit, snooze or reject it like anything else. See [Review in the Inbox](review.md) and [Outreach etiquette](../best-practices/outreach.md).
