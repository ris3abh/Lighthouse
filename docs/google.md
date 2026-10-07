# Connecting Google

Email needs only an **app password**: no Google Cloud project, no consent screen, no test users (ADR 0014 and
its amendment). Two-way Google Calendar sync is optional and is the only part that needs your own Google client.

## 1. Connect Gmail (about two minutes)

1. Turn on **2-Step Verification** for your Google account at
   [myaccount.google.com/signinoptions/twosv](https://myaccount.google.com/signinoptions/twosv), if it isn't on
   yet. Google offers app passwords only with it on.
2. Create an **app password** at [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords).
   Name it "Area O1". Google shows 16 letters, once.
3. In Area O1: **Settings > Google > Connect Gmail** (or the Email step of onboarding), paste your Gmail address
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
- **Opportunity mail** (the daily opportunity job, coming next): bodies are read in memory only; Area O1 keeps
  only the facts and one quoted sentence.
- **Sending**: only when you press **Approve & send** on a draft, from your Gmail (it shows up in Sent), to an
  address still on the contact, and at most 10 a day (Settings: `outreach.daily_limit`). Agents and autopilot
  can't send. Follow-ups after 7 quiet days are drafts for you to approve, never sent on their own.

## 3. Turning it off

**Settings > Google > Disconnect** forgets the app password on this computer. Google has no way for an app to
revoke an app password, so also remove it at
[myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords).

## 4. Advanced: also sync Google Calendar

Without this, your deadlines live on the **Calendar** page and in `data/calendar.ics`. Calendar apps on this
computer (Apple Calendar, Outlook, Thunderbird) can follow them one way with the **Subscribe link**
(`webcal://127.0.0.1:<port>/calendar.ics`). Google Calendar fetches subscriptions from Google's servers, which
can't reach your computer, so to see deadlines there you need two-way sync with your own Google client:

1. Open [console.cloud.google.com](https://console.cloud.google.com/) and create a project, for example
   "Area O1 (personal)".
2. **APIs & Services > Library**: enable the **Google Calendar API**.
3. **OAuth consent screen**: choose **External**, name the app "Area O1 (personal)", use your own email for the
   support and developer contacts, and add yourself under **Test users**.
4. **Credentials > Create credentials > OAuth client ID**, application type **Desktop app**. Copy the client ID
   and the client secret.
5. In Area O1: **Settings > Google > Advanced: also sync Google Calendar**, paste both, tick the calendar and
   press **Connect Google Calendar**.

Area O1 asks only for `calendar.app.created`: it creates one calendar named "Area O1" and syncs your deadlines
with it, both ways. Your other calendars stay invisible to it. The latest edit wins, and every change from Google
is logged and can be undone.

**Testing vs. production.** While your consent screen is in **Testing**, Google's refresh tokens expire after
7 days, so you'd connect again every week. To stop that, choose **OAuth consent screen > Publish app >
In production**. You don't need Google's verification for a client only you use; when you sign in you'll see
"Google hasn't verified this app", which is expected. Choose **Advanced > Go to Area O1 (personal)**.

**Disconnect** in that section revokes the calendar access with Google and deletes the token from your keychain.

A Gmail connection made through this client before app passwords were the default keeps working. When both
exist, Area O1 uses the app password for mail.
