// Typed client for the Lighthouse API. Shapes mirror lighthouse_gc/core/models.py.

export type CriterionStatus = "banked" | "building" | "gap" | "dropped";

export interface CriterionScore {
  id: string;
  label: string;
  status: CriterionStatus;
  exhibit_count: number;
  exhibit_ids: string[];
  matched_signals: string[];
  missing_signals: string[];
  needed_exhibits: number;
  in_progress_count: number;
  reason: string;
  overridden: boolean;
}

export interface Scoreboard {
  profile: string;
  profile_name: string;
  computed_at: string;
  threshold: number;
  target: number;
  banked: number;
  building: number;
  criteria: CriterionScore[];
  reviewer_note: string | null;
}

export interface Point {
  date: string;
  value: number;
}

export interface Series {
  source: string;
  item: string;
  metric: string;
  url?: string | null;
  points: Point[];
  date: string;
  value: number;
  previous: number | null;
  previous_date: string | null;
  delta: number | null;
}

export interface Task {
  kind: string;
  title: string;
  due?: string;
  link?: string | null;
}

export interface Deadline {
  id: string;
  title: string;
  due: string;
  kind: string;
  criterion: string | null;
  url: string | null;
  days_left: number;
}

export interface Overview {
  person: { name: string; field: string; current_status: string; filing_target: { profile: string; target_date: string | null } };
  profile: string;
  profiles: { id: string; name: string }[];
  scoreboard: Scoreboard;
  inbox_pending: number;
  tasks: Task[];
  deadlines: Deadline[];
  sparklines: Series[];
  sources: { id: string; kind: string; last_sync: string | null; last_error: string | null }[];
}

export interface Candidate {
  id: string;
  fingerprint: string;
  source: string;
  item_id: string | null;
  evidence_type: string;
  proposed_criterion: string;
  title: string;
  summary: string;
  confidence: number;
  raw_url: string | null;
  signals: string[];
  facts: Record<string, string | number>;
  created_at: string;
  status: "pending" | "snoozed" | "rejected";
  snoozed_until: string | null;
  stage: string | null;
  claim_ids: string[];
  kind: "evidence" | "pipeline" | "deadline" | "letter" | "update" | "metric";
  attachment: string | null;
  source_tier: string | null;
  proposal: Record<string, unknown>;
}

export type ReviewStatus = "proposed" | "corroborated" | "approved" | "rejected";

export interface Claim {
  id: string;
  subject: string;
  predicate: string;
  value: string | number | boolean | null;
  stage: string | null;
  valid_from: string | null;
  recorded_at: string;
  excerpt: string;
  excerpt_start: number;
  excerpt_end: number;
  confidence: "high" | "medium" | "low";
  version: number;
  status: ReviewStatus;
  source_url: string | null;
  connector: string | null;
  captured_at: string | null;
  snapshot: string | null;
}

/** Stages that count toward a criterion; everything else (invited, submitted, preprint…) waits. */
export const COMPLETED_STAGES = new Set(["completed", "published", "granted"]);
export const STAGES = ["invited", "accepted", "completed", "declined", "cancelled", "preprint", "submitted", "published", "retracted", "applied", "granted", "denied"];
export const stageCounts = (stage: string | null) => stage === null || COMPLETED_STAGES.has(stage);

export interface Exhibit {
  id: string;
  criterion: string;
  evidence_type: string;
  title: string;
  summary: string;
  date: string;
  file: string;
  source_url: string | null;
  signals: string[];
  stage: string | null;
  claim_ids: string[];
  accepted_at: string;
}

export interface Signal {
  id: string;
  label: string;
}

export interface EvidenceCriterion extends CriterionScore {
  evidence_types: string[];
  strength_signals: Signal[];
  bank: { min_exhibits: number; min_signals: number } | null;
  exhibits: Exhibit[];
}

export interface NamingIssue {
  file: string;
  problem: string;
  detail: string;
}

export interface EvidenceView {
  criteria: EvidenceCriterion[];
  other_exhibits: Exhibit[];
  naming_issues: NamingIssue[];
}

export interface ProfileCriterion {
  id: string;
  label: string;
  regulation: string;
  description: string;
  evidence_types: string[];
  strength_signals: Signal[];
}

