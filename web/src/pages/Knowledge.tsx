import { useRef, useState } from "react";
import { api, type KnowledgeView, type VaultSourceStatus } from "../api";
import { useRefresh } from "../App";
import { RefreshCw } from "lucide-react";
import { Button, Card, Chip, cx, Empty, ErrorBox, Loading, PageHeader, plural, Stat, useToast } from "../components/ui";
import { useLoad } from "../hooks";

const TIER_LABEL = { 1: "Tier 1 · primary law and agency", 2: "Tier 2 · adjudication", 3: "Tier 3 · secondary (context only)" } as const;

const when = (iso: string | null) => (iso ? new Date(iso).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "—");
const day = (iso: string | null) => (iso ? new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" }) : "—");

function freshness(s: VaultSourceStatus): { label: string; tone: "ink" | "outline" | "alert" | "muted" } {
  if (s.status === "unreadable") return { label: s.checked_at ? "unreadable · stale soon" : "unreadable", tone: "alert" };
  if (s.status === "error") return { label: "error", tone: "alert" };
  if (!s.checked_at) return { label: "never fetched", tone: "muted" };
  return s.fresh ? { label: "fresh", tone: "ink" } : { label: "stale", tone: "outline" };
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
    <div>
      <PageHeader
        eyebrow={plural(official.length, "official source")}
        title="Knowledge"
        subtitle="The official sources every rule statement is checked against: what each said, when it was checked, and what changed."
        actions={
          <Button variant="primary" size="sm" disabled={!k.enabled || busy !== null} onClick={() => sync()}>
            <RefreshCw className={cx(busy === "all" && "animate-spin")} />
            {busy === "all" ? "Checking…" : "Check what's due"}
          </Button>
        }
      />
      {!k.enabled && (
        <p className="mb-8 border border-alert bg-surface px-5 py-4 text-sm text-ink">
          The vault is turned off (<code>vault: {"{enabled: false}"}</code> in areao1.yaml). Nothing is fetched, and rule statements show as unverified.
        </p>
      )}

      <section className="card mb-8 grid animate-rise grid-cols-2 @3xl:grid-cols-5 [&>div]:border-line [&>div]:p-6">
        <div className="border-r border-b @3xl:border-b-0">
          <Stat label="Tier 1 fresh" value={t1.filter((s) => s.fresh).length} sub={`OF ${t1.length}`} />
        </div>
        <div className="border-b @3xl:border-r @3xl:border-b-0">
          <Stat label="Fresh sources" value={counts.fresh} />
        </div>
        <div className="border-r border-b @3xl:border-b-0">
          <Stat label="Stale" value={counts.stale} />
        </div>
        <div className="border-b @3xl:border-r @3xl:border-b-0">
          <Stat label="Can't read automatically" value={counts.unreadable} alert={counts.unreadable > 0} />
        </div>
        <div className="col-span-2 @3xl:col-span-1">
          <Stat label="Open conflicts" value={k.conflicts.length} alert={k.conflicts.length > 0} />
        </div>
      </section>

      {k.conflicts.length > 0 && (
        <Card title="Open conflicts" className="mb-8 border-alert">
          <ul className="divide-y divide-line">
            {k.conflicts.map((c) => (
              <li key={c.claim.id} className="p-6 text-sm">
                <p className="text-[15px] font-medium">{c.claim.text}</p>
                <p className="mt-0.5 text-xs text-muted">
                  In{" "}
                  <a className="link" href={c.where.type === "run" ? `#/agent?run=${c.where.id}` : c.where.type === "briefing" ? "#/overview" : "#/inbox"}>
                    {c.where.label}
                  </a>{" "}
                  · {day(c.at)}
                </p>
                <div className="mt-2 grid gap-2 md:grid-cols-2">
                  {c.claim.citations.map((x, i) => (
                    <blockquote key={i} className={cx("border-l-2 pl-2 text-xs", x.verdict === "contradicts" ? "border-alert" : "border-ink")}>
                      <p>“{x.quote}”</p>
                      <p className="mt-0.5 text-muted">
                        {x.verdict === "contradicts" ? "says otherwise" : "says so"} · Tier {x.tier} ·{" "}
                        <a className="link" href={x.url} target="_blank" rel="noreferrer">
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

      <div className="grid grid-cols-[minmax(0,1fr)] gap-8 @5xl:grid-cols-[minmax(0,1fr)_380px]">
        <div className="flex flex-col gap-8">
          {([1, 2, 3] as const).map((tier) => {
            const rows = official.filter((s) => s.tier === tier);
            return rows.length ? (
              <Card key={tier} title={TIER_LABEL[tier]}>
                <ul className="divide-y divide-line">
                  {rows.map((s) => (
                    <SourceRow key={s.id} s={s} busy={busy} enabled={k.enabled} onSync={() => sync([s.id], true)} onDone={bump} />
                  ))}
                </ul>
              </Card>
            ) : null;
          })}
          {findings.length > 0 && (
            <Card title={`Found by the agent (${findings.length})`}>
              <p className="border-b border-line px-5 py-3 text-sm text-ink-2">
                Official pages the agent read. They're searchable, but rule statements aren't verified against them until you add them as sources.
              </p>
              <ul className="divide-y divide-line">
                {findings.map((s) => (
                  <FindingRow key={s.id} s={s} kinds={k.kinds} onDone={bump} />
                ))}
              </ul>
            </Card>
          )}
        </div>

        <Card title="Recent changes">
          {k.recent.length ? (
            <ul className="max-h-[80vh] divide-y divide-line overflow-y-auto text-xs">
              {k.recent.map((e) => (
                <li key={e.id} className="px-5 py-4">
                  <div className="flex items-center gap-1.5">
                    <Chip tone={e.status === "changed" ? "ink" : e.status === "new" ? "outline" : e.status === "unchanged" ? "muted" : "alert"}>{e.status}</Chip>
                    {e.origin !== "fetch" && <Chip>{e.origin === "manual" ? "imported" : "agent"}</Chip>}
                    <span className="num ml-auto text-[10.5px] text-muted">{when(e.fetched_at)}</span>
                  </div>
                  <p className="mt-2 text-sm font-medium text-ink">{e.title}</p>
                  {e.diff && e.diff.sample.length > 0 && (
                    <ul className="mt-2 space-y-1 border-l-2 border-ink pl-3 font-mono text-[11px] text-ink-2">
                      {e.diff.sample.map((line, i) => (
                        <li key={i}>+ {line}</li>
                      ))}
                    </ul>
                  )}
                  {e.diff && (
                    <p className="mt-0.5 text-[11px] text-muted">
                      {plural(e.diff.added, "line")} added, {e.diff.removed} removed
                    </p>
                  )}
                  {e.error && <p className="mt-0.5 text-alert">{e.error}</p>}
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


function SourceRow({ s, busy, enabled, onSync, onDone }: { s: VaultSourceStatus; busy: string | null; enabled: boolean; onSync: () => void; onDone: () => void }) {
  const toast = useToast();
  const file = useRef<HTMLInputElement>(null);
  const f = freshness(s);
  const blocked = s.status === "unreadable";
  return (
    <li className="px-5 py-4 text-sm">
      <div className="flex flex-wrap items-start gap-2">
        <div className="min-w-0 flex-1">
          <a href={s.link || s.url} target="_blank" rel="noreferrer" className="text-[15px] font-medium hover:underline">
            {s.title}
          </a>
          <p className="mt-0.5 text-xs text-muted">
            {s.manual && "manual import · "}
            {s.secondary_to && `secondary to ${s.secondary_to} · `}
            {s.kind.replace("_", " ")} · fresh for {s.ttl === "monthly" ? "the month" : `${s.ttl} days`}
            {s.checked_at && ` · checked ${when(s.checked_at)}`}
            {s.expires_at && ` · ${s.fresh ? "until" : "expired"} ${day(s.expires_at)}`}
            {s.effective_date && ` · page dated ${day(s.effective_date)}`}
            {s.snapshots > 1 && ` · ${s.snapshots} versions kept`}
            {s.last_changed && ` · changed ${day(s.last_changed)}`}
          </p>
          {s.error && <p className="mt-0.5 text-xs text-alert">{s.error}</p>}
          {(blocked || (s.manual && !s.checked_at)) && (
            <p className="mt-0.5 text-xs text-muted">
              This site can't be read automatically right now. Open the link, save the page from your browser (HTML or PDF) and import it here.
            </p>
          )}
          {s.notes && !blocked && !(s.manual && !s.checked_at) && <p className="mt-0.5 text-xs text-muted">{s.notes}</p>}
        </div>
        <Chip tone={f.tone}>{f.label}</Chip>
        <Button size="sm" variant="ghost" disabled={!enabled || busy !== null} onClick={onSync}>
          {busy === s.id ? "Fetching…" : "Re-fetch"}
        </Button>
        <Button size="sm" variant={blocked || s.status === "error" || (s.manual && !s.fresh) ? "secondary" : "ghost"} onClick={() => file.current?.click()}>
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
    <li className="flex flex-wrap items-center gap-2 px-5 py-4 text-sm">
      <div className="min-w-0 flex-1">
        <a href={s.url} target="_blank" rel="noreferrer" className="font-medium hover:underline">
          {s.title}
        </a>
        <p className="mt-0.5 text-xs text-muted">
          Tier {s.tier} domain · read {when(s.checked_at)} · {s.notes}
        </p>
      </div>
      <select aria-label="Kind of source" className="input h-8 w-auto py-0 font-mono text-[11px]" value={kind} onChange={(e) => setKind(e.target.value)}>
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
