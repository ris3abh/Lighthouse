# Evidence preflight

Preflight checks your exhibits, letters and drafts for what a reviewer would notice, so you can fix it before
anyone else reads the file.

## What it is

Preflight is a fixed set of rules that read your workspace files. It uses no AI model, so the same files always give
the same issues.

Each issue has a severity, a title in plain words, a detail line, and links to the exact claims, exhibits, letters
or drafts involved, with values and dates where they differ.

Severity says how likely a reader is to notice the issue. It says nothing about your case's chances: there is no
score and no probability.

## Run it

On the [Evidence page](../tour/evidence.md), press **Run preflight** in the **Preflight** panel (**Run again** after
the first time). The panel shows how many issues are open at each severity and how many exhibits and claims were
checked. The report is saved in `data/preflight.json`.

From the terminal, `areao1 preflight` runs the same checks, saves the same file and prints the open issues.

## Preflight never blocks anything

An open issue doesn't stop you from accepting, uploading, drafting a letter or building the review packet. It's a
list for you to read, not a gate.

## The rules

| Rule | Severity | What it means | What to do |
|---|---|---|---|
| Outdated value cited | high | An exhibit, letter or draft cites a value that a newer one replaced, such as 1,840 stars when memory now says 2,100. | Update the document to the current value, or keep it and make sure it's dated. |
| Unsupported claim cited | high | A letter or draft cites a claim that isn't approved, or doesn't exist in memory. | Approve the claim in the Inbox or Memory, or redraft without it. |
| Facts disagree (names) | high | Approved claims give different names for the same person or organization. | Find which document is wrong and correct it. |
| Facts disagree (titles, employers, dates) | medium | Approved claims give different job titles or employers for the same subject, the same event has two dates, or an exhibit's date is more than three days from the event its source describes. | If it changed over time, that's fine: make sure each document is dated. Otherwise fix the wrong one. |
| Metric differs | medium | Documents cite different values of the same metric. Both values are shown with their dates. | Use one dated value, or say each document's date. |
| Invited, not completed | medium | An exhibit is at `invited` with no matching completed exhibit, or an activity at `accepted` has no completion proof linked in its [proof checklist](proof-recipes.md). | Save the thank-you, certificate or program once it's done. |
| No primary copy | medium | An exhibit is only a capture (`.md`, `.html`, `.htm` or `.txt`) with no PDF, image, `.eml` or `.docx` copy from the same address or linked to it. | Save the page or email as a PDF (or the original `.eml`) and upload it. |
| Fact without an exhibit | low | An approved, current claim that no exhibit cites. One issue per person or entity. | File the primary document behind it. |
| No document date | low | An exhibit's date is unconfirmed, or is only the day it was filed with no dated claim behind it. | Set the date the document shows (**Set date** or **Change date** on the exhibit), or run `areao1 repair-dates`. |

Names, titles and employers are compared after normalizing case, punctuation, company suffixes and common
abbreviations, so "Sr. Engineer" and "Senior Engineer" don't conflict.

## Reading the panel

Issues are sorted high, then medium, then low. Low-severity issues are hidden until you press **Show N low-severity
issues**. Each issue shows up to five links; **+N more** shows the rest. A link opens the claim in Memory, the
exhibit's criterion on Evidence, the Letters page, or the proof checklist.

## Dismiss an issue

If an issue isn't a problem, press **Not a problem…**, say why, and press **Dismiss**. The reason is required.

A dismissed issue stays in `data/preflight.json` and is listed under **Show N dismissed issues** with your reason.
A later run keeps the dismissal as long as it finds the same issue: the same rule about the same document, person or
exhibit. A different issue, even a similar one, shows up open.

## Where issues show up

- the **Preflight** panel on Evidence,
- `areao1 preflight` in the terminal,
- the `run_preflight` tool, for the in-app agent and [MCP clients](../mcp/tools.md#run_preflight): it checks fresh
  and is read-only, so it saves nothing,
- the [review packet](review-packet.md).

## In the review packet

The packet always includes the open issues, so your attorney sees what you saw. Building the packet runs the checks
fresh and leaves out the issues you dismissed.

In the packet's PDF and `.docx`, a low-severity rule with more than three issues becomes one row, "N similar
issues", naming the first three. The packet's `preflight.json` keeps every open issue in full.

The design is recorded in
[ADR 0018](https://github.com/ris3abh/areao1/blob/main/docs/adr/0018-evidence-preflight.md). Whether the evidence
is enough is for your attorney to assess. See the [legal disclaimer](../reference/disclaimer.md).
