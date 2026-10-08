# Letters

How to choose recommendation-letter writers and work with them so each letter is accurate and truly theirs.

This is practical guidance on using Area O1, not legal advice. Your attorney decides how many letters you need and from whom.

## Independent and collaborator writers

The Letters page records each writer's relationship to you: **independent**, **employer** or **co-author**. Its coverage table counts writers per criterion in those three columns, so you can see at a glance where you rely only on people who worked with you.

- **Independent writers** know your work through its impact (they used your project, cited your paper, judged you at an event) without having worked alongside you. Their letters show recognition beyond your own circle.
- **Collaborators** (employers, managers, co-authors) can speak to details nobody else knows: what you built, what your role was, what happened because of it.

Most files benefit from both. Ask your attorney for the mix that fits your case.

## Track each writer

For each writer, add their name, credentials and relationship, and the criteria their letter should cover. Then keep the status current as things move: prospect, asked, drafting, sent, signed or declined. Set **Last contact** when you talk to them, so the follow-up reminders stay accurate.

If you imported your chats, a line like "I asked Dr. … for a letter" shows up as a suggestion in your Inbox. It's self-reported, so confirm it before you rely on it.

## Draft from approved claims

**Draft from claims** writes a starting draft from your **approved** claims only, for the criteria the writer covers. Claims still waiting for review, and claims in conflict, are left out. The drafting code is in [areao1/criteria/letters.py](https://github.com/ris3abh/areao1/blob/main/areao1/criteria/letters.py).

- Every sentence that states a fact ends with the ids of the claims it rests on, in square brackets, and the sources are listed at the end. A sentence that cites no approved claim is dropped.
- Where only the writer can speak (how they know you, their own judgment), the draft leaves a placeholder such as `[WRITER: how you worked together]`.
- The draft never says you qualify, meet a criterion or will be approved. Sentences like that are removed.
- With an OpenAI key connected, the agent writes the draft from those claims and nothing else. Without one, you get a plain template that lists the facts.

Drafts are saved in your workspace under `drafts/letters/`. **Redraft** writes a new one after you approve more claims.

So approve the claims you want a writer to mention first. Review them in the Inbox before you draft.

## The writer rewrites and signs

A draft is a set of facts with citations, not a finished letter. Area O1 never signs or sends anything as the writer.

1. Click **Send to** (the writer's last name). This puts an email from you, with the draft, on the Contacts page.
2. Read it, edit it, then press **Approve & send** (see [Outreach etiquette](outreach.md)).
3. The writer rewrites it in their own words, fills in the placeholders, and signs it on their own letterhead.
4. When it's done, mark it **Mark signed** and upload the signed letter as an exhibit.

Some habits that help:

- Tell the writer plainly that the draft is a list of facts to save them time, and that they should change anything they don't agree with.
- Never send a letter "as" someone, or sign for them, even if they say it's fine.
- Keep the facts checkable. Each fact in the letter should match a document in your file, and the claim ids show you which one.
- Keep the placeholders visible until the writer fills them. Don't fill in their opinion for them.

## Citing facts

When the writer rewrites, the claim ids don't need to stay in the final letter, but the facts should stay accurate. Before it's signed, compare the numbers and dates in the letter against the claims and the source documents. If a writer wants to add a fact that isn't in your file, add the document that supports it.