export interface Profile {
  id: string;
  name: string;
  threshold: number;
  target: number;
  criteria: ProfileCriterion[];
}

export interface TrackedItem {
  id: string;
  kind: string;
  name: string;
  url: string;
  title: string;
  private: boolean;
  tracked: boolean;
}

export interface Source {
  id: string;
  kind: string;
  handle: string;
  url: string;
  auth: "none" | "token";
  last_sync: string | null;
  last_error: string | null;
  items: TrackedItem[];
  token_help: string | null;
}

export interface SyncReport {
  source_id: string;
  items: number;
  new_items: number;
  metrics_written: number;
  candidates_added: number;
  errors: string[];
}

export interface ChannelView {
  name: string;
  kind: string;
  enabled: boolean;
  detail: "full" | "minimal";
  secret_ref: string | null;
  secret_stored: boolean;
  server?: string;
  topic?: string | null;
  host?: string | null;
  to_addr?: string | null;
}

export interface Autopilot {
  tracker_updates: boolean;
  metrics: boolean;
  tier1_deadlines: boolean;
}

export interface ChangeView {
  id: string;
  at: string;
  actor: string;
  action: string;
  target_type: string;
  target_id: string | null;
  summary: string;
  auto: boolean;
  undoes: string | null;
  undoable: boolean;
  undone: boolean;
}

export interface BriefingView {
  generated_at: string | null;
  run_id: string | null;
  since: string | null;
  changed: string[];
  todos: {
    title: string;
    why: string;
    candidate_id: string | null;
    link: string | null;
    candidate: { id: string; kind: Candidate["kind"]; title: string; status: string; proposed_criterion: string; source_tier: string | null } | null;
  }[];
  refreshing: string | null;
}

export interface Missions {
  opportunity_scout: boolean;
  what_changed: boolean;
}

export interface MissionView {
  name: keyof Missions;
  title: string;
  enabled: boolean;
  job: string;
  schedule: string | null;
  next_run: string | null;
  model: string;
  last_run: { id: string; at: string; proposals: number; cost_usd: number | null } | null;
}

export interface SettingsView {
  profile: string;
  engine: string;
  privacy: { redact_before_llm: boolean };
  channels: ChannelView[];
  routes: Record<string, string[]>;
  deadline_alert_days: number[];
  autopilot: Autopilot;
  missions: Missions;
  schedules: Record<string, string>;
  recent_notifications: { at: string; event: string; title: string; ok: boolean; results: { channel: string; ok: boolean; error: string | null }[] }[];
}

export interface DeadlineItem {
  id: string;
  title: string;
  due: string;
  kind: string;
  criterion: string | null;
  url: string | null;
  human_only: boolean;
  done: boolean;
  days_left: number;
}

export interface PipelineCard {
  id: string;
  title: string;
  criterion: string | null;
  stage: "idea" | "applied" | "waiting" | "done";
  url: string | null;
  follow_up: string | null;
  created_at: string;
  moved_at: string;
  notes: string;
  days_since_move: number;
  stale: boolean;
}

export interface JobStatus {
  name: string;
  description: string;
  schedule: string | null;
  next_run: string | null;
  error: string | null;
  last_run?: string;
  ok?: boolean;
  summary?: string[];
}

export interface LetterWriter {
  id: string;
  name: string;
  relationship: "employer" | "independent" | "coauthor";
  credentials: string;
  criteria: string[];
  asks: string[];
  status: "prospect" | "asked" | "drafting" | "sent" | "signed" | "declined";
  draft_path: string | null;
  last_contact: string | null;
  draft_exists: boolean;
}

export interface LettersView {
  letters: LetterWriter[];
  coverage: { id: string; label: string; independent: number; employer: number; coauthor: number }[];
  criteria: { id: string; label: string }[];
}

export interface AgentStatus {
  engine: string;
  available: boolean;
  reason: string;
  model: string;
  models: { chat: string; task: string; mission: string };
  effort: string;
  web_search: boolean;
  budget: { per_run_tokens: number; per_run_usd: number | null; monthly_tokens: number; monthly_usd: number | null };
  month: { tokens: number; usd: number; cache_read: number; cache_write: number; uncached_input: number; cache_hit_rate: number | null };
}

