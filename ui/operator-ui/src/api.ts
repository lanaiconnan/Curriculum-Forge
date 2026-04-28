/**
 * API client for Curriculum-Forge Gateway
 */

const API_BASE = '';

export interface Job {
  id: string;
  profile: string;
  description: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'waiting' | 'cancelled';
  current_phase: string;
  phases: Record<string, PhaseInfo>;
  created_at: string;
  updated_at: string;
  finished_at: string | null;
  metrics: Record<string, unknown>;
  config?: Record<string, unknown>;
  state_data?: Record<string, unknown>;
}

export interface PhaseInfo {
  status: string;
  output: unknown;
}

export interface Profile {
  name: string;
  file: string;
  description: string;
}

export interface Plugin {
  name: string;
  enabled: boolean;
  description: string;
  hooks: string[];
  config: Record<string, unknown>;
}

export interface CreateJobRequest {
  profile: string;
  description?: string;
  config?: Record<string, unknown>;
}

export async function listJobs(params?: {
  profile?: string;
  state?: string;
  limit?: number;
}): Promise<Job[]> {
  const search = new URLSearchParams();
  if (params?.profile) search.set('profile', params.profile);
  if (params?.state) search.set('state', params.state);
  if (params?.limit) search.set('limit', String(params.limit));
  const qs = search.toString() ? `?${search}` : '';
  const res = await fetch(`${API_BASE}/jobs${qs}`);
  if (!res.ok) throw new Error(`Failed to list jobs: ${res.statusText}`);
  const data = await res.json();
  return data.jobs;
}

export async function getJob(id: string): Promise<Job> {
  const res = await fetch(`${API_BASE}/jobs/${id}`);
  if (!res.ok) throw new Error(`Failed to get job ${id}: ${res.statusText}`);
  return res.json();
}

