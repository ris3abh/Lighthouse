# Calendar

Deadlines and pipeline follow-ups in one place, and as a calendar feed for the app you already use.

![The Calendar page: October with deadlines and follow-ups, an Add a deadline form and the upcoming list](../assets/shots/calendar-light.webp#only-light)
![The Calendar page: October with deadlines and follow-ups, an Add a deadline form and the upcoming list](../assets/shots/calendar-dark.webp#only-dark)


## What's on it

- A **month** or **week** view. Click a deadline to edit it, or drag it to another day. Follow-ups from the
  [Pipeline](pipeline.md) appear with a dashed outline.
- **Add a deadline**: a title, a date and a kind (filing, application, submission, follow-up, personal or
  other).
- **Upcoming**: days left for each open deadline. Tick one to mark it done.
- **Recurring jobs**: when the scheduled jobs run next.

## Reminders

The `deadline-check` job (daily at 07:00) notifies you 14, 3 and 1 days before a deadline, on the day, and
when it's overdue.

## Subscribe from your calendar app

`data/calendar.ics` in your workspace updates with every change.

- **Subscribe link** copies `webcal://127.0.0.1:7777/calendar.ics`, which Apple Calendar, Outlook and
  Thunderbird on the same computer can subscribe to while `areao1 up` is running.
- **.ics** downloads the file. Google Calendar can't reach your computer, so import the file there.