export interface TimelineItem {
  type: "text" | "tool_call" | "error";
  at: string;
  text: string;
  tool: string | null;
  tool_id: string | null;
  input: Record<string, unknown>;
  ok: boolean | null;
  result: string;
}

export interface AgentRunView {
  id: string;
  kind: "chat" | "manual" | "scheduled";
  mission: string | null;
  status: "running" | "done" | "error" | "stopped";
  engine: string;
  model: string;
  prompt: string;
  conversation_id: string | null;
  started_at: string;
  finished_at: string | null;
  text: string;
  timeline?: TimelineItem[];
  sources: { url: string; title: string; observation_id: string | null; at: string }[];
  proposals: string[];
  changes: string[];
  usage: { input_tokens: number; output_tokens: number; cache_creation_input_tokens: number; cache_read_input_tokens: number };
  counted_tokens: number;
  cost_usd: number | null;
  stop_reason: string | null;
  error: string | null;
  tool_calls?: number;
}

export interface ConversationView {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  messages: { role: "user" | "assistant"; text: string; at: string; run_id: string | null }[];
}

/** One event from /api/agent/runs/{id}/stream. */
export type AgentEvent = { type: string; [key: string]: unknown };

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const init: RequestInit = { method, headers: {} };
  const headers = init.headers as Record<string, string>;
  if (method !== "GET") headers["X-Lighthouse"] = "1"; // the server rejects writes without it
  if (body instanceof FormData) {
    init.body = body;
  } else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(body);
  }
  const res = await fetch(`./api${path}`, init);
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const data = await res.json();
      detail = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail);
    } catch {
      /* not JSON */
    }
    throw new ApiError(detail, res.status);
  }
  return (await res.json()) as T;
}

const enc = encodeURIComponent;

