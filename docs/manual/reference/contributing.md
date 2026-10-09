# Contributing

How to set up a development copy of Area O1, run the checks, and add connectors and profiles.

The main contribution surfaces are **connectors**, **profiles**, **scans** and **skills**. None of them needs real credentials: tests run against recorded fixtures. The full guide is [CONTRIBUTING.md](https://github.com/ris3abh/areao1/blob/main/CONTRIBUTING.md).

!!! warning "Also using Area O1 for your own case?"
    Keep two completely separate repositories: a public fork for code, and a private workspace for your case. Never put case material in the fork. See [Keep case and code apart](../best-practices/two-repos.md).

## Set up

```sh
git clone https://github.com/<you>/areao1 ~/code/areao1
cd ~/code/areao1
uv venv && uv pip install -e '.[dev]'
npm --prefix web install
git config core.hooksPath .githooks   # once per clone: repo guard + gitleaks on every commit
npm --prefix web run build            # builds the dashboard into the package
```

Then make a workspace somewhere outside the clone and start it:

```sh
.venv/bin/areao1 init ~/dev-case --name "Alex Rivera"
.venv/bin/areao1 up -w ~/dev-case
```

## Run the checks

```sh
.venv/bin/pytest                 # all tests use recorded fixtures, no live network
.venv/bin/ruff check . && .venv/bin/mypy
npm --prefix web run dev         # Vite dev server, proxies /api to 127.0.0.1:7777
```

Run `npm --prefix web run dev` alongside `areao1 up` for live-reloading pages.

## The pre-commit check

With `core.hooksPath` set, every commit runs `.githooks/pre-commit`:

1. `scripts/check_repo.py` fails if the spec loses a required section, if the README or CONTRIBUTING lose the two-repos warning, or if something that looks like a case workspace (an `areao1.yaml`) appears outside `tests/fixtures/workspaces/`. The test suite runs it too.
2. [gitleaks](https://github.com/gitleaks/gitleaks) scans the staged changes for secrets (skipped with a warning if it isn't installed).

Before you push, also run `gitleaks detect`.

## The docs site

These pages are built with [MkDocs Material](https://squidfunk.github.io/mkdocs-material/) from `docs/manual/` (config in `mkdocs.yml`).

```sh
uv pip install -e '.[docs]'
.venv/bin/mkdocs serve           # preview at http://127.0.0.1:8000
.venv/bin/mkdocs build --strict  # what CI checks: broken links fail the build
```

Write in plain, short sentences, use fictional examples only, and never say anything qualifies someone.

## Adding a connector

1. Create `areao1/sources/<kind>.py` with a class implementing the `Source` protocol in `areao1/sources/base.py`: `detect`, `parse`, `source_url`, `discover`, `snapshot`, `candidates`. Use the provided `HttpClient` (ETag cache, backoff) for every request.
2. Attach the raw response to each candidate and metric row with `.with_evidence(Evidence(...))`, and make every `ClaimDraft.excerpt` a verbatim substring of it. The memory store rejects claims that don't quote their source. Set `stage` on activities (an invitation is `invited`, not `completed`).
3. Register it in `CONNECTORS` in `areao1/sources/__init__.py`.
4. Connectors never write evidence. `candidates()` returns proposals and the user decides in the Inbox. Give each candidate a stable `fingerprint` so re-imports don't create duplicates.
5. Add recorded JSON responses under `tests/fixtures/<kind>/` (fictional or public data only, no tokens) and tests that mock HTTP with `respx`. Tests must not touch the network.

## Adding or editing a profile

Profiles are YAML in `profiles/`, validated by the `Profile` model (`areao1/core/models.py`, schema in `areao1/core/schemas/profile.schema.json`).

- Reuse existing criterion ids (`awards`, `judging`, `press`, ...) where the meaning matches, so evidence carries across profiles.
- Cite the regulation for every criterion.
- Keep `bank` rules simple and explainable; judgment belongs to the agent.
- Add a test in `tests/test_criteria.py` that loads the profile.

## Changing a workspace file shape

1. Edit the model: domain-agnostic shapes in `areao1/core/models.py`, profile and case shapes in `areao1/criteria/models.py`. `areao1/core` must never import from the domain layer or mention a specific profile (`tests/test_layering.py` enforces this).
2. Regenerate the schemas: `python -m areao1.schemas`.
3. Regenerate the fictional test workspace with `python scripts/make_fixture_workspace.py` (runs the real connectors against recorded fixtures, no network), then check it with `areao1 validate -w tests/fixtures/workspaces/alex-rivera`. A breaking change needs a new `schema_version` and a migration.
4. Record significant design decisions as an ADR in `docs/adr/`.

## Writes go through the service layer

Any create, update or move a page or the agent makes goes through `areao1/service.py`, which records it in `data/changes.jsonl`. Don't call workspace write methods from a route directly. `tests/test_service_layer.py` fails if a route writes outside the service layer, or if a new write route isn't covered.

## The filming workspace

The vault's test fixtures (the Policy Manual chapters and Kazarian) are real copies of the sources, recorded in
`tests/fixtures/vault/SOURCES.json`. `python scripts/check_vault_fixtures.py` fetches the live sources and checks the
fixtures and every quoted passage of the standard still match them. It uses the network, so CI never runs it on
push; a weekly workflow (`.github/workflows/vault-fixtures.yml`) does, and opens an issue labeled `vault-wording`
when a source's wording changes.

To record a demo, `scripts/film_demo.py` builds a fictional, offline workspace (Gmail, the AI and the keychain are all in-memory fakes) and serves it:

```sh
python scripts/film_demo.py            # builds ./film-maya and serves http://127.0.0.1:7920
python scripts/film_demo.py --rebuild  # start over
```

It's a developer tool and isn't part of the installed package. The recording checklist is in [docs/filming.md](https://github.com/ris3abh/areao1/blob/main/docs/filming.md).

## Ground rules

- Keep to the current phase in [SPEC.md](https://github.com/ris3abh/areao1/blob/main/SPEC.md) and [TODO.md](https://github.com/ris3abh/areao1/blob/main/TODO.md). Product work (usable out of the box) comes before research work.
- No personal data, ever. The fixture personas (Alex, Maya, Ravi, Lena) and their numbers are fictional, and they live only in `tests/fixtures/`. The package ships no fake data.
- No telemetry and no network calls beyond the sources a user connected.
- Report security problems privately (see [Privacy and security](privacy-security.md#report-a-vulnerability)).
- By contributing you agree your work is licensed under Apache-2.0.
