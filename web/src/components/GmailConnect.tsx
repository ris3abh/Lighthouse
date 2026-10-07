import { Check, ExternalLink, LogOut, Mail, RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";
import { api, type GmailStatus } from "../api";
import { Button, Chip, useToast } from "./ui";

export const APP_PASSWORDS = "https://myaccount.google.com/apppasswords";

/** Connect Gmail with an app password (ADR 0014, amendment): no Google Cloud project. Shared by onboarding (with
 * `onDone`) and Settings > Gmail. */
export default function GmailConnect({ onDone, busy }: { onDone?: () => void; busy?: boolean }) {
  const toast = useToast();
  const [s, setS] = useState<GmailStatus | null>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    api.gmailStatus().then(setS, () => setS(null));
  }, []);
  if (!s) return null;
  const mail = s;

  const connect = async () => {
    setSaving(true);
    setError("");
    try {
      setS(await api.connectGmail(email.trim(), password));
      setPassword("");
      toast("Gmail connected. The app password is in your keychain, not your workspace.");
      onDone?.();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  if (mail.connected)
    return (
      <div className="grid gap-3" data-gmail="connected">
        <p className="flex flex-wrap items-center gap-2 text-sm">
          <Chip tone="ink">Gmail connected</Chip> {mail.email}
        </p>
        {onDone && (
          <div>
            <Button variant="primary" disabled={busy} onClick={onDone}>
              <Check /> Use this Gmail
            </Button>
          </div>
        )}
        {!onDone && (
          <div className="flex flex-wrap gap-2">
            <Button
              onClick={() =>
                api.syncGmail().then(
                  (r) => toast(r.lines.join(" ")),
                  (e: Error) => toast(e.message, "error"),
                )
              }
            >
              <RefreshCw /> Refresh threads
            </Button>
            <Button
              variant="ghost"
              onClick={() =>
                api.disconnectGmail().then(
                  (r) => {
                    setS(r);
                    toast("Forgotten here. To revoke it at Google too, remove it on the App passwords page.");
                  },
                  (e: Error) => toast(e.message, "error"),
                )
              }
            >
              <LogOut /> Disconnect
            </Button>
          </div>
        )}
      </div>
    );

  return (
    <div className="grid gap-4" data-gmail="none">
      <ol className="grid max-w-3xl list-decimal gap-1.5 pl-5 text-sm leading-relaxed text-ink-2">
        <li>
          Turn on{" "}
          <a className="link" href="https://myaccount.google.com/signinoptions/twosv" target="_blank" rel="noreferrer">
            2-Step Verification <ExternalLink className="inline size-3" aria-hidden />
          </a>{" "}
          for your Google account, if it isn't on yet.
        </li>
        <li>
          Create an app password at{" "}
          <a className="link" href={APP_PASSWORDS} target="_blank" rel="noreferrer">
            myaccount.google.com/apppasswords <ExternalLink className="inline size-3" aria-hidden />
          </a>{" "}
          (name it "Area O1"). Google shows 16 letters once.
        </li>
        <li>Paste it here with your Gmail address. I check it with one sign-in and keep it in your keychain.</li>
      </ol>
      <form
        className="grid gap-3 md:grid-cols-[1fr_1fr_auto] md:items-end"
        onSubmit={(e) => {
          e.preventDefault();
          if (email.trim() && password.trim()) connect();
        }}
      >
        <label>
          <span className="label">Gmail address</span>
          <input className="input" type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@gmail.com" />
        </label>
        <label>
          <span className="label">App password</span>
          <input
            className="input font-mono"
            type="password"
            autoComplete="off"
            spellCheck={false}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="xxxx xxxx xxxx xxxx"
          />
        </label>
        <Button type="submit" variant="primary" disabled={saving || busy || !email.trim() || !password.trim()}>
          <Mail /> {saving ? "Checking…" : "Connect Gmail"}
        </Button>
      </form>
      {error && (
        <p role="alert" className="max-w-3xl border border-alert bg-alert-soft px-3 py-2 text-sm text-ink">
          {error}
        </p>
      )}
      <p className="font-mono text-[10.5px] leading-relaxed text-muted uppercase">
        Password in your keychain · read-only: headers of case mail, first lines to sort it, a message's text only
        when you open it · sends only what you approve, up to 10 a day
      </p>
    </div>
  );
}
