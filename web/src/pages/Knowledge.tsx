import { useRef, useState } from "react";
import { api, type KnowledgeView, type VaultSourceStatus } from "../api";
import { useRefresh } from "../App";
import { Button, Card, Chip, cx, Empty, ErrorBox, Loading, PageHeader, useToast } from "../components/ui";
import { useLoad } from "../hooks";

const TIER_LABEL = { 1: "Tier 1 · primary law and agency", 2: "Tier 2 · adjudication", 3: "Tier 3 · secondary (context only)" } as const;

const when = (iso: string | null) => (iso ? new Date(iso).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "—");
const day = (iso: string | null) => (iso ? new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" }) : "—");

function freshness(s: VaultSourceStatus): { label: string; tone: "emerald" | "amber" | "red" | "zinc" } {
  if (s.status === "unreadable") return { label: s.checked_at ? "unreadable · stale soon" : "unreadable", tone: "red" };
  if (s.status === "error") return { label: "error", tone: "red" };
  if (!s.checked_at) return { label: "never fetched", tone: "zinc" };
  return s.fresh ? { label: "fresh", tone: "emerald" } : { label: "stale", tone: "amber" };
}

export default function Knowledge() {
  const { version, bump } = useRefresh();
  const toast = useToast();
  const data = useLoad(() => api.knowledge(), [version]);
  const [busy, setBusy] = useState<string | null>(null);

  if (data.error) return <ErrorBox error={data.error} retry={data.reload} />;
  if (!data.data) return <Loading />;
  const k: KnowledgeView = data.data;
  const official = k.sources.filter((s) => !s.finding);
  const findings = k.sources.filter((s) => s.finding);
  const t1 = official.filter((s) => s.tier === 1);
  const counts = {
    fresh: official.filter((s) => s.fresh).length,
    stale: official.filter((s) => s.checked_at && !s.fresh && s.status === "ok").length,
    unreadable: official.filter((s) => s.status === "unreadable" || s.status === "error").length,
    never: official.filter((s) => !s.checked_at && s.status === "never fetched").length,
  };

  const sync = async (sources?: string[], force = false) => {
    const key = sources?.join(",") ?? "all";
    setBusy(key);
    try {
      const results = await api.knowledgeSync(sources, force);
      const changed = results.filter((r) => r.status === "changed").length;
      const failed = results.filter((r) => r.status === "unreadable" || r.status === "error").length;
      toast(results.length ? `Checked ${results.length}: ${changed} changed${failed ? `, ${failed} couldn't be read` : ""}` : "Everything is fresh");
      bump();
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="mx-auto max-w-7xl">
      <PageHeader
        title="Knowledge"
        subtitle="The official sources every rule statement is checked against: what each said, when it was checked, and what changed."
        actions={
          <Button variant="primary" size="sm" disabled={!k.enabled || busy !== null} onClick={() => sync()}>
            {busy === "all" ? "Checking…" : "Check what's due"}
          </Button>
        }
      />
      {!k.enabled && (
        <p className="mb-4 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-200">
          The vault is turned off (<code>vault: {"{enabled: false}"}</code> in lighthouse.yaml). Nothing is fetched, and rule statements show as unverified.
        </p>
      )}

      <div className="mb-4 grid grid-cols-2 gap-4 md:grid-cols-5">
        <Stat label="Tier 1 fresh" value={`${t1.filter((s) => s.fresh).length}/${t1.length}`} />
        <Stat label="Fresh sources" value={counts.fresh} />
        <Stat label="Stale" value={counts.stale} tone={counts.stale ? "amber" : undefined} />
        <Stat label="Can't read automatically" value={counts.unreadable} tone={counts.unreadable ? "red" : undefined} />
        <Stat label="Open conflicts" value={k.conflicts.length} tone={k.conflicts.length ? "red" : undefined} />
      </div>

      {k.conflicts.length > 0 && (
        <Card title="Open conflicts" className="mb-4">
          <ul className="divide-y divide-zinc-100 dark:divide-zinc-800">
            {k.conflicts.map((c) => (
              <li key={c.claim.id} className="p-4 text-sm">
                <p className="font-medium">{c.claim.text}</p>
                <p className="mt-0.5 text-xs text-zinc-500">
                  In{" "}
                  <a className="underline" href={c.where.type === "run" ? `#/agent?run=${c.where.id}` : c.where.type === "briefing" ? "#/overview" : "#/inbox"}>
                    {c.where.label}
                  </a>{" "}
                  · {day(c.at)}
                </p>
                <div className="mt-2 grid gap-2 md:grid-cols-2">
                  {c.claim.citations.map((x, i) => (
                    <blockquote key={i} className={cx("border-l-2 pl-2 text-xs", x.verdict === "contradicts" ? "border-red-400" : "border-emerald-400")}>
                      <p>“{x.quote}”</p>
                      <p className="mt-0.5 text-zinc-500">
                        {x.verdict === "contradicts" ? "says otherwise" : "says so"} · Tier {x.tier} ·{" "}
                        <a className="underline" href={x.url} target="_blank" rel="noreferrer">
                          {x.title}
                        </a>
                      </p>
                    </blockquote>
                  ))}
                </div>
              </li>
            ))}
          </ul>
        </Card>
      )}

      <div className="grid gap-4 lg:grid-cols-[1fr_360px]">
        <div className="flex flex-col gap-4">
          {([1, 2, 3] as const).map((tier) => {
            const rows = official.filter((s) => s.tier === tier);
            return rows.length ? (
              <Card key={tier} title={TIER_LABEL[tier]}>
                <ul className="divide-y divide-zinc-100 dark:divide-zinc-800">
                  {rows.map((s) => (
                    <SourceRow key={s.id} s={s} busy={busy} enabled={k.enabled} onSync={() => sync([s.id], true)} onDone={bump} />
                  ))}
                </ul>
              </Card>
            ) : null;
          })}
          {findings.length > 0 && (
            <Card title={`Found by the agent (${findings.length})`}>
              <p className="border-b border-zinc-100 px-4 py-2 text-xs text-zinc-500 dark:border-zinc-800">
                Official pages the agent read. They're searchable, but rule statements aren't verified against them until you add them as sources.
              </p>
              <ul className="divide-y divide-zinc-100 dark:divide-zinc-800">
                {findings.map((s) => (
                  <FindingRow key={s.id} s={s} kinds={k.kinds} onDone={bump} />
                ))}
              </ul>
            </Card>
          )}
        </div>

        <Card title="Recent changes">
          {k.recent.length ? (
            <ul className="max-h-[80vh] divide-y divide-zinc-100 overflow-y-auto text-xs dark:divide-zinc-800">
              {k.recent.map((e) => (
                <li key={e.id} className="px-3 py-2">
                  <div className="flex items-center gap-1.5">
                    <Chip tone={e.status === "changed" ? "amber" : e.status === "new" ? "emerald" : e.status === "unchanged" ? "zinc" : "red"}>{e.status}</Chip>
                    {e.origin !== "fetch" && <Chip>{e.origin === "manual" ? "imported" : "agent"}</Chip>}
                    <span className="ml-auto text-zinc-400">{when(e.fetched_at)}</span>
                  </div>
                  <p className="mt-1 font-medium text-zinc-700 dark:text-zinc-200">{e.title}</p>
                  {e.diff && e.diff.sample.length > 0 && (
                    <ul className="mt-1 space-y-0.5 text-zinc-500">
                      {e.diff.sample.map((line, i) => (
                        <li key={i}>+ {line}</li>
                      ))}
                    </ul>
                  )}
                  {e.diff && (
                    <p className="mt-0.5 text-[11px] text-zinc-400">
                      {e.diff.added} line(s) added, {e.diff.removed} removed
                    </p>
                  )}
                  {e.error && <p className="mt-0.5 text-red-600">{e.error}</p>}
                </li>
              ))}
            </ul>
          ) : (
            <Empty>Nothing fetched yet. Press “Check what's due”.</Empty>
          )}
        </Card>
      </div>
    </div>
  );
}

function Stat({ label, value, tone }: { label: string; value: number | string; tone?: "amber" | "red" }) {
  return (
    <div className="card p-4">
      <p className="text-xs font-medium text-zinc-500 dark:text-zinc-400">{label}</p>
      <p className={cx("mt-1 text-2xl font-semibold tabular-nums", tone === "amber" && "text-amber-700 dark:text-amber-400", tone === "red" && "text-red-700 dark:text-red-400")}>
        {value}
      </p>
    </div>
  );
}

function SourceRow({ s, busy, enabled, onSync, onDone }: { s: VaultSourceStatus; busy: string | null; enabled: boolean; onSync: () => void; onDone: () => void }) {
  const toast = useToast();
  const file = useRef<HTMLInputElement>(null);
  const f = freshness(s);
  const blocked = s.status === "unreadable";
  return (
    <li className="px-4 py-3 text-sm">
      <div className="flex flex-wrap items-start gap-2">
        <div className="min-w-0 flex-1">
          <a href={s.url} target="_blank" rel="noreferrer" className="font-medium hover:underline">
            {s.title}
          </a>
          <p className="mt-0.5 text-xs text-zinc-500">
            {s.kind.replace("_", " ")} · fresh for {s.ttl === "monthly" ? "the month" : `${s.ttl} days`}
            {s.checked_at && ` · checked ${when(s.checked_at)}`}
            {s.expires_at && ` · ${s.fresh ? "until" : "expired"} ${day(s.expires_at)}`}
            {s.effective_date && ` · page dated ${day(s.effective_date)}`}
            {s.snapshots > 1 && ` · ${s.snapshots} versions kept`}
            {s.last_changed && ` · changed ${day(s.last_changed)}`}
          </p>
          {s.error && <p className="mt-0.5 text-xs text-red-600">{s.error}</p>}
          {blocked && (
            <p className="mt-0.5 text-xs text-zinc-500">
              This site can't be read automatically right now. Open the link, save the page from your browser (HTML or PDF) and import it here.
            </p>
          )}
          {s.notes && !blocked && <p className="mt-0.5 text-xs text-zinc-400">{s.notes}</p>}
        </div>
        <Chip tone={f.tone}>{f.label}</Chip>
        <Button size="sm" variant="ghost" disabled={!enabled || busy !== null} onClick={onSync}>
          {busy === s.id ? "Fetching…" : "Re-fetch"}
        </Button>
        <Button size="sm" variant={blocked || s.status === "error" ? "secondary" : "ghost"} onClick={() => file.current?.click()}>
          Import saved page
        </Button>
        <input
          ref={file}
          type="file"
          accept=".html,.htm,.pdf,.txt,.xml,.json"
          className="hidden"
          onChange={async (e) => {
            const picked = e.target.files?.[0];
            e.target.value = "";
            if (!picked) return;
            try {
              const r = await api.knowledgeImport(s.id, picked);
              toast(`Imported (${r.status})`);
              onDone();
            } catch (err) {
              toast((err as Error).message, "error");
            }
          }}
        />
      </div>
    </li>
  );
}

function FindingRow({ s, kinds, onDone }: { s: VaultSourceStatus; kinds: string[]; onDone: () => void }) {
  const toast = useToast();
  const [kind, setKind] = useState("guidance");
  return (
    <li className="flex flex-wrap items-center gap-2 px-4 py-3 text-sm">
      <div className="min-w-0 flex-1">
        <a href={s.url} target="_blank" rel="noreferrer" className="font-medium hover:underline">
          {s.title}
        </a>
        <p className="mt-0.5 text-xs text-zinc-500">
          Tier {s.tier} domain · read {when(s.checked_at)} · {s.notes}
        </p>
      </div>
      <select aria-label="Kind of source" className="input w-auto py-1 text-xs" value={kind} onChange={(e) => setKind(e.target.value)}>
        {kinds.map((k) => (
          <option key={k} value={k}>
            {k.replace("_", " ")}
          </option>
        ))}
      </select>
      <Button
        size="sm"
        onClick={() =>
          api
            .promoteFinding(s.id, kind)
            .then(() => {
              toast("Added to the vault as a source");
              onDone();
            })
            .catch((e: Error) => toast(e.message, "error"))
        }
      >
        Add as a source
      </Button>
    </li>
  );
}
