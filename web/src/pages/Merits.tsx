import { BadgeCheck, CircleAlert, CircleDashed, ExternalLink, Sigma } from "lucide-react";
import { useState } from "react";
import { api, type MeritsReport, type MeritsTheme, type ThemeStatus } from "../api";
import { useRefresh } from "../App";
import { Button, Card, Chip, cx, Empty, ErrorBox, Loading, PageHeader, plural, useToast } from "../components/ui";
import { useLoad, useOnce } from "../hooks";

const STATUS: Record<ThemeStatus, { label: string; tone: "banked" | "building" | "muted" }> = {
  strong: { label: "Strong", tone: "banked" },
  building: { label: "Building", tone: "building" },
  missing: { label: "Missing", tone: "muted" },
};

/** The final-merits view (ADR 0019): the counted evidence as a whole, by rules anyone can read. Statuses describe the
 * evidence against those rules; there is no score and no verdict (SPEC §2a). */
export default function Merits() {
  const { version, bump } = useRefresh();
  const view = useLoad(() => api.merits(), [version]);
  if (view.error && !view.data) return <ErrorBox error={view.error} retry={view.reload} />;
  if (!view.data) return <Loading />;
  const r = view.data;
  return (
    <div className="flex flex-col gap-8">
      <PageHeader
        eyebrow={r.profile === "eb1a" ? "EB-1A · step two" : "O-1A · the evidence as a whole"}
        title={r.label}
        subtitle={r.framing}
      />
      <Themes r={r} />
      <Timeline r={r} />
      <Benchmarks r={r} onFetched={bump} />
      {r.no_organization.length > 0 && <Organizations r={r} onSaved={bump} />}
      <Standard r={r} />
    </div>
  );
}

function Themes({ r }: { r: MeritsReport }) {
  return (
    <Card title="Themes" panel="merits themes">
      {r.themes.length === 0 ? (
        <Empty>This profile has no final-merits themes.</Empty>
      ) : (
        <ul className="divide-y divide-line">
          {r.themes.map((t) => (
            <ThemeRow key={t.id} t={t} r={r} />
          ))}
        </ul>
      )}
      <p className="border-t border-line px-5 py-3 text-xs text-ink-2">
        {r.employer.length ? `Employer: ${r.employer.join(", ")}. ` : ""}A status says what your counted evidence covers against the rule shown. It isn't a score, and the
        officer's weighing is holistic.
      </p>
    </Card>
  );
}

