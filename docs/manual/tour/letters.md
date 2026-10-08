# Letters

Your recommendation letter writers, what each one covers, and where each letter stands.

![The Letters page with one independent writer covering Judging, and coverage by criterion](../assets/shots/letters-light.webp#only-light)
![The Letters page with one independent writer covering Judging, and coverage by criterion](../assets/shots/letters-dark.webp#only-dark)


## Writers

Add a writer with their name, credentials and relationship (**independent**, **employer** or
**co-author**). For each one, track what you asked for (a letter, a membership reference), the status, and
when you last spoke. **Mark sent** and **Mark signed** move the letter along.

**Coverage by criterion** counts your writers per criterion and relationship, so you can see where you have
no independent voice yet. Declined writers are left out.

## Draft from claims

**Draft from claims** writes a draft for the writer to review, rewrite and sign:

- It uses **approved claims only**, and every factual sentence ends with the ids of the claims it rests on;
  the sources are listed at the end.
- Sentences that cite nothing approved are dropped, and so is any sentence about eligibility or approval.
- Where only the writer can speak (how they know you, their own judgment) there's a bracketed placeholder.
- It ends with "Sincerely," and a placeholder for the writer's signature. Area O1 never signs anything.

With an AI connected, the hard model tier writes the draft from the claims; without one, a plain template
lists the facts. The draft is saved to `drafts/letters/<writer>.md`.

**Send to the writer** puts an email from you, with the draft (citations removed) and a note asking them to
rewrite it in their own words, into Contacts for your **Approve & send**. The writer has to be a contact with
an email address.

See [Letters best practices](../best-practices/letters.md).
