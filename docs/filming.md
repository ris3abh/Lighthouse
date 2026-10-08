# Filming the demo

A checklist for recording Area O1 with the fictional filming workspace. Everything in it is invented and it works
offline: Gmail is an in-memory fake, the AI is a scripted engine, the keychain lives in memory, and nothing leaves
the computer. It's a developer tool: it isn't part of the installed package.

## 1. Start the workspace

```sh
python scripts/film_demo.py            # builds ./film-maya and serves http://127.0.0.1:7920
python scripts/film_demo.py --rebuild  # start over (or type r and Enter in its terminal)
```

Keep that terminal visible to you (not on camera): the event keys below are typed there.

## 2. The window

- **Chrome in a clean profile** (Profile > Add, or a Guest window): no extensions, no history, no saved logins.
- **Hide the bookmarks bar**: `Cmd+Shift+B` (Windows/Linux: `Ctrl+Shift+B`).
- **Hide extension icons**: pin none in the puzzle menu.
- **Window size**: 1440 × 900 content area for a 2880 × 1800 (2×) recording, or 1920 × 1080 for 1080p. Zoom at
  100% (`Cmd+0`). Full screen (`Cmd+Ctrl+F`) hides the tab strip.
- **Phone shots**: DevTools device toolbar (`Cmd+Shift+M`), 390 × 844 (iPhone 14), then hide DevTools.
- **Desktop**: turn on Do Not Disturb, but allow notifications from Chrome and the terminal, so the opportunity
  notification shows and nothing else does. Hide desktop icons; use a plain wallpaper.

## 3. Theme and motion

- **Theme**: the sun / moon switch in the header. Dark looks best for Memory (its sky is dark in both themes);
  light reads best for Inbox and Letters. Pick one per scene and don't switch mid-take.
- **Motion**: make sure the computer's "Reduce motion" setting is off, or the stars won't fade in or twinkle and
  the replay jumps to the end.

## 4. Keys (type in the film_demo terminal, then Enter)

| Key | What happens | What to show |
|---|---|---|
| `j` | A judging invitation from Lakeside Hacks arrives in the fake Gmail; the daily opportunity check runs, confirms the event on its (stubbed) official page and files it **verified** | The desktop notification "New signal detected: Lakeside Hacks 2026, verified.", then Inbox (reload) with the verified chip |
| `u` | An invitation from a look-alike domain (Riverside Hack5) arrives; it comes out **suspicious**, nothing is drafted | Inbox: the suspicious chip and its note |
| `r` | Rebuild the workspace from scratch | Reload the page |
| `q` | Quit | |

## 5. Shot list

1. **Overview**: the scoreboard and briefing.
2. **Memory**: let the stars fade in ("Aligning the stars..." flashes first), press **Replay** to grow the case
   from 2024 to today, click a star to draw its trail back to the source.
3. Type `j`. **Notification**, then **Inbox**: the verified judging invitation, its sender check and the official
   page in its note.
4. **Ask** (`Cmd+K`): "Where do I stand?" The answer streams, its rule sentence gets the **verified** badge.
5. **Contacts**: the follow-up draft to Omar; **Approve & send**, then **Undo send** within ten seconds (it goes to the
   fake Gmail either way).
6. **Letters**: **Draft from claims** for Dr. Priya Natarajan, open the draft (every sentence cites its claims),
   **Send to Natarajan** (it waits for approval on Contacts).
7. **Contacts > Mail**: the categories, the sender badges, and the "Bring in emails from another account" guide.

## 6. After

Quit with `q`. Delete `./film-maya` when you're done; it's gitignored.
