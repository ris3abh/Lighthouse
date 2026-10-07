import { useState } from "react";
import { api } from "../api";
import { useRefresh } from "../App";
import { Button, Card, Chip, cx, Empty, ErrorBox, Loading, PageHeader, useToast } from "../components/ui";
import { useLoad } from "../hooks";

const MISSIONS = [
  { id: "opportunity_scout", job: "mission-opportunity-scout", label: "Weekly opportunity scout", detail: "Finds current opportunities for your weakest criteria and proposes them." },
  { id: "what_changed", job: "mission-what-changed", label: "Daily what-changed check", detail: "Reviews what changed and writes this week's briefing. Skipped, at no cost, when nothing changed." },
] as const;

const AUTOPILOT = [
  { id: "tracker_updates", label: "Tracker updates", detail: "Move pipeline items, set follow-ups and notes, update a letter writer's status or last contact, mark deadlines done." },
  { id: "metrics", label: "Metrics", detail: "Record a metric (e.g. citations) the agent read on a page and quoted, word for word." },
  { id: "tier1_deadlines", label: "Tier-1 deadlines", detail: "Add a deadline quoted from a Tier 1 source (official law and agency sites in the vault manifest, e.g. uscis.gov, ecfr.gov, federalregister.gov)." },
] as const;

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
    <div>
      <PageHeader
        title="Settings"
        subtitle={
          <>
            Edit <code>lighthouse.yaml</code> in your workspace to change these. Secrets go in the OS keychain:{" "}
            <code>lighthouse-gc secret set &lt;secret_ref&gt;</code>.
          </>
        }
      />

      <Card title="Notification channels" className="mb-8" actions={
        <Button size="sm" disabled={!!busy} onClick={() => test()}>
          {busy === "all" ? "Sending…" : "Send test"}
        </Button>
      }>
        <ul className="divide-y divide-line">
          {s.channels.map((ch) => (
            <li key={ch.name} className="flex flex-wrap items-center gap-2 px-5 py-4 text-sm">
              <span className="text-[15px] font-medium">{ch.name}</span>
              <Chip>{ch.kind}</Chip>
              {!ch.enabled && <Chip tone="muted">disabled</Chip>}
              <span title="minimal = counts only, no titles; for channels that leave this machine">
                <Chip tone={ch.detail === "minimal" ? "ink" : "muted"}>detail: {ch.detail}</Chip>
              </span>
              {ch.secret_ref && (
                <span className={cx("text-xs", ch.secret_stored ? "text-ink" : "text-alert")}>
                  {ch.secret_stored ? `🔑 ${ch.secret_ref} in keychain` : `missing secret: lighthouse-gc secret set ${ch.secret_ref}`}
                </span>
              )}
              {ch.kind === "ntfy" && <span className="text-xs text-muted">{ch.server}/{ch.topic}</span>}
              {ch.kind === "email" && <span className="text-xs text-muted">{ch.to_addr} via {ch.host}</span>}
              <Button className="ml-auto" size="sm" variant="ghost" disabled={!!busy} onClick={() => test(ch.name)}>
                {busy === ch.name ? "Sending…" : "Test"}
              </Button>
            </li>
          ))}
        </ul>
      </Card>

      <Card title="Missions" className="mb-8">
        <div className="p-6">
          <p className="mb-5 max-w-3xl text-sm leading-relaxed text-ink-2">
            Scheduled agent runs on the missions model, inside your monthly budget. Results land on the Agent page and as a
            notification; suggestions go to your Inbox (or are applied, where autopilot is on).
          </p>
          <div className="flex flex-col divide-y divide-line border-y border-line">
            {MISSIONS.map((m) => (
              <label key={m.id} className="flex cursor-pointer items-start gap-4 py-4 text-sm">
                <input
                  type="checkbox"
                  className="mt-1 size-4 accent-[var(--ink)]"
                  checked={s.missions[m.id]}
                  disabled={busy === m.id}
                  onChange={async (e) => {
                    setBusy(m.id);
                    try {
                      await api.setMissions({ [m.id]: e.target.checked });
                      toast(`${m.label}: ${e.target.checked ? "on" : "off"}`);
                      bump();
                    } catch (err) {
                      toast((err as Error).message, "error");
                    } finally {
                      setBusy(null);
                    }
                  }}
                />
                <span>
                  <span className="text-[15px] font-medium">{m.label}</span>
                  <span className="mt-1 block text-sm text-ink-2">
                    {m.detail} Schedule: <code>{s.schedules[m.job] || "off"}</code>
                  </span>
                </span>
              </label>
            ))}
          </div>
        </div>
      </Card>

      <Card title="Agent autopilot" className="mb-8">
        <div className="p-6">
          <p className="mb-5 max-w-3xl text-sm leading-relaxed text-ink-2">
            Let the agent apply some changes without asking. Each one is logged and can be undone in one click on the Agent page.
            Anything that could affect a criterion (evidence, exhibits, overrides, your profile) always waits for your approval,
            whatever you turn on here.
          </p>
          <div className="flex flex-col divide-y divide-line border-y border-line">
            {AUTOPILOT.map((a) => (
              <label key={a.id} className="flex cursor-pointer items-start gap-4 py-4 text-sm">
                <input
                  type="checkbox"
                  className="mt-1 size-4 accent-[var(--ink)]"
                  checked={s.autopilot[a.id]}
                  disabled={busy === a.id}
                  onChange={async (e) => {
                    setBusy(a.id);
                    try {
                      await api.setAutopilot({ [a.id]: e.target.checked });
                      toast(`${a.label}: ${e.target.checked ? "on" : "off"}`);
                      bump();
                    } catch (err) {
                      toast((err as Error).message, "error");
                    } finally {
                      setBusy(null);
                    }
                  }}
                />
                <span>
                  <span className="text-[15px] font-medium">{a.label}</span>
                  <span className="mt-1 block text-sm text-ink-2">{a.detail}</span>
                </span>
              </label>
            ))}
          </div>
        </div>
      </Card>

      <div className="mb-8 grid gap-8 @4xl:grid-cols-2">
        <Card title="Routes: which event goes where">
          <table className="w-full text-sm">
            <tbody>
              {Object.entries(s.routes).map(([event, chans]) => (
                <tr key={event} className="border-b border-line last:border-0">
                  <td className="px-5 py-3 font-mono text-xs">{event}</td>
                  <td className="px-5 py-3">{chans.length ? chans.join(", ") : <span className="text-muted">none</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="px-5 py-3 font-mono text-[11px] text-muted uppercase">Deadline alerts at {s.deadline_alert_days.join(", ")} days out.</p>
        </Card>
        <Card title="Workspace">
          <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-3 px-5 py-5 text-sm [&_dt]:eyebrow [&_dt]:pt-0.5">
            <dt className="text-muted">Profile</dt>
            <dd>{s.profile}</dd>
            <dt className="text-muted">Agent engine</dt>
            <dd>{s.engine}</dd>
            <dt className="text-muted">Redact before LLM</dt>
            <dd>{s.privacy.redact_before_llm ? "on" : "off"}</dd>
          </dl>
        </Card>
      </div>

      <Card title="Recent notifications">
        {s.recent_notifications.length ? (
          <ul className="divide-y divide-line text-sm">
            {s.recent_notifications.map((n, i) => (
              <li key={i} className="flex flex-wrap items-center gap-2 px-5 py-3">
                <span className="num text-[11px] text-muted">{n.at.replace("T", " ").slice(0, 16)}</span>
                <Chip>{n.event}</Chip>
                <span className="min-w-0 flex-1 truncate">{n.title}</span>
                <span className={cx("text-xs", n.ok ? "text-ink" : "text-alert")}>
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
