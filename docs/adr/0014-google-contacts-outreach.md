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

## Consequences

- Nothing Google-related works until you create a client; every part of it is optional and off by default.
- Area O1 can act as you only in one way (sending a draft you approved) and see only mail with your contacts.
- Tests use recorded Google responses; no test reaches Google.
