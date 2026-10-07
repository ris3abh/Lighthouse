import { ArrowLeft, ArrowRight, Plus, X } from "lucide-react";
import { useEffect, useState, type DragEvent } from "react";
import { api, type PipelineCard } from "../api";
import { useRefresh } from "../App";
import { Button, Chip, cx, ErrorBox, Loading, PageHeader, plural, useToast } from "../components/ui";
import { useLoad } from "../hooks";
import { withViewTransition } from "../lib/motion";

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
  const [moved, setMoved] = useState<Record<string, Stage>>({}); // optimistic stage while a move saves
  useEffect(() => setMoved({}), [data.data]);

  if (data.error) return <ErrorBox error={data.error} retry={data.reload} />;
  if (!data.data) return <Loading />;
  const [rawItems, profile] = data.data;
  const items = rawItems.map((i) => (moved[i.id] ? { ...i, stage: moved[i.id] } : i));
  const labels = Object.fromEntries(profile.criteria.map((c) => [c.id, c.label]));
  const short = Object.fromEntries(profile.criteria.map((c) => [c.id, c.short_label || c.label]));

  const save = async (fn: () => Promise<unknown>, msg?: string) => {
    try {
      await fn();
      if (msg) toast(msg);
      bump();
      return true;
    } catch (e) {
      toast((e as Error).message, "error");
      return false;
    }
  };
  const move = async (item: PipelineCard, stage: Stage) => {
    if (item.stage === stage) return;
    withViewTransition(() => setMoved((m) => ({ ...m, [item.id]: stage })));
    if (!(await save(() => api.updatePipeline(item.id, { stage }), `Moved to ${stage}`)))
      withViewTransition(() => setMoved((m) => Object.fromEntries(Object.entries(m).filter(([k]) => k !== item.id)) as Record<string, Stage>));
  };
  const drop = (e: DragEvent, stage: Stage) => {
    e.preventDefault();
    setOver(null);
    const item = items.find((i) => i.id === e.dataTransfer.getData("text/x-areao1-pipeline"));
    if (item) move(item, stage);
  };
  const stale = items.filter((i) => i.stale).length;

  return (
    <div>
      <PageHeader
        eyebrow={`${plural(items.length, "item")}${stale ? ` · ${stale} stale` : ""}`}
        title="Pipeline"
        subtitle="In-flight work. Drag cards between columns. Items with no movement for 14+ days are flagged stale."
      />
      <div className="grid gap-4 @3xl:grid-cols-2 @6xl:grid-cols-4">
        {STAGES.map((col, ci) => {
          const cards = items.filter((i) => i.stage === col.id);
          return (
            <section
              data-panel="pipeline"
              key={col.id}
              aria-label={col.label}
              onDragOver={(e) => {
                if (e.dataTransfer.types.includes("text/x-areao1-pipeline")) {
                  e.preventDefault();
                  setOver(col.id);
                }
              }}
              onDragLeave={() => setOver(null)}
              onDrop={(e) => drop(e, col.id)}
              className={cx("card flex min-h-80 animate-rise flex-col transition-colors duration-150", over === col.id && "bg-sunken outline-2 outline-offset-2 outline-ink")}
            >
              <h2 className="flex items-baseline justify-between border-b border-frame px-5 py-4">
                <span className="display text-3xl">{col.label}</span>
                <span className="num text-sm text-ink-2">{cards.length}</span>
              </h2>
              {col.id === "idea" && (
                <form
                  className="flex border-b border-line"
                  onSubmit={(e) => {
                    e.preventDefault();
                    if (title.trim()) save(() => api.addPipeline({ title: title.trim() }).then(() => setTitle("")), "Added");
                  }}
                >
                  <input className="min-w-0 flex-1 bg-transparent px-5 py-3 text-sm placeholder:text-muted focus:outline-none" placeholder="Add an idea" aria-label="New idea" value={title} onChange={(e) => setTitle(e.target.value)} />
                  <Button size="sm" type="submit" variant="ghost" className="m-1.5 px-2" aria-label="Add idea">
                    <Plus />
                  </Button>
                </form>
              )}
              <div className="flex flex-col">
                {cards.map((item) => (
                  <article
                    key={item.id}
                    draggable
                    onDragStart={(e) => {
                      e.dataTransfer.setData("text/x-areao1-pipeline", item.id);
                      e.dataTransfer.effectAllowed = "move";
                    }}
                    style={{ viewTransitionName: `pl-${item.id}` }}
                    className={cx("cursor-grab border-b border-line bg-surface px-5 py-4 active:cursor-grabbing", item.stale && "border-l-[3px] border-l-alert")}
                  >
                    <div className="flex items-start gap-2">
                      <h3 className="min-w-0 flex-1 text-[15px] leading-snug font-medium">
                        {item.url ? (
                          <a href={item.url} target="_blank" rel="noreferrer" className="link">
                            {item.title}
                          </a>
                        ) : (
                          item.title
                        )}
                      </h3>
                      <button className="text-muted hover:text-ink" aria-label={`Delete ${item.title}`} onClick={() => save(() => api.deletePipeline(item.id), "Deleted")}>
                        <X className="size-4" />
                      </button>
                    </div>
                    <div className="mt-2 flex flex-wrap items-center gap-1">
                      {item.criterion && (
                        <span title={labels[item.criterion] ?? item.criterion}>
                          <Chip>{short[item.criterion] ?? item.criterion}</Chip>
                        </span>
                      )}
                      {item.stale && <Chip tone="alert">stale {item.days_since_move}d</Chip>}
                    </div>
                    {item.notes && <p className="mt-2 line-clamp-3 text-xs leading-relaxed text-ink-2">{item.notes}</p>}
                    <div className="mt-3 flex items-center gap-2">
                      <label className="eyebrow flex flex-1 items-center gap-2">
                        Follow up
                        <input
                          type="date"
                          className="input h-7 w-auto px-1.5 py-0 font-mono text-[11px]"
                          value={item.follow_up ?? ""}
                          onChange={(e) => save(() => api.updatePipeline(item.id, { follow_up: e.target.value || null }))}
                        />
                      </label>
                      <Button size="sm" variant="ghost" className="h-7 px-1.5" disabled={ci === 0} aria-label="Move left" onClick={() => move(item, STAGES[ci - 1].id)}>
                        <ArrowLeft />
                      </Button>
                      <Button size="sm" variant="ghost" className="h-7 px-1.5" disabled={ci === STAGES.length - 1} aria-label="Move right" onClick={() => move(item, STAGES[ci + 1].id)}>
                        <ArrowRight />
                      </Button>
                    </div>
                  </article>
                ))}
              </div>
            </section>
          );
        })}
      </div>
    </div>
  );
}
