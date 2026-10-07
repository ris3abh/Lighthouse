import { useState } from "react";
import { api, type LetterWriter } from "../api";
import { useRefresh } from "../App";
import { Button, Card, Chip, cx, Empty, ErrorBox, Loading, PageHeader, useToast } from "../components/ui";
import { today, useLoad } from "../hooks";

const STATUSES: LetterWriter["status"][] = ["prospect", "asked", "drafting", "sent", "signed", "declined"];
const RELATIONSHIPS: LetterWriter["relationship"][] = ["independent", "employer", "coauthor"];
const ASKS = [
  { id: "letter", label: "Letter" },
  { id: "membership_ref", label: "Membership ref" },
] as const;
const STATUS_TONE: Record<string, string> = {
  signed: "text-ink",
  declined: "text-muted line-through",
  sent: "text-ink",
};

export default function Letters() {
  const { version, bump } = useRefresh();
  const toast = useToast();
  const data = useLoad(() => api.letters(), [version]);
  const [form, setForm] = useState({ name: "", relationship: "independent" as LetterWriter["relationship"], credentials: "" });
  if (data.error) return <ErrorBox error={data.error} retry={data.reload} />;
  if (!data.data) return <Loading />;
  const { letters, coverage, criteria } = data.data;
  const label = Object.fromEntries(criteria.map((c) => [c.id, c.label]));

  const save = async (fn: () => Promise<unknown>, msg: string) => {
    try {
      await fn();
      toast(msg);
      bump();
    } catch (e) {
      toast((e as Error).message, "error");
    }
  };
  const setStatus = (lt: LetterWriter, status: LetterWriter["status"]) =>
    save(() => api.updateLetter(lt.id, { status, last_contact: today() }), `${lt.name}: ${status}`);

  return (
    <div>
      <PageHeader eyebrow={`${letters.length} writers`} title="Letters" subtitle="Recommendation letter writers, what each one covers, and where each letter stands." />

      <Card title="Writers" className="mb-8">
        {letters.length ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="eyebrow text-left">
                <tr className="border-b border-line">
                  <th className="px-5 py-3 font-medium">Writer</th>
                  <th className="px-3 py-3 font-medium">Relationship</th>
                  <th className="px-3 py-3 font-medium">Covers</th>
                  <th className="px-3 py-3 font-medium">Asks</th>
                  <th className="px-3 py-3 font-medium">Status</th>
                  <th className="px-3 py-3 font-medium">Last contact</th>
                  <th className="px-3 py-3 font-medium">Draft</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {letters.map((lt) => (
                  <tr key={lt.id} className="border-b border-line last:border-0">
                    <td className="px-5 py-4 align-top">
                      <div className={cx("text-[15px] font-medium", STATUS_TONE[lt.status])}>{lt.name}</div>
                      {lt.credentials && <div className="mt-0.5 text-xs text-ink-2">{lt.credentials}</div>}
                    </td>
                    <td className="px-3 py-4 align-top">
                      <Chip>{lt.relationship}</Chip>
                    </td>
                    <td className="px-3 py-4 align-top">
                      <div className="flex flex-wrap gap-1">
                        {lt.criteria.length ? lt.criteria.map((c) => (
                          <span key={c} title={label[c] ?? c}>
                            <Chip>{c}</Chip>
                          </span>
                        )) : <span className="text-xs text-muted">none yet</span>}
                      </div>
                    </td>
                    <td className="px-3 py-4 align-top">
                      <div className="flex flex-col gap-0.5">
                        {ASKS.map((a) => (
                          <label key={a.id} className="flex items-center gap-1.5 text-xs whitespace-nowrap">
                            <input
                              type="checkbox"
                              checked={lt.asks.includes(a.id)}
                              onChange={(e) =>
                                save(
                                  () => api.updateLetter(lt.id, { asks: e.target.checked ? [...lt.asks, a.id] : lt.asks.filter((x) => x !== a.id) }),
                                  `${lt.name}: ${e.target.checked ? "asking for" : "no longer asking for"} ${a.label.toLowerCase()}`,
                                )
                              }
                            />
                            {a.label}
                          </label>
                        ))}
                      </div>
                    </td>
                    <td className="px-3 py-4 align-top">
                      <select aria-label={`Status for ${lt.name}`} className="input h-8 w-auto py-0 font-mono text-[11px]" value={lt.status} onChange={(e) => setStatus(lt, e.target.value as LetterWriter["status"])}>
                        {STATUSES.map((s) => (
                          <option key={s}>{s}</option>
                        ))}
                      </select>
                    </td>
                    <td className="px-3 py-4 align-top">
                      <input
                        type="date"
                        aria-label={`Last contact with ${lt.name}`}
                        className="input h-8 w-auto px-2 py-0 font-mono text-[11px]"
                        value={lt.last_contact ?? ""}
                        onChange={(e) => save(() => api.updateLetter(lt.id, { last_contact: e.target.value || null }), `${lt.name}: last contact updated`)}
                      />
                    </td>
                    <td className="px-3 py-4 align-top text-xs">
                      {lt.draft_exists && lt.draft_path ? (
                        <a className="link" href={api.draftUrl(lt.draft_path)} target="_blank" rel="noreferrer">
                          open
                        </a>
                      ) : (
                        <span className="text-muted">—</span>
                      )}
                    </td>
                    <td className="px-3 py-4 text-right align-top whitespace-nowrap">
                      {lt.status !== "sent" && lt.status !== "signed" && (
                        <Button size="sm" variant="ghost" onClick={() => setStatus(lt, "sent")}>
                          Mark sent
                        </Button>
                      )}
                      {lt.status !== "signed" && (
                        <Button size="sm" variant="ghost" onClick={() => setStatus(lt, "signed")}>
                          Mark signed
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty>No writers yet. Add one below, or import your chats; "I asked Dr. … for a letter" becomes a suggestion.</Empty>
        )}
        <form
          className="flex flex-wrap items-end gap-3 border-t border-line p-5"
          onSubmit={(e) => {
            e.preventDefault();
            save(async () => {
              await api.addLetter(form);
              setForm({ ...form, name: "", credentials: "" });
            }, "Writer added");
          }}
        >
          <label className="min-w-48 flex-1">
            <span className="label">Name</span>
            <input className="input" required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          </label>
          <label className="min-w-48 flex-1">
            <span className="label">Credentials</span>
            <input className="input" placeholder="e.g. Professor, Lakeshore University" value={form.credentials} onChange={(e) => setForm({ ...form, credentials: e.target.value })} />
          </label>
          <label>
            <span className="label">Relationship</span>
            <select className="input" value={form.relationship} onChange={(e) => setForm({ ...form, relationship: e.target.value as LetterWriter["relationship"] })}>
              {RELATIONSHIPS.map((r) => (
                <option key={r}>{r}</option>
              ))}
            </select>
          </label>
          <Button type="submit" variant="primary">
            Add writer
          </Button>
        </form>
      </Card>

      <Card title="Coverage by criterion (declined writers excluded)">
        <table className="w-full text-sm">
          <thead className="eyebrow text-left">
            <tr className="border-b border-line">
              <th className="px-5 py-3 font-medium">Criterion</th>
              <th className="px-3 py-3 text-right font-medium">Independent</th>
              <th className="px-3 py-3 text-right font-medium">Employer</th>
              <th className="px-5 py-3 text-right font-medium">Co-author</th>
            </tr>
          </thead>
          <tbody>
            {coverage.map((row) => (
              <tr key={row.id} className="border-b border-line last:border-0">
                <td className="px-5 py-3">{row.label}</td>
                <td className={cx("display px-3 py-3 text-right text-2xl", !row.independent && "text-muted")}>{row.independent}</td>
                <td className={cx("display px-3 py-3 text-right text-2xl", !row.employer && "text-muted")}>{row.employer}</td>
                <td className={cx("display px-5 py-3 text-right text-2xl", !row.coauthor && "text-muted")}>{row.coauthor}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
