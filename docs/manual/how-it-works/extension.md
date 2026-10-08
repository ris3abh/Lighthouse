# Capture extension and community vault

Two optional helpers keep blocked official pages fresh in your vault without you saving pages by hand.

Some official sites, such as uscis.gov and travel.state.gov, block automated reading, so Area O1 can't refresh them by itself. The capture extension saves those pages when **you** visit them. The community library shares copies other people captured. Both are explained in [ADR 0011](https://github.com/ris3abh/areao1/blob/main/docs/adr/0011-vault-without-babysitting.md).

## The capture extension

When you visit one of the pages your vault lists, the extension sends that page to Area O1 on your computer, which imports it like a saved copy. It never opens, reloads or fetches pages on its own, and it only talks to Area O1 at `http://127.0.0.1`.

### Install it (Chrome, Edge, Brave)

1. Run `areao1 extension`. It prints the folder where the extension is. (If you have the release zip, `areao1-capture-<version>.zip`, unzip it instead.)
2. Open `chrome://extensions`, turn on **Developer mode**, click **Load unpacked** and choose that folder.

### Pair it

1. In Area O1, open **Knowledge**. In the **Browser extension** card, click **Get a pairing code**. The code works once, for ten minutes.
2. Click the extension's icon. Check the Area O1 address (default `http://127.0.0.1:7777`), type the code and press **Pair**.

The card then shows **Paired** and how many pages it watches. Visit one, such as the Form I-129 page, and the extension's badge shows **OK**: the page is in your vault, checked now.

To pair again, click **Pair again**. To stop, click **Unpair**. Either one replaces the old capture token.

### What it can and can't do

- **Permissions:** `storage`, `scripting`, the vault's official domains (uscis.gov, ecfr.gov, federalregister.gov, travel.state.gov and the others on the Tier 1 and 2 lists) and `127.0.0.1`. Nothing else.
- **Only listed pages:** it reads a page only when its address matches one of the vault's sources exactly. Everything else you browse is ignored.
- **Only to your computer:** it sends the page's HTML to your local Area O1 with a capture token. Area O1 stores only the token's hash, and accepts captures only with that token, only for listed URLs, and only on 127.0.0.1.

## The community vault

The community library is a public repository of snapshots of U.S. government pages, which are in the public domain (17 U.S.C. § 105): [github.com/ris3abh/areao1-community-vault](https://github.com/ris3abh/areao1-community-vault). Each entry has the page's URL, source id, capture date and SHA-256 hash. The library's checks reject entries that aren't on the official domains or whose hash doesn't match.

### Pulling copies

The daily `vault-watch` job reads the library's manifest. For a source that blocks automated reading, it imports a snapshot only when:

- it's newer than your local copy, and
- its SHA-256 matches the file.

A bad or altered snapshot is ignored, not trusted. Pulled copies go through the same freshness and rule-check rules as any other.

Pulling is on by default. To turn it off, set this in `areao1.yaml`:

```yaml
vault:
  community: false
```

### Sharing your captures (opt-in)

Sharing is off by default. To help, tick **Share captures of public government pages with the community library** in the extension's popup. Then:

- captures of Tier 1 pages are written to a local outbox in your workspace, `.areao1/cache/community-outbox/`, as the exact file and manifest entry to contribute;
- nothing is uploaded automatically: you decide whether to send them to the library;
- before a capture goes to the outbox, per-visit values a page carries (form, feedback and CSRF tokens, nonces) are emptied, since they could be tied to whoever captured it. The library's checks reject snapshots that still have them.

## When you'd still get a reminder

With the extension or the community library in place, most weeks nothing asks you for anything. You get one notification only when a relevant rule changed (or a source's timer lapsed) and no newer copy exists anywhere. It links to the page; with the extension installed, opening it is enough. See [Rule check and the knowledge vault](rule-check.md#freshness).
