// Typed client for the Area O1 API. Shapes mirror areao1/core/models.py.
import { WRITE_HEADER } from "./names";

export type CriterionStatus = "banked" | "building" | "gap" | "dropped";

export interface CriterionScore {
  id: string;
  label: string;
  short_label?: string;
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
  /** Self-reported to-dos (kind "todo") can be ticked off; they never count toward a criterion. */
  id?: string;
  criterion?: string | null;
  criterion_label?: string;
  self_reported?: boolean;
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

export type RuleStatus = "verified" | "unverified" | "stale" | "conflict";

export interface RuleCitation {
  chunk_id: string;
  source_id: string;
  title: string;
  tier: number;
  url: string;
  quote: string;
  sha256: string;
  checked_at: string;
  verdict: "entails" | "contradicts";
  fresh: boolean;
}

export interface RuleClaim {
  id: string;
  text: string;
  sentence: string;
  kind: string;
  status: RuleStatus;
  reason: string;
  citations: RuleCitation[];
}

export interface RuleCheck {
  checked_at: string;
  model: string | null;
  claims: RuleClaim[];
  note: string | null;
}

export interface Candidate {
  rule_check?: RuleCheck | null;
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
  kind: "evidence" | "pipeline" | "deadline" | "letter" | "update" | "metric" | "context";
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
  short_label?: string;
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
  unreadable: string | null;
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
  rule_check: RuleCheck | null;
}

export interface VaultSourceStatus {
  id: string;
  title: string;
  tier: 1 | 2 | 3;
  kind: string;
  topics: string[];
  url: string;
  enabled: boolean;
  notes: string;
  ttl: number | "monthly";
  status: string;
  error: string | null;
  checked_at: string | null;
  expires_at: string | null;
  fresh: boolean;
  effective_date: string | null;
  snapshots: number;
  last_changed: string | null;
  finding: boolean;
  manual: boolean;
  secondary_to: string | null;
  link: string;
}

export interface VaultFetch {
  id: string;
  source_id: string;
  title: string;
  url: string;
  tier: number;
  fetched_at: string;
  status: "new" | "changed" | "unchanged" | "unreadable" | "error";
  origin: "fetch" | "manual" | "agent";
  error: string | null;
  diff: { added: number; removed: number; sample: string[] } | null;
}

export interface KnowledgeView {
  enabled: boolean;
  sources: VaultSourceStatus[];
  recent: VaultFetch[];
  conflicts: { claim: RuleClaim; where: { type: "run" | "briefing" | "candidate"; id: string | null; label: string }; at: string }[];
  tier1_domains: string[];
  tier2_domains: string[];
  kinds: string[];
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
  coverage: { id: string; label: string; short_label?: string; independent: number; employer: number; coauthor: number }[];
  criteria: { id: string; label: string; short_label?: string }[];
}

export interface AgentStatus {
  engine: string;
  available: boolean;
  reason: string;
  model: string;
  models: { chat: string; task: string; mission: string };
  cheap_mode: boolean;
  routes: { task: string; tier: "hard" | "mid" | "mundane"; provider: "openai"; model: string }[];
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
  rule_check?: RuleCheck | null;
  id: string;
  kind: "chat" | "manual" | "scheduled";
  mission: string | null;
  status: "running" | "done" | "error" | "stopped";
  engine: string;
  model: string;
  task?: string | null;
  tier?: "hard" | "mid" | "mundane" | null;
  provider?: "anthropic" | "openai" | null;
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
  searches?: number;
  search_cost_usd?: number;
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
  summary?: string;
  summarized?: number;
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


export interface Refusal {
  at: string;
  run_id: string | null;
  rule: string;
  message: string;
  alternative: string;
  detail: string;
}

// ---------------------------------------------------------------- onboarding (ADR 0008)

export type FieldStatus = "pending" | "confirmed" | "fixed" | "skipped";
export interface ChatMatch {
  id: string;
  kind: "conversation" | "project";
  provider: string;
  title: string;
  date: string | null;
  messages: number;
  score: number;
  reasons: string[];
  ticked: boolean;
}
export interface ChatScan {
  id: string;
  summary: string;
  formats: string[];
  unread: { file: string; why: string }[];
  skipped: number;
  items: ChatMatch[];
}

export interface OnboardingQuestion {
  id: string;
  text: string;
  keys: string[];
  kind: "confirm" | "choice" | "month";
  values: Record<string, string | string[]>;
  options: { value: string; label: string }[];
  quote: string;
}
export interface OnboardingLookup {
  id: string;
  kind: "papers" | "github" | "orcid" | "website" | "find";
  prompt: string;
  targets: string[];
  status: "offered" | "declined" | "searching" | "found" | "nothing_found" | "unreachable" | "blocked" | "failed" | "accepted" | "done";
  result: string;
  resolved?: Record<string, string>;
}
export type Relationship = "recommender" | "collaborator" | "organizer" | "editor" | "mentor" | "employer" | "other";
export interface GmailThreadView {
  id: string;
  subject: string;
  contact_ids: string[];
  last_at: string;
  last_from: "you" | "them";
  snippet: string;
  messages: number;
}
export interface ContactView {
  id: string;
  name: string;
  emails: string[];
  org: string;
  relationship: Relationship;
  notes: string;
  asks: string[];
  next_follow_up: string | null;
  last_touch: string | null;
  letter_ids: string[];
  pipeline_ids: string[];
  virtual: boolean;
  letters: { id: string; name: string; status: string }[];
  pipeline: { id: string; title: string; stage: string }[];
  threads: GmailThreadView[];
}
export type ContactFields = Partial<Pick<ContactView, "name" | "emails" | "org" | "relationship" | "notes" | "asks" | "next_follow_up" | "last_touch" | "letter_ids" | "pipeline_ids">>;
export interface OutreachDraftView {
  id: string;
  contact_id: string;
  contact: string;
  to: string;
  subject: string;
  body: string;
  purpose: string;
  status: "draft" | "queued" | "sent" | "rejected";
  drafted_by: string;
  thread_id: string | null;
  created_at: string;
  queued_at: string | null;
  sent_at: string | null;
}
export interface SendFailure {
  at: string;
  draft_id: string;
  to: string;
  subject: string;
  error: string;
  contact: string;
}
export interface OutreachView {
  drafts: OutreachDraftView[];
  sent_today: number;
  daily_limit: number;
  can_send: boolean;
  undo_seconds: number;
  failures: SendFailure[];
}
export type MailCategory = "invites" | "judging" | "reviewer" | "letters" | "press" | "awards" | "contacts";
export interface MailItemView {
  id: string;
  thread_id: string;
  at: string;
  from_name: string;
  from_addr: string;
  to: string[];
  subject: string;
  outgoing: boolean;
  category: MailCategory;
  by: "rule" | "learned" | "model" | "you";
  why: string;
  contact_ids: string[];
  contacts: string[];
  candidate: { id: string; title: string } | null;
  source: "gmail" | "eml";
  auth: { verdict: "verified" | "failed" | "unverified"; spf: string | null; dkim: string | null; dmarc: string | null; dkim_domain: string | null; by: string | null } | null;
  forwarded_part: string | null;
}
export interface MailView {
  connected: boolean;
  categories: { id: MailCategory; label: string; count: number }[];
  items: MailItemView[];
  rules: { sender: string; category: MailCategory | "hide"; at: string }[];
  unsorted: number;
  model_sorting: boolean;
  synced_at: string | null;
  lines?: string[];
}
export interface MailText {
  from: string;
  to: string;
  cc: string;
  subject: string;
  date: string;
  text: string;
}
export interface GmailStatus {
  connected: boolean;
  email: string | null;
}
export interface AiStatus {
  key: "keychain" | "environment" | null;
  ready: boolean;
  how: string;
  cost: string;
}
export interface OnboardingView {
  needed: boolean;
  state: {
    status: "new" | "in_progress" | "done" | "skipped";
    step: "linkedin" | "questions" | "ai" | "lookups" | "chats" | "mail" | "tour" | "done";
    source: { filename: string; chars: number; redactions: number; parser: string } | null;
    lookups: OnboardingLookup[];
    transcript: { who: "areao1" | "you"; text: string }[];
    target_profile: string | null;
    tour: string;
    chats: string;
    mail?: "pending" | "connected" | "skipped";
    ai: "pending" | "login" | "key" | "skipped";
  };
  question: OnboardingQuestion | null;
  nav: { back: { step: string; question?: string | null } | null; reached: string; steps: { id: string; reachable: boolean }[] };
  panel: { key: string; label: string; value: string | string[]; status: FieldStatus; quote?: string }[];
  person: { name: string; field: string; location: string };
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const init: RequestInit = { method, headers: {} };
  const headers = init.headers as Record<string, string>;
  if (method !== "GET") headers[WRITE_HEADER] = "1"; // the server rejects writes without it
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
  refusals: () => request<Refusal[]>("GET", "/agent/refusals"),
  onboarding: () => request<OnboardingView>("GET", "/onboarding"),
  onboardingLinkedin: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<OnboardingView>("POST", "/onboarding/linkedin", form);
  },
  onboardingAnswer: (id: string, action: "yes" | "fix" | "skip", value?: unknown) =>
    request<OnboardingView>("POST", "/onboarding/answer", { id, action, value }),
  onboardingStep: (step: string) => request<OnboardingView>("POST", "/onboarding/step", { step }),
  onboardingLookup: (id: string, accept: boolean) => request<OnboardingView>("POST", `/onboarding/lookups/${id}`, { accept }),
  onboardingGoto: (step: string, question?: string | null) => request<OnboardingView>("POST", "/onboarding/goto", { step, question }),
  onboardingRestart: () => request<OnboardingView>("POST", "/onboarding/restart"),
  onboardingAi: (choice: "key" | "skip") => request<OnboardingView>("POST", "/onboarding/ai", { choice }),
  aiStatus: () => request<AiStatus>("GET", "/ai"),
  contacts: () => request<ContactView[]>("GET", "/contacts"),
  addContact: (fields: ContactFields) => request<ContactView>("POST", "/contacts", fields),
  updateContact: (id: string, fields: ContactFields) => request<ContactView>("PATCH", `/contacts/${enc(id)}`, fields),
  deleteContact: (id: string) => request<unknown>("DELETE", `/contacts/${enc(id)}`),
  outreach: () => request<OutreachView>("GET", "/outreach"),
  draftEmail: (contact_id: string, subject: string, body: string) => request<OutreachDraftView>("POST", "/outreach", { contact_id, subject, body }),
  editDraft: (id: string, fields: { subject?: string; body?: string }) => request<OutreachDraftView>("PATCH", `/outreach/${enc(id)}`, fields),
  undoSend: (id: string) => request<OutreachDraftView>("POST", `/outreach/${enc(id)}/undo`),
  rejectDraft: (id: string) => request<OutreachDraftView>("POST", `/outreach/${enc(id)}/reject`),
  sendDraft: (id: string) => request<OutreachDraftView>("POST", `/outreach/${enc(id)}/send`),
  syncGmail: () => request<{ lines: string[] }>("POST", "/gmail/sync"),
  mail: () => request<MailView>("GET", "/mail"),
  syncMail: () => request<MailView>("POST", "/mail/sync"),
  moveMail: (id: string, category: MailCategory | "hide") => request<MailView>("PUT", `/mail/${enc(id)}`, { category }),
  setMailSorting: (on: boolean) => request<{ model_sorting: boolean }>("PUT", "/settings/mail", { model_sorting: on }),
  importForwarded: (id: string) => request<Candidate>("POST", `/mail/${enc(id)}/import`),
  mailText: (id: string) => request<MailText>("GET", `/mail/${enc(id)}/text`),
  gmailStatus: () => request<GmailStatus>("GET", "/gmail"),
  connectGmail: (email: string, password: string) => request<GmailStatus>("PUT", "/gmail", { email, password }),
  disconnectGmail: () => request<GmailStatus>("DELETE", "/gmail"),
  setCheapMode: (on: boolean) => request<AgentStatus>("PUT", "/settings/agent", { cheap_mode: on }),
  saveAiKey: (key: string) => request<AiStatus>("PUT", "/ai/key", { key }),
  forgetAiKey: () => request<AiStatus>("DELETE", "/ai/key"),
  scanChats: (files: File[], paths: (f: File) => string) => {
    const form = new FormData();
    for (const f of files) form.append("files", f, paths(f));
    return request<ChatScan>("POST", "/imports/chats/scan", form);
  },
  importScan: (id: string, ids: string[]) =>
    request<{ picked: number; candidates_added: Record<string, number>; extracted_by: string; cost_usd: number; summary: string }>(
      "POST",
      `/imports/chats/${enc(id)}/import`,
      { ids },
    ),
  discardScan: (id: string) => request<unknown>("DELETE", `/imports/chats/${enc(id)}`),
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
  updateTodo: (id: string, status: "open" | "done" | "dismissed") => request<unknown>("PATCH", `/todos/${enc(id)}`, { status }),
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
  knowledge: () => request<KnowledgeView>("GET", "/knowledge"),
  knowledgeSync: (sources?: string[], force = false) => request<VaultFetch[]>("POST", "/knowledge/sync", { sources, force }),
  knowledgeImport: (sourceId: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<VaultFetch>("POST", `/knowledge/import/${enc(sourceId)}`, form);
  },
  promoteFinding: (sourceId: string, kind: string) => request<unknown>("POST", `/knowledge/findings/${enc(sourceId)}/promote`, { kind }),
  recheckRun: (id: string) => request<RuleCheck>("POST", `/rulecheck/runs/${enc(id)}`),
  recheckBriefing: () => request<RuleCheck>("POST", "/rulecheck/briefing"),
  recheckCandidate: (id: string) => request<RuleCheck>("POST", `/rulecheck/inbox/${enc(id)}`),
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
