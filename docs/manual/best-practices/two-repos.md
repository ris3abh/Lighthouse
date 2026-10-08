# Keep case and code apart

If you contribute to Area O1 and also use it for your own filing, keep two completely separate repositories.

Area O1's code is public. Your case is not. The two must never share a repository, a fork or a folder.

| Repo | What goes in it | Visibility |
|---|---|---|
| **Your fork of the app repo** | code, profiles, connectors, docs, fictional fixtures only | public |
| **Your case workspace** (created with `areao1 init`) | your evidence, letters, metrics, personal data | **private** |

## The rules

- **Never create your case workspace inside your fork.** Don't run `areao1 init` anywhere under your clone of the app repo.
- **Never copy case material into the fork.** That means filing documents, screenshots, real metrics and personal data, and it includes `examples/` and test fixtures. Fixtures use the fictional personas in `tests/fixtures/` only.
- **Make the workspace a fresh private repo, not a fork.** A GitHub fork of a public repo can't be made private.
- **Keep them in different folders**, for example `~/code/areao1` for the app and `~/my-case` for your case.
- **Check `git remote -v` before you push.** Make sure the case workspace points at your private remote and the fork points at your public one.

## Set it up

1. Clone the app repo somewhere for code only:

    ```sh
    git clone https://github.com/<you>/areao1 ~/code/areao1
    ```

2. Create your case workspace in a separate folder (or keep the default `~/AreaO1`):

    ```sh
    areao1 init ~/my-case --name "Your Name"
    ```

3. If you want a backup, create a new **private** repository on GitHub (not a fork), then commit and push the workspace to it. Area O1 doesn't commit for you, so commit whenever you want a backup point:

    ```sh
    cd ~/my-case
    git add -A && git commit -m "Case backup"
    git remote add origin git@github.com:<you>/my-case-private.git
    git remote -v      # check it's the private one
    git push -u origin main
    ```

## What the safety nets catch, and what they don't

Both repos have pre-commit checks, but neither can recognize your documents.

- The **workspace** hook, installed by `areao1 init`, runs [gitleaks](https://github.com/gitleaks/gitleaks) on staged changes and blocks commits that contain tokens or keys. If gitleaks isn't installed, it skips the scan and says so.
- The **app repo** hook (`.githooks/pre-commit`, turned on with `git config core.hooksPath .githooks`) runs `scripts/check_repo.py`, which fails if something that looks like a case workspace (an `areao1.yaml`) appears outside `tests/fixtures/workspaces/`, then runs gitleaks.

Neither hook can tell a passport scan or a pay stub from any other file. Keeping the repos separate is what protects your documents.

If you think something private reached a public repo, remove it, then treat it as exposed: rotate any token in it, and ask GitHub support about purging cached views if needed.

See also [Privacy habits](privacy.md) and [Contributing](../reference/contributing.md).
