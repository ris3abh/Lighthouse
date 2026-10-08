# GitHub

The GitHub connector tracks your repositories' adoption (stars, forks, releases, traffic) and proposes your
widely used projects as evidence of original contributions.

## Add your account or a repo

Paste any of these on the **Sources** page, or pass it to `areao1 import`:

| Input | What it tracks |
|---|---|
| `https://github.com/mayachen` or `github:mayachen` | Every repo the account owns |
| `https://github.com/orgs/tidy-lab` or `https://github.com/tidy-lab` | The organization's repos |
| `https://github.com/mayachen/tidy-ml` or `github:mayachen/tidy-ml` | One repo |

Forks are skipped unless you set `connectors.include_forks: true` in `areao1.yaml`.

Public repos need no token. Without one, GitHub allows far fewer API requests an hour, so a large account may
hit the rate limit. Area O1 waits up to a minute and retries; if the limit lasts longer, it says how long and you
can try again later (or add a token).

## Private repos and traffic

To read private repos, or traffic for any repo, add a **read-only fine-grained personal access token**.

1. Open GitHub's new-token page. Area O1 links to it with the right permissions filled in (the Sources page's
   **Create one with minimum scopes** link, or the link `areao1 import --private` prints).
2. Under **Repository access**, choose the repos you want tracked.
3. Under **Repository permissions**, set:

    | Permission | Access | Why |
    |---|---|---|
    | Metadata | Read-only | Required by GitHub for any token |
    | Contents | Read-only | Private repos, their READMEs and releases |
    | Administration | Read-only | **Only if you want traffic** (views and clones) |

4. Generate the token and copy it.
5. Add it in one of these ways:
    - **Sources** page: press **Private repos? Add a read-only token**, paste it, then **Import**.
    - Command line:

        ```sh
        areao1 import https://github.com/mayachen --private
        ```

        It prints the token link and prompts for the token (hidden as you type).
    - From an environment variable: `areao1 import https://github.com/mayachen --token-env GITHUB_TOKEN`.

The token goes to your OS keychain under the name `github:<handle>`; `sources.json` stores only that name. To
replace it later, press **Re-auth** on the source.

!!! tip "Read-only only"
    Never give Area O1 a token with write permissions. It only ever reads.

## What it reads

For each repo:

| Metric | From |
|---|---|
| `stars`, `forks`, `watchers`, `open_issues` | The repo record |
| `contributors` | The contributor list (anonymous contributors included) |
| `releases` | The release list |
| `views`, `views_unique`, `clones`, `clones_unique` | Traffic, one row per day (needs a token with Administration read) |

Each snapshot is saved as an observation, with claims that quote the exact fields
(for example `"stargazers_count": 1840`).

### What it proposes

- **Open-source project** for *original contributions*, when a repo has at least 5 stars
  (`connectors.min_stars_for_candidate`). The candidate notes signals such as *widely adopted* (100+ stars),
  *used by others* (10+ forks) and *sustained activity* (3+ releases), plus language, topics and created date.
- **A paper**, for each arXiv link in the repo's README. A link doesn't prove authorship, so you confirm it. The
  same paper found by a scholarly connector is proposed only once.

## Traffic and the 14-day window

GitHub keeps traffic for only the last **14 days**. To build a longer history, Area O1 stores every daily point
it sees in `data/metrics.csv`.

The `metrics-snapshot` job does this. While `areao1 up` is running, it's scheduled on Mondays and skips unless 13
or more days have passed since the last snapshot, so it runs every other week, inside GitHub's window. You can
also run it by hand at any time:

```sh
areao1 run metrics-snapshot
```

If Area O1 isn't running for more than two weeks, the days in between are lost: GitHub no longer has them.
Adding a source also takes a snapshot right away (skip that with `--no-snapshot`).
