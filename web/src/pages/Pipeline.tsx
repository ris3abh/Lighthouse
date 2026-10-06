import { useState, type DragEvent } from "react";
import { api, type PipelineCard } from "../api";
import { useRefresh } from "../App";
import { Button, Chip, cx, ErrorBox, Loading, PageHeader, useToast } from "../components/ui";
import { useLoad } from "../hooks";

const STAGES = [
  { id: "idea", label: "Idea" },
  { id: "applied", label: "Applied" },
  { id: "waiting", label: "Waiting" },
  { id: "done", label: "Done" },
] as const;
type Stage = (typeof STAGES)[number]["id"];

export default function Pipeline() {
  const { version, bump } = useRefresh();
  const toast = useToast();
  const data = useLoad(() => Promise.all([api.pipeline(), api.profile()]), [version]);
  const [over, setOver] = useState<Stage | null>(null);
  const [title, setTitle] = useState("");

  if (data.error) return <ErrorBox error={data.error} retry={data.reload} />;
  if (!data.data) return <Loading />;
  const [items, profile] = data.data;
  const labels = Object.fromEntries(profile.criteria.map((c) => [c.id, c.label]));

  const save = async (fn: () => Promise<unknown>, msg?: string) => {
    try {
      await fn();
      if (msg) toast(msg);
      bump();
    } catch (e) {
      toast((e as Error).message, "error");
    }
  };
  const move = (item: PipelineCard, stage: Stage) =>
    item.stage !== stage && save(() => api.updatePipeline(item.id, { stage }), `Moved to ${stage}`);
  const drop = (e: DragEvent, stage: Stage) => {
    e.preventDefault();
    setOver(null);
    const item = items.find((i) => i.id === e.dataTransfer.getData("text/x-lighthouse-pipeline"));
    if (item) move(item, stage);
  };
  const stale = items.filter((i) => i.stale).length;

  return (
    <div className="mx-auto max-w-7xl">
      <PageHeader
        title="Pipeline"
        subtitle={`In-flight work. Drag cards between columns. Items with no movement for 14+ days are flagged stale${stale ? ` (${stale} now)` : ""}.`}
      />
      <div className="grid gap-3 md:grid-cols-4">
        {STAGES.map((col, ci) => {
          const cards = items.filter((i) => i.stage === col.id);
          return (
            <section
              key={col.id}
              aria-label={col.label}
              onDragOver={(e) => {
                if (e.dataTransfer.types.includes("text/x-lighthouse-pipeline")) {
                  e.preventDefault();
                  setOver(col.id);
                }
              }}
              onDragLeave={() => setOver(null)}
              onDrop={(e) => drop(e, col.id)}
              className={cx(
                "flex min-h-64 flex-col gap-2 rounded-xl border border-zinc-200 bg-zinc-100/50 p-2 dark:border-zinc-800 dark:bg-zinc-900/50",
                over === col.id && "border-amber-400 bg-amber-50 dark:bg-amber-950/30",
              )}
            >
              <h2 className="flex items-center gap-2 px-1 text-sm font-semibold">
                {col.label}
                <span className="rounded-full bg-zinc-200 px-1.5 text-xs tabular-nums dark:bg-zinc-800">{cards.length}</span>
              </h2>
              {col.id === "idea" && (
                <form
                  className="flex gap-1"
                  onSubmit={(e) => {
                    e.preventDefault();
                    if (title.trim()) save(() => api.addPipeline({ title: title.trim() }).then(() => setTitle("")), "Added");
                  }}
                >
                  <input className="input py-1 text-xs" placeholder="Add an idea…" value={title} onChange={(e) => setTitle(e.target.value)} />
                  <Button size="sm" type="submit">
                    +
                  </Button>
                </form>
              )}
              {cards.map((item) => (
                <article
                  key={item.id}
                  draggable
                  onDragStart={(e) => {
                    e.dataTransfer.setData("text/x-lighthouse-pipeline", item.id);
                    e.dataTransfer.effectAllowed = "move";
                  }}
                  className={cx("card cursor-grab p-2.5 active:cursor-grabbing", item.stale && "border-amber-300 dark:border-amber-800")}
                >
                  <div className="flex items-start gap-1">
                    <h3 className="min-w-0 flex-1 text-sm font-medium">
                      {item.url ? (
                        <a href={item.url} target="_blank" rel="noreferrer" className="link">
                          {item.title}
                        </a>
                      ) : (
                        item.title
                      )}
                    </h3>
                    <button className="text-xs text-zinc-400 hover:text-red-600" aria-label={`Delete ${item.title}`} onClick={() => save(() => api.deletePipeline(item.id), "Deleted")}>
                      ✕
                    </button>
                  </div>
                  <div className="mt-1.5 flex flex-wrap items-center gap-1">
                    {item.criterion && (
                      <span title={labels[item.criterion] ?? item.criterion}>
                        <Chip>{item.criterion}</Chip>
                      </span>
                    )}
                    {item.stale && <Chip tone="amber">stale {item.days_since_move}d</Chip>}
                  </div>
                  {item.notes && <p className="mt-1.5 line-clamp-3 text-xs text-zinc-500">{item.notes}</p>}
                  <label className="mt-2 flex items-center gap-1.5 text-[11px] text-zinc-500">
                    Follow up
                    <input
                      type="date"
                      className="input w-auto px-1.5 py-0.5 text-[11px]"
                      value={item.follow_up ?? ""}
                      onChange={(e) => save(() => api.updatePipeline(item.id, { follow_up: e.target.value || null }))}
                    />
                  </label>
                  <div className="mt-2 flex justify-between">
                    <Button size="sm" variant="ghost" disabled={ci === 0} aria-label="Move left" onClick={() => move(item, STAGES[ci - 1].id)}>
                      ←
                    </Button>
                    <Button size="sm" variant="ghost" disabled={ci === STAGES.length - 1} aria-label="Move right" onClick={() => move(item, STAGES[ci + 1].id)}>
                      →
                    </Button>
                  </div>
                </article>
              ))}
            </section>
          );
        })}
      </div>
    </div>
  );
}
