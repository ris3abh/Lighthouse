# Connecting Gmail

Area O1 connects to Gmail with an **app password**, the way mail apps do (ADR 0014 and its amendment). Gmail is
the only Google service it uses.

## 1. Connect Gmail (about two minutes)

1. Turn on **2-Step Verification** for your Google account at
   [myaccount.google.com/signinoptions/twosv](https://myaccount.google.com/signinoptions/twosv), if it isn't on
   yet. Google offers app passwords only with it on.
2. Create an **app password** at [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords).
   Name it "Area O1". Google shows 16 letters, once.
3. In Area O1: **Settings > Gmail** (or the Email step of onboarding), paste your Gmail address
   and the app password, and press **Connect Gmail**.

Area O1 checks the password with one sign-in to `imap.gmail.com` and keeps it in your OS keychain, never in your
workspace.

### If it doesn't connect

| Area O1 says | What to do |
|---|---|
| Gmail didn't accept that app password | Check the address; create a new app password and paste it right away |
| That's your normal Google password | Use an app password (step 2), not the password you sign in with |
| An app password is 16 letters / 2-Step Verification is off | If the App passwords page says the setting isn't available, turn on 2-Step Verification first (step 1) |
| IMAP is turned off for this Gmail account | Gmail > Settings > See all settings > Forwarding and POP/IMAP > Enable IMAP. On a work or school account, your admin may need to allow it |
| Google wants you to sign in once in your browser | Open gmail.com in your browser, then try again |
| Couldn't reach Gmail | Check your internet connection |

## 2. What Area O1 does with it

An app password opens your whole mailbox over IMAP and SMTP; Google can't narrow it the way OAuth scopes do. The
limits are Area O1's own rules, each covered by tests:

- **Reading**: All Mail is opened read-only. Area O1 searches only for mail to or from the email addresses of your
  contacts, and fetches **headers only**: who, when, the subject and the Message-ID. It never fetches bodies or
  attachments, and nothing turns read. Each contact's last touch follows their newest thread.
- **The Mail view** (Contacts > Mail): case-relevant mail only, in seven categories (Invites, Judging &
  hackathons, Reviewer requests, Letter writers, Press & media, Awards & memberships, Other contact threads).
  Press **Refresh mail** to read the last 30 days (Promotions and Social skipped): headers, plus the first lines
  of new messages so they can be sorted. Rules sort first (your contacts, known organizer domains, subject
  keywords, and senders you taught by moving a message); only what's left goes to the small, cheap model tier,
  redacted. Area O1 keeps who, when and the redacted subject of case mail and nothing at all of the rest. Opening
  a message fetches its text from Gmail right then and never saves it. Still read-only: nothing turns read,
  moves, gets a label or is deleted in Gmail.
- **Opportunity mail** (the daily opportunity job, coming next): bodies are read in memory only; Area O1 keeps
  only the facts and one quoted sentence.
- **Sending**: only when you press **Approve & send** on a draft, from your Gmail (it shows up in Sent), to an
  address still on the contact, and at most 10 a day (Settings: `outreach.daily_limit`). Agents and autopilot
  can't send. Follow-ups after 7 quiet days are drafts for you to approve, never sent on their own.

## 3. Turning it off

**Settings > Gmail > Disconnect** forgets the app password on this computer. Google has no way for an app to
revoke an app password, so also remove it at
[myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords).

## 4. Calendars

Area O1 doesn't sync with Google Calendar. Your deadlines live on the **Calendar** page and in
`data/calendar.ics`. Calendar apps on this computer (Apple Calendar, Outlook, Thunderbird) can follow them with
the **Subscribe link** (`webcal://127.0.0.1:<port>/calendar.ics`). Google Calendar can't reach your computer,
so import the file there instead (Google Calendar > Settings > Import & export); re-import it when deadlines
change.