export async function createJob(req: CreateJobRequest): Promise<Job> {
  const res = await fetch(`${API_BASE}/jobs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || 'Failed to create job');
  }
  const data = await res.json();
  return data.job;
}

export interface JobMetrics {
  job_id: string;
  phase: string;
  state: string;
  duration_ms: number | null;
  started_at: string;
  finished_at: string | null;
  providers_run: number;
  providers_succeeded: number;
  retry_count: number;
  max_retries: number;
  error: string | null;
  phase_durations: Record<string, number>;
  tokens_used: number | null;
  tokens_prompt: number | null;
  tokens_completion: number | null;
}

export async function getJobMetrics(id: string): Promise<JobMetrics> {
  const res = await fetch(`${API_BASE}/jobs/${id}/metrics`);
  if (!res.ok) throw new Error(`Failed to get metrics for job ${id}: ${res.statusText}`);
  return res.json();
}

export async function resumeJob(id: string): Promise<Job> {
  const res = await fetch(`${API_BASE}/jobs/${id}/resume`, { method: 'POST' });
  if (!res.ok) throw new Error(`Failed to resume job: ${res.statusText}`);
  const data = await res.json();
  return data.job;
}

export async function abortJob(id: string): Promise<Job> {
  const res = await fetch(`${API_BASE}/jobs/${id}/abort`, { method: 'POST' });
  if (!res.ok) throw new Error(`Failed to abort job: ${res.statusText}`);
  const data = await res.json();
  return data.job;
}

export async function listProfiles(): Promise<Profile[]> {
  const res = await fetch(`${API_BASE}/profiles`);
  if (!res.ok) throw new Error(`Failed to list profiles: ${res.statusText}`);
  const data = await res.json();
  return data.profiles;
}

export async function healthCheck(): Promise<{ status: string; version: string }> {
  const res = await fetch(`${API_BASE}/health`);
  if (!res.ok) throw new Error('Gateway unhealthy');
  return res.json();
}

export async function getStats(): Promise<Record<string, unknown>> {
  const res = await fetch(`${API_BASE}/stats`);
  if (!res.ok) throw new Error('Failed to get stats');
  return res.json();
}

export interface StatsBucket {
  timestamp: string;
  total: number;
  completed: number;
  failed: number;
  avg_duration_ms: number;
  retries: number;
}

export async function getStatsTimeseries(hours = 24): Promise<StatsBucket[]> {
  const res = await fetch(`${API_BASE}/stats/timeseries?hours=${hours}`);
  if (!res.ok) throw new Error('Failed to get stats timeseries');
  const data = await res.json();
  return data.buckets || [];
}

// ── Plugins ──────────────────────────────────────────────────────────────────

export async function listPlugins(): Promise<Plugin[]> {
  const res = await fetch(`${API_BASE}/plugins`);
  if (!res.ok) throw new Error(`Failed to list plugins: ${res.statusText}`);
  const data = await res.json();
  return data.plugins || [];
}

export async function enablePlugin(name: string): Promise<void> {
  const res = await fetch(`${API_BASE}/plugins/${encodeURIComponent(name)}/enable`, { method: 'POST' });
  if (!res.ok) throw new Error(`Failed to enable plugin: ${res.statusText}`);
}

export async function disablePlugin(name: string): Promise<void> {
  const res = await fetch(`${API_BASE}/plugins/${encodeURIComponent(name)}/disable`, { method: 'POST' });
  if (!res.ok) throw new Error(`Failed to disable plugin: ${res.statusText}`);
}

export async function updatePluginConfig(name: string, config: Record<string, unknown>): Promise<void> {
  const res = await fetch(`${API_BASE}/plugins/${encodeURIComponent(name)}/config`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ config }),
  });
  if (!res.ok) throw new Error(`Failed to update plugin config: ${res.statusText}`);
}

// ── Audit ─────────────────────────────────────────────────────────────────────

export interface AuditEntry {
  id: string;
  timestamp: string;
  category: string;
  event: string;
  actor: string;
  target: string;
  metadata: Record<string, unknown>;
}

export async function getAuditLogs(params?: Record<string, string>): Promise<AuditEntry[]> {
  const qs = params ? '?' + new URLSearchParams(params).toString() : '';
  const res = await fetch(`${API_BASE}/audit${qs}`);
  if (!res.ok) throw new Error(`Failed to get audit logs: ${res.statusText}`);
  const data = await res.json();
  return data.entries || [];
}

export async function getAuditStats(): Promise<Record<string, unknown>> {
  const today = new Date().toISOString().split('T')[0];
  const res = await fetch(`${API_BASE}/audit/stats?date=${today}`);
  if (!res.ok) return {};
  return res.json();
}

// ── SSE Utilities ─────────────────────────────────────────────────────────────

const MAX_RETRIES = 5;

/**
 * Open an SSE connection with automatic exponential-backoff reconnection.
 * Returns a cleanup function. onError is called after MAX_RETRIES exhausted.
 */
export function openSSE(
  url: string,
  handlers: {
    onMessage: (data: Record<string, unknown>) => void;
    onError?: (err: Event) => void;
    onConnect?: () => void;
    onDisconnect?: () => void;
  },
): () => void {
  const { onMessage, onError, onConnect, onDisconnect } = handlers;

  let es: EventSource;
  let retries = 0;
  let destroyed = false;
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

  const connect = () => {
    if (destroyed) return;
    es = new EventSource(url);

    es.onopen = () => {
      retries = 0;
      onConnect?.();
    };

    es.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data) as Record<string, unknown>;
        if (data == null) return; // skip keepalive comment lines
        onMessage(data);
      } catch { /* ignore */ }
    };

    es.onerror = (err) => {
      if (destroyed) return;
      es.close();
      if (retries < MAX_RETRIES) {
        const delay = Math.min(500 * Math.pow(2, retries), 15000);
        retries++;
        reconnectTimer = setTimeout(connect, delay);
      } else {
        onError?.(err);
        onDisconnect?.();
      }
    };
  };

  connect();

  return () => {
    destroyed = true;
    if (reconnectTimer != null) clearTimeout(reconnectTimer);
    es?.close();
    onDisconnect?.();
  };
}

/** Legacy compat — delegates to openSSE */
export function subscribeJob(id: string, onEvent: (data: Record<string, unknown>) => void): () => void {
  return openSSE(`${API_BASE}/jobs/${id}/stream`, { onMessage: onEvent });
}

/** Subscribe to global coordinator events (all job/workflow status changes) */
export function subscribeCoordinatorEvents(
  onEvent: (data: Record<string, unknown>) => void,
  handlers?: { onError?: (err: Event) => void; onDisconnect?: () => void },
): () => void {
  return openSSE(`${API_BASE}/coordinator/events`, {
    onMessage: onEvent,
    onError: handlers?.onError,
    onDisconnect: handlers?.onDisconnect,
  });
}

// ── Job Comparison ──────────────────────────────────────────────────────────

export interface ComparedJob {
  job_id: string;
  profile: string;
  phase: string;
  state: string;
  duration_ms: number | null;
  started_at: string;
  finished_at: string | null;
  providers_run: number;
  providers_succeeded: number;
  retry_count: number;
  max_retries: number;
  phase_durations: Record<string, number>;
  tokens_used: number | null;
  tokens_prompt: number | null;
  tokens_completion: number | null;
  error: string | null;
}

export interface CompareResult {
  jobs: ComparedJob[];
  summary: {
    count: number;
    avg_duration_ms: number | null;
    min_duration_ms: number | null;
    max_duration_ms: number | null;
    total_providers_run: number;
    total_providers_succeeded: number;
    total_retries: number;
  };
}

export async function compareJobs(ids: string[]): Promise<CompareResult> {
  const res = await fetch(`${API_BASE}/jobs/compare?ids=${ids.join(',')}`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || 'Failed to compare jobs');
  }
  return res.json();
}

// ── Knowledge / Memory ──────────────────────────────────────────────────────────

export interface MemoryPage {
  title: string;
  content: string;
  tags: string[];
  created_at: string;
  updated_at: string;
  links: string[];
}

export interface MemoryStats {
  total_pages: number;
  total_links: number;
  total_tags: number;
  recent_pages: string[];
}

export interface SearchResult {
  title: string;
  score: number;
  snippet: string;
}

export interface GraphData {
  nodes: { id: string; label: string }[];
  edges: { source: string; target: string }[];
}

export async function listMemoryPages(): Promise<string[]> {
  const res = await fetch(`${API_BASE}/memory/pages`);
  if (!res.ok) throw new Error('Failed to list memory pages');
  const data = await res.json();
  return data.titles || data.pages || [];
}

export async function getMemoryPage(title: string): Promise<MemoryPage> {
  const res = await fetch(`${API_BASE}/memory/pages/${encodeURIComponent(title)}`);
  if (!res.ok) throw new Error(`Failed to get page: ${title}`);
  return res.json();
}

export async function createMemoryPage(params: {
  title: string;
  content: string;
  tags?: string[];
}): Promise<MemoryPage> {
  const res = await fetch(`${API_BASE}/memory/pages`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  });
  if (!res.ok) throw new Error('Failed to create memory page');
  return res.json();
}

export async function searchMemory(query: string): Promise<SearchResult[]> {
  const res = await fetch(`${API_BASE}/memory/search?q=${encodeURIComponent(query)}`);
  if (!res.ok) throw new Error('Failed to search memory');
  const data = await res.json();
  return data.results || [];
}

export async function storeExperience(params: {
  task_id: string;
  task_type?: string;
  description?: string;
  approach?: string;
  outcome?: string;
  reflection?: string;
  tags?: string[];
}): Promise<{ title: string; filepath: string }> {
  const res = await fetch(`${API_BASE}/memory/store`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  });
  if (!res.ok) throw new Error('Failed to store experience');
  return res.json();
}

export async function retrieveExperiences(params: {
  keywords?: string;
  task_type?: string;
  limit?: number;
}): Promise<MemoryPage[]> {
  const res = await fetch(`${API_BASE}/memory/retrieve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  });
  if (!res.ok) throw new Error('Failed to retrieve experiences');
  const data = await res.json();
  return data.experiences || [];
}

