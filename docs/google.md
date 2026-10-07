# Connecting Google

Area O1 uses **your own** Google OAuth client (ADR 0014). It ships no client and runs no server: you sign in in
your browser, Google sends you back to `127.0.0.1` on your computer, and the tokens go into your OS keychain.

## 1. Create the client (about five minutes)

1. Open [console.cloud.google.com](https://console.cloud.google.com/) and create a project, for example
   "Area O1 (personal)".
2. **APIs & Services > Library**: enable the **Gmail API** and the **Google Calendar API**.
3. **OAuth consent screen**: choose **External**, name the app "Area O1 (personal)", use your own email for the
   support and developer contacts, and add yourself under **Test users**.
4. **Credentials > Create credentials > OAuth client ID**, application type **Desktop app**. Copy the client ID
   and the client secret.
5. In Area O1: **Settings > Google**, paste both, tick what Area O1 may do, and press **Connect Google**.

## 2. What each permission allows

| You tick | Google scope | What Area O1 can do with it |
|---|---|---|
| Threads with your case contacts | `gmail.readonly` | search for mail to or from your contacts; it keeps only each thread's subject, who, when and a one-line snippet |
| Send drafts you approved | `gmail.send` | send a draft you approved, as you; it can't read, change or delete mail with this scope |
| A dedicated Area O1 calendar | `calendar.app.created` | create one calendar and sync your deadlines with it; your other calendars stay invisible |

You can tick more later; Google asks only for what's new. **Disconnect** revokes the access with Google.

## 3. Testing vs. production

While your consent screen is in **Testing**, Google's refresh tokens expire after **7 days**, so you'd sign in
again every week. To stop that, publish the app: **OAuth consent screen > Publish app > In production**.

- You don't need Google's verification for a client only you use. When you sign in you'll see "Google hasn't
  verified this app"; that's expected for your own client. Choose **Advanced > Go to Area O1 (personal)**.
- Gmail scopes are "restricted": an unverified app in production is limited to 100 users, which is plenty for one.

## 4. Turning it off

Settings > Google > **Disconnect** revokes the token with Google and deletes it from your keychain. To remove
everything, also delete the OAuth client in your Google Cloud project.
