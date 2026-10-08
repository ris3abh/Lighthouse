// The constellation memory map (ADR 0012): pure layout, filtering, hit-testing and easing, so the page only draws.

export type StarStatus = "approved" | "pending" | "superseded" | "rejected";

export interface Star {
  id: string;
  criterion: string;
  entity: string;
  entity_name: string;
  predicate: string;
  value: string | number | boolean | null;
  stage: string | null;
  date: string; // YYYY-MM-DD
  confidence: number; // 0.33 / 0.66 / 1
  band: string;
  status: StarStatus;
  review: string | null;
  conflict: boolean;
  source: string;
  source_url: string | null;
  connector: string | null;
  exhibits: string[];
}

export interface Cluster {
  id: string;
  label: string;
}

export interface Placed {
  star: Star;
  x: number;
  y: number;
  r: number; // world radius
  order: number; // date order within the whole case (for the replay and the fade-in)
}

export interface Layout {
  placed: Placed[];
  byId: Map<string, Placed>;
  centers: Map<string, { x: number; y: number; radius: number; label: string }>;
  sources: Map<string, { x: number; y: number }>; // "<cluster>|<observation>": a source node beside each cluster using it
  exhibits: Map<string, { x: number; y: number }>; // "<cluster>|<exhibit>"
  bounds: { minX: number; minY: number; maxX: number; maxY: number };
  dates: string[]; // distinct dates, ascending
}

const GOLDEN = Math.PI * (3 - Math.sqrt(5));
const SPACING = 9;

function hash(s: string): number {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) h = Math.imul(h ^ s.charCodeAt(i), 16777619);
  return (h >>> 0) / 4294967296;
}

/** Clusters on a ring, stars spiraling out of each cluster's center in date order (oldest in the middle). */
export function layout(clusters: Cluster[], stars: Star[]): Layout {
  const byCluster = new Map<string, Star[]>(clusters.map((c) => [c.id, []]));
  for (const s of stars) (byCluster.get(s.criterion) ?? byCluster.set(s.criterion, []).get(s.criterion)!).push(s);
  const ids = [...byCluster.keys()];
  const radius = (n: number) => SPACING * Math.sqrt(Math.max(n, 1)) + 24;
  const biggest = Math.max(...ids.map((id) => radius(byCluster.get(id)!.length)), 60);
  const ring = ids.length <= 1 ? 0 : Math.max(420, (biggest * 2.4 * ids.length) / (2 * Math.PI));
  const sorted = [...stars].sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : a.id < b.id ? -1 : 1));
  const order = new Map(sorted.map((s, i) => [s.id, i]));
  const placed: Placed[] = [];
  const centers: Layout["centers"] = new Map();
  const sources: Layout["sources"] = new Map();
  const exhibits: Layout["exhibits"] = new Map();
  ids.forEach((id, i) => {
    const angle = ids.length <= 1 ? 0 : (i / ids.length) * Math.PI * 2 - Math.PI / 2;
    const cx = Math.cos(angle) * ring;
    const cy = Math.sin(angle) * ring;
    const members = byCluster.get(id)!.sort((a, b) => order.get(a.id)! - order.get(b.id)!);
    const rad = radius(members.length);
    centers.set(id, { x: cx, y: cy, radius: rad, label: clusters.find((c) => c.id === id)?.label ?? id });
    const phase = hash(id) * Math.PI * 2;
    members.forEach((s, k) => {
      const r = SPACING * Math.sqrt(k + 0.5);
      const t = k * GOLDEN + phase;
      placed.push({ star: s, x: cx + Math.cos(t) * r, y: cy + Math.sin(t) * r, r: 1.2 + 1.6 * s.confidence, order: order.get(s.id)! });
      const sk = `${id}|${s.source}`;
      if (!sources.has(sk)) {
        const a = hash(s.source) * Math.PI * 2;
        sources.set(sk, { x: cx + Math.cos(a) * (rad + 36), y: cy + Math.sin(a) * (rad + 36) });
      }
      for (const ex of s.exhibits) {
        const ek = `${id}|${ex}`;
        if (!exhibits.has(ek)) {
          const a = hash(ex) * Math.PI * 2;
          exhibits.set(ek, { x: cx + Math.cos(a) * (rad + 64), y: cy + Math.sin(a) * (rad + 64) });
        }
      }
    });
  });
  const xs = [...placed.map((p) => p.x), ...[...centers.values()].flatMap((c) => [c.x - c.radius - 70, c.x + c.radius + 70])];
  const ys = [...placed.map((p) => p.y), ...[...centers.values()].flatMap((c) => [c.y - c.radius - 70, c.y + c.radius + 70])];
  const bounds = { minX: Math.min(...xs, -100), minY: Math.min(...ys, -100), maxX: Math.max(...xs, 100), maxY: Math.max(...ys, 100) };
  const dates = [...new Set(sorted.map((s) => s.date))];
  return { placed, byId: new Map(placed.map((p) => [p.star.id, p])), centers, sources, exhibits, bounds, dates };
}

export interface Filters {
  criterion: string; // "all" or a cluster id
  entity: string; // a search over entity, value and predicate
  statuses: Set<StarStatus>;
  from: string | null; // YYYY-MM-DD, inclusive
  until: string | null; // the time slider: inclusive
}