function ThemeRow({ t, r }: { t: MeritsTheme; r: MeritsReport }) {
  const s = STATUS[t.status];
  const behind = t.exhibit_ids.filter((id) => r.exhibits[id]);
  return (
    <li className="px-5 py-4" id={`theme-${t.id}`}>
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <Chip tone={s.tone}>{s.label}</Chip>
        <h3 className="text-lg font-medium">{t.label}</h3>
      </div>
      <p className="mt-1.5 text-[15px]">{t.why}</p>
      <p className="mt-1 font-mono text-[11px] text-muted">{t.rule}</p>
      {(behind.length > 0 || t.letter_ids.length > 0) && (
        <details className="mt-2">
          <summary className="cursor-pointer text-xs text-ink-2">
            What's behind it ({plural(behind.length + t.letter_ids.length, "item")})
          </summary>
          <ul className="mt-2 space-y-1 text-sm">
            {behind.map((id) => (
              <li key={id}>
                <a className="link" href={`#/evidence?c=${r.exhibits[id].criterion}`}>
                  {r.exhibits[id].title}
                </a>{" "}
                <span className="font-mono text-[11px] text-muted">
                  {r.exhibits[id].date.slice(0, 4)} · {r.exhibits[id].organization || "no organization"}
                </span>
              </li>
            ))}
            {t.letter_ids.map((id) => (
              <li key={id}>
                <a className="link" href="#/letters">
                  {r.letters[id] ?? "Letter writer"}
                </a>{" "}
                <span className="font-mono text-[11px] text-muted">independent letter writer</span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </li>
  );
}

function Timeline({ r }: { r: MeritsReport }) {
  if (r.first_year === null || r.last_year === null)
    return (
      <Card title="Sustained acclaim, by year">
        <Empty>No counted exhibits yet. Accept evidence in the Inbox and it appears here by year.</Empty>
      </Card>
    );
  const years = Array.from({ length: r.last_year - r.first_year + 1 }, (_, i) => r.first_year! + i);
  const byYear = Object.fromEntries(r.timeline.map((y) => [y.year, y]));
  const crits = [...new Set(r.timeline.flatMap((y) => Object.keys(y.by_criterion)))];
  return (
    <Card title="Sustained acclaim, by year" panel="merits timeline">
      <p className="border-b border-line px-5 py-3 text-sm text-ink-2">
        {plural(r.timeline.reduce((n, y) => n + y.count, 0), "counted exhibit")} from {r.first_year} to {r.last_year}
        {r.gap_years.length ? `; nothing counted in ${r.gap_years.join(", ")}.` : "."}
      </p>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <caption className="sr-only">Counted exhibits by criterion and year</caption>
          <thead>
            <tr className="border-b border-line">
              <th scope="col" className="px-5 py-2 text-left font-mono text-[11px] font-normal text-ink-2 uppercase">
                Criterion
              </th>
              {years.map((y) => (
                <th key={y} scope="col" className={cx("px-3 py-2 text-right font-mono text-[11px] font-normal", byYear[y] ? "text-ink" : "text-muted")}>
                  {y}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {crits.map((c) => (
              <tr key={c} className="border-b border-line last:border-b-0">
                <th scope="row" className="px-5 py-2 text-left font-normal">
                  <a className="link" href={`#/evidence?c=${c}`}>
                    {r.criteria[c] ?? c}
                  </a>
                </th>
                {years.map((y) => {
                  const n = byYear[y]?.by_criterion[c]?.length ?? 0;
                  return (
                    <td key={y} className={cx("num px-3 py-2 text-right", n ? "text-ink" : "text-muted")}>
                      {n || "·"}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

function Benchmarks({ r, onFetched }: { r: MeritsReport; onFetched: () => void }) {
  const toast = useToast();
  const { run, busy } = useOnce();
  const fetchNow = () =>
    run("benchmarks", async () => {
      try {
        const out = await api.fetchBenchmarks();
        toast(out.benchmarks ? `Recorded ${plural(out.benchmarks, "field benchmark")} from OpenAlex.` : "OpenAlex has no field percentiles for these works yet.");
        onFetched();
      } catch (e) {
        toast((e as Error).message, "error");
      }
    });
  return (
    <Card
      title="Field benchmarks"
      panel="merits benchmarks"
      actions={
        r.openalex_authors > 0 && (
          <Button size="sm" onClick={fetchNow} disabled={busy("benchmarks")}>
            <Sigma /> {busy("benchmarks") ? "Asking OpenAlex…" : r.benchmarks.length ? "Fetch again" : "Fetch from OpenAlex"}
          </Button>
        )
      }
    >
      {r.openalex_authors === 0 && r.benchmarks.length === 0 ? (
        <Empty>
          Benchmarks compare how often your works are cited with works of the same field and year. They need your OpenAlex author page:{" "}
          <a className="link" href="#/sources">
            add it in Sources
          </a>
          , then fetch them here.
        </Empty>
      ) : r.benchmarks.length === 0 ? (
        <Empty>
          How often your works are cited compared with works of the same field and year, from OpenAlex. Fetched only when you press the button, and kept in Memory with
          the response quoted.
        </Empty>
      ) : (
        <ul className="divide-y divide-line">
          {r.benchmarks.map((b) => (
            <li key={b.claim_id} className="flex flex-wrap items-baseline gap-x-3 gap-y-1 px-5 py-3">
              <span className="display w-16 shrink-0 text-3xl">{Math.round(b.percentile)}</span>
              <span className="min-w-0 flex-1">
                <span className="block break-words">{b.work}</span>
                <span className="text-xs text-ink-2">
                  Cited more than {Math.round(b.percentile)}% of {b.year ?? "same-year"} works in its field (OpenAlex). Context, not a verdict.
                </span>
              </span>
              <a className="link text-xs" href={`#/memory?claim=${b.claim_id}`}>
                {b.review === "approved" ? "Approved" : b.review === "rejected" ? "Rejected" : "Review"} in Memory
              </a>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function Organizations({ r, onSaved }: { r: MeritsReport; onSaved: () => void }) {
  return (
    <Card title={`Who issued it · ${plural(r.no_organization.length, "exhibit")} without an organization`} panel="merits organizations">
      <p className="border-b border-line px-5 py-3 text-sm text-ink-2">
        Recognition outside your employer is read from who issued or published each exhibit. These name no organization and have no web address to read one from.
      </p>
      <ul className="divide-y divide-line">
        {r.no_organization.map((id) => (
          <OrgRow key={id} id={id} title={r.exhibits[id]?.title ?? id} onSaved={onSaved} />
        ))}
      </ul>
    </Card>
  );
}

function OrgRow({ id, title, onSaved }: { id: string; title: string; onSaved: () => void }) {
  const toast = useToast();
  const [value, setValue] = useState("");
  const [saving, setSaving] = useState(false);
  const save = async () => {
    setSaving(true);
    try {
      await api.setOrganization(id, value);
      onSaved();
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setSaving(false);
    }
  };
  return (
    <li className="flex flex-wrap items-center gap-3 px-5 py-3">
      <span className="min-w-0 flex-1 break-words">{title}</span>
      <label className="sr-only" htmlFor={`org-${id}`}>
        Organization that issued {title}
      </label>
      <input id={`org-${id}`} className="input w-56 max-w-full" placeholder="e.g. Lakeside Hacks" value={value} onChange={(e) => setValue(e.target.value)} />
      <Button size="sm" onClick={save} disabled={saving || !value.trim()}>
        {saving ? "Saving…" : "Save"}
      </Button>
    </li>
  );
}

const CHECK = {
  verified: { icon: BadgeCheck, label: "Verified", tone: "banked" as const },
  stale: { icon: CircleDashed, label: "Stale", tone: "building" as const },
  unverified: { icon: CircleAlert, label: "Unverified", tone: "muted" as const },
};

function Standard({ r }: { r: MeritsReport }) {
  return (
    <Card title="The standard, from your vault" panel="merits standard">
      <ul className="divide-y divide-line">
        {r.standard.map((s, i) => {
          const c = CHECK[s.status];
          const Icon = c.icon;
          return (
            <li key={i} className="px-5 py-4">
              <p className="text-[15px]">
                {s.text}{" "}
                <Chip tone={c.tone}>
                  <Icon aria-hidden /> {c.label}
                </Chip>
              </p>
              <blockquote className="mt-2 border-l-2 border-line pl-3 text-sm text-ink-2">“{s.quote}”</blockquote>
              <p className="mt-1 flex flex-wrap items-center gap-x-2 font-mono text-[11px] text-muted">
                {s.link ? (
                  <a className="link inline-flex items-center gap-1" href={s.link} target="_blank" rel="noreferrer">
                    {s.title || s.source_id} <ExternalLink className="size-3" aria-hidden />
                  </a>
                ) : (
                  <span>{s.title || s.source_id}</span>
                )}
                <span>· {s.why}</span>
              </p>
            </li>
          );
        })}
      </ul>
    </Card>
  );
}
