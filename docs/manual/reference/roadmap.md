# Roadmap

What's planned after v0.2.0.

These are plans, not promises. Priorities can change, and some items may land differently or not at all. The working plan is in [SPEC.md](https://github.com/ris3abh/areao1/blob/main/SPEC.md) (section 11, build phases), progress is in [TODO.md](https://github.com/ris3abh/areao1/blob/main/TODO.md), and what changed in each release is in the [CHANGELOG](https://github.com/ris3abh/areao1/blob/main/CHANGELOG.md).

Product work comes first: Area O1 should be easy to install and useful out of the box before the research work grows.

## Coming next

- **`export` and `purge` commands.** Export your case in one go, and delete a case cleanly. Until then, see [Deleting a case](../best-practices/privacy.md#deleting-a-case).
- **More criteria profiles.** Beyond O-1A and EB-1A, contributed by the community. You can already add your own as YAML in a workspace's `profiles/` folder.
- **An adapter for Claude's dated-file export**, alongside the current Claude and ChatGPT `conversations.json` imports.

## Later in the plan

- **EB-1A final-merits narrative and an attorney export.** A layer for the second, final-merits step of an EB-1A case, and an export your attorney can work from.
- **Session context packs and MCP memory tools.** Richer ways for an agent to load what's relevant to a task from your claim memory.
- **An evaluation harness.** Measured results for the claim memory (three systems, five scenarios, metrics and ablations), with a research-portfolio profile and fixture workspace. Area O1 makes no performance claims until this exists.
- **A Docker image** and a GitHub Actions template for running jobs.
- **A short video** walking through onboarding with a fictional persona.
- **Contributor guides** for new connectors, profiles and opportunity scans.
- **Release artifacts**: evaluation results and a Zenodo DOI with each release, and a documented PROV-JSON export.

## Have an idea?

Open an issue or a discussion on [GitHub](https://github.com/ris3abh/areao1). See [Contributing](contributing.md) if you'd like to build it.
