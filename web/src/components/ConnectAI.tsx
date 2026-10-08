import { Check, KeyRound, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { api, type AiStatus } from "../api";
import { Button, Chip, useToast } from "./ui";

/** Connect your AI (ADR 0015 §3): an OpenAI API key, checked with a free request and kept in the OS keychain. Shared by
 * onboarding (with `onChoose`) and Settings. */
export default function ConnectAI({ onChoose, busy }: { onChoose?: (choice: "key") => void; busy?: boolean }) {
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
        <Chip tone={status.ready ? "ink" : "muted"}>{status.ready ? "API key" : "Not connected"}</Chip>
        <p className="min-w-0 flex-1 text-sm text-ink-2">{status.how}</p>
      </div>
      {onChoose && status.key && (
        <div>
          <Button variant="primary" disabled={busy} onClick={() => onChoose("key")}>
            <Check /> Use my API key
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
          <span className="label">{status.key === "keychain" ? "Replace your OpenAI API key" : "OpenAI API key (platform.openai.com > API keys)"}</span>
          <input
            className="input font-mono"
            type="password"
            autoComplete="off"
            spellCheck={false}
            placeholder="sk-…"
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
        Checked with a free request to OpenAI · kept in this computer's keychain · {status.cost}
      </p>
    </div>
  );
}
