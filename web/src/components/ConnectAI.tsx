import { Check, KeyRound, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { api, type AiStatus } from "../api";
import { Button, Chip, useToast } from "./ui";

/** Connect your AI (S3, ADR 0013): the Claude Code login on this computer, or an Anthropic API key that's checked
 * with a free request and kept in the OS keychain. Shared by onboarding (with `onChoose`) and Settings. */
export default function ConnectAI({ onChoose, busy }: { onChoose?: (choice: "login" | "key") => void; busy?: boolean }) {
  const toast = useToast();
  const [status, setStatus] = useState<AiStatus | null>(null);
  const [key, setKey] = useState("");
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    api.aiStatus().then(setStatus, () => setStatus(null));
  }, []);
  if (!status) return null;

  const save = async () => {
    setSaving(true);
    try {
      setStatus(await api.saveAiKey(key));
      setKey("");
      toast("The key works. It's in your keychain, not your workspace.");
      onChoose?.("key");
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setSaving(false);
    }
  };
  const forget = async () => {
    try {
      setStatus(await api.forgetAiKey());
      toast("Key removed from your keychain.");
    } catch (e) {
      toast((e as Error).message, "error");
    }
  };

  return (
    <div className="grid gap-4" data-ai-ready={status.ready}>
      <div className="flex flex-wrap items-center gap-2">
        <Chip tone={status.key || status.cli !== "missing" ? "ink" : "muted"}>
          {status.key ? "API key" : status.cli === "missing" ? "Not connected" : "Claude Code login"}
        </Chip>
        <p className="min-w-0 flex-1 text-sm text-ink-2">{status.how}</p>
      </div>
      {onChoose && (status.key || status.cli !== "missing") && (
        <div>
          <Button variant="primary" disabled={busy} onClick={() => onChoose(status.key ? "key" : "login")}>
            <Check /> {status.key ? "Use my API key" : "Use my Claude Code login"}
          </Button>
        </div>
      )}
      <form
        className="flex flex-wrap items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (key.trim()) save();
        }}
      >
        <label className="min-w-0 flex-1 basis-64">
          <span className="label">{status.key === "keychain" ? "Replace your Anthropic API key" : "Or paste an Anthropic API key"}</span>
          <input
            className="input font-mono"
            type="password"
            autoComplete="off"
            spellCheck={false}
            placeholder="sk-ant-…"
            value={key}
            onChange={(e) => setKey(e.target.value)}
          />
        </label>
        <Button type="submit" disabled={saving || busy || !key.trim()}>
          <KeyRound /> {saving ? "Checking…" : "Check and save"}
        </Button>
        {status.key === "keychain" && !onChoose && (
          <Button type="button" variant="ghost" onClick={forget}>
            <Trash2 /> Forget the key
          </Button>
        )}
      </form>
      <p className="font-mono text-[10.5px] leading-relaxed text-muted uppercase">
        Checked with a free request to Anthropic · kept in this computer's keychain · {status.cost}
      </p>
    </div>
  );
}
