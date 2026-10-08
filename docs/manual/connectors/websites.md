# Websites

The website connector reads any public web page, or a sitemap of pages, and proposes the ones that mention you:
press articles, award announcements, winners lists.

## Add a page or a sitemap

Paste the URL on the **Sources** page, or:

```sh
areao1 import https://example.com/news/2026-research-awards
areao1 import https://example.com/sitemap.xml
```

Any `http(s)` URL that no other connector recognizes goes here.

- **A page** is read once when you add it. If it can't be fetched at all (a typo, an HTTP 404), it isn't added,
  so a mistyped address never becomes a source.
- **A sitemap** (a URL ending in `sitemap.xml` or `sitemap_index.xml`) adds up to **25 pages** from it, on the
  same host as the sitemap.

Pages have no numbers to track, so this connector records no metrics. Sync reads the pages again.

## How a page is read

Area O1 reads pages "readability-style": it takes the page's main text (the `<article>` or `<main>` when there is
one) and drops navigation, headers, footers, side panels, forms and scripts. It also picks up the page's title,
published date, author and site name when the page states them.

Then it looks for **sentences that mention you**, by your name and any aliases in your profile. Once your full
name appears, your family name alone counts too, the way news articles write ("Chen said...").

## What it proposes

If a page mentions you, one candidate goes to your [Inbox](../tour/inbox.md), quoting up to three of those
sentences word for word:

| The page | Proposed as | Criterion |
|---|---|---|
| Says you won, were awarded or received an award, prize, medal, fellowship, grant or honor | Award notice | Awards |
| Is about you (your name is in the title, or it mentions you three or more times) | Press article | Press |
| Mentions you in passing | Media mention | Press |

The proposal tells you what to check: for an award, its scope and selectivity (how many entrants, who judged);
for press, that it's really about you and that the outlet is major media or a professional publication.

A page that doesn't mention you is tracked but proposes nothing.

## Pages that can't be read

Some sites don't serve their content to automated readers. Area O1 recognizes these and marks the item
**unreadable** with the reason, instead of storing a challenge page as if it were content:

- Bot-protection and CAPTCHA pages ("Just a moment...", "Verify you are human")
- HTTP 401, 403, 429 or 451 answers, and login walls
- Maintenance pages
- Pages that need JavaScript and have almost no text without it
- Files that aren't HTML or plain text

For these, open the page in your browser, save it (or print it to PDF), and drop the file on the
[Evidence](../tour/evidence.md) page.

## The private-network guard

The website connector, the agent's page reader and the knowledge vault all fetch pages through the same guard:

- Only `http` and `https` URLs.
- Only **public** hosts. An address that resolves to your own computer, your local network or any other private
  or reserved range is refused: "it resolves to a private or local address".
- Every redirect is checked again (at most 3), so a public page can't bounce Area O1 to a private one.
- Pages over 2 MB are refused.
- Sitemaps with a DTD or entities are refused.

This keeps a page you add, or a link in one, from pointing Area O1 at a router, a NAS or a service on your laptop.
