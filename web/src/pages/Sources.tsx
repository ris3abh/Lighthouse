import { ArrowRight, KeyRound, TriangleAlert } from "lucide-react";
import { useState } from "react";
import { api, type Source } from "../api";
import { useRefresh } from "../App";
import ChatImport from "../components/ChatImport";
import { Button, Card, Chip, Empty, ErrorBox, Loading, Modal, PageHeader, plural, useToast } from "../components/ui";
import { useLoad } from "../hooks";

const TOKEN_PAGES: Record<string, string> = {
  github:
    "https://github.com/settings/personal-access-tokens/new?name=lighthouse-gc&description=Read-only+access+for+Lighthouse&metadata=read&contents=read&administration=read",
  huggingface: "https://huggingface.co/settings/tokens/new?tokenType=read",
};

function guessKind(input: string) {
  if (/github\.com|^gh:|^github:/i.test(input)) return "github";
  if (/huggingface\.co|hf\.co|^hf:/i.test(input)) return "huggingface";
  if (/semanticscholar\.org\/author\/|^s2:/i.test(input)) return "semantic_scholar";
  if (/openalex\.org\/(authors\/)?a\d|^openalex:/i.test(input)) return "openalex";
  if (/arxiv\.org\/a\/|^arxiv:[a-z]/i.test(input)) return "arxiv";
  if (/orcid\.org\/|^(orcid:)?\d{4}-\d{4}-\d{4}-\d{3}[\dX]$/i.test(input.trim())) return "orcid";
  if (/^https?:\/\/\S+$/i.test(input.trim())) return "website";
  return null;
}

function ago(iso: string | null) {
  if (!iso) return "never";
  const mins = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (mins < 60) return `${mins}m ago`;
  if (mins < 48 * 60) return `${Math.round(mins / 60)}h ago`;
  return `${Math.round(mins / 1440)}d ago`;
}

