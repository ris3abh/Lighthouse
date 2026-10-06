import { useState } from "react";
import { api, type Source } from "../api";
import { useRefresh } from "../App";
import DropZone from "../components/DropZone";
import { Button, Card, Chip, Empty, ErrorBox, Loading, Modal, PageHeader, useToast } from "../components/ui";
import { useLoad } from "../hooks";

const TOKEN_PAGES: Record<string, string> = {
  github:
    "https://github.com/settings/personal-access-tokens/new?name=lighthouse-gc&description=Read-only+access+for+Lighthouse&metadata=read&contents=read&administration=read",
  huggingface: "https://huggingface.co/settings/tokens/new?tokenType=read",
};

function guessKind(input: string) {
  if (/github\.com|^gh:|^github:/i.test(input)) return "github";
  if (/huggingface\.co|hf\.co|^hf:/i.test(input)) return "huggingface";
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
      return `${r.source_id}: ${r.items} item(s), ${r.candidates_added} new candidate(s) in the Inbox`;
    });
  };

  if (sources.error) return <ErrorBox error={sources.error} retry={sources.reload} />;
  if (!sources.data) return <Loading />;

  return (
    <div className="mx-auto max-w-5xl">
      <PageHeader title="Sources" subtitle="Connected accounts and the items Lighthouse tracks. Connectors only read." />

      <Card className="mb-4">
        <form onSubmit={add} className="flex flex-col gap-3 p-4">
          <label>
            <span className="label">Add a source — paste a GitHub or Hugging Face profile, org or repo URL</span>
            <div className="flex gap-2">
              <input
                className="input"
                placeholder="https://github.com/you  ·  https://huggingface.co/you"
                value={input}
                onChange={(e) => setInput(e.target.value)}
              />
              <Button type="submit" variant="primary" disabled={!input.trim() || busy === "add"}>
                {busy === "add" ? "Importing…" : "Import"}
              </Button>
            </div>
          </label>
          <div className="flex flex-wrap items-center gap-2 text-xs text-zinc-500">
            {kind ? <Chip tone="emerald">detected: {kind}</Chip> : input && <Chip tone="amber">not recognized yet</Chip>}
            <button type="button" className="link" onClick={() => setShowToken(!showToken)}>
              {showToken ? "Public only" : "Private repos? Add a read-only token"}
            </button>
          </div>
          {showToken && (
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

      <Card className="mb-4" title="Import your Claude or ChatGPT history">
        <div className="p-4">
          <p className="mb-3 text-xs text-zinc-600 dark:text-zinc-400">
            Export your data (Claude: Settings → Privacy → Export data; ChatGPT: Settings → Data controls → Export), then drop the{" "}
            <code>.zip</code> or <code>conversations.json</code> here. Every conversation is saved as a private snapshot in your
            workspace. Lighthouse reads <strong>only your own messages</strong> and proposes deadlines, pipeline items and letter
            writers. These are self-reported: they keep you organized but never count toward a criterion.
          </p>
          <DropZone
            busy={busy === "chats"}
            onFiles={(files) =>
              run("chats", async () => {
                const r = await api.importChats(files[0]);
                window.location.hash = "#/inbox";
                return r.summary;
              })
            }
          >
            <p className="text-sm font-medium">{busy === "chats" ? "Importing…" : "Drop your export here, or click to choose"}</p>
            <p className="text-xs text-zinc-500">conversations.json or the export .zip · stays on this machine</p>
          </DropZone>
        </div>
      </Card>

      {sources.data.length === 0 ? (
        <Card>
          <Empty>No sources yet. Import your GitHub or Hugging Face account above.</Empty>
        </Card>
      ) : (
        <div className="flex flex-col gap-3">
          {sources.data.map((s) => (
            <Card
              key={s.id}
              title={
                <span className="flex items-center gap-2">
                  <a href={s.url} target="_blank" rel="noreferrer" className="link">
                    {s.id}
                  </a>
                  <Chip>{s.auth === "token" ? "🔑 token" : "public"}</Chip>
                </span>
              }
              actions={
                <div className="flex items-center gap-1">
                  <span className="mr-2 text-xs text-zinc-500" title={s.last_sync ?? ""}>
                    synced {ago(s.last_sync)}
                  </span>
                  <Button
                    size="sm"
                    disabled={!!busy}
                    onClick={() =>
                      run(s.id, async () => {
                        const r = await api.syncSource(s.id);
                        return r.errors.length
                          ? `Synced with ${r.errors.length} error(s): ${r.errors[0]}`
                          : `Synced: ${r.metrics_written} metric rows, ${r.candidates_added} new candidate(s)`;
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
              {s.last_error && <p className="border-b border-red-100 bg-red-50 px-4 py-2 text-xs text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">⚠ {s.last_error}</p>}
              <ul className="divide-y divide-zinc-100 dark:divide-zinc-800">
                {s.items.map((i) => (
                  <li key={i.id} className="flex items-center gap-3 px-4 py-2 text-sm">
                    <Chip>{i.kind}</Chip>
                    <a href={i.url} target="_blank" rel="noreferrer" className="link truncate">
                      {i.name}
                    </a>
                    {i.private && <Chip tone="amber">private</Chip>}
                    <span className="min-w-0 flex-1 truncate text-xs text-zinc-500">{i.title}</span>
                    <a href={`#/metrics?item=${encodeURIComponent(i.name)}`} className="text-xs text-zinc-500 hover:text-zinc-900 dark:hover:text-white">
                      metrics →
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
        <p className="text-sm text-zinc-600 dark:text-zinc-300">
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
