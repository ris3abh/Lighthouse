# 0014. Google, contacts and outreach

- Status: accepted
- Date: 2026-10-07
- Phase: Part E (E1–E5)

## Context

A case runs on relationships: letter writers, organizers who invite you to judge, editors, collaborators. Today
Area O1 knows their names (Letters, Pipeline, chat imports) but not when you last spoke, what you asked for, or
when to follow up, and its deadlines don't reach the calendar you actually look at. Connecting Google closes that
gap, but it also means reading your mail and acting as you, so the limits come first.

## Decision

### 1. Your own Google client, the narrowest scopes (E1)

- **Your OAuth client, not ours.** You create a Desktop-app OAuth client in your own Google Cloud project and paste
  its ID and secret into Settings. Area O1 ships no client and no server: sign-in runs in your browser with PKCE and
  a loopback redirect to `127.0.0.1`, and Google talks to your computer only.
- **Scopes, each asked for only when you turn its feature on:**

  | Feature | Scope | Why this one |
  |---|---|---|
  | Contacts' threads | `gmail.readonly` | the narrowest scope that can search mail by participant |
  | Sending approved drafts | `gmail.send` | send only: it can't read, change or delete anything |
  | Calendar | `calendar.app.created` | only calendars Area O1 creates; your other calendars stay invisible |

- **Tokens** (client secret, refresh token) live in the OS keychain, never in the workspace. Disconnecting revokes
  the token with Google and deletes it locally.
- **Production mode.** A client in Google's "Testing" mode gets refresh tokens that expire after 7 days. The docs
  explain publishing your own client to "In production" for personal use (you'll see Google's unverified-app
  screen, which is expected for a personal client), and that nothing about Area O1 needs Google's verification.

### 2. Gmail: only threads with your case contacts (E2)

Area O1 searches Gmail for messages to or from the email addresses of people in your contacts (E4), and nothing
else. For each thread it keeps the thread ID, subject, the participants who are your contacts, the date and sender
of the last message, and a one-line snippet, redacted like everything else that reaches a model. No bodies, no
attachments, no other mail. Each contact's last-touch date comes from these threads.

### 3. Two-way sync with a dedicated calendar (E3)

- Area O1 creates one calendar named "Area O1" and syncs deadlines with it, both ways: a deadline becomes an
  all-day event (tagged with its ID), and an event you add, move, rename or delete there changes the deadline.
- **Latest edit wins**, compared by the event's `updated` time and the deadline's last change. Every change from
  Google goes through the service layer as `google-calendar`, is logged, and can be undone like any other.
- Sync uses Google's sync tokens, so each run fetches only what changed. Nothing outside that calendar is read.

### 4. Contacts (E4)

A Contacts page lists people: name, emails, organization, relationship, the letters and pipeline items they're
linked to, their threads, what you've asked of them, last touch and next follow-up. People come from letter
writers, pipeline items, accepted chat-import suggestions and what you add. Contacts are self-reported tracking:
they never count toward a criterion.

### 5. Outreach: drafted, approved, sent (E5)

- The agent can draft an email to a contact (an ask, a thank-you, a follow-up). A draft never sends itself:
  you approve, edit or reject it, and only an approval sends it from your Gmail with `gmail.send`.
- **Case contacts only**: the recipient must be a person in your contacts, and the draft goes through the same
  guardrails and rule check as other petition-facing text.
- **Daily send limit** (default 10, in Settings), checked at approval.
- **Follow-ups**: when you wrote to a contact and 7 days pass without a reply, a daily job drafts a follow-up
  for your approval. It never sends one on its own, and it drafts at most one per thread.

## Amendment (2026-10-07): Gmail only, with an app password; Google Calendar sync dropped

- Status of §1 and §3: **superseded**. §2, §4 and §5 stand, with Gmail reached as below.

Creating a Google Cloud project, a consent screen and a test user (and publishing it so tokens last more than 7
days) is too much to ask, and two-way calendar sync was the only thing that still needed it. So Google is now
Gmail only, signed in the way mail apps do:

- **Removed: the OAuth client flow and Google Calendar sync** (sign-in, scopes, tokens, the dedicated "Area O1"
  calendar and its sync state). The local Calendar page and `calendar.ics` stay as they were; calendar apps on
  this computer can follow the `.ics` with the subscribe link, and Google Calendar can import the file. A client
  or token saved before this is removed from the keychain on the next start (a token is revoked with Google
  first, best effort). A workspace's old `data/google-calendar.json` is left alone and no longer read.