export default function Sources() {
  const { version, bump } = useRefresh();
  const toast = useToast();
  const sources = useLoad(() => api.sources(), [version]);
  const [input, setInput] = useState("");
  const [token, setToken] = useState("");
  const [showToken, setShowToken] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [reauth, setReauth] = useState<Source | null>(null);
  const kind = guessKind(input);

  const run = async (key: string, fn: () => Promise<string>) => {
    setBusy(key);
    try {
      toast(await fn());
      bump();
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setBusy(null);
    }
  };

  const add = (e: React.FormEvent) => {
    e.preventDefault();
    run("add", async () => {
      const r = await api.addSource(input.trim(), token.trim() || undefined);
      setInput("");
      setToken("");
      setShowToken(false);
      return `${r.source_id}: ${plural(r.items, "item")}, ${plural(r.candidates_added, "new candidate")} in the Inbox`;
    });
  };

  if (sources.error) return <ErrorBox error={sources.error} retry={sources.reload} />;
  if (!sources.data) return <Loading />;

  return (
    <div>
      <PageHeader
        eyebrow={`${plural(sources.data.length, "source")} connected`}
        title="Sources"
        subtitle="Connected accounts and the items Lighthouse tracks. Connectors only read."
      />

      <Card className="mb-8" title="Add a source">
        <form onSubmit={add} className="flex flex-col gap-4 p-6">
          <label>
            <span className="mb-3 block max-w-3xl text-[15px] leading-relaxed text-ink-2">
              Paste a GitHub or Hugging Face profile, org or repo URL, a scholarly profile (Semantic Scholar, OpenAlex, arXiv
              author page, ORCID), or any web page or sitemap (press, award pages).
            </span>
            <div className="flex flex-col gap-3 sm:flex-row">
              <input
                className="input h-12 text-base"
                placeholder="https://github.com/you  ·  https://huggingface.co/you  ·  https://orcid.org/0000-…"
                value={input}
                onChange={(e) => setInput(e.target.value)}
              />
              <Button type="submit" variant="primary" className="h-12 px-6" disabled={!input.trim() || busy === "add"}>
                {busy === "add" ? "Importing…" : "Import"}
              </Button>
            </div>
          </label>
          <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
            {kind ? <Chip tone="ink">detected: {kind}</Chip> : input && <Chip tone="outline">not recognized yet</Chip>}
            {(!kind || kind in TOKEN_PAGES) && (
              <button type="button" className="link" onClick={() => setShowToken(!showToken)}>
                {showToken ? "Public only" : "Private repos? Add a read-only token"}
              </button>
            )}
          </div>
          {showToken && (!kind || kind in TOKEN_PAGES) && (
            <label>
              <span className="label">
                Read-only token — stored in your OS keychain, never in workspace files.{" "}
                {kind && (
                  <a className="link" href={TOKEN_PAGES[kind]} target="_blank" rel="noreferrer">
                    Create one with minimum scopes
                  </a>
                )}
              </span>
              <input type="password" autoComplete="off" className="input font-mono" value={token} onChange={(e) => setToken(e.target.value)} />
            </label>
          )}
        </form>
      </Card>

      <Card className="mb-8" title="Import your Claude or ChatGPT history">
        <div className="p-6">
          <p className="mb-4 max-w-3xl text-sm leading-relaxed text-ink-2">
            Export your data (Claude: Settings, Privacy, Export data. ChatGPT: Settings, Data controls, Export). Lighthouse reads it on this
            computer, shows what looks related to your case and why, and imports only what you tick. From those it proposes deadlines,
            opportunities, people, asks and decisions, each quoting your own words. Self-reported: they keep you organized but never count
            toward a criterion.
          </p>
          <ChatImport
            onDone={(summary) => {
              toast(summary);
              window.location.hash = "#/inbox";
            }}
          />
        </div>
      </Card>

      {sources.data.length === 0 ? (
        <Card>
          <Empty>No sources yet. Import your GitHub, Hugging Face or scholarly profile above.</Empty>
        </Card>
      ) : (
        <div className="flex flex-col gap-8">
          {sources.data.map((s) => (
            <Card
              key={s.id}
              title={
                <span className="flex items-center gap-2">
                  <a href={s.url} target="_blank" rel="noreferrer" className="link">
                    {s.id}
                  </a>
                  <Chip>{s.auth === "token" ? (<><KeyRound /> token</>) : "public"}</Chip>
                </span>
              }
              actions={
                <div className="flex items-center gap-1">
                  <span className="num mr-2 text-[10.5px] text-muted uppercase" title={s.last_sync ?? ""}>
                    synced {ago(s.last_sync)}
                  </span>
                  <Button
                    size="sm"
                    disabled={!!busy}
                    onClick={() =>
                      run(s.id, async () => {
                        const r = await api.syncSource(s.id);
                        return r.errors.length
                          ? `Synced with ${plural(r.errors.length, "error")}: ${r.errors[0]}`
                          : `Synced: ${plural(r.metrics_written, "metric row")}, ${plural(r.candidates_added, "new candidate")}`;
                      })
                    }
                  >
                    {busy === s.id ? "Syncing…" : "Sync now"}
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => setReauth(s)}>
                    Re-auth
                  </Button>
                  <Button
                    size="sm"
                    variant="danger"
                    disabled={!!busy}
                    onClick={() =>
                      confirm(`Remove ${s.id}? Metrics and exhibits already collected stay in your workspace.`) &&
                      run(s.id, async () => {
                        await api.removeSource(s.id);
                        return `Removed ${s.id}`;
                      })
                    }
                  >
                    Remove
                  </Button>
                </div>
              }
            >
              {s.last_error && (
                <p className="flex items-start gap-2 border-b border-alert bg-alert-soft px-5 py-3 text-xs text-alert">
                  <TriangleAlert className="mt-px size-3.5 shrink-0" aria-hidden /> {s.last_error}
                </p>
              )}
              <ul className="divide-y divide-line">
                {s.items.map((i) => (
                  <li key={i.id} className="flex items-center gap-3 px-5 py-3 text-sm">
                    <Chip>{i.kind}</Chip>
                    <a href={i.url} target="_blank" rel="noreferrer" className="link truncate">
                      {i.name}
                    </a>
                    {i.private && <Chip tone="outline">private</Chip>}
                    {i.unreadable && (
                      <span title={`${i.unreadable}. Save the page from your browser and drop it on the Evidence page.`}>
                        <Chip tone="alert">unreadable</Chip>
                      </span>
                    )}
                    <span className="min-w-0 flex-1 truncate text-xs text-muted">
                      {i.unreadable ? `${i.unreadable} — save the page from your browser and drop it on the Evidence page` : i.title}
                    </span>
                    <a href={`#/metrics?item=${encodeURIComponent(i.name)}`} className="inline-flex items-center gap-1 font-mono text-[10.5px] text-muted uppercase hover:text-ink">
                      Metrics <ArrowRight className="size-3" aria-hidden />
                    </a>
                  </li>
                ))}
                {s.items.length === 0 && <Empty>No items discovered.</Empty>}
              </ul>
            </Card>
          ))}
        </div>
      )}

      {reauth && <ReauthModal source={reauth} onClose={() => setReauth(null)} onDone={bump} />}
    </div>
  );
}

function ReauthModal({ source, onClose, onDone }: { source: Source; onClose: () => void; onDone: () => void }) {
  const toast = useToast();
  const [token, setToken] = useState("");
  const help = source.token_help ?? TOKEN_PAGES[source.kind];
  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const r = await api.setToken(source.id, token.trim());
      toast(`Token saved to ${r.stored_in}`);
      onDone();
      onClose();
    } catch (err) {
      toast((err as Error).message, "error");
    }
  };
  return (
    <Modal title={`Re-authenticate ${source.id}`} onClose={onClose}>
      <form onSubmit={save} className="grid gap-3">
        <p className="text-sm text-ink-2">
          Paste a <strong>read-only</strong> token. It goes to your OS keychain; workspace files only store its name.
          {help && (
            <>
              {" "}
              <a className="link" href={help} target="_blank" rel="noreferrer">
                Create a token with minimum scopes
              </a>
              .
            </>
          )}
        </p>
        <input type="password" autoComplete="off" required className="input font-mono" value={token} onChange={(e) => setToken(e.target.value)} />
        <div className="flex justify-end gap-2">
          <Button type="button" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" variant="primary" disabled={!token.trim()}>
            Save token
          </Button>
        </div>
      </form>
    </Modal>
  );
}