export async function getMemoryStats(): Promise<MemoryStats> {
  const res = await fetch(`${API_BASE}/memory/stats`);
  if (!res.ok) throw new Error('Failed to get memory stats');
  return res.json();
}

export async function getMemoryGraph(): Promise<GraphData> {
  const res = await fetch(`${API_BASE}/memory/graph`);
  if (!res.ok) throw new Error('Failed to get memory graph');
  return res.json();
}

export async function deleteMemoryPage(title: string): Promise<void> {
  const res = await fetch(`${API_BASE}/memory/pages/${encodeURIComponent(title)}`, {
    method: 'DELETE',
  });
  if (!res.ok) throw new Error(`Failed to delete page: ${title}`);
}

// ── Governance ────────────────────────────────────────────────────────────────

export interface AgentInfo {
  id: string;
  name: string;
  capabilities: string[];
  status: 'active' | 'inactive';
  registered_at: string;
}

export interface RuleInfo {
  id: string;
  name: string;
  description: string;
  enabled: boolean;
  priority: number;
}

export interface ProposalInfo {
  id: string;
  title: string;
  status: 'open' | 'passed' | 'rejected' | 'closed';
  votes_for: number;
  votes_against: number;
  created_at: string;
}

export interface RequestInfo {
  id: string;
  user_id: string;
  type: string;
  status: 'pending' | 'assigned' | 'completed' | 'failed';
  created_at: string;
}

