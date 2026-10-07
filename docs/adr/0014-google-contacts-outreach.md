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

## Amendment (2026-10-07): Gmail with an app password, the OAuth client only for Google Calendar

Creating a Google Cloud project, a consent screen and a test user (and publishing it so tokens last more than 7
days) is too much to ask before email works. So email signs in the way mail apps do:

- **Default: an app password.** Settings > Google > *Connect Gmail* asks for your Gmail address and a
  16-character app password (2-Step Verification on, then https://myaccount.google.com/apppasswords). Area O1
  checks it with one IMAP login before keeping it, in the OS keychain only (`google:app-password`), and says
  plainly what went wrong: a wrong password, your normal password instead of an app password, 2-Step
  Verification off (Google offers no app passwords then), or IMAP turned off in Gmail's settings.
- **Reading: IMAP** (`imap.gmail.com`, SSL), mailbox opened read-only, searched with Gmail's own search
  (`X-GM-RAW`) for your contacts' addresses only, and fetched as **headers only**
  (`BODY.PEEK[HEADER.FIELDS (...)]`, which also leaves mail unread). Threads are grouped by Gmail's thread ID.
  There is no snippet: IMAP has none without reading the body, so §2's one-line snippet stays empty.
- **Sending: SMTP** (`smtp.gmail.com`, SSL) with the same password, only from Approve & send, within the daily
  limit, to an address still on the contact. A follow-up replies in the thread (`In-Reply-To`).
- **Opportunity mail (Part F)** keeps its own rule: bodies are read in memory only, and only the facts and one
  quoted sentence are kept.
- **An app password can do more than OAuth scopes would** (full mail access over IMAP and SMTP). The limits are
  Area O1's code (the rules above, enforced by tests), not Google's scopes; you can revoke the password at any
  time at the same page, and Disconnect forgets it here (Google has no API to revoke it for you).
- **The OAuth client is optional**: *Advanced: also sync Google Calendar*. Without it, deadlines still live in
  Area O1's Calendar page and `calendar.ics`, which calendar apps on this computer (Apple Calendar, Outlook) can
  follow one way with the *Subscribe link*. Google Calendar fetches subscriptions from Google's servers, which
  can't reach `127.0.0.1`, so following deadlines there needs the optional client. A Gmail sign-in made through OAuth before this amendment keeps working;
  when both exist, the app password is used for mail.

## Consequences

- Email needs only an app password; the calendar's two-way sync still needs your own client. Every part is
  optional and off by default.
- Area O1 can act as you only in one way (sending a draft you approved) and see only mail with your contacts.
- Tests use recorded Google responses and fake IMAP and SMTP servers; no test reaches Google.
