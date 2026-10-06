# Contributing

Thanks for helping. The four contribution surfaces are **connectors**, **profiles**, **scans** and
**skills**. None of them needs real credentials: tests run against recorded fixtures.

## ⚠️ If you're also an active user: keep two separate repos

If you contribute to Lighthouse and also use it for your own filing, keep **two completely separate
repositories**:

| Repo | What goes in it | Visibility |
|---|---|---|
| **Your fork of this app repo** | code, profiles, connectors, docs, fictional fixtures only | public |
| **Your case workspace** (created with `lighthouse-gc init`) | your evidence, letters, metrics, personal data | **private** |

- Never create your case workspace inside your fork, and never copy filing documents, screenshots, real
  metrics or personal data into the fork, not even into `examples/` or test fixtures.
- Make the workspace a **fresh private repo**, not a fork: GitHub forks of a public repo can't be made private.
- Keep them in different folders (e.g. `~/code/lighthouse` and `~/my-case`), and check `git remote -v`
  before you push.
- The workspace's gitleaks pre-commit hook blocks tokens, but it can't recognize a passport scan or a pay stub.
  Keeping the repos separate is what protects your documents.

## Setup

```sh
uv venv && uv pip install -e '.[dev]'
npm --prefix web install
.venv/bin/pytest && .venv/bin/ruff check . && .venv/bin/mypy
npm --prefix web run build
```

## Adding a connector

1. Create `lighthouse_gc/sources/<kind>.py` with a class implementing the `Source` protocol in
   `lighthouse_gc/sources/base.py`: `detect`, `parse`, `source_url`, `discover`, `snapshot`, `candidates`.
   Use the provided `HttpClient` (ETag cache, backoff) for every request.
   Attach the raw response to each candidate / metric row with `.with_evidence(Evidence(...))` and make every
   `ClaimDraft.excerpt` a verbatim substring of it. The memory store rejects claims that don't quote their
   source. Set `stage` on activities (an invitation is `invited`, not `completed`).
2. Register it in `CONNECTORS` in `lighthouse_gc/sources/__init__.py`.
3. Connectors **never** write evidence. `candidates()` returns proposals; the user decides in the Inbox. Give
   each candidate a stable `fingerprint` so re-imports don't create duplicates.
4. Add recorded JSON responses under `tests/fixtures/<kind>/` (fictional or public data only, no tokens) and
   tests that mock HTTP with `respx`. Tests must not touch the network.

## Adding or editing a profile

Profiles are YAML in `profiles/`, validated by the `Profile` model (`lighthouse_gc/core/models.py`, schema in
`lighthouse_gc/core/schemas/profile.schema.json`).

- Reuse existing criterion ids (`awards`, `judging`, `press`, ...) where the meaning matches, so evidence
  carries across profiles.
- Cite the regulation for every criterion.
- Keep `bank` rules simple and explainable; judgment belongs to the agent.
- Add a test in `tests/test_criteria.py` that loads the profile.

## Changing a workspace file shape

1. Edit the model: domain-agnostic shapes in `lighthouse_gc/core/models.py`, profile/case shapes in
   `lighthouse_gc/criteria/models.py`. `lighthouse_gc/core` must never import from the domain layer or
   mention a specific profile (`tests/test_layering.py` enforces this).
2. Regenerate schemas: `python -m lighthouse_gc.schemas`.
3. Regenerate the demo: `python scripts/make_demo.py` (runs the real connectors against recorded fixtures,
   no network), then check `lighthouse-gc validate -w examples/demo-workspace`.
   A breaking change needs a new `schema_version` and a migration.
4. Record significant design decisions as an ADR in `docs/adr/`.

## Ground rules

- Keep to the current phase in [SPEC.md](SPEC.md) and [TODO.md](TODO.md). Product work (usable out of the box)
  comes before research work; see SPEC.md section 11a.
- No personal data, ever: the demo persona and its numbers are fictional.
- No telemetry and no network calls beyond the sources a user connected.
- By contributing you agree your work is licensed under Apache-2.0.