export const DEFAULT_STATUSES: StarStatus[] = ["approved", "pending", "superseded"];

export function visible(s: Star, f: Filters): boolean {
  if (f.criterion !== "all" && s.criterion !== f.criterion) return false;
  if (!f.statuses.has(s.status)) return false;
  if (f.from && s.date < f.from) return false;
  if (f.until && s.date > f.until) return false;
  if (f.entity) {
    const q = f.entity.toLowerCase();
    if (![s.entity_name, s.entity, s.predicate, String(s.value ?? "")].some((t) => t.toLowerCase().includes(q))) return false;
  }
  return true;
}

/** A spatial grid over the stars, for picking the one under a pointer among thousands. */
export class Grid {
  private cells = new Map<string, Placed[]>();
  private size: number;
  constructor(items: Placed[], size = 24) {
    this.size = size;
    for (const p of items) {
      const k = this.key(p.x, p.y);
      (this.cells.get(k) ?? this.cells.set(k, []).get(k)!).push(p);
    }
  }
  private key(x: number, y: number) {
    return `${Math.floor(x / this.size)},${Math.floor(y / this.size)}`;
  }
  /** The nearest visible star within `radius` (world units) of (x, y). */
  nearest(x: number, y: number, radius: number, ok: (p: Placed) => boolean = () => true): Placed | null {
    let best: Placed | null = null;
    let bestD = radius * radius;
    const span = Math.ceil(radius / this.size);
    const cx = Math.floor(x / this.size);
    const cy = Math.floor(y / this.size);
    for (let i = cx - span; i <= cx + span; i++)
      for (let j = cy - span; j <= cy + span; j++)
        for (const p of this.cells.get(`${i},${j}`) ?? []) {
          const d = (p.x - x) ** 2 + (p.y - y) ** 2;
          if (d <= bestD && ok(p)) {
            best = p;
            bestD = d;
          }
        }
    return best;
  }
}

export interface Camera {
  x: number;
  y: number;
  k: number; // pixels per world unit
}

/** The camera that fits `bounds` into a w × h viewport. */
export function fit(bounds: Layout["bounds"], w: number, h: number): Camera {
  const k = Math.min(w / (bounds.maxX - bounds.minX), h / (bounds.maxY - bounds.minY)) * 0.92;
  return { x: (bounds.minX + bounds.maxX) / 2, y: (bounds.minY + bounds.maxY) / 2, k: Math.max(0.05, k) };
}

export const toScreen = (c: Camera, w: number, h: number, x: number, y: number) => ({ sx: (x - c.x) * c.k + w / 2, sy: (y - c.y) * c.k + h / 2 });
export const toWorld = (c: Camera, w: number, h: number, sx: number, sy: number) => ({ x: (sx - w / 2) / c.k + c.x, y: (sy - h / 2) / c.k + c.y });

/** Zoom by `factor` keeping the world point under (sx, sy) where it is. */
export function zoomAt(c: Camera, w: number, h: number, sx: number, sy: number, factor: number): Camera {
  const k = Math.min(40, Math.max(0.05, c.k * factor));
  const p = toWorld(c, w, h, sx, sy);
  return { k, x: p.x - (sx - w / 2) / k, y: p.y - (sy - h / 2) / k };
}

/** One step of a glide toward `target` (exponential ease; `dt` in ms). Returns the new camera and whether it settled. */
export function glide(c: Camera, target: Camera, dt: number): [Camera, boolean] {
  const a = 1 - Math.exp(-dt / 120);
  const next = { x: c.x + (target.x - c.x) * a, y: c.y + (target.y - c.y) * a, k: c.k + (target.k - c.k) * a };
  const done = Math.abs(next.k - target.k) / target.k < 0.002 && Math.hypot(next.x - target.x, next.y - target.y) * target.k < 0.5;
  return [done ? target : next, done];
}

/** The provenance trail on the sky: the star, then its raw source, then each exhibit that cites it. */
export function trail(l: Layout, id: string): { x: number; y: number }[] {
  const p = l.byId.get(id);
  if (!p) return [];
  const pts = [{ x: p.x, y: p.y }];
  const src = l.sources.get(`${p.star.criterion}|${p.star.source}`);
  if (src) pts.push(src);
  for (const ex of p.star.exhibits) {
    const e = l.exhibits.get(`${p.star.criterion}|${ex}`);
    if (e) pts.push(e);
  }
  return pts;
}

/** The part of a polyline drawn at `progress` (0..1), for the animated trail. */
export function partial(points: { x: number; y: number }[], progress: number): { x: number; y: number }[] {
  if (points.length < 2 || progress >= 1) return points;
  const seg = points.slice(1).map((p, i) => Math.hypot(p.x - points[i].x, p.y - points[i].y));
  let left = seg.reduce((a, b) => a + b, 0) * Math.max(0, progress);
  const out = [points[0]];
  for (let i = 0; i < seg.length; i++) {
    if (left >= seg[i]) {
      out.push(points[i + 1]);
      left -= seg[i];
      continue;
    }
    const t = seg[i] ? left / seg[i] : 0;
    out.push({ x: points[i].x + (points[i + 1].x - points[i].x) * t, y: points[i].y + (points[i + 1].y - points[i].y) * t });
    break;
  }
  return out;
}