export interface GovernanceStats {
  agents: { total: number; active: number };
  rules: { total: number; enabled: number };
  proposals: { total: number; open: number };
  requests: { total: number; pending: number };
  reputation: { avg: number; min: number; max: number };
}

export async function getGovernanceStats(): Promise<GovernanceStats> {
  const res = await fetch(`${API_BASE}/governance/stats`);
  if (!res.ok) throw new Error('Failed to get governance stats');
  return res.json();
}

export async function listAgents(): Promise<AgentInfo[]> {
  const res = await fetch(`${API_BASE}/governance/agents`);
  if (!res.ok) throw new Error('Failed to list agents');
  const data = await res.json();
  return data.agents || [];
}

export async function registerAgent(params: {
  name: string;
  capabilities?: string[];
}): Promise<AgentInfo> {
  const res = await fetch(`${API_BASE}/governance/agents`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  });
  if (!res.ok) throw new Error('Failed to register agent');
  return res.json();
}

export async function listRules(): Promise<RuleInfo[]> {
  const res = await fetch(`${API_BASE}/governance/rules`);
  if (!res.ok) throw new Error('Failed to list rules');
  const data = await res.json();
  return data.rules || [];
}

export async function listProposals(): Promise<ProposalInfo[]> {
  const res = await fetch(`${API_BASE}/governance/proposals`);
  if (!res.ok) throw new Error('Failed to list proposals');
  const data = await res.json();
  return data.proposals || [];
}

export async function listRequests(): Promise<RequestInfo[]> {
  const res = await fetch(`${API_BASE}/governance/requests`);
  if (!res.ok) throw new Error('Failed to list requests');
  const data = await res.json();
  return data.requests || [];
}

// ── Tenants ──────────────────────────────────────────────────────────────────

export interface Tenant {
  id: string;
  name: string;
  status: 'active' | 'suspended';
  plan: string;
  created_at: string;
  quota: Record<string, unknown>;
}

export interface TenantUsage {
  jobs_count: number;
  storage_mb: number;
  api_calls: number;
  period: string;
}

export interface TenantStats {
  total_tenants: number;
  active_tenants: number;
  suspended_tenants: number;
}

export async function listTenants(): Promise<Tenant[]> {
  const res = await fetch(`${API_BASE}/tenants`);
  if (!res.ok) throw new Error('Failed to list tenants');
  const data = await res.json();
  return data.tenants || [];
}

export async function createTenant(params: {
  name: string;
  plan?: string;
  quota?: Record<string, unknown>;
}): Promise<Tenant> {
  const res = await fetch(`${API_BASE}/tenants`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  });
  if (!res.ok) throw new Error('Failed to create tenant');
  return res.json();
}

export async function getTenant(id: string): Promise<Tenant> {
  const res = await fetch(`${API_BASE}/tenants/${encodeURIComponent(id)}`);
  if (!res.ok) throw new Error('Failed to get tenant');
  return res.json();
}

