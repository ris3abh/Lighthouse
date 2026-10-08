import { ExternalLink, List, Minus, Pause, Play, Plus, Scan, Sparkles, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, type ConstellationView, type Provenance } from "../api";
import Banter from "../components/Banter";
import { Button, Chip, cx, Empty, ErrorBox, Loading, PageHeader, plural, Segmented, useReducedMotion } from "../components/ui";
import { useLoad } from "../hooks";
import {
  DEFAULT_STATUSES,
  fit,
  glide,
  Grid,
  layout,
  partial,
  toScreen,
  toWorld,
  trail,
  visible,
  zoomAt,
  type Camera,
  type Filters,
  type Placed,
  type StarStatus,
} from "../lib/constellation";

const STATUS_LABEL: Record<StarStatus, string> = { approved: "approved", pending: "pending", superseded: "superseded", rejected: "rejected" };

/** The constellation memory map (H1, ADR 0012): every claim a star in its criterion's cluster. */
export default function Memory() {
  const data = useLoad(() => api.constellation(), []);
  const [view, setView] = useState<"sky" | "list">("sky");
  const [filters, setFilters] = useState<Filters>({ criterion: "all", entity: "", statuses: new Set(DEFAULT_STATUSES), from: null, until: null });
  const [selected, setSelected] = useState<string | null>(null);
  if (data.error) return <ErrorBox error={data.error} retry={data.reload} />;
  if (!data.data)
    return (
      <div className="flex h-[62vh] min-h-[360px] items-center justify-center border border-ink md:h-[70vh]" style={{ background: "var(--sky-1)", color: "var(--sky-ink)" }} data-sky-loading>
        <Banter id="constellation_loading" className="font-mono text-sm tracking-[0.08em] uppercase" fallback="Loading the constellation" />
      </div>
    );
  const c = data.data;
  const approved = c.stars.filter((s) => s.status === "approved").length;
  return (
    <div data-page="memory">
      <PageHeader
        eyebrow={`${plural(c.stars.length, "claim")} · ${approved} approved`}
        title="Memory"
        subtitle="Every fact Area O1 holds, as a sky: one cluster per criterion, one star per claim. Bright is confident, solid is approved, a ring is waiting for you, red is a conflict. Click a star for its trail back to the source."
        actions={
          <Segmented
            label="Sky or list"
            value={view}
            onChange={setView}
            options={[
              { value: "sky", label: <><Sparkles /> Sky</> },
              { value: "list", label: <><List /> List</> },
            ]}
          />
        }
      />
      {c.stars.length === 0 ? (
        <Empty>No claims yet. They arrive from your sources, uploads and the Inbox, each quoting where it came from.</Empty>
      ) : (
        <>
          <FilterBar c={c} filters={filters} setFilters={setFilters} />
          {view === "sky" ? (
            <Sky c={c} filters={filters} selected={selected} onSelect={setSelected} />
          ) : (
            <StarList c={c} filters={filters} onSelect={setSelected} />
          )}
          <TimeSlider dates={[...new Set(c.stars.map((s) => s.date))].sort()} until={filters.until} onChange={(until) => setFilters({ ...filters, until })} />
          {selected && <Trail c={c} id={selected} onClose={() => setSelected(null)} />}
        </>
      )}
    </div>
  );
}

