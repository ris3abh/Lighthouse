# Area O1 community vault

Snapshots of official U.S. government pages that block automated reading (uscis.gov, travel.state.gov), shared so
that [Area O1](https://github.com/ris3abh/areao1) installs stay current without everyone saving the same pages by
hand ([ADR 0011](https://github.com/ris3abh/areao1/blob/main/docs/adr/0011-vault-without-babysitting.md)).

## What's here

- `manifest.json`: one entry per snapshot: the Area O1 vault `source_id`, the page `url`, when it was captured
  (`captured_at`), its `sha256`, the `file`, and the `license`.
- `snapshots/<sha256>.html` (or `.pdf`, `.txt`): the page exactly as captured.
- `validate.py`: the checks CI runs on every push and pull request: structure, official domains only (`.gov` or the
  listed `official_domains`), the file's SHA-256, size, and no stray files.

Only works of the U.S. federal government belong here: they're in the public domain (17 U.S.C. § 105), so every
entry carries `"license": "public-domain-us-gov"`. No personal data, no state or private pages.

## How Area O1 uses it

Area O1's daily vault check reads `manifest.json` and, for a source it can't fetch itself, imports a snapshot only
when it's newer than the local copy **and** its SHA-256 matches. A snapshot that fails the check is ignored, never
trusted. It's on by default (`vault.community` in `areao1.yaml`) and can be turned off; it reads this repository's
raw files from GitHub, nothing else.

## Contributing

In the Area O1 capture extension, tick **Share captures with the community library**. Captures of Tier 1 pages are
then written to your workspace's `.areao1/cache/community-outbox/`, each as the snapshot file and the manifest entry
to add. To contribute one, open a pull request that adds the file under `snapshots/` and the entry to
`manifest.json`, and run `python validate.py` first. Nothing is ever uploaded for you.

## License

Snapshots: U.S. government works, public domain. Manifest, scripts and docs: CC0 1.0.
