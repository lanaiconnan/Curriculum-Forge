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
