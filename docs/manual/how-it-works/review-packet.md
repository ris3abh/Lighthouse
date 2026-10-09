# The review packet

**Build review packet** organizes your case for your attorney to review: numbered exhibits, every approved fact
matched to the page that shows it, a starting outline, and the open preflight issues. It is never a petition. Every
page and every generated paragraph is labeled "Draft for attorney review", and nothing in it says whether you
qualify.

## Build one

On [Evidence](../tour/evidence.md), the **Review packet** panel has **Build review packet**. Or, from a terminal:

```sh
areao1 packet
```

The build takes a few seconds. The panel then shows the latest build (pages, numbered exhibits, cited claims, open
preflight issues, its date and input hash) with four downloads: **Review PDF**, **Editable .docx**, **Attorney
export (ZIP)** and **Matrix (CSV)**.

## What's in it

| Section | What it holds |
|---|---|
| Cover | Your name, the profile, the date, the counts and the input hash. |
| Contents | Each section's page. |
| Exhibit index | Exhibits by criterion: number, title, date, type, stage and page range in the PDF. |
| Claim, exhibit, page and quote | Every approved fact an exhibit cites, the exhibit, the page its quote is on, and the quote. |
| Outline | One sentence per approved fact, each ending with its exhibit and a footnote. |
| Final merits | The themes and the standard from [Final merits](../tour/merits.md). |
| Open preflight issues | What [preflight](preflight.md) found and you haven't dismissed. |
| Exhibits | Each exhibit behind a cover sheet: PDFs as they are, images placed on a page, text captures typeset. |

The PDF numbers its pages straight through, exhibits included ("Page 12 of 140").

### Exhibit numbers

Counted exhibits are numbered per criterion: `C<n>-<nn>`, where `n` is the criterion's place in your profile
(Awards is C1 in O-1A) and `nn` is the exhibit's order within it, by date and then title. Only counted exhibits
get a number. Self-reported material (your notes, chat history) never enters the packet as evidence.

### The matrix finds the page

For each approved fact, Area O1 searches the exhibit's text for the quote and gives the page it's on, in the
exhibit and in the packet. If the quote isn't in the text (a scan, a photo), the matrix says "not found". It
never guesses a page.

A fact that was later replaced by a newer value isn't listed. Preflight still flags an exhibit that cites the
old value.

### The outline

The outline is a starting point for your attorney to rewrite. It is drafted only from approved, current facts,
one sentence each, from a template for the exhibit's evidence type. It goes criterion by criterion, then exhibit
by exhibit (each under its number and title): the exhibit's main fact first, then its figures, then the supporting
details.

> Maya received the Northwind Engineering Excellence Award in May 2024 (Exhibit C1-01).¹
>
> Acme Robotics runs FastQueue, as captured on September 15, 2025 (Exhibit C5-01).²

A template keeps the source's words. It is used only when its verb is in the quote, and it writes that verb: an
exhibit that says "adopted" reads "adopted", never "uses". The person, the organization and the value it names must
be in the quote too. A date reads as the quote states it ("in May 2024"); when the quote gives no date, the sentence
says when the exhibit was captured ("as captured on September 15, 2025") rather than implying when it happened.

When no template fits the quote (a detail such as "3 of 412 nominees", or a quote that says it another way), the
sentence quotes the exhibit instead:

> Exhibit C1-01 states: “The jury selected 3 recipients from 412 nominees.”³

Each footnote says where the fact is: the exhibit, its page, the packet page and the quote. In the .docx these
are ordinary Word footnotes. Any sentence that reads as an eligibility verdict is dropped, even when it's a quote.

Claim ids don't appear in the PDF or the .docx. The full ids are in `matrix.csv` (and in the provenance files),
so anyone can trace a sentence back to its source.

## The files

Each build goes to its own folder in your workspace, `exports/packet-<date>-<hash>/`:

| File | What it is |
|---|---|
| `packet.pdf` | The review PDF, exhibits included. |
| `packet.docx` | The front matter as an editable Word document, the label in its header and page numbers in its footer. |
| `matrix.csv` | The matrix, one row per fact, with the full claim id, the quote and the sentence. |
| `preflight.json` | Every open preflight issue. |
| `provenance.json` | The cited claims, their observations, decisions and links. |
| `provenance.prov.json` | The same, as W3C PROV-JSON. |
| `manifest.json` | The build: input hash, exhibits and page ranges, counts, and each file's SHA-256. |
| `attorney-export.zip` | All of the above plus the original exhibit files, named by exhibit number. |

## Same inputs, same files

Building twice with nothing changed gives byte-identical files in the same folder. The date inside the files is
the date of your latest review decision, not the clock, and the folder name ends with the first eight characters
of the input hash. Accept an exhibit or approve a fact, and the next build gets a new folder; earlier builds stay
in `exports/`.

A packet is a snapshot. It doesn't change when your workspace does, so build a new one before you send it.

## What it isn't

The packet doesn't file anything, doesn't decide which criteria you meet, and isn't legal advice. It puts your
evidence in the order an attorney would look for it, with every fact traceable to its document. See
[ADR 0020](https://github.com/ris3abh/areao1/blob/main/docs/adr/0020-review-packet.md) for the design.