- **Connect Gmail (Settings > Gmail)** asks for your Gmail address and a 16-character app password
  (2-Step Verification on, then https://myaccount.google.com/apppasswords). Area O1 checks it with one IMAP
  login before keeping it, in the OS keychain only (`google:app-password`), and says plainly what went wrong: a
  wrong password, your normal password instead of an app password, 2-Step Verification off (Google offers no app
  passwords then), or IMAP turned off in Gmail's settings.
- **Reading: IMAP** (`imap.gmail.com`, SSL). All Mail is opened read-only, searched with Gmail's own search
  (`X-GM-RAW`) for your contacts' addresses only, and fetched as **headers only**
  (`BODY.PEEK[HEADER.FIELDS (...)]`, which also leaves mail unread). Threads are grouped by Gmail's thread ID.
  There is no snippet: IMAP has none without reading the body, so §2's one-line snippet stays empty.
- **Sending: SMTP** (`smtp.gmail.com`, SSL) with the same password, only from Approve & send, within the daily
  limit (10 by default), to an address still on the contact. Approve & send starts a 10-second Undo send window;
  sends run one at a time and re-read the draft, so a double click sends once. Every attempt is logged (time,
  recipient, Message-ID or error) and the daily limit counts sends Gmail accepted. A follow-up replies in the thread (`In-Reply-To`).
- **Opportunity mail (Part F)** keeps its own rule: bodies are read in memory only, and only the facts and one
  quoted sentence are kept.
- **An app password can do more than OAuth scopes would** (full mail access over IMAP and SMTP). The limits are
  Area O1's code (the rules above, enforced by tests), not Google's scopes. You can revoke the password at any
  time on the same page; Disconnect forgets it here (Google has no API to revoke it for you).

## Amendment (2026-10-07): the Mail view (read-only, case mail only)

Contacts gets a read-only **Mail** view: one contact's threads (sent and received), or all case-relevant mail,
in seven categories: Invites, Judging & hackathons, Reviewer requests, Letter writers, Press & media, Awards &
memberships, Other contact threads. This widens what Area O1 reads, so the rules are written down here:

- **What's read**: the last 30 days of All Mail except Gmail's Promotions and Social tabs, plus anything to or
  from a contact (300 newest per refresh). Headers for all of them; for messages not seen before, the **first
  2 KB of the text**, so the first lines can be sorted. All Mail is opened read-only and every fetch is a PEEK:
  nothing turns read, and nothing is moved, labelled, archived or deleted (tests fail on any other IMAP command).
- **Sorting is rules first**: a sender you taught by moving a message; a contact on the message (a letter writer
  goes to Letter writers); a known organizer or review-system domain; a keyword in the subject. Only what no rule
  decides goes to the **mundane tier**, and only with **model sorting** on (Settings > Gmail, off by default),
  with the sender, subject and first 300 characters, redacted like any
  model input, under the monthly cap, its cost recorded as a run. The model's answer can only be a category name
  or "none"; the prompt says the mail is data, not instructions, and any other answer counts as "none". With it off,
  or without a model (no key, or over the cap), undecided mail waits, unshown and unkept (only a count).
- **What's kept** (`data/mail.json`): for case-relevant mail only, who, when, the redacted subject, the category
  and why; for everything else, a one-way hash of the message ID so it isn't read twice. First lines are never
  kept. Everything outside the categories is never shown or stored.
- **Opening a message** fetches its text from Gmail then (PEEK), returns it as plain text (HTML turned into text,
  so nothing in it runs), with `Cache-Control: no-store`, and never writes it to disk. Only mail the view kept can
  be opened.
- **Moving** a message to another category, or hiding it ("Not case mail"), teaches a rule for that sender:
  their later mail goes there without the model, and their stored mail follows now.
- **Opportunity-looking mail** (Invites, Judging, Reviewer requests, Press, Awards) links to its Inbox candidate
  when one names the message or thread as its source, or has the subject as its title.

The contact threads of §2 (headers only) and the opportunity-mail rule (Part F) are unchanged.

## Consequences

- Gmail needs only an app password and is optional and off by default. Nothing in Area O1 needs a Google Cloud
  project; deadlines reach other calendars through `calendar.ics` only.
- Area O1 acts as you in one way only (sending a draft you approved). It reads headers of mail with your contacts;
  the Mail view also reads the first lines of recent mail to sort it and a message's text when you open it, and
  keeps only case-relevant headers.
- Tests use fake IMAP and SMTP servers; no test reaches Google.
