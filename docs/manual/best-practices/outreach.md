# Outreach etiquette

How Area O1 sends email on your behalf, and how to use it without wearing out the people you write to.

## Nothing goes out without you

Area O1 writes **drafts**: yours, the agent's, the follow-up job's, a letter draft for a writer, or a check-in to an event organizer. Drafts wait on the Contacts page. Nothing is sent until you press **Approve & send**.

1. Open Contacts and read the draft in full.
2. Edit the subject and body until it sounds like you.
3. Press **Approve & send**.
4. For the next 10 seconds you can press **Undo send** to stop it. After that it's sent from your Gmail.

Rules are checked the moment you approve, so a refusal shows right away instead of after the undo window:

- Email goes only to your case contacts, at an address saved on the contact.
- Gmail must be connected (Settings > Gmail).
- You must be under today's send limit.

If Gmail doesn't accept a send, the email stays a draft and the failure is listed on Contacts.

## The daily send limit

By default Area O1 sends at most 10 emails a day. The Contacts page shows how many went out today. The limit is `outreach.daily_limit` in `areao1.yaml` (0 to 100). When you reach it, the message says the limit resets tomorrow.

```yaml
outreach:
  daily_limit: 10
  follow_up_days: 7
```

Keep it low. A limit you never hit is a good sign.

## Follow-ups

When you wrote last in a thread with a contact and they've been quiet for `outreach.follow_up_days` days (7 by default), the `google` job drafts one short follow-up in the same thread. There's at most one follow-up draft per message of yours, and it's a plain template: make it personal before you approve it, or delete it.

- One gentle follow-up is usually enough. If there's still no answer, let it go or try another way to reach them.
- A deadline is a fair reason to follow up sooner. Say what you need and by when.

## Check-ins to organizers

When the daily opportunity check finds an invitation it can't confirm, it drafts a short check-in to the organizer and adds them to Contacts. When the sender looks suspicious (a failed sender check or a look-alike domain), nothing is drafted, so you never confirm a phisher's address. See [Daily opportunity check](../how-it-works/opportunities.md).

Before approving a check-in:

- Make sure the invitation is one you'd accept if it's real.
- Keep it short: who you are, which event, and a simple question.
- Don't send a check-in for every newsletter or platform digest.

## Respect people's time

- Write to people you have a real reason to contact. Area O1 only writes to case contacts, but who counts as a contact is up to you.
- Ask for one thing per email, and make it easy to say no.
- Thank people when they help, whether or not it counts for your case.
- Never ask someone to judge, review or write for you just to fill a criterion. Ask because the work is real.
- Keep letters, asks and follow-ups in Area O1 so you don't write to the same person twice by accident.
