# Scholarly sources

Four connectors read your papers and citations from public scholarly databases: Semantic Scholar, OpenAlex, arXiv
and ORCID.

None of them needs a key or an account. Add one or several; the same paper found by more than one is proposed
only once.

## How they work

Each connector turns an author profile into:

- **One author item**, with profile metrics where the source has them: `citations`, `h_index` and `papers`.
- **One paper item per work** (up to 500), with its `citations` when the source counts them.

Every paper is proposed for the **scholarly articles** criterion, with what the source says about it: venue,
year, type, citations, DOI or arXiv id.

| What the source says | Proposed as | Stage |
|---|---|---|
| A journal | Journal article (peer reviewed) | Published |
| A conference | Conference paper (peer reviewed) | Published |
| A preprint, or no venue | Preprint | Preprint |
| A named venue of unknown type | Paper | Published |

A preprint's proposal asks you to add the venue if it was later published.

!!! note "Confirm each paper is yours"
    Author pages get merged, and people share names. A connector can't know whether a listed paper is really
    yours, so every proposal asks you to confirm you're an author before you accept it.

Papers are matched across sources by arXiv id, then DOI. A paper linked from a GitHub README or a Hugging Face
repo is the same candidate as the one a scholarly connector finds.

## Semantic Scholar

Uses the free [Semantic Scholar Graph API](https://api.semanticscholar.org). Reads your papers, citations,
venues, publication types and h-index.

| Input | Example |
|---|---|
| Author page | `https://www.semanticscholar.org/author/Maya-Chen/12345678` |
| Handle | `s2:12345678` |

Find your author page by searching your name on semanticscholar.org. Requests are rate-limited; Area O1 backs off
and retries.

## OpenAlex

Uses the free [OpenAlex API](https://api.openalex.org). Reads your works, citation counts, venues, types and
h-index.

| Input | Example |
|---|---|
| Author URL | `https://openalex.org/A5000000001` (or `https://openalex.org/authors/A5000000001`) |
| Handle | `openalex:A5000000001` |

OpenAlex asks callers for a contact email for its faster "polite pool". Area O1 doesn't send one, because it would
identify you.

## arXiv

Reads the papers on your arXiv author page, from its Atom feed.

| Input | Example |
|---|---|
| Author page | `https://arxiv.org/a/chen_m_1` |
| Handle | `arxiv:chen_m_1` |

arXiv has no citation counts, so you get the paper list and the `papers` count. Papers are preprints unless the
feed carries a journal reference.

Because an arXiv author page is claimed by its owner, its proposals start with higher confidence than Semantic
Scholar's or OpenAlex's. The same goes for ORCID.

## ORCID

Reads the works on a public ORCID record through the [public ORCID API](https://pub.orcid.org).

| Input | Example |
|---|---|
| Record URL | `https://orcid.org/0000-0002-1825-0097` |
| Bare iD | `0000-0002-1825-0097` or `orcid:0000-0002-1825-0097` |

ORCID lists works but not citations. Works are classed by their ORCID type (journal article, conference paper,
preprint, working paper). Only works you've made public on your record are visible.

## Which ones to add

You don't need all four. A common setup:

- **ORCID** or **arXiv** for the list of works you've curated yourself.
- **Semantic Scholar** or **OpenAlex** for citation counts and h-index over time, on the
  [Metrics](../tour/metrics.md) page.

Citation numbers differ between databases. Use the same source consistently when you compare over time.
