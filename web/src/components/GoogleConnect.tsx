import { Check, ExternalLink, LogOut, Save } from "lucide-react";
import { useEffect, useState } from "react";
import { api, type GoogleStatus } from "../api";
import { Button, Chip, useToast } from "./ui";

/** Google (ADR 0014 §1): your own Desktop OAuth client, then sign in for just the features you turn on. */
export default function GoogleConnect() {
  const toast = useToast();
  const [s, setS] = useState<GoogleStatus | null>(null);
  const [id, setId] = useState("");
  const [secret, setSecret] = useState("");
  const [want, setWant] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    api.googleStatus().then((g) => {
      setS(g);
      setWant(new Set(g.features.filter((f) => f.granted).map((f) => f.id)));
    }, () => setS(null));
    const q = new URLSearchParams(window.location.hash.split("?")[1] ?? "");
    if (q.get("google") === "connected") toast("Google connected.");
    else if (q.get("google") === "error") toast(`Google sign-in didn't finish: ${q.get("why") ?? "unknown"}`, "error");
  }, [toast]);
  if (!s) return null;

  const run = async (fn: () => Promise<GoogleStatus>, ok: string) => {
    setBusy(true);
    try {
      setS(await fn());
      toast(ok);
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setBusy(false);
    }
  };
  const connect = async () => {
    setBusy(true);
    try {
      window.location.href = (await api.connectGoogle([...want])).url; // Google, then back to Settings
    } catch (e) {
      toast((e as Error).message, "error");
      setBusy(false);
    }
  };

  return (
    <div className="grid gap-5 p-6" data-google={s.connected ? "connected" : s.client ? "client" : "none"}>
      {!s.client && (
        <ol className="grid max-w-3xl list-decimal gap-1.5 pl-5 text-sm leading-relaxed text-ink-2">
          <li>
            At{" "}
            <a className="link" href="https://console.cloud.google.com/" target="_blank" rel="noreferrer">
              console.cloud.google.com <ExternalLink className="inline size-3" aria-hidden />
            </a>
            , create a project and enable the Gmail API and the Google Calendar API.
          </li>
          <li>OAuth consent screen: External, add yourself as a test user (or publish it for personal use; see docs/google.md).</li>
          <li>Credentials &gt; Create credentials &gt; OAuth client ID &gt; Desktop app. Paste its ID and secret here.</li>
        </ol>
      )}
      {!s.connected && (
        <form
          className="grid gap-3 md:grid-cols-[1fr_1fr_auto] md:items-end"
          onSubmit={(e) => {
            e.preventDefault();
            run(() => api.saveGoogleClient(id, secret), "Client saved in your keychain.");
          }}
        >
          <label>
            <span className="label">{s.client ? "Replace the client ID" : "Client ID"}</span>
            <input className="input font-mono" value={id} onChange={(e) => setId(e.target.value)} placeholder="…apps.googleusercontent.com" />
          </label>
          <label>
            <span className="label">Client secret</span>
            <input className="input font-mono" type="password" autoComplete="off" value={secret} onChange={(e) => setSecret(e.target.value)} />
          </label>
          <Button type="submit" disabled={busy || !id.trim() || !secret.trim()}>
            <Save /> Save
          </Button>
        </form>
      )}
      {s.client && (
        <div className="grid gap-3">
          {s.connected && (
            <p className="flex flex-wrap items-center gap-2 text-sm">
              <Chip tone="ink">Connected</Chip> {s.email}
            </p>
          )}
          <fieldset className="grid gap-2">
            <legend className="label">What Area O1 may do</legend>
            {s.features.map((f) => (
              <label key={f.id} className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={want.has(f.id)} onChange={(e) => {
                  const next = new Set(want);
                  if (e.target.checked) next.add(f.id);
                  else next.delete(f.id);
                  setWant(next);
                }} />
                {f.label}
                {f.granted && <Chip>granted</Chip>}
              </label>
            ))}
          </fieldset>
          <div className="flex flex-wrap gap-2">
            <Button variant="primary" disabled={busy || !want.size} onClick={connect}>
              <Check /> {s.connected ? "Update access" : "Connect Google"}
            </Button>
            {s.connected && (
              <Button variant="ghost" disabled={busy} onClick={() => run(() => api.disconnectGoogle(), "Disconnected; Google revoked the access.")}>
                <LogOut /> Disconnect
              </Button>
            )}
          </div>
          <p className="font-mono text-[10.5px] leading-relaxed text-muted uppercase">
            Your own client · sign-in stays on this computer · tokens in your keychain · Gmail: only threads with your case contacts ·
            calendar: only the one Area O1 creates
          </p>
        </div>
      )}
    </div>
  );
}
