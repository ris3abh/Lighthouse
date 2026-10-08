# .eml and forwarded mail

Bring in emails from any account as `.eml` files, or forward them as attachments to your connected Gmail, and
Area O1 checks who really sent them.

This is how evidence from a mailbox Area O1 isn't connected to (a work account, an old university address) gets
into your case: an invitation to judge, a thank-you for reviewing, an award notice.

!!! warning "Check your employer's email policy first"
    Many employers don't allow forwarding work mail to a personal account. Bring in only emails about your own work
    and recognition, never confidential business mail.

## Two ways in

### Drop `.eml` files

Save the email as an `.eml` file and drop it (or several at once) on any of these:

| Where | What happens |
|---|---|
| **Evidence** page | Uploaded like any file; emails get the sender check and a suggested criterion |
| **Inbox** | The same, from the Inbox's drop area |
| **Contacts > Mail** | The Mail view's drop area; accepts only `.eml` files |

How to get an `.eml` file:

- **Gmail**: open the message, then More (⋮) > *Download message*.
- **Outlook on the web**: save or download the message as `.eml`.
- **Apple Mail**: File > Save As, format *Raw Message Source*.
- **Outlook for Windows** saves `.msg` files, which Area O1 can't read. Use forward as attachment instead.

Files can be up to 25 MB each.

### Forward as attachment

If Gmail is connected, forward the message **as an attachment** to that Gmail address. In Gmail: More (⋮) >
*Forward as attachment*. Outlook and Apple Mail call it *Forward as Attachment* too.

Then press **Refresh mail** in Contacts > Mail. The forward is shown as the **original** message: its sender, its
subject and its sender check (the forward's own headers only prove who forwarded it). Press **Import original** to
send it to your Inbox with the original file.

!!! note "A plain Forward isn't enough"
    A normal **Forward** copies the text but drops the original headers, so the sender can't be verified. Use one
    of the two ways above.

## The sender check

Area O1 reads the receiving mail server's verdict from the original headers (the topmost
`Authentication-Results`, or `ARC-Authentication-Results` when that's all there is). It doesn't contact anyone to
do this.

| Result | When | What you see |
|---|---|---|
| **Verified** | DMARC passed, or DKIM passed for the sender's own domain | *Verified sender (DMARC passed, checked by mx.example.com)* |
| **Failed** | DMARC, DKIM or SPF explicitly failed, or DMARC said quarantine or reject | *Sender authentication failed (DMARC fail)* |
| **Unverified** | The headers carry no authentication results | *Sender not verified (no authentication results in the original headers)* |

"The sender's own domain" means the organizational domain: a DKIM signature from `mail.example.edu` counts for a
sender at `example.edu`.

Unverified isn't the same as fake: older messages and some mail systems don't record results. A failed check is a
reason to be careful; the daily opportunity check marks such a find suspicious and drafts nothing.

## What the Inbox candidate says

Each email becomes one Inbox candidate with:

- **A summary**: who sent it and when, the sender check, the most telling sentence from the message, and why it
  was sorted where it was.
- **A suggested criterion**, from the same rules as the Mail view:

    | Sorted as | Suggested criterion |
    |---|---|
    | Judging & hackathons | Judging |
    | Reviewer requests | Judging |
    | Awards & memberships | Awards (or Membership when the subject mentions membership) |
    | Press & media | Press |
    | Anything else | None: you choose |

- **A stage**, described below.
- **The facts**: sender address, date, the sender-check result, which server checked it, the file name and size.

A verified sender gives the candidate higher confidence. Accepting the candidate files the original `.eml` as the
exhibit, so the headers travel with your evidence.

## Invited vs completed

An invitation is not a completion. Area O1 reads the text and marks an email:

- **Completed** only when it says so explicitly: "thank you for judging", "your review has been submitted", a
  certificate of appreciation, "you have been selected as", "congratulations on winning", "we are pleased to
  confirm that you".
- **Invited** otherwise.

For judging, reviewing and invitations, that's the stage you see. For awards and memberships, only an explicit
confirmation sets the stage to *granted*; otherwise it's left for you to set.

Only completed, published or granted evidence counts toward a criterion. An invitation to judge is worth keeping
(it may lead to the real thing), but it doesn't count by itself. Ask the organizer for a confirmation or
thank-you once you've done it. See [Invited vs completed](../how-it-works/invited-vs-completed.md).