function FilterBar({ c, filters, setFilters }: { c: ConstellationView; filters: Filters; setFilters: (f: Filters) => void }) {
  const toggle = (s: StarStatus) => {
    const next = new Set(filters.statuses);
    if (next.has(s)) next.delete(s);
    else next.add(s);
    setFilters({ ...filters, statuses: next });
  };
  return (
    <div className="mb-4 flex flex-wrap items-end gap-3" data-memory-filters>
      <label>
        <span className="label">Criterion</span>
        <select className="input" value={filters.criterion} onChange={(e) => setFilters({ ...filters, criterion: e.target.value })}>
          <option value="all">All criteria</option>
          {c.clusters.map((k) => (
            <option key={k.id} value={k.id}>
              {k.label}
            </option>
          ))}
        </select>
      </label>
      <label className="min-w-0 flex-1 basis-48">
        <span className="label">Entity</span>
        <input className="input" type="search" placeholder="A paper, repo, event or person" value={filters.entity} onChange={(e) => setFilters({ ...filters, entity: e.target.value })} />
      </label>
      <label>
        <span className="label">From</span>
        <input className="input" type="date" value={filters.from ?? ""} onChange={(e) => setFilters({ ...filters, from: e.target.value || null })} />
      </label>
      <div className="flex flex-wrap gap-1.5" role="group" aria-label="Status">
        {(["approved", "pending", "superseded", "rejected"] as StarStatus[]).map((s) => (
          <button
            key={s}
            type="button"
            aria-pressed={filters.statuses.has(s)}
            onClick={() => toggle(s)}
            className={cx(
              "h-8 border px-3 font-mono text-[11px] tracking-[0.06em] uppercase transition-colors duration-150",
              filters.statuses.has(s) ? "border-ink bg-ink text-on-ink" : "border-line text-ink-2 hover:border-ink",
            )}
          >
            {STATUS_LABEL[s]}
          </button>
        ))}
      </div>
    </div>
  );
}

function cssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