export const api = {
  overview: () => request<Overview>("GET", "/overview"),
  profiles: () => request<Profile[]>("GET", "/profiles"),
  profile: () => request<Profile>("GET", "/profile"),
  setProfile: (id: string) => request<Scoreboard>("PUT", "/profile", { id }),
  setOverride: (criterion: string, status: "dropped" | "gap" | null) =>
    request<Scoreboard>("PUT", `/criteria/${enc(criterion)}/override`, { status }),

  inbox: () => request<Candidate[]>("GET", "/inbox"),
  editCandidate: (id: string, edits: Partial<Candidate>) => request<Candidate>("PATCH", `/inbox/${enc(id)}`, edits),
  accept: (id: string, edits: Partial<Candidate> & { date?: string }) =>
    request<Exhibit>("POST", `/inbox/${enc(id)}/accept`, edits),
  uploadToInbox: (files: File[], criterion?: string) => {
    const form = new FormData();
    for (const f of files) form.append("files", f);
    if (criterion) form.append("criterion", criterion);
    return request<Candidate[]>("POST", "/inbox/upload", form);
  },
  importChats: (file: File, keepAll = false) => {
    const form = new FormData();
    form.append("file", file);
    form.append("keep_all", String(keepAll));
    return request<{ provider: string; conversations: number; snapshots_new: number; candidates_added: Record<string, number>; summary: string }>(
      "POST",
      "/imports/chats",
      form,
    );
  },
  attachmentUrl: (obsId: string) => `./api/attachments/${enc(obsId)}`,
  reject: (id: string) => request<Candidate>("POST", `/inbox/${enc(id)}/reject`),
  snooze: (id: string, until?: string) => request<Candidate>("POST", `/inbox/${enc(id)}/snooze`, { until }),

  claims: (ids: string[]) => request<Claim[]>("GET", `/claims?ids=${ids.map(enc).join(",")}`),

  evidence: () => request<EvidenceView>("GET", "/exhibits"),
  upload: (form: FormData) => request<Exhibit>("POST", "/exhibits/upload", form),
  remap: (id: string, criterion: string) => request<Exhibit>("PATCH", `/exhibits/${enc(id)}`, { criterion }),
  fileUrl: (path: string) => `./api/files/${path.split("/").map(enc).join("/")}`,

  metrics: () => request<{ series: Series[] }>("GET", "/metrics"),
  snapshot: () => request<{ reports: SyncReport[] }>("POST", "/metrics/snapshot"),
  exportUrl: "./api/metrics/export.csv",

  deadlines: () => request<DeadlineItem[]>("GET", "/deadlines"),
  addDeadline: (d: { title: string; due: string; kind: string }) => request<DeadlineItem>("POST", "/deadlines", d),
  updateDeadline: (id: string, d: Partial<DeadlineItem>) => request<DeadlineItem>("PATCH", `/deadlines/${enc(id)}`, d),
  deleteDeadline: (id: string) => request<{ removed: string }>("DELETE", `/deadlines/${enc(id)}`),
  pipeline: () => request<PipelineCard[]>("GET", "/pipeline"),
  addPipeline: (p: Partial<PipelineCard>) => request<PipelineCard>("POST", "/pipeline", p),
  updatePipeline: (id: string, p: Partial<PipelineCard>) => request<PipelineCard>("PATCH", `/pipeline/${enc(id)}`, p),
  deletePipeline: (id: string) => request<{ removed: string }>("DELETE", `/pipeline/${enc(id)}`),
  letters: () => request<LettersView>("GET", "/letters"),
  addLetter: (l: Partial<LetterWriter>) => request<LetterWriter>("POST", "/letters", l),
  updateLetter: (id: string, l: Partial<LetterWriter>) => request<LetterWriter>("PATCH", `/letters/${enc(id)}`, l),
  deleteLetter: (id: string) => request<{ removed: string }>("DELETE", `/letters/${enc(id)}`),
  draftUrl: (path: string) => `./api/drafts/${path.replace(/^drafts\//, "").split("/").map(enc).join("/")}`,
  jobs: () => request<JobStatus[]>("GET", "/jobs"),
  runJob: (name: string) => request<JobStatus>("POST", `/jobs/${enc(name)}/run`),
  calendarUrl: "./calendar.ics",

  agentStatus: () => request<AgentStatus>("GET", "/agent/status"),
  chat: (message: string, conversation_id?: string | null, page?: string) =>
    request<{ run_id: string; conversation_id: string }>("POST", "/agent/chat", { message, conversation_id: conversation_id ?? null, page }),
  briefing: () => request<BriefingView>("GET", "/briefing"),
  missions: () => request<MissionView[]>("GET", "/agent/missions"),
  runMission: (name: string) => request<{ run_id: string }>("POST", `/agent/missions/${enc(name)}/run`),
  setMissions: (flags: Partial<Missions>) => request<Missions>("PUT", "/settings/missions", flags),
  startRun: (prompt: string) => request<{ run_id: string }>("POST", "/agent/runs", { prompt }),
  stopRun: (id: string) => request<{ stopping: boolean }>("POST", `/agent/runs/${enc(id)}/stop`),
  runs: () => request<AgentRunView[]>("GET", "/agent/runs"),
  run: (id: string) => request<AgentRunView>("GET", `/agent/runs/${enc(id)}`),
  runStreamUrl: (id: string) => `./api/agent/runs/${enc(id)}/stream`,
  changes: (actor?: string) => request<ChangeView[]>("GET", `/changes${actor ? `?actor=${enc(actor)}` : ""}`),
  undoChange: (id: string) => request<ChangeView>("POST", `/changes/${enc(id)}/undo`),
  setAutopilot: (flags: Partial<Autopilot>) => request<Autopilot>("PUT", "/settings/autopilot", flags),
  allCandidates: () => request<Candidate[]>("GET", "/inbox?status=all"),
  conversations: () => request<{ id: string; title: string; updated_at: string; messages: number }[]>("GET", "/agent/conversations"),
  conversation: (id: string) => request<ConversationView>("GET", `/agent/conversations/${enc(id)}`),

  settings: () => request<SettingsView>("GET", "/settings"),
  notifyTest: (channel?: string) => request<{ ok: boolean; summary: string }>("POST", "/notify/test", { channel: channel ?? null }),

  sources: () => request<Source[]>("GET", "/sources"),
  addSource: (input: string, token?: string) => request<SyncReport>("POST", "/sources", { input, token }),
  syncSource: (id: string) => request<SyncReport>("POST", `/sources/${id}/sync`),
  setToken: (id: string, token: string) => request<{ stored_in: string }>("PUT", `/sources/${id}/token`, { token }),
  removeSource: (id: string) => request<{ removed: string }>("DELETE", `/sources/${id}`),
};