export async function updateTenant(id: string, params: Partial<Tenant>): Promise<Tenant> {
  const res = await fetch(`${API_BASE}/tenants/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  });
  if (!res.ok) throw new Error('Failed to update tenant');
  return res.json();
}

export async function deleteTenant(id: string): Promise<void> {
  const res = await fetch(`${API_BASE}/tenants/${encodeURIComponent(id)}`, {
    method: 'DELETE',
  });
  if (!res.ok) throw new Error('Failed to delete tenant');
}

export async function suspendTenant(id: string): Promise<void> {
  const res = await fetch(`${API_BASE}/tenants/${encodeURIComponent(id)}/suspend`, {
    method: 'POST',
  });
  if (!res.ok) throw new Error('Failed to suspend tenant');
}

export async function activateTenant(id: string): Promise<void> {
  const res = await fetch(`${API_BASE}/tenants/${encodeURIComponent(id)}/activate`, {
    method: 'POST',
  });
  if (!res.ok) throw new Error('Failed to activate tenant');
}

export async function getTenantUsage(id: string): Promise<TenantUsage> {
  const res = await fetch(`${API_BASE}/tenants/${encodeURIComponent(id)}/usage`);
  if (!res.ok) throw new Error('Failed to get tenant usage');
  return res.json();
}

export async function getTenantStats(): Promise<TenantStats> {
  const res = await fetch(`${API_BASE}/tenants/stats`);
  if (!res.ok) throw new Error('Failed to get tenant stats');
  return res.json();
}

// ── Auth / Users ────────────────────────────────────────────────────────────

export interface User {
  id: string;
  username: string;
  role: string;
  active: boolean;
  created_at: string;
  last_login: string | null;
}

export interface APIKey {
  id: string;
  name: string;
  client_id: string;
  scopes: string[];
  created_at: string;
  last_used: string | null;
}

export interface Role {
  name: string;
  permissions: string[];
  description: string;
}

export async function login(username: string, password: string): Promise<{ access_token: string; refresh_token: string; token_type: string }> {
  const res = await fetch(`${API_BASE}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) throw new Error('Invalid credentials');
  return res.json();
}

export async function logout(): Promise<void> {
  await fetch(`${API_BASE}/auth/logout`, { method: 'POST' });
}

export async function listUsers(): Promise<User[]> {
  const res = await fetch(`${API_BASE}/users`);
  if (!res.ok) throw new Error('Failed to list users');
  const data = await res.json();
  return data.users || [];
}

export async function createUser(params: {
  username: string;
  password: string;
  role?: string;
}): Promise<User> {
  const res = await fetch(`${API_BASE}/users`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || 'Failed to create user');
  }
  return res.json();
}

export async function deleteUser(id: string): Promise<void> {
  const res = await fetch(`${API_BASE}/users/${encodeURIComponent(id)}`, {
    method: 'DELETE',
  });
  if (!res.ok) throw new Error('Failed to delete user');
}

export async function listAPIKeys(): Promise<APIKey[]> {
  const res = await fetch(`${API_BASE}/auth/keys`);
  if (!res.ok) throw new Error('Failed to list API keys');
  const data = await res.json();
  return data.keys || [];
}

export async function createAPIKey(params: {
  name: string;
  scopes?: string[];
}): Promise<APIKey & { key: string }> {
  const res = await fetch(`${API_BASE}/auth/keys`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  });
  if (!res.ok) throw new Error('Failed to create API key');
  return res.json();
}

export async function deleteAPIKey(id: string): Promise<void> {
  const res = await fetch(`${API_BASE}/auth/keys/${encodeURIComponent(id)}`, {
    method: 'DELETE',
  });
  if (!res.ok) throw new Error('Failed to delete API key');
}

export async function listRoles(): Promise<Role[]> {
  const res = await fetch(`${API_BASE}/roles`);
  if (!res.ok) throw new Error('Failed to list roles');
  const data = await res.json();
  return data.roles || [];
}

export async function listPermissions(): Promise<string[]> {
  const res = await fetch(`${API_BASE}/permissions`);
  if (!res.ok) throw new Error('Failed to list permissions');
  const data = await res.json();
  return data.permissions || [];
}