/** The sky: one canvas, drawn when something changes; drag to pan, wheel or pinch to zoom, click a star. */
function Sky({ c, filters, selected, onSelect }: { c: ConstellationView; filters: Filters; selected: string | null; onSelect: (id: string | null) => void }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const wrap = useRef<HTMLDivElement>(null);
  const L = useMemo(() => layout(c.clusters, c.stars), [c]);
  const grid = useMemo(() => new Grid(L.placed), [L]);
  const [size, setSize] = useState({ w: 800, h: 520 });
  const cam = useRef<Camera | null>(null);
  const target = useRef<Camera | null>(null); // where the camera glides to
  const pointers = useRef(new Map<number, { x: number; y: number }>());
  const moved = useRef(0);
  const [, force] = useState(0);
  const reduced = useReducedMotion();
  const born = useRef(performance.now()); // stars fade in from here
  const trailAt = useRef(0); // when the selected star's trail started drawing
  const frame = useRef(0);
  const last = useRef(performance.now());
  const shown = useCallback((p: Placed) => visible(p.star, filters), [filters]);
  useEffect(() => {
    trailAt.current = performance.now();
  }, [selected]);

  useEffect(() => {
    const el = wrap.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setSize({ w: Math.max(280, e.contentRect.width), h: Math.max(320, e.contentRect.height) }));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  useEffect(() => {
    cam.current = fit(L.bounds, size.w, size.h);
    target.current = cam.current;
    force((n) => n + 1);
  }, [L, size.w, size.h]);

  /** Draw one frame; returns whether anything is still moving (a fade, a twinkle, a glide, a trail). */
  const draw = useCallback((): boolean => {
    const el = canvas.current;
    const now = performance.now();
    const dt = now - last.current;
    last.current = now;
    let moving = false;
    if (cam.current && target.current && cam.current !== target.current) {
      if (reduced) cam.current = target.current;
      else {
        const [next, done] = glide(cam.current, target.current, dt);
        cam.current = next;
        moving = !done;
      }
    }
    const camera = cam.current;
    if (!el || !camera) return false;
    const dpr = window.devicePixelRatio || 1;
    if (el.width !== Math.round(size.w * dpr)) {
      el.width = Math.round(size.w * dpr);
      el.height = Math.round(size.h * dpr);
    }
    const g = el.getContext("2d")!;
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    const bg = g.createRadialGradient(size.w / 2, size.h / 2, 0, size.w / 2, size.h / 2, Math.max(size.w, size.h) * 0.75);
    bg.addColorStop(0, cssVar("--sky-2"));
    bg.addColorStop(1, cssVar("--sky-1"));
    g.fillStyle = bg;
    g.fillRect(0, 0, size.w, size.h);
    const star = cssVar("--star");
    const conflict = cssVar("--star-conflict");
    g.font = "10.5px 'JetBrains Mono Variable', ui-monospace, monospace";
    g.textAlign = "center";
    for (const [id, ctr] of L.centers) {
      const { sx, sy } = toScreen(camera, size.w, size.h, ctr.x, ctr.y);
      g.strokeStyle = "rgba(233,230,220,0.08)";
      g.lineWidth = 1;
      g.beginPath();
      g.arc(sx, sy, ctr.radius * camera.k, 0, Math.PI * 2);
      g.stroke();
      g.fillStyle = filters.criterion === "all" || filters.criterion === id ? cssVar("--sky-muted") : "rgba(138,143,160,0.35)";
      g.fillText(ctr.label.toUpperCase(), sx, sy - ctr.radius * camera.k - 8);
    }
    const scale = Math.max(0.7, Math.min(2.6, camera.k * 1.4));
    const n = Math.max(1, L.placed.length);
    const age = now - born.current;
    for (const p of L.placed) {
      if (!shown(p)) continue;
      const { sx, sy } = toScreen(camera, size.w, size.h, p.x, p.y);
      if (sx < -10 || sy < -10 || sx > size.w + 10 || sy > size.h + 10) continue;
      const s = p.star;
      let alpha = 0.35 + 0.65 * s.confidence;
      if (!reduced) {
        const fade = Math.min(1, Math.max(0, (age - (p.order / n) * 900) / 500)); // fade in, oldest first
        if (fade < 1) moving = true;
        alpha *= fade;
        if (s.status === "pending") {
          alpha *= 0.62 + 0.38 * Math.sin(now / 700 + p.order * 1.7); // only pending stars twinkle
          moving = true;
        }
      }
      if (s.status === "superseded") alpha *= 0.25;
      if (s.status === "rejected") alpha *= 0.2;
      const r = p.r * scale;
      g.globalAlpha = alpha;
      const color = s.conflict ? conflict : star;
      if (s.conflict) {
        g.shadowColor = conflict;
        g.shadowBlur = 10;
      }
      g.beginPath();
      g.arc(sx, sy, r, 0, Math.PI * 2);
      if (s.status === "pending") {
        g.strokeStyle = color;
        g.lineWidth = 1;
        g.stroke();
      } else {
        g.fillStyle = color;
        g.fill();
      }
      g.shadowBlur = 0;
    }
    g.globalAlpha = 1;
    if (selected) {
      const progress = reduced ? 1 : Math.min(1, (now - trailAt.current) / 900);
      if (progress < 1) moving = true;
      const full = trail(L, selected);
      const drawn = partial(full, progress);
      const pts = drawn.map((q) => toScreen(camera, size.w, size.h, q.x, q.y));
      g.strokeStyle = cssVar("--star-trail");
      g.lineWidth = 1.5;
      g.setLineDash([4, 3]);
      g.beginPath();
      pts.forEach((q, i) => (i ? g.lineTo(q.sx, q.sy) : g.moveTo(q.sx, q.sy)));
      g.stroke();
      g.setLineDash([]);
      pts.slice(1).filter((_, i) => i + 1 < pts.length && (progress >= 1 || i + 2 < pts.length)).forEach((q, i) => {
        g.fillStyle = cssVar("--star-trail");
        g.fillRect(q.sx - 3, q.sy - 3, 6, 6);
        g.fillStyle = cssVar("--sky-ink");
        g.textAlign = "center";
        g.fillText(i === 0 ? "SOURCE" : "EXHIBIT", q.sx, q.sy + 15); // below the node: cluster labels sit above
      });
      const first = pts[0];
      if (first) {
        g.strokeStyle = cssVar("--star-trail");
        g.beginPath();
        g.arc(first.sx, first.sy, 7, 0, Math.PI * 2);
        g.stroke();
      }
    }
    return moving;
  }, [L, size, shown, selected, filters.criterion, reduced]);

  // Draw on every change, and keep animating only while something moves.
  const kick = useCallback(() => {
    cancelAnimationFrame(frame.current);
    const loop = () => {
      if (draw()) frame.current = requestAnimationFrame(loop);
    };
    last.current = performance.now();
    loop();
  }, [draw]);
  useEffect(() => {
    kick();
    return () => cancelAnimationFrame(frame.current);
  }, [kick]);

  const pick = (sx: number, sy: number) => {
    const camera = cam.current!;
    const w = toWorld(camera, size.w, size.h, sx, sy);
    return grid.nearest(w.x, w.y, 12 / camera.k, shown);
  };
  const local = (e: { clientX: number; clientY: number }) => {
    const r = canvas.current!.getBoundingClientRect();
    return { x: e.clientX - r.left, y: e.clientY - r.top };
  };
  const zoom = (factor: number, at?: { x: number; y: number }, now = false) => {
    target.current = zoomAt(target.current ?? cam.current!, size.w, size.h, at?.x ?? size.w / 2, at?.y ?? size.h / 2, factor);
    if (now) cam.current = target.current;
    kick();
  };
  const goTo = (c2: Camera) => {
    target.current = c2;
    kick();
  };

  return (
    <div ref={wrap} className="relative h-[62vh] min-h-[360px] overflow-hidden border border-ink md:h-[70vh]" data-sky>
      <canvas
        ref={canvas}
        role="img"
        aria-label={`Constellation of ${c.stars.length} claims; use the List view to read them`}
        tabIndex={0}
        className="block h-full w-full cursor-grab touch-none outline-none focus-visible:ring-2 focus-visible:ring-[var(--star-trail)]"
        style={{ width: size.w, height: size.h }}
        onWheel={(e) => zoom(Math.exp(-e.deltaY * 0.0015), local(e))}
        onPointerDown={(e) => {
          (e.target as Element).setPointerCapture(e.pointerId);
          pointers.current.set(e.pointerId, local(e));
          moved.current = 0;
        }}
        onPointerMove={(e) => {
          const prev = pointers.current.get(e.pointerId);
          if (!prev) return;
          const now = local(e);
          if (pointers.current.size === 2) {
            const [a, b] = [...pointers.current.values()];
            const other = a === prev ? b : a;
            const before = Math.hypot(prev.x - other.x, prev.y - other.y);
            const after = Math.hypot(now.x - other.x, now.y - other.y);
            if (before > 0) zoom(after / before, { x: (now.x + other.x) / 2, y: (now.y + other.y) / 2 }, true);
          } else {
            const camera = cam.current!;
            cam.current = { ...camera, x: camera.x - (now.x - prev.x) / camera.k, y: camera.y - (now.y - prev.y) / camera.k };
            target.current = cam.current; // dragging follows the finger
            kick();
          }
          moved.current += Math.abs(now.x - prev.x) + Math.abs(now.y - prev.y);
          pointers.current.set(e.pointerId, now);
        }}
        onPointerUp={(e) => {
          const at = local(e);
          pointers.current.delete(e.pointerId);
          if (moved.current < 6) {
            const hit = pick(at.x, at.y);
            onSelect(hit?.star.id ?? null);
            if (hit) {
              const t = target.current ?? cam.current!;
              goTo({ k: Math.max(t.k, 1.6), x: hit.x, y: hit.y }); // glide to the star
            }
          }
        }}
        onKeyDown={(e) => {
          const camera = cam.current!;
          const step = 60 / camera.k;
          const moves: Record<string, [number, number]> = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] };
          if (moves[e.key]) {
            e.preventDefault();
            const t = target.current ?? camera;
            goTo({ ...t, x: t.x + moves[e.key][0], y: t.y + moves[e.key][1] });
          } else if (e.key === "+" || e.key === "=") zoom(1.4);
          else if (e.key === "-") zoom(1 / 1.4);
          else if (e.key === "0") goTo(fit(L.bounds, size.w, size.h));
          else if (e.key === "Escape") onSelect(null);
        }}
      />
      <div className="absolute top-3 right-3 flex flex-col gap-1">
        <Button size="sm" aria-label="Zoom in" onClick={() => zoom(1.4)}>
          <Plus />
        </Button>
        <Button size="sm" aria-label="Zoom out" onClick={() => zoom(1 / 1.4)}>
          <Minus />
        </Button>
        <Button size="sm" aria-label="Fit the whole sky" onClick={() => goTo(fit(L.bounds, size.w, size.h))}>
          <Scan />
        </Button>
      </div>
      <Legend />
    </div>
  );
}

