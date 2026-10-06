import { useState } from "react";
import { api } from "../api";
import { useRefresh } from "../App";
import { Button, Card, Chip, cx, Empty, ErrorBox, Loading, PageHeader, useToast } from "../components/ui";
import { useLoad } from "../hooks";

export default function Settings() {
  const { version, bump } = useRefresh();
  const toast = useToast();
  const settings = useLoad(() => api.settings(), [version]);
  const [busy, setBusy] = useState<string | null>(null);
  if (settings.error) return <ErrorBox error={settings.error} retry={settings.reload} />;
  if (!settings.data) return <Loading />;
  const s = settings.data;

  const test = async (channel?: string) => {
    setBusy(channel ?? "all");
    try {
      const r = await api.notifyTest(channel);
      toast(r.summary, r.ok ? "ok" : "error");
      bump();
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="mx-auto max-w-5xl">
      <PageHeader
        title="Settings"
        subtitle={
          <>
            Edit <code>lighthouse.yaml</code> in your workspace to change these. Secrets go in the OS keychain:{" "}
            <code>lighthouse-gc secret set &lt;secret_ref&gt;</code>.
          </>
        }
      />

      <Card title="Notification channels" className="mb-4" actions={
        <Button size="sm" disabled={!!busy} onClick={() => test()}>
          {busy === "all" ? "Sending…" : "Send test"}
        </Button>
      }>
        <ul className="divide-y divide-zinc-100 dark:divide-zinc-800">
          {s.channels.map((ch) => (
            <li key={ch.name} className="flex flex-wrap items-center gap-2 px-4 py-2.5 text-sm">
              <span className="font-medium">{ch.name}</span>
              <Chip>{ch.kind}</Chip>
              {!ch.enabled && <Chip tone="amber">disabled</Chip>}
              <span title="minimal = counts only, no titles; for channels that leave this machine">
                <Chip tone={ch.detail === "minimal" ? "emerald" : "zinc"}>detail: {ch.detail}</Chip>
              </span>
              {ch.secret_ref && (
                <span className={cx("text-xs", ch.secret_stored ? "text-emerald-600" : "text-red-600")}>
                  {ch.secret_stored ? `🔑 ${ch.secret_ref} in keychain` : `missing secret: lighthouse-gc secret set ${ch.secret_ref}`}
                </span>
              )}
              {ch.kind === "ntfy" && <span className="text-xs text-zinc-500">{ch.server}/{ch.topic}</span>}
              {ch.kind === "email" && <span className="text-xs text-zinc-500">{ch.to_addr} via {ch.host}</span>}
              <Button className="ml-auto" size="sm" variant="ghost" disabled={!!busy} onClick={() => test(ch.name)}>
                {busy === ch.name ? "Sending…" : "Test"}
              </Button>
            </li>
          ))}
        </ul>
      </Card>

      <div className="mb-4 grid gap-4 md:grid-cols-2">
        <Card title="Routes: which event goes where">
          <table className="w-full text-sm">
            <tbody>
              {Object.entries(s.routes).map(([event, chans]) => (
                <tr key={event} className="border-b border-zinc-100 last:border-0 dark:border-zinc-800">
                  <td className="px-4 py-2 font-mono text-xs">{event}</td>
                  <td className="px-4 py-2">{chans.length ? chans.join(", ") : <span className="text-zinc-400">none</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="px-4 pb-3 text-xs text-zinc-500">Deadline alerts at {s.deadline_alert_days.join(", ")} days out.</p>
        </Card>
        <Card title="Workspace">
          <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 px-4 py-3 text-sm">
            <dt className="text-zinc-500">Profile</dt>
            <dd>{s.profile}</dd>
            <dt className="text-zinc-500">Agent engine</dt>
            <dd>{s.engine}</dd>
            <dt className="text-zinc-500">Redact before LLM</dt>
            <dd>{s.privacy.redact_before_llm ? "on" : "off"}</dd>
          </dl>
        </Card>
      </div>

      <Card title="Recent notifications">
        {s.recent_notifications.length ? (
          <ul className="divide-y divide-zinc-100 text-sm dark:divide-zinc-800">
            {s.recent_notifications.map((n, i) => (
              <li key={i} className="flex flex-wrap items-center gap-2 px-4 py-2">
                <span className="text-xs text-zinc-500 tabular-nums">{n.at.replace("T", " ").slice(0, 16)}</span>
                <Chip>{n.event}</Chip>
                <span className="min-w-0 flex-1 truncate">{n.title}</span>
                <span className={cx("text-xs", n.ok ? "text-emerald-600" : "text-red-600")}>
                  {n.results.map((r) => `${r.channel} ${r.ok ? "✓" : "✗"}`).join(" · ")}
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <Empty>Nothing sent yet.</Empty>
        )}
      </Card>
    </div>
  );
}
