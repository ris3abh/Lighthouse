"""vault-watch: the daily job. Re-checks every Tier 1 source (and anything past its freshness window) and
notifies when a Tier 1 source changed."""

from __future__ import annotations

from collections import Counter

import anyio
import httpx

from lighthouse_gc.core.workspace import Workspace
from lighthouse_gc.vault.models import VaultFetch
from lighthouse_gc.vault.store import Vault


def summarize(results: list[VaultFetch]) -> str:
    c = Counter(r.status for r in results)
    parts = [f"{c[s]} {s}" for s in ("new", "changed", "unchanged", "unreadable", "error") if c[s]]
    return "vault: " + (", ".join(parts) if parts else "nothing due")


def notify_changes(ws: Workspace, vault: Vault, results: list[VaultFetch]) -> str | None:
    from lighthouse_gc.notify import Notification, send

    changed = [r for r in results if r.status == "changed" and r.tier == 1]
    if not changed:
        return None
    titles = {s.id: s.title for s in vault.manifest.sources}
    lines = []
    for r in changed:
        sample = "; ".join(r.diff.sample) if r.diff and r.diff.sample else "see the Knowledge page"
        lines.append(f"· {titles.get(r.source_id, r.source_id)}: {sample}\n  {r.url}")
    title = (f"Tier 1 source changed: {titles.get(changed[0].source_id, changed[0].source_id)}" if len(changed) == 1
             else f"{len(changed)} Tier 1 sources changed")  # fmt: skip
    port = ws.config().server.port
    note = Notification("vault", title[:120], "\n".join(lines)[:1800], url=f"http://127.0.0.1:{port}/#/knowledge",
                        priority="high", minimal_body=f"{len(changed)} official source(s) changed. Check the Knowledge page.",
                        key="vault:" + ",".join(sorted(r.sha256 or "" for r in changed)))  # fmt: skip
    return send(ws, note).line()


def run_watch(ws: Workspace, scheduled: bool = False, client: httpx.AsyncClient | None = None) -> list[str]:
    if not ws.config().vault.enabled:
        return ["skipped: the vault is turned off (vault.enabled in lighthouse.yaml)"]
    vault = Vault(ws)

    async def go() -> list[VaultFetch]:
        return await vault.sync(tier1_daily=True, client=client)

    results = anyio.run(go)
    lines = [summarize(results)]
    lines += [f"{r.source_id}: {r.status}: {r.error}" for r in results if r.status in ("unreadable", "error")]
    sent = notify_changes(ws, vault, results)
    if sent:
        lines.append(sent)
    return lines
