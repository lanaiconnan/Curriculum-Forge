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

// SSE subscription
export function subscribeJob(id: string, onEvent: (data: Record<string, unknown>) => void) {
  const es = new EventSource(`${API_BASE}/jobs/${id}/stream`);
  es.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data);
      onEvent(data);
    } catch { /* ignore parse errors */ }
  };
  es.onerror = () => {
    // Reconnect handled by browser
  };
  return () => es.close();
}