function Legend() {
  return (
    <ul className="pointer-events-none absolute bottom-3 left-3 hidden gap-3 font-mono text-[10px] tracking-[0.06em] uppercase sm:flex" style={{ color: "var(--sky-muted)" }}>
      <li className="flex items-center gap-1.5">
        <span className="inline-block size-2 rounded-full" style={{ background: "var(--star)" }} /> approved
      </li>
      <li className="flex items-center gap-1.5">
        <span className="inline-block size-2 rounded-full border" style={{ borderColor: "var(--star)" }} /> pending
      </li>
      <li className="flex items-center gap-1.5">
        <span className="inline-block size-2 rounded-full opacity-30" style={{ background: "var(--star)" }} /> superseded
      </li>
      <li className="flex items-center gap-1.5">
        <span className="inline-block size-2 rounded-full" style={{ background: "var(--star-conflict)", boxShadow: "0 0 6px var(--star-conflict)" }} /> conflict
      </li>
    </ul>
  );
}

/** The time slider: the case up to a date. Play replays it in date order (about six seconds); with reduced motion
 * it jumps to the end. */
function TimeSlider({ dates, until, onChange }: { dates: string[]; until: string | null; onChange: (d: string | null) => void }) {
  const reduced = useReducedMotion();
  const [playing, setPlaying] = useState(false);
  const idx = until ? Math.max(0, dates.findIndex((d) => d >= until)) : dates.length - 1;
  useEffect(() => {
    if (!playing) return;
    if (reduced) {
      onChange(null);
      setPlaying(false);
      return;
    }
    let i = idx >= dates.length - 1 ? 0 : idx;
    const step = Math.max(16, 6000 / dates.length);
    onChange(dates[i]);
    const timer = window.setInterval(() => {
      i += 1;
      if (i >= dates.length - 1) {
        onChange(null);
        setPlaying(false);
        window.clearInterval(timer);
      } else onChange(dates[i]);
    }, step);
    return () => window.clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [playing]);
  if (dates.length < 2) return null;
  return (
    <div className="mt-4 flex flex-wrap items-center gap-3" data-time-slider>
      <Button size="sm" aria-label={playing ? "Pause the replay" : "Replay the case in date order"} onClick={() => setPlaying((p) => !p)}>
        {playing ? <Pause /> : <Play />} {playing ? "Pause" : "Replay"}
      </Button>
      <span className="font-mono text-[10.5px] text-muted uppercase">{dates[0]}</span>
      <input
        type="range"
        min={0}
        max={dates.length - 1}
        value={idx}
        aria-label="Show the case up to this date"
        className="min-w-0 flex-1 accent-[var(--ink)]"
        onChange={(e) => {
          setPlaying(false);
          const i = Number(e.target.value);
          onChange(i >= dates.length - 1 ? null : dates[i]);
        }}
      />
      <span className="font-mono text-[10.5px] text-ink uppercase">Up to {dates[idx]}</span>
    </div>
  );
}

function StarList({ c, filters, onSelect }: { c: ConstellationView; filters: Filters; onSelect: (id: string) => void }) {
  const rows = c.stars.filter((s) => visible(s, filters));
  const labels = Object.fromEntries(c.clusters.map((k) => [k.id, k.label]));
  return (
    <div className="max-h-[70vh] overflow-auto border border-ink" data-star-list>
      <table className="w-full text-left text-sm">
        <thead className="sticky top-0 bg-surface font-mono text-[10.5px] text-muted uppercase">
          <tr>
            <th className="px-3 py-2">Date</th>
            <th className="px-3 py-2">Criterion</th>
            <th className="px-3 py-2">Claim</th>
            <th className="px-3 py-2">Status</th>
          </tr>
        </thead>
        <tbody>
          {rows.slice(0, 500).map((s) => (
            <tr key={s.id} className="border-t border-line">
              <td className="px-3 py-2 font-mono text-[11px] whitespace-nowrap">{s.date}</td>
              <td className="px-3 py-2">{labels[s.criterion] ?? s.criterion}</td>
              <td className="px-3 py-2">
                <button type="button" className="link text-left" onClick={() => onSelect(s.id)}>
                  {s.entity_name}: {s.predicate.replace(/_/g, " ")} {String(s.value ?? "")}
                </button>
              </td>
              <td className="px-3 py-2">
                <Chip tone={s.conflict ? "outline" : s.status === "approved" ? "ink" : "muted"} className={s.conflict ? "border-alert text-alert" : undefined}>
                  {s.conflict ? "conflict" : s.status}
                </Chip>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {rows.length > 500 && <p className="p-3 font-mono text-[10.5px] text-muted uppercase">Showing 500 of {rows.length}; narrow the filters to see the rest.</p>}
    </div>
  );
}

/** The provenance trail of one claim: excerpt, raw source, reviews, versions, citing exhibits. A side panel on wide
 * screens, a sheet on phones. */
function Trail({ c, id, onClose }: { c: ConstellationView; id: string; onClose: () => void }) {
  const [p, setP] = useState<Provenance | null>(null);
  const [error, setError] = useState<Error | null>(null);
  useEffect(() => {
    setP(null);
    api.provenance(id).then(setP, setError);
  }, [id]);
  const star = c.stars.find((s) => s.id === id);
  return (
    <aside
      className="fixed inset-x-0 bottom-0 z-40 max-h-[65vh] overflow-y-auto border-t border-ink bg-surface p-5 md:inset-x-auto md:top-24 md:right-6 md:bottom-auto md:max-h-[calc(100vh-8rem)] md:w-[380px] md:border"
      aria-label="Provenance"
      data-provenance
    >
      <div className="mb-3 flex items-start justify-between gap-3">
        <p className="font-mono text-[10.5px] text-muted uppercase">Provenance · {id}</p>
        <button type="button" aria-label="Close" onClick={onClose} className="text-ink-2 hover:text-ink">
          <X className="size-4" />
        </button>
      </div>
      {error ? (
        <ErrorBox error={error} />
      ) : !p ? (
        <Loading />
      ) : (
        <ol className="grid gap-4 text-sm">
          <li>
            <p className="label">Claim</p>
            <p className="font-medium">
              {p.entity?.name ?? p.claim.subject}: {p.claim.predicate.replace(/_/g, " ")} {String(p.claim.value ?? "")}
            </p>
            <p className="mt-1 flex flex-wrap gap-1.5">
              <Chip tone={p.claim.status === "approved" ? "ink" : "muted"}>{p.claim.status}</Chip>
              <Chip>{p.claim.confidence} confidence</Chip>
              {!p.claim.current && <Chip tone="outline">superseded</Chip>}
              {star?.conflict && <Chip tone="outline" className="border-alert text-alert">conflict</Chip>}
            </p>
          </li>
          <li>
            <p className="label">Excerpt {p.excerpt_verified ? "· verified against the snapshot" : "· not verified"}</p>
            <blockquote className="border-l-2 border-ink pl-3 text-ink-2">"{p.claim.excerpt}"</blockquote>
          </li>
          <li>
            <p className="label">Raw source</p>
            {p.observation ? (
              <>
                <p>
                  {p.observation.connector} · captured {p.observation.captured_at.slice(0, 10)}
                </p>
                {/^https?:/.test(p.observation.source_url) && (
                  <a className="link inline-flex items-center gap-1 break-all" href={p.observation.source_url} target="_blank" rel="noreferrer">
                    {p.observation.source_url} <ExternalLink className="inline size-3" aria-hidden />
                  </a>
                )}
                <p className="font-mono text-[10.5px] break-all text-muted">{p.observation.snapshot}</p>
              </>
            ) : (
              <p className="text-muted">The snapshot is missing.</p>
            )}
          </li>
          <li>
            <p className="label">Reviews</p>
            {p.reviews.length ? (
              p.reviews.map((r, i) => (
                <p key={i}>
                  {r.decision} {r.at.slice(0, 10)}
                  {r.rationale ? ` · ${r.rationale}` : ""}
                </p>
              ))
            ) : (
              <p className="text-muted">Not reviewed yet.</p>
            )}
          </li>
          {(p.supersedes.length > 0 || p.superseded_by.length > 0) && (
            <li>
              <p className="label">Versions</p>
              {p.superseded_by.map((v) => (
                <p key={v.id}>Replaced by {String(v.value)} ({v.valid_from ?? "undated"})</p>
              ))}
              {p.supersedes.map((v) => (
                <p key={v.id}>Replaces {String(v.value)} ({v.valid_from ?? "undated"})</p>
              ))}
            </li>
          )}
          {p.cited_by.length > 0 && (
            <li>
              <p className="label">Cited by</p>
              {p.cited_by.map((e) => (
                <a key={e.exhibit_id} className="link block" href="#/evidence">
                  {e.title}
                </a>
              ))}
            </li>
          )}
        </ol>
      )}
    </aside>
  );
}
