import { useState, useEffect, useCallback, useRef } from 'react';
import {
  listJobs, getJob, getJobMetrics, createJob, resumeJob, abortJob,
  listProfiles, healthCheck, subscribeJob, subscribeCoordinatorEvents,
  listPlugins, enablePlugin, disablePlugin, updatePluginConfig,
  getAuditLogs, getAuditStats, getStats, getStatsTimeseries,
  compareJobs,
  listMemoryPages, getMemoryPage, createMemoryPage, searchMemory,
  getMemoryStats, getMemoryGraph, deleteMemoryPage,
  listAgents, listRules, listProposals, listRequests, getGovernanceStats,
  listTenants, createTenant, suspendTenant, activateTenant, deleteTenant, getTenantUsage, getTenantStats,
  listUsers, createUser, deleteUser, listAPIKeys, createAPIKey, deleteAPIKey, listRoles,
  type Job, type Profile, type StatsBucket, type CompareResult,
  type MemoryPage, type MemoryStats, type SearchResult, type GraphData,
} from './api';

// ── Types ─────────────────────────────────────────────────────────────────────

type Tab = 'jobs' | 'knowledge' | 'governance' | 'tenants' | 'auth' | 'plugins' | 'audit' | 'config' | 'compare';

interface Plugin {
  name: string;
  enabled: boolean;
  description: string;
  hooks: string[];
  config: Record<string, unknown>;
}

interface AuditEntry {
  id: string;
  timestamp: string;
  category: string;
  event: string;
  actor: string;
  target: string;
  metadata: Record<string, unknown>;
}

interface LogLine {
  ts: string;
  level: 'info' | 'warn' | 'error' | 'phase';
  text: string;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function timeAgo(ts: string): string {
  const diff = Date.now() - new Date(ts).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1) return 'just now';
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

function PhaseStatusBadge({ phase }: { phase: string }) {
  const s = phase.toLowerCase();
  const cls = s === 'running'
    ? 'badge-running'
    : s === 'completed'
    ? 'badge-completed'
    : s === 'failed'
    ? 'badge-failed'
    : s === 'waiting'
    ? 'badge-waiting'
    : 'badge-pending';
  return <span className={`badge ${cls}`}>{phase}</span>;
}

function LoadingSpinner({ msg = 'Loading…' }: { msg?: string }) {
  return (
    <div className="flex items-center justify-center py-12 text-gray-400 text-sm">
      <span className="animate-spin mr-2">⟳</span> {msg}
    </div>
  );
}

// ── Create Job Modal ──────────────────────────────────────────────────────────

function CreateJobModal({
  profiles,
  onClose,
  onCreated,
}: {
  profiles: Profile[];
  onClose: () => void;
  onCreated: (job: Job) => void;
}) {
  const [profile, setProfile] = useState(profiles[0]?.name || '');
  const [description, setDescription] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!profile) { setError('Please select a profile'); return; }
    setLoading(true); setError('');
    try {
      const job = await createJob({ profile, description });
      onCreated(job); onClose();
    } catch (err) { setError(String(err)); }
    finally { setLoading(false); }
  };

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
      <div className="card p-6 w-full max-w-md">
        <h2 className="text-xl font-semibold mb-4">Create New Job</h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm text-gray-400 mb-1">Profile</label>
            <select
              value={profile}
              onChange={e => setProfile(e.target.value)}
              className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 focus:border-indigo-500 outline-none"
            >
              {profiles.map(p => <option key={p.name} value={p.name}>{p.name}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-sm text-gray-400 mb-1">Description (optional)</label>
            <input
              value={description}
              onChange={e => setDescription(e.target.value)}
              placeholder="What does this job do?"
              className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 focus:border-indigo-500 outline-none"
            />
          </div>
          {error && <p className="text-red-400 text-sm">{error}</p>}
          <div className="flex gap-3 pt-2">
            <button type="submit" disabled={loading} className="btn-primary flex-1">
              {loading ? 'Creating…' : 'Create Job'}
            </button>
            <button type="button" onClick={onClose} className="btn-secondary">Cancel</button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ── Live Log Panel ─────────────────────────────────────────────────────────────

function LogPanel({ jobId, maxLines = 200 }: { jobId: string; maxLines?: number }) {
  const [lines, setLines] = useState<LogLine[]>([]);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setLines([]);
    const unsub = subscribeJob(jobId, (event) => {
      const ts = new Date().toLocaleTimeString();
      const level = (event.level as string)?.toLowerCase() || 'info';
      const text = String(event.text || event.message || '');

      if (event.event === 'phase_start') {
        setLines(prev => [...prev.slice(-(maxLines - 1)), { ts, level: 'phase', text: `▶ Phase: ${event.phase}` }]);
      } else if (event.event === 'phase_done') {
        setLines(prev => [...prev.slice(-(maxLines - 1)), {
          ts, level: event.ok ? 'info' : 'error',
          text: `✓ Phase "${event.phase}" ${event.ok ? 'completed' : 'failed'}`
        }]);
      } else if (event.event === 'start') {
        setLines(prev => [...prev.slice(-(maxLines - 1)), { ts, level: 'phase', text: `🚀 Job started (run_id: ${event.run_id})` }]);
      } else if (event.event === 'done' || event.event === 'error') {
        setLines(prev => [...prev.slice(-(maxLines - 1)), { ts, level: 'phase', text: `■ Job ${event.event}` }]);
      } else if (event.type === 'job_created') {
        setLines(prev => [...prev.slice(-(maxLines - 1)), { ts, level: 'phase', text: `▶ Job created: ${event.profile || event.job_id}` }]);
      } else if (event.type === 'job_completed') {
        setLines(prev => [...prev.slice(-(maxLines - 1)), { ts, level: 'info', text: `✅ Job completed (status: ${event.status})` }]);
      } else if (event.type === 'job_failed') {
        setLines(prev => [...prev.slice(-(maxLines - 1)), { ts, level: 'error', text: `❌ Job failed: ${event.error}` }]);
      } else if (event.type === 'job_status_changed') {
        setLines(prev => [...prev.slice(-(maxLines - 1)), { ts, level: 'warn', text: `🔄 Job status: ${event.status}` }]);
      } else if (event.type === 'retry_scheduled') {
        setLines(prev => [...prev.slice(-(maxLines - 1)), { ts, level: 'warn', text: `🔁 Retry ${event.retry}/${event.max_retries} scheduled` }]);
      } else if (text) {
        setLines(prev => [...prev.slice(-(maxLines - 1)), { ts, level: level as LogLine['level'], text }]);
      }
    });
    return unsub;
  }, [jobId, maxLines]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [lines]);

  const levelColor = (l: LogLine['level']) => {
    if (l === 'error') return 'text-red-400';
    if (l === 'warn') return 'text-yellow-400';
    if (l === 'phase') return 'text-indigo-400 font-medium';
    return 'text-gray-300';
  };

  return (
    <div className="bg-black/50 border border-gray-800 rounded px-3 py-2 font-mono text-xs h-48 overflow-y-auto space-y-0.5">
      {lines.length === 0 && (
        <p className="text-gray-600 italic">Waiting for log events…</p>
      )}
      {lines.map((line, i) => (
        <div key={i} className={`${levelColor(line.level)} flex gap-3`}>
          <span className="text-gray-600 shrink-0">{line.ts}</span>
          <span className="shrink-0 uppercase text-[10px] font-bold opacity-60">{line.level}</span>
          <span className="break-all">{line.text}</span>
        </div>
      ))}
      <div ref={bottomRef} />
    </div>
  );
}

// ── Job Detail ───────────────────────────────────────────────────────────────

function JobDetail({
  job: initialJob,
  onBack,
  onRefresh,
}: {
  job: Job;
  onBack: () => void;
  onRefresh: (job: Job) => void;
}) {
  const [job, setJob] = useState(initialJob);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [activeSection, setActiveSection] = useState<'phases' | 'log' | 'config' | 'metrics'>('phases');

  useEffect(() => {
    const unsub = subscribeJob(job.id, (event) => {
      if (event.job) setJob(event.job as Job);
      else if (event.event === 'done' || event.event === 'error') {
        getJob(job.id).then(setJob).catch(() => {});
      } else if (event.type === 'job_completed' || event.type === 'job_failed') {
        getJob(job.id).then(setJob).catch(() => {});
      }
    });
    return unsub;
  }, [job.id]);

  const handleResume = async () => {
    setLoading(true); setError('');
    try { const u = await resumeJob(job.id); setJob(u); onRefresh(u); }
    catch (e) { setError(String(e)); }
    finally { setLoading(false); }
  };

  const handleAbort = async () => {
    setLoading(true); setError('');
    try { const u = await abortJob(job.id); setJob(u); onRefresh(u); }
    catch (e) { setError(String(e)); }
    finally { setLoading(false); }
  };

  const [metrics, setMetrics] = useState<import('./api').JobMetrics | null>(null);
  const [metricsLoading, setMetricsLoading] = useState(false);

  // Load metrics when Metrics tab is active
  useEffect(() => {
    if (activeSection !== 'metrics') return;
    let cancelled = false;
    setMetricsLoading(true);
    getJobMetrics(job.id)
      .then(m => { if (!cancelled) setMetrics(m); })
      .catch(() => {})
      .finally(() => { if (!cancelled) setMetricsLoading(false); });
    return () => { cancelled = true; };
  }, [activeSection, job.id]);

  const sections = [
    { key: 'phases', label: 'Phases' },
    { key: 'log', label: 'Live Log' },
    { key: 'config', label: 'Config' },
    { key: 'metrics', label: 'Metrics' },
  ] as const;

  return (
    <div className="space-y-4">
      <button onClick={onBack} className="text-sm text-gray-400 hover:text-white flex items-center gap-1">
        ← Back to Jobs
      </button>

      <div className="card p-4 flex items-start justify-between">
        <div>
          <h2 className="text-lg font-mono text-indigo-400">{job.id}</h2>
          <p className="text-sm text-gray-400">{job.profile} · {job.description || '—'}</p>
          <p className="text-xs text-gray-500 mt-1">Created {timeAgo(job.created_at)}</p>
        </div>
        <div className="flex flex-col items-end gap-2">
          <PhaseStatusBadge phase={job.status} />
          {job.current_phase && <span className="text-xs text-gray-500">Phase: {job.current_phase}</span>}
          {(job as any).retry_count != null && (
            <span className="text-xs text-gray-500">Retry: {(job as any).retry_count}/{(job as any).max_retries}</span>
          )}
        </div>
      </div>

      {error && <p className="text-red-400 text-sm">{error}</p>}

      {job.status !== 'running' && (
        <div className="flex gap-3">
          <button onClick={handleResume} disabled={loading || job.status === 'completed'} className="btn-primary">
            {loading ? '…' : '▶ Resume'}
          </button>
          {job.status !== 'completed' && job.status !== 'failed' && (
            <button onClick={handleAbort} disabled={loading} className="btn-secondary">⬛ Abort</button>
          )}
        </div>
      )}

      {/* Section tabs */}
      <div className="flex gap-1 border-b border-gray-800">
        {sections.map(s => (
          <button
            key={s.key}
            onClick={() => setActiveSection(s.key)}
            className={`px-4 py-2 text-sm border-b-2 transition-colors ${
              activeSection === s.key
                ? 'border-indigo-500 text-indigo-400'
                : 'border-transparent text-gray-500 hover:text-gray-300'
            }`}
          >
            {s.label}
          </button>
        ))}
      </div>

      {/* Phases */}
      {activeSection === 'phases' && (
        <div className="card overflow-hidden">
          {Object.entries(job.phases || {}).length === 0 ? (
            <p className="p-4 text-gray-500 text-sm">No phase data yet.</p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-800 text-left text-gray-500 text-xs">
                  <th className="px-4 py-2 font-medium">Phase</th>
                  <th className="px-4 py-2 font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(job.phases || {}).map(([name, info]) => (
                  <tr key={name} className="border-b border-gray-800/50 hover:bg-gray-800/30">
                    <td className="px-4 py-3 font-mono text-indigo-300">{name}</td>
                    <td className="px-4 py-3"><PhaseStatusBadge phase={info.status} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* Live Log */}
      {activeSection === 'log' && <LogPanel jobId={job.id} />}

      {/* Config */}
      {activeSection === 'config' && (
        <div className="card p-4">
          {job.config && Object.keys(job.config).length > 0 ? (
            <pre className="text-xs text-gray-300 overflow-x-auto whitespace-pre-wrap">
              {JSON.stringify(job.config, null, 2)}
            </pre>
          ) : (
            <p className="text-gray-500 text-sm">No config stored for this job.</p>
          )}
        </div>
      )}

      {/* Metrics */}
      {activeSection === 'metrics' && (
        <div className="space-y-4">
          {metricsLoading && <p className="text-gray-500 text-sm">Loading metrics…</p>}
          {metrics && (<>
            {/* Overview cards */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div className="bg-gray-900 rounded p-3 border border-gray-800">
                <div className="text-lg font-bold text-white">{metrics.duration_ms != null ? `${(metrics.duration_ms / 1000).toFixed(1)}s` : '—'}</div>
                <div className="text-xs text-gray-500">Total Duration</div>
              </div>
              <div className="bg-gray-900 rounded p-3 border border-gray-800">
                <div className="text-lg font-bold text-green-400">{metrics.providers_succeeded}/{metrics.providers_run}</div>
                <div className="text-xs text-gray-500">Providers OK</div>
              </div>
              <div className="bg-gray-900 rounded p-3 border border-gray-800">
                <div className="text-lg font-bold text-yellow-400">{metrics.retry_count}/{metrics.max_retries}</div>
                <div className="text-xs text-gray-500">Retries</div>
              </div>
              <div className="bg-gray-900 rounded p-3 border border-gray-800">
                <div className="text-lg font-bold text-purple-400">{metrics.tokens_used?.toLocaleString?.() ?? '—'}</div>
                <div className="text-xs text-gray-500">Tokens Used</div>
              </div>
            </div>

            {/* Phase Durations Breakdown */}
            {Object.keys(metrics.phase_durations).length > 0 && (
              <div className="card overflow-hidden">
                <h3 className="px-4 pt-3 pb-2 text-sm font-medium text-gray-400">Phase Duration Breakdown</h3>
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-800 text-left text-gray-500 text-xs">
                      <th className="px-4 py-2 font-medium">Phase</th>
                      <th className="px-4 py-2 font-medium">Duration</th>
                      <th className="px-4 py-2 font-medium">Bar</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(metrics.phase_durations).map(([phase, ms]) => {
                      const maxMs = Math.max(...Object.values(metrics.phase_durations));
                      const pct = maxMs > 0 ? (ms / maxMs) * 100 : 0;
                      return (
                        <tr key={phase} className="border-b border-gray-800/50">
                          <td className="px-4 py-3 font-mono text-indigo-300">{phase}</td>
                          <td className="px-4 py-3 text-gray-300">{ms >= 1000 ? `${(ms / 1000).toFixed(2)}s` : `${ms}ms`}</td>
                          <td className="px-4 py-3">
                            <div className="h-2 bg-gray-800 rounded-full overflow-hidden">
                              <div className="h-full bg-indigo-500 rounded-full" style={{ width: `${pct}%` }} />
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}

            {/* Token detail */}
            {(metrics.tokens_prompt || metrics.tokens_completion) && (
              <div className="card p-4">
                <h3 className="text-sm font-medium text-gray-400 mb-2">Token Usage</h3>
                <div className="grid grid-cols-3 gap-3 text-sm">
                  <div><span className="text-gray-500">Prompt:</span> <span className="text-white">{metrics.tokens_prompt?.toLocaleString?.() ?? '—'}</span></div>
                  <div><span className="text-gray-500">Completion:</span> <span className="text-white">{metrics.tokens_completion?.toLocaleString?.() ?? '—'}</span></div>
                  <div><span className="text-gray-500">Total:</span> <span className="text-white">{metrics.tokens_used?.toLocaleString?.() ?? '—'}</span></div>
                </div>
              </div>
            )}

            {/* Error */}
            {metrics.error && (
              <div className="card p-4 border-l-4 border-red-500">
                <h3 className="text-sm font-medium text-red-400 mb-1">Error</h3>
                <pre className="text-xs text-gray-300 overflow-x-auto">{metrics.error}</pre>
              </div>
            )}
          </>)}
        </div>
      )}
    </div>
  );
}

// ── Jobs List ─────────────────────────────────────────────────────────────────


function Sparkline({ data, color = '#60a5fa', height = 24 }: { data: number[]; color?: string; height?: number }) {
  if (!data.length) return null;
  const max = Math.max(...data, 1);
  const width = data.length * 4; // 4px per point
  const points = data.map((v, i) => {
    const x = i * 4 + 2;
    const y = height - (v / max) * (height - 2);
    return `${x},${y}`;
  }).join(' ');
  return (
    <svg width={width} height={height} className="opacity-60">
      <polyline fill="none" stroke={color} strokeWidth="1.5" points={points} />
    </svg>
  );
}

function StatsCard({ stats, timeseries, loading }: { stats: Record<string, unknown> | null; timeseries: StatsBucket[]; loading: boolean }) {
  if (loading) return <div className="text-gray-500 text-sm py-4">Loading stats…</div>;
  if (!stats) return null;
  
  const fmt = (v: number | undefined) => v?.toLocaleString?.() ?? '-';
  
  // Extract sparkline data from timeseries
  const totalData = timeseries.map(b => b.total).reverse();
  const successData = timeseries.map(b => b.total > 0 ? Math.round((b.completed / b.total) * 100) : 0).reverse();
  const durationData = timeseries.map(b => b.avg_duration_ms || 0).reverse();
  const throughputData = timeseries.map(b => b.total).reverse();
  
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
      <div className="bg-gray-900 rounded p-3 border border-gray-800">
        <div className="text-2xl font-bold text-white">{fmt(stats.total as number)}</div>
        <div className="text-xs text-gray-500 mb-1">Total Jobs</div>
        <Sparkline data={totalData} color="#ffffff" />
      </div>
      <div className="bg-gray-900 rounded p-3 border border-gray-800">
        <div className="text-2xl font-bold text-green-400">{fmt(stats.success_rate as number)}%</div>
        <div className="text-xs text-gray-500 mb-1">Success Rate</div>
        <Sparkline data={successData} color="#4ade80" />
      </div>
      <div className="bg-gray-900 rounded p-3 border border-gray-800">
        <div className="text-2xl font-bold text-blue-400">{fmt(stats.avg_duration_ms as number)}ms</div>
        <div className="text-xs text-gray-500 mb-1">Avg Duration</div>
        <Sparkline data={durationData} color="#60a5fa" />
      </div>
      <div className="bg-gray-900 rounded p-3 border border-gray-800">
        <div className="text-2xl font-bold text-yellow-400">{fmt(stats.throughput_last_hour as number)}</div>
        <div className="text-xs text-gray-500 mb-1">Jobs/Hour</div>
        <Sparkline data={throughputData} color="#facc15" />
      </div>
    </div>
  );
}

function JobsList({
  jobs,
  onSelect,
  onRefresh,
  filter,
  setFilter,
}: {
  jobs: Job[];
  onSelect: (job: Job) => void;
  onRefresh: () => void;
  filter: string;
  setFilter: (f: string) => void;
}) {
  const filtered = jobs.filter(j =>
    filter === '' ||
    j.id.includes(filter) ||
    j.profile.includes(filter) ||
    j.description?.toLowerCase().includes(filter.toLowerCase())
  );

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-medium">Jobs <span className="text-gray-500 font-normal">({filtered.length})</span></h2>
        <button onClick={onRefresh} className="text-sm text-gray-400 hover:text-white">↻ Refresh</button>
      </div>
      <input
        value={filter}
        onChange={e => setFilter(e.target.value)}
        placeholder="Search jobs…"
        className="w-full bg-gray-900 border border-gray-700 rounded px-3 py-2 text-sm focus:border-indigo-500 outline-none"
      />
      {filtered.length === 0 ? (
        <p className="text-gray-500 text-sm py-8 text-center">No jobs yet. Create one!</p>
      ) : (
        <div className="space-y-2">
          {filtered.map(job => (
            <div
              key={job.id}
              onClick={() => onSelect(job)}
              className="card p-4 hover:border-indigo-600 cursor-pointer transition-colors"
            >
              <div className="flex items-center justify-between">
                <div>
                  <span className="font-mono text-sm text-indigo-400">{job.id}</span>
                  <span className="text-gray-500 text-xs ml-3">{job.profile}</span>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-xs text-gray-500">{timeAgo(job.updated_at || job.created_at)}</span>
                  <PhaseStatusBadge phase={job.status} />
                </div>
              </div>
              {job.description && <p className="text-xs text-gray-400 mt-1 truncate">{job.description}</p>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Plugins Tab ───────────────────────────────────────────────────────────────

function PluginsTab() {
  const [plugins, setPlugins] = useState<Plugin[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [configPlugin, setConfigPlugin] = useState<Plugin | null>(null);
  const [configText, setConfigText] = useState('');
  const [configSaving, setConfigSaving] = useState(false);

  const loadPlugins = useCallback(async () => {
    setLoading(true); setError('');
    try {
      const data = await listPlugins();
      setPlugins(data);
    } catch (e) { setError(String(e)); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { loadPlugins(); }, [loadPlugins]);

  const handleToggle = async (p: Plugin) => {
    try {
      if (p.enabled) {
        await disablePlugin(p.name);
      } else {
        await enablePlugin(p.name);
      }
      await loadPlugins();
    } catch (e) { setError(String(e)); }
  };

  const openConfig = (p: Plugin) => {
    setConfigPlugin(p);
    setConfigText(JSON.stringify(p.config || {}, null, 2));
  };

  const handleSaveConfig = async () => {
    if (!configPlugin) return;
    setConfigSaving(true); setError('');
    try {
      const config = JSON.parse(configText);
      await updatePluginConfig(configPlugin.name, config);
      setConfigPlugin(null);
      await loadPlugins();
    } catch (e) {
      setError(`JSON parse error: ${e}`);
    } finally { setConfigSaving(false); }
  };

  if (loading) return <LoadingSpinner msg="Loading plugins…" />;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-medium">Plugins</h2>
        <button onClick={loadPlugins} className="text-sm text-gray-400 hover:text-white">↻ Refresh</button>
      </div>

      {error && <p className="text-red-400 text-sm">{error}</p>}

      {plugins.length === 0 ? (
        <p className="text-gray-500 text-sm py-8 text-center">No plugins found.</p>
      ) : (
        <div className="space-y-2">
          {plugins.map(p => (
            <div key={p.name} className="card p-4">
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <div className="flex items-center gap-3">
                    <span className="font-mono text-indigo-300">{p.name}</span>
                    <span className={`badge text-xs ${p.enabled ? 'badge-completed' : 'badge-pending'}`}>
                      {p.enabled ? 'enabled' : 'disabled'}
                    </span>
                  </div>
                  {p.description && <p className="text-xs text-gray-400 mt-1">{p.description}</p>}
                  <p className="text-xs text-gray-600 mt-1">Hooks: {p.hooks.join(', ')}</p>
                </div>
                <div className="flex gap-2 ml-4">
                  <button
                    onClick={() => handleToggle(p)}
                    className={`text-xs px-3 py-1 rounded transition-colors ${
                      p.enabled
                        ? 'bg-red-600/20 text-red-400 hover:bg-red-600/40'
                        : 'bg-emerald-600/20 text-emerald-400 hover:bg-emerald-600/40'
                    }`}
                  >
                    {p.enabled ? 'Disable' : 'Enable'}
                  </button>
                  <button
                    onClick={() => openConfig(p)}
                    className="text-xs bg-gray-700 hover:bg-gray-600 text-gray-300 px-3 py-1 rounded transition-colors"
                  >
                    Config
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Config Modal */}
      {configPlugin && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="card p-6 w-full max-w-lg">
            <h3 className="text-lg font-semibold mb-3">Configure: {configPlugin.name}</h3>
            <textarea
              value={configText}
              onChange={e => setConfigText(e.target.value)}
              rows={12}
              className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 font-mono text-xs text-gray-200 focus:border-indigo-500 outline-none resize-y"
            />
            {error && <p className="text-red-400 text-xs mt-2">{error}</p>}
            <div className="flex gap-3 mt-3">
              <button
                onClick={handleSaveConfig}
                disabled={configSaving}
                className="btn-primary flex-1"
              >
                {configSaving ? 'Saving…' : 'Save'}
              </button>
              <button onClick={() => setConfigPlugin(null)} className="btn-secondary">Cancel</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Audit Tab ─────────────────────────────────────────────────────────────────

function AuditTab() {
  const [entries, setEntries] = useState<AuditEntry[]>([]);
  const [stats, setStats] = useState<Record<string, unknown>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [filterEvent, setFilterEvent] = useState('');
  const [filterTarget, setFilterTarget] = useState('');

  const loadAudit = useCallback(async () => {
    setLoading(true); setError('');
    try {
      const params: Record<string, string> = {};
      if (filterEvent) params.event = filterEvent;
      if (filterTarget) params.target = filterTarget;
      const [logs, st] = await Promise.all([getAuditLogs(params), getAuditStats()]);
      setEntries(logs.slice(0, 200)); // cap display
      setStats(st);
    } catch (e) { setError(String(e)); }
    finally { setLoading(false); }
  }, [filterEvent, filterTarget]);

  useEffect(() => { loadAudit(); }, [loadAudit]);

  if (loading) return <LoadingSpinner msg="Loading audit log…" />;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-medium">Audit Log</h2>
        <button onClick={loadAudit} className="text-sm text-gray-400 hover:text-white">↻ Refresh</button>
      </div>

      {/* Stats summary */}
      {Object.keys(stats).length > 0 && (
        <div className="grid grid-cols-3 gap-3">
          {Object.entries(stats).slice(0, 6).map(([k, v]) => (
            <div key={k} className="card p-3 text-center">
              <div className="text-2xl font-bold text-indigo-400">{String(v)}</div>
              <div className="text-xs text-gray-500 mt-1">{k}</div>
            </div>
          ))}
        </div>
      )}

      {/* Filters */}
      <div className="flex gap-3">
        <input
          value={filterEvent}
          onChange={e => setFilterEvent(e.target.value)}
          placeholder="Filter by event…"
          className="flex-1 bg-gray-900 border border-gray-700 rounded px-3 py-2 text-sm focus:border-indigo-500 outline-none"
        />
        <input
          value={filterTarget}
          onChange={e => setFilterTarget(e.target.value)}
          placeholder="Filter by target…"
          className="flex-1 bg-gray-900 border border-gray-700 rounded px-3 py-2 text-sm focus:border-indigo-500 outline-none"
        />
        <button onClick={loadAudit} className="btn-secondary text-sm">Apply</button>
      </div>

      {error && <p className="text-red-400 text-sm">{error}</p>}

      {/* Table */}
      <div className="card overflow-hidden">
        {entries.length === 0 ? (
          <p className="p-4 text-gray-500 text-sm text-center">No audit entries found.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-800 text-left text-gray-500 text-xs">
                  <th className="px-4 py-2 font-medium">Time</th>
                  <th className="px-4 py-2 font-medium">Category</th>
                  <th className="px-4 py-2 font-medium">Event</th>
                  <th className="px-4 py-2 font-medium">Actor</th>
                  <th className="px-4 py-2 font-medium">Target</th>
                </tr>
              </thead>
              <tbody>
                {entries.map(e => (
                  <tr key={e.id} className="border-b border-gray-800/50 hover:bg-gray-800/30">
                    <td className="px-4 py-2 text-gray-500 text-xs whitespace-nowrap">
                      {new Date(e.timestamp).toLocaleString()}
                    </td>
                    <td className="px-4 py-2">
                      <span className="badge badge-pending text-xs">{e.category}</span>
                    </td>
                    <td className="px-4 py-2 font-mono text-indigo-300 text-xs">{e.event}</td>
                    <td className="px-4 py-2 text-gray-400 text-xs">{e.actor}</td>
                    <td className="px-4 py-2 text-gray-400 text-xs font-mono truncate max-w-[120px]">{e.target}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Config Tab ─────────────────────────────────────────────────────────────────

function ConfigTab() {
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [selectedProfile, setSelectedProfile] = useState<Profile | null>(null);
  const [profileData, setProfileData] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const loadProfiles = useCallback(async () => {
    setLoading(true); setError('');
    try {
      const list = await listProfiles();
      setProfiles(list);
    } catch (e) { setError(String(e)); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { loadProfiles(); }, [loadProfiles]);

  const selectProfile = async (p: Profile) => {
    setSelectedProfile(p); setError('');
    try {
      const res = await fetch(`/profiles/${p.name}`);
      if (!res.ok) throw new Error(await res.text());
      setProfileData(await res.json());
    } catch (e) { setError(String(e)); }
  };

  if (loading) return <LoadingSpinner msg="Loading profiles…" />;

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-medium">Profile Config</h2>

      {error && <p className="text-red-400 text-sm">{error}</p>}

      <div className="flex gap-6">
        {/* Profile list */}
        <div className="w-48 shrink-0 space-y-1">
          {profiles.map(p => (
            <button
              key={p.name}
              onClick={() => selectProfile(p)}
              className={`w-full text-left px-3 py-2 rounded text-sm transition-colors ${
                selectedProfile?.name === p.name
                  ? 'bg-indigo-600 text-white'
                  : 'bg-gray-800 text-gray-300 hover:bg-gray-700'
              }`}
            >
              {p.name}
            </button>
          ))}
        </div>

        {/* Profile viewer/editor */}
        <div className="flex-1">
          {!selectedProfile ? (
            <p className="text-gray-500 text-sm">Select a profile to view or edit.</p>
          ) : !profileData ? (
            <LoadingSpinner msg="Loading profile…" />
          ) : (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <h3 className="font-medium text-indigo-300">Profile: {selectedProfile.name}</h3>
                <span className="text-xs text-gray-500">{selectedProfile.description || '—'}</span>
              </div>
              <pre className="bg-black/40 border border-gray-800 rounded p-4 text-xs text-gray-300 overflow-auto max-h-96 whitespace-pre-wrap">
                {JSON.stringify(profileData, null, 2)}
              </pre>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Compare Tab ─────────────────────────────────────────────────────────────────

function CompareTab() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [result, setResult] = useState<CompareResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [comparing, setComparing] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    listJobs({ limit: 100 }).then(setJobs).catch(e => setError(String(e))).finally(() => setLoading(false));
  }, []);

  const toggle = (id: string) => {
    const next = new Set(selectedIds);
    next.has(id) ? next.delete(id) : next.add(id);
    setSelectedIds(next);
  };

  const runCompare = async () => {
    if (selectedIds.size < 2) return;
    setComparing(true); setError('');
    try {
      const data = await compareJobs(Array.from(selectedIds));
      setResult(data);
    } catch (e) { setError(String(e)); }
    finally { setComparing(false); }
  };

  if (loading) return <LoadingSpinner msg="Loading jobs…" />;

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-medium">Job Comparison</h2>
      <p className="text-gray-500 text-sm">Select 2–10 jobs to compare metrics side-by-side.</p>

      {error && <p className="text-red-400 text-sm">{error}</p>}

      {/* Job selector */}
      <div className="bg-gray-900/50 border border-gray-800 rounded p-4">
        <div className="flex items-center justify-between mb-3">
          <span className="text-sm text-gray-400">{selectedIds.size} selected</span>
          <button
            onClick={runCompare}
            disabled={selectedIds.size < 2 || comparing}
            className="btn-primary text-sm disabled:opacity-50"
          >
            {comparing ? 'Comparing…' : 'Compare'}
          </button>
        </div>
        <div className="max-h-64 overflow-y-auto space-y-1">
          {jobs.map(j => (
            <label key={j.id} className="flex items-center gap-2 px-2 py-1 hover:bg-gray-800/50 rounded cursor-pointer">
              <input
                type="checkbox"
                checked={selectedIds.has(j.id)}
                onChange={() => toggle(j.id)}
                className="rounded border-gray-600"
              />
              <span className="text-sm font-mono text-gray-300">{j.id.slice(0, 8)}</span>
              <span className={`text-xs ${j.status === 'completed' ? 'text-green-400' : j.status === 'failed' ? 'text-red-400' : 'text-gray-500'}`}>
                {j.status}
              </span>
              <span className="text-xs text-gray-600">{j.profile}</span>
            </label>
          ))}
        </div>
      </div>

      {/* Comparison result */}
      {result && (
        <div className="space-y-4">
          {/* Summary */}
          <div className="grid grid-cols-4 gap-3">
            <div className="bg-gray-900/50 border border-gray-800 rounded p-3 text-center">
              <div className="text-2xl font-bold text-indigo-400">{result.summary.count}</div>
              <div className="text-xs text-gray-500">Jobs</div>
            </div>
            <div className="bg-gray-900/50 border border-gray-800 rounded p-3 text-center">
              <div className="text-2xl font-bold text-blue-400">{result.summary.avg_duration_ms ? (result.summary.avg_duration_ms / 1000).toFixed(1) + 's' : '—'}</div>
              <div className="text-xs text-gray-500">Avg Duration</div>
            </div>
            <div className="bg-gray-900/50 border border-gray-800 rounded p-3 text-center">
              <div className="text-2xl font-bold text-green-400">{result.summary.total_providers_succeeded}/{result.summary.total_providers_run}</div>
              <div className="text-xs text-gray-500">Providers OK</div>
            </div>
            <div className="bg-gray-900/50 border border-gray-800 rounded p-3 text-center">
              <div className="text-2xl font-bold text-yellow-400">{result.summary.total_retries}</div>
              <div className="text-xs text-gray-500">Total Retries</div>
            </div>
          </div>

          {/* Per-job table */}
          <div className="bg-gray-900/50 border border-gray-800 rounded overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-gray-800/50">
                <tr>
                  <th className="px-3 py-2 text-left text-gray-400">Job</th>
                  <th className="px-3 py-2 text-left text-gray-400">Profile</th>
                  <th className="px-3 py-2 text-left text-gray-400">Duration</th>
                  <th className="px-3 py-2 text-left text-gray-400">Providers</th>
                  <th className="px-3 py-2 text-left text-gray-400">Retries</th>
                  <th className="px-3 py-2 text-left text-gray-400">Tokens</th>
                  <th className="px-3 py-2 text-left text-gray-400">State</th>
                </tr>
              </thead>
              <tbody>
                {result.jobs.map(j => (
                  <tr key={j.job_id} className="border-t border-gray-800">
                    <td className="px-3 py-2 font-mono text-xs text-indigo-300">{j.job_id.slice(0, 8)}</td>
                    <td className="px-3 py-2 text-gray-300">{j.profile}</td>
                    <td className="px-3 py-2 text-gray-300">{j.duration_ms ? (j.duration_ms / 1000).toFixed(2) + 's' : '—'}</td>
                    <td className="px-3 py-2 text-gray-300">{j.providers_succeeded}/{j.providers_run}</td>
                    <td className="px-3 py-2 text-gray-300">{j.retry_count}</td>
                    <td className="px-3 py-2 text-gray-300">{j.tokens_used ?? '—'}</td>
                    <td className="px-3 py-2">
                      <span className={`badge ${j.state === 'completed' ? 'badge-completed' : j.state === 'failed' ? 'badge-failed' : 'badge-running'}`}>
                        {j.state}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Knowledge Tab ──────────────────────────────────────────────────────────────

function KnowledgeTab() {
  const [pages, setPages] = useState<string[]>([]);
  const [selectedPage, setSelectedPage] = useState<MemoryPage | null>(null);
  const [stats, setStats] = useState<MemoryStats | null>(null);
  const [graph, setGraph] = useState<GraphData | null>(null);
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showCreate, setShowCreate] = useState(false);
  const [showSearch, setShowSearch] = useState(false);
  const [showGraph, setShowGraph] = useState(false);

  const loadData = useCallback(async () => {
    setLoading(true); setError('');
    try {
      const [pageList, st] = await Promise.all([listMemoryPages(), getMemoryStats()]);
      setPages(pageList);
      setStats(st);
    } catch (e) { setError(String(e)); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const selectPage = async (title: string) => {
    try {
      const page = await getMemoryPage(title);
      setSelectedPage(page);
    } catch (e) { setError(String(e)); }
  };

  const handleSearch = async () => {
    if (!searchQuery.trim()) return;
    try {
      const results = await searchMemory(searchQuery);
      setSearchResults(results);
      setShowSearch(true);
    } catch (e) { setError(String(e)); }
  };

  const handleShowGraph = async () => {
    try {
      const g = await getMemoryGraph();
      setGraph(g);
      setShowGraph(true);
    } catch (e) { setError(String(e)); }
  };

  const handleCreatePage = async (title: string, content: string, tags: string[]) => {
    try {
      await createMemoryPage({ title, content, tags });
      setShowCreate(false);
      await loadData();
      await selectPage(title);
    } catch (e) { setError(String(e)); }
  };

  const handleDeletePage = async (title: string) => {
    try {
      await deleteMemoryPage(title);
      if (selectedPage?.title === title) setSelectedPage(null);
      await loadData();
    } catch (e) { setError(String(e)); }
  };

  if (loading) return <LoadingSpinner msg="Loading knowledge base…" />;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-medium">Knowledge Base</h2>
        <div className="flex gap-2">
          <button onClick={() => setShowSearch(!showSearch)} className="btn-secondary text-sm">
            {showSearch ? 'Hide Search' : '🔍 Search'}
          </button>
          <button onClick={handleShowGraph} className="btn-secondary text-sm">
            🔗 Graph
          </button>
          <button onClick={() => setShowCreate(true)} className="btn-primary text-sm">
            + New Page
          </button>
        </div>
      </div>

      {error && <p className="text-red-400 text-sm">{error}</p>}

      {/* Stats */}
      {stats && (
        <div className="grid grid-cols-3 gap-3">
          <div className="bg-gray-900 rounded p-3 border border-gray-800 text-center">
            <div className="text-2xl font-bold text-indigo-400">{stats.total_pages}</div>
            <div className="text-xs text-gray-500">Pages</div>
          </div>
          <div className="bg-gray-900 rounded p-3 border border-gray-800 text-center">
            <div className="text-2xl font-bold text-blue-400">{stats.total_links}</div>
            <div className="text-xs text-gray-500">Links</div>
          </div>
          <div className="bg-gray-900 rounded p-3 border border-gray-800 text-center">
            <div className="text-2xl font-bold text-purple-400">{stats.total_tags}</div>
            <div className="text-xs text-gray-500">Tags</div>
          </div>
        </div>
      )}

      {/* Search */}
      {showSearch && (
        <div className="card p-4">
          <div className="flex gap-2 mb-3">
            <input
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleSearch()}
              placeholder="Search knowledge base…"
              className="flex-1 bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm focus:border-indigo-500 outline-none"
            />
            <button onClick={handleSearch} className="btn-primary text-sm">Search</button>
          </div>
          {searchResults.length > 0 && (
            <div className="space-y-2">
              {searchResults.map(r => (
                <div
                  key={r.title}
                  onClick={() => selectPage(r.title)}
                  className="p-2 rounded hover:bg-gray-800/50 cursor-pointer border border-gray-800"
                >
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-sm text-indigo-300">{r.title}</span>
                    <span className="text-xs text-gray-500">score: {r.score.toFixed(2)}</span>
                  </div>
                  <p className="text-xs text-gray-400 mt-1 line-clamp-2">{r.snippet}</p>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Graph Modal */}
      {showGraph && graph && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="card p-6 w-full max-w-2xl max-h-[80vh] overflow-auto">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold">Knowledge Graph</h3>
              <button onClick={() => setShowGraph(false)} className="text-gray-400 hover:text-white">✕</button>
            </div>
            <div className="text-xs text-gray-400 mb-3">
              {graph.nodes.length} nodes · {graph.edges.length} edges
            </div>
            {/* Simple ASCII-style graph rendering */}
            <div className="bg-black/50 border border-gray-800 rounded p-4 font-mono text-xs space-y-1 max-h-96 overflow-auto">
              {graph.nodes.map(n => (
                <div key={n.id} className="flex items-center gap-2">
                  <span className="text-indigo-400">●</span>
                  <span className="text-gray-200">{n.label || n.id}</span>
                  {graph.edges.filter(e => e.source === n.id).map(e => {
                    const target = graph.nodes.find(nn => nn.id === e.target);
                    return (
                      <span key={e.target} className="text-gray-500">
                        → <span className="text-blue-400">{target?.label || e.target}</span>
                      </span>
                    );
                  })}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Content: Page list + Detail view */}
      <div className="flex gap-4">
        {/* Page list */}
        <div className="w-56 shrink-0">
          <div className="space-y-1 max-h-[60vh] overflow-y-auto">
            {pages.map(title => (
              <div
                key={title}
                onClick={() => selectPage(title)}
                className={`px-3 py-2 rounded text-sm cursor-pointer transition-colors flex items-center justify-between group ${
                  selectedPage?.title === title
                    ? 'bg-indigo-600 text-white'
                    : 'bg-gray-800 text-gray-300 hover:bg-gray-700'
                }`}
              >
                <span className="truncate">{title}</span>
                <button
                  onClick={e => { e.stopPropagation(); handleDeletePage(title); }}
                  className="text-gray-500 hover:text-red-400 opacity-0 group-hover:opacity-100 text-xs ml-1"
                >×</button>
              </div>
            ))}
            {pages.length === 0 && (
              <p className="text-gray-500 text-sm text-center py-4">No pages yet</p>
            )}
          </div>
        </div>

        {/* Page detail */}
        <div className="flex-1 min-w-0">
          {!selectedPage ? (
            <div className="card p-8 text-center text-gray-500">
              <p className="text-lg mb-2">📚 Select a page to view</p>
              <p className="text-sm">Or create a new one with the + New Page button</p>
            </div>
          ) : (
            <div className="space-y-3">
              <div className="card p-4">
                <h3 className="text-lg font-semibold text-indigo-300 mb-2">{selectedPage.title}</h3>
                <div className="flex gap-2 mb-3">
                  {selectedPage.tags?.map(t => (
                    <span key={t} className="badge badge-pending text-xs">{t}</span>
                  ))}
                </div>
                <pre className="text-sm text-gray-300 whitespace-pre-wrap font-sans leading-relaxed">
                  {selectedPage.content}
                </pre>
              </div>
              {selectedPage.links && selectedPage.links.length > 0 && (
                <div className="card p-3">
                  <h4 className="text-xs text-gray-500 mb-2">Linked Pages</h4>
                  <div className="flex flex-wrap gap-1">
                    {selectedPage.links.map(link => (
                      <button
                        key={link}
                        onClick={() => selectPage(link)}
                        className="text-xs bg-blue-900/30 text-blue-400 px-2 py-1 rounded hover:bg-blue-900/50"
                      >
                        [[{link}]]
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Create Page Modal */}
      {showCreate && (
        <CreatePageModal
          onClose={() => setShowCreate(false)}
          onCreate={handleCreatePage}
        />
      )}
    </div>
  );
}

function CreatePageModal({
  onClose,
  onCreate,
}: {
  onClose: () => void;
  onCreate: (title: string, content: string, tags: string[]) => void;
}) {
  const [title, setTitle] = useState('');
  const [content, setContent] = useState('');
  const [tags, setTags] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) { setError('Title is required'); return; }
    setLoading(true); setError('');
    try {
      await onCreate(title.trim(), content, tags.split(',').map(t => t.trim()).filter(Boolean));
    } catch (err) { setError(String(err)); }
    finally { setLoading(false); }
  };

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
      <div className="card p-6 w-full max-w-lg">
        <h2 className="text-xl font-semibold mb-4">Create Knowledge Page</h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm text-gray-400 mb-1">Title</label>
            <input
              value={title}
              onChange={e => setTitle(e.target.value)}
              placeholder="Page title"
              className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 focus:border-indigo-500 outline-none"
            />
          </div>
          <div>
            <label className="block text-sm text-gray-400 mb-1">Content (Markdown)</label>
            <textarea
              value={content}
              onChange={e => setContent(e.target.value)}
              rows={8}
              placeholder="Write content here… Use [[wikilinks]] to link pages."
              className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 focus:border-indigo-500 outline-none resize-y font-mono text-sm"
            />
          </div>
          <div>
            <label className="block text-sm text-gray-400 mb-1">Tags (comma-separated)</label>
            <input
              value={tags}
              onChange={e => setTags(e.target.value)}
              placeholder="tag1, tag2, tag3"
              className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 focus:border-indigo-500 outline-none"
            />
          </div>
          {error && <p className="text-red-400 text-sm">{error}</p>}
          <div className="flex gap-3 pt-2">
            <button type="submit" disabled={loading} className="btn-primary flex-1">
              {loading ? 'Creating…' : 'Create Page'}
            </button>
            <button type="button" onClick={onClose} className="btn-secondary">Cancel</button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ── Governance Tab ────────────────────────────────────────────────────────────

function GovernanceTab() {
  const [agents, setAgents] = useState<import('./api').AgentInfo[]>([]);
  const [rules, setRules] = useState<import('./api').RuleInfo[]>([]);
  const [proposals, setProposals] = useState<import('./api').ProposalInfo[]>([]);
  const [requests, setRequests] = useState<import('./api').RequestInfo[]>([]);
  const [stats, setStats] = useState<import('./api').GovernanceStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [section, setSection] = useState<'agents' | 'rules' | 'proposals' | 'requests'>('agents');

  const loadData = useCallback(async () => {
    setLoading(true); setError('');
    try {
      const [a, r, p, req, st] = await Promise.all([
        listAgents().catch(() => []),
        listRules().catch(() => []),
        listProposals().catch(() => []),
        listRequests().catch(() => []),
        getGovernanceStats().catch(() => null),
      ]);
      setAgents(a); setRules(r); setProposals(p); setRequests(req); setStats(st);
    } catch (e) { setError(String(e)); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  if (loading) return <LoadingSpinner msg="Loading governance…" />;

  const sections = [
    { key: 'agents' as const, label: `Agents (${agents.length})` },
    { key: 'rules' as const, label: `Rules (${rules.length})` },
    { key: 'proposals' as const, label: `Proposals (${proposals.length})` },
    { key: 'requests' as const, label: `Requests (${requests.length})` },
  ];

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-medium">Governance</h2>
      {error && <p className="text-red-400 text-sm">{error}</p>}

      {/* Stats */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          <div className="bg-gray-900 rounded p-3 border border-gray-800 text-center">
            <div className="text-2xl font-bold text-indigo-400">{stats.agents.active}/{stats.agents.total}</div>
            <div className="text-xs text-gray-500">Active Agents</div>
          </div>
          <div className="bg-gray-900 rounded p-3 border border-gray-800 text-center">
            <div className="text-2xl font-bold text-green-400">{stats.rules.enabled}/{stats.rules.total}</div>
            <div className="text-xs text-gray-500">Active Rules</div>
          </div>
          <div className="bg-gray-900 rounded p-3 border border-gray-800 text-center">
            <div className="text-2xl font-bold text-yellow-400">{stats.proposals.open}</div>
            <div className="text-xs text-gray-500">Open Proposals</div>
          </div>
          <div className="bg-gray-900 rounded p-3 border border-gray-800 text-center">
            <div className="text-2xl font-bold text-blue-400">{stats.requests.pending}</div>
            <div className="text-xs text-gray-500">Pending Requests</div>
          </div>
          <div className="bg-gray-900 rounded p-3 border border-gray-800 text-center">
            <div className="text-2xl font-bold text-purple-400">{stats.reputation.avg?.toFixed(1) ?? '-'}</div>
            <div className="text-xs text-gray-500">Avg Reputation</div>
          </div>
        </div>
      )}

      {/* Section tabs */}
      <div className="flex gap-1 border-b border-gray-800">
        {sections.map(s => (
          <button
            key={s.key}
            onClick={() => setSection(s.key)}
            className={`px-4 py-2 text-sm border-b-2 transition-colors ${
              section === s.key
                ? 'border-indigo-500 text-indigo-400'
                : 'border-transparent text-gray-500 hover:text-gray-300'
            }`}
          >
            {s.label}
          </button>
        ))}
      </div>

      {/* Agents */}
      {section === 'agents' && (
        <div className="card overflow-hidden">
          {agents.length === 0 ? (
            <p className="p-4 text-gray-500 text-sm text-center">No agents registered</p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-800 text-left text-gray-500 text-xs">
                  <th className="px-4 py-2 font-medium">Name</th>
                  <th className="px-4 py-2 font-medium">Status</th>
                  <th className="px-4 py-2 font-medium">Capabilities</th>
                  <th className="px-4 py-2 font-medium">Registered</th>
                </tr>
              </thead>
              <tbody>
                {agents.map(a => (
                  <tr key={a.id} className="border-b border-gray-800/50 hover:bg-gray-800/30">
                    <td className="px-4 py-3 font-mono text-indigo-300">{a.name}</td>
                    <td className="px-4 py-3">
                      <span className={`badge ${a.status === 'active' ? 'badge-completed' : 'badge-pending'}`}>
                        {a.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-gray-400 text-xs">{a.capabilities?.join(', ') || '-'}</td>
                    <td className="px-4 py-3 text-gray-500 text-xs">{timeAgo(a.registered_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* Rules */}
      {section === 'rules' && (
        <div className="space-y-2">
          {rules.length === 0 ? (
            <p className="text-gray-500 text-sm text-center py-8">No rules defined</p>
          ) : rules.map(r => (
            <div key={r.id} className="card p-4 flex items-center justify-between">
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-medium text-indigo-300">{r.name}</span>
                  <span className={`badge ${r.enabled ? 'badge-completed' : 'badge-pending'}`}>
                    {r.enabled ? 'enabled' : 'disabled'}
                  </span>
                  <span className="text-xs text-gray-600">priority: {r.priority}</span>
                </div>
                {r.description && <p className="text-xs text-gray-400 mt-1">{r.description}</p>}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Proposals */}
      {section === 'proposals' && (
        <div className="space-y-2">
          {proposals.length === 0 ? (
            <p className="text-gray-500 text-sm text-center py-8">No proposals</p>
          ) : proposals.map(p => (
            <div key={p.id} className="card p-4">
              <div className="flex items-center justify-between">
                <span className="font-medium text-indigo-300">{p.title}</span>
                <span className={`badge ${
                  p.status === 'passed' ? 'badge-completed' :
                  p.status === 'rejected' ? 'badge-failed' :
                  p.status === 'open' ? 'badge-running' : 'badge-pending'
                }`}>{p.status}</span>
              </div>
              <div className="flex gap-4 mt-2 text-xs text-gray-400">
                <span>👍 {p.votes_for}</span>
                <span>👎 {p.votes_against}</span>
                <span>{timeAgo(p.created_at)}</span>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Requests */}
      {section === 'requests' && (
        <div className="card overflow-hidden">
          {requests.length === 0 ? (
            <p className="p-4 text-gray-500 text-sm text-center">No requests</p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-800 text-left text-gray-500 text-xs">
                  <th className="px-4 py-2 font-medium">ID</th>
                  <th className="px-4 py-2 font-medium">User</th>
                  <th className="px-4 py-2 font-medium">Type</th>
                  <th className="px-4 py-2 font-medium">Status</th>
                  <th className="px-4 py-2 font-medium">Created</th>
                </tr>
              </thead>
              <tbody>
                {requests.map(r => (
                  <tr key={r.id} className="border-b border-gray-800/50 hover:bg-gray-800/30">
                    <td className="px-4 py-3 font-mono text-xs text-indigo-300">{r.id.slice(0, 8)}</td>
                    <td className="px-4 py-3 text-gray-400 text-xs">{r.user_id}</td>
                    <td className="px-4 py-3 text-gray-300 text-xs">{r.type}</td>
                    <td className="px-4 py-3">
                      <span className={`badge ${
                        r.status === 'completed' ? 'badge-completed' :
                        r.status === 'failed' ? 'badge-failed' :
                        r.status === 'pending' ? 'badge-waiting' : 'badge-running'
                      }`}>{r.status}</span>
                    </td>
                    <td className="px-4 py-3 text-gray-500 text-xs">{timeAgo(r.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}

// ── Tenants Tab ──────────────────────────────────────────────────────────────

function TenantsTab() {
  const [tenants, setTenants] = useState<import('./api').Tenant[]>([]);
  const [stats, setStats] = useState<import('./api').TenantStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showCreate, setShowCreate] = useState(false);
  const [selectedTenant, setSelectedTenant] = useState<string | null>(null);
  const [usage, setUsage] = useState<import('./api').TenantUsage | null>(null);

  const loadData = useCallback(async () => {
    setLoading(true); setError('');
    try {
      const [t, st] = await Promise.all([listTenants(), getTenantStats()]);
      setTenants(t); setStats(st);
    } catch (e) { setError(String(e)); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const handleSuspend = async (id: string) => {
    try { await suspendTenant(id); await loadData(); }
    catch (e) { setError(String(e)); }
  };

  const handleActivate = async (id: string) => {
    try { await activateTenant(id); await loadData(); }
    catch (e) { setError(String(e)); }
  };

  const handleDelete = async (id: string) => {
    if (!confirm('Are you sure you want to delete this tenant?')) return;
    try { await deleteTenant(id); await loadData(); }
    catch (e) { setError(String(e)); }
  };

  const handleShowUsage = async (id: string) => {
    try {
      const u = await getTenantUsage(id);
      setUsage(u); setSelectedTenant(id);
    } catch (e) { setError(String(e)); }
  };

  const handleCreateTenant = async (name: string, plan: string) => {
    try {
      await createTenant({ name, plan: plan || undefined });
      setShowCreate(false);
      await loadData();
    } catch (e) { setError(String(e)); }
  };

  if (loading) return <LoadingSpinner msg="Loading tenants…" />;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-medium">Tenants</h2>
        <button onClick={() => setShowCreate(true)} className="btn-primary text-sm">
          + New Tenant
        </button>
      </div>

      {error && <p className="text-red-400 text-sm">{error}</p>}

      {/* Stats */}
      {stats && (
        <div className="grid grid-cols-3 gap-3">
          <div className="bg-gray-900 rounded p-3 border border-gray-800 text-center">
            <div className="text-2xl font-bold text-indigo-400">{stats.total_tenants}</div>
            <div className="text-xs text-gray-500">Total</div>
          </div>
          <div className="bg-gray-900 rounded p-3 border border-gray-800 text-center">
            <div className="text-2xl font-bold text-green-400">{stats.active_tenants}</div>
            <div className="text-xs text-gray-500">Active</div>
          </div>
          <div className="bg-gray-900 rounded p-3 border border-gray-800 text-center">
            <div className="text-2xl font-bold text-red-400">{stats.suspended_tenants}</div>
            <div className="text-xs text-gray-500">Suspended</div>
          </div>
        </div>
      )}

      {/* Tenant list */}
      <div className="space-y-2">
        {tenants.length === 0 ? (
          <p className="text-gray-500 text-sm text-center py-8">No tenants yet</p>
        ) : tenants.map(t => (
          <div key={t.id} className="card p-4">
            <div className="flex items-center justify-between">
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-medium text-indigo-300">{t.name}</span>
                  <span className="font-mono text-xs text-gray-500">{t.id.slice(0, 8)}</span>
                  <span className={`badge ${t.status === 'active' ? 'badge-completed' : 'badge-failed'}`}>
                    {t.status}
                  </span>
                  <span className="badge badge-pending">{t.plan}</span>
                </div>
                <p className="text-xs text-gray-500 mt-1">Created {timeAgo(t.created_at)}</p>
              </div>
              <div className="flex gap-2">
                <button onClick={() => handleShowUsage(t.id)} className="text-xs bg-gray-700 hover:bg-gray-600 text-gray-300 px-3 py-1 rounded">
                  Usage
                </button>
                {t.status === 'active' ? (
                  <button onClick={() => handleSuspend(t.id)} className="text-xs bg-yellow-600/20 text-yellow-400 hover:bg-yellow-600/40 px-3 py-1 rounded">
                    Suspend
                  </button>
                ) : (
                  <button onClick={() => handleActivate(t.id)} className="text-xs bg-emerald-600/20 text-emerald-400 hover:bg-emerald-600/40 px-3 py-1 rounded">
                    Activate
                  </button>
                )}
                <button onClick={() => handleDelete(t.id)} className="text-xs bg-red-600/20 text-red-400 hover:bg-red-600/40 px-3 py-1 rounded">
                  Delete
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Usage Modal */}
      {selectedTenant && usage && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="card p-6 w-full max-w-md">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold">Tenant Usage</h3>
              <button onClick={() => { setSelectedTenant(null); setUsage(null); }} className="text-gray-400 hover:text-white">✕</button>
            </div>
            <div className="grid grid-cols-3 gap-3">
              <div className="bg-gray-800 rounded p-3 text-center">
                <div className="text-xl font-bold text-indigo-400">{usage.jobs_count}</div>
                <div className="text-xs text-gray-500">Jobs</div>
              </div>
              <div className="bg-gray-800 rounded p-3 text-center">
                <div className="text-xl font-bold text-blue-400">{usage.storage_mb.toFixed(1)}</div>
                <div className="text-xs text-gray-500">Storage MB</div>
              </div>
              <div className="bg-gray-800 rounded p-3 text-center">
                <div className="text-xl font-bold text-green-400">{usage.api_calls}</div>
                <div className="text-xs text-gray-500">API Calls</div>
              </div>
            </div>
            <p className="text-xs text-gray-500 mt-3 text-center">Period: {usage.period}</p>
          </div>
        </div>
      )}

      {/* Create Tenant Modal */}
      {showCreate && (
        <CreateTenantModal
          onClose={() => setShowCreate(false)}
          onCreate={handleCreateTenant}
        />
      )}
    </div>
  );
}

function CreateTenantModal({
  onClose,
  onCreate,
}: {
  onClose: () => void;
  onCreate: (name: string, plan: string) => void;
}) {
  const [name, setName] = useState('');
  const [plan, setPlan] = useState('free');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) { setError('Name is required'); return; }
    setLoading(true); setError('');
    try { await onCreate(name.trim(), plan); }
    catch (err) { setError(String(err)); }
    finally { setLoading(false); }
  };

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
      <div className="card p-6 w-full max-w-md">
        <h2 className="text-xl font-semibold mb-4">Create Tenant</h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm text-gray-400 mb-1">Name</label>
            <input
              value={name}
              onChange={e => setName(e.target.value)}
              placeholder="Organization name"
              className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 focus:border-indigo-500 outline-none"
            />
          </div>
          <div>
            <label className="block text-sm text-gray-400 mb-1">Plan</label>
            <select value={plan} onChange={e => setPlan(e.target.value)}
              className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 focus:border-indigo-500 outline-none"
            >
              <option value="free">Free</option>
              <option value="pro">Pro</option>
              <option value="enterprise">Enterprise</option>
            </select>
          </div>
          {error && <p className="text-red-400 text-sm">{error}</p>}
          <div className="flex gap-3 pt-2">
            <button type="submit" disabled={loading} className="btn-primary flex-1">
              {loading ? 'Creating…' : 'Create Tenant'}
            </button>
            <button type="button" onClick={onClose} className="btn-secondary">Cancel</button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ── Auth Tab ────────────────────────────────────────────────────────────────

function AuthTab() {
  const [users, setUsers] = useState<import('./api').User[]>([]);
  const [apiKeys, setApiKeys] = useState<import('./api').APIKey[]>([]);
  const [roles, setRoles] = useState<import('./api').Role[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [section, setSection] = useState<'users' | 'keys' | 'roles'>('users');
  const [showCreateUser, setShowCreateUser] = useState(false);
  const [showCreateKey, setShowCreateKey] = useState(false);
  const [newKeyDisplay, setNewKeyDisplay] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    setLoading(true); setError('');
    try {
      const [u, k, r] = await Promise.all([
        listUsers().catch(() => []),
        listAPIKeys().catch(() => []),
        listRoles().catch(() => []),
      ]);
      setUsers(u); setApiKeys(k); setRoles(r);
    } catch (e) { setError(String(e)); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const handleDeleteUser = async (id: string) => {
    if (!confirm('Delete this user?')) return;
    try { await deleteUser(id); await loadData(); }
    catch (e) { setError(String(e)); }
  };

  const handleDeleteKey = async (id: string) => {
    try { await deleteAPIKey(id); await loadData(); }
    catch (e) { setError(String(e)); }
  };

  const handleCreateUser = async (username: string, password: string, role: string) => {
    try {
      await createUser({ username, password, role: role || undefined });
      setShowCreateUser(false);
      await loadData();
    } catch (e) { setError(String(e)); }
  };

  const handleCreateKey = async (name: string, scopes: string) => {
    try {
      const result = await createAPIKey({
        name,
        scopes: scopes ? scopes.split(',').map(s => s.trim()).filter(Boolean) : undefined,
      });
      setShowCreateKey(false);
      setNewKeyDisplay(result.key);
      await loadData();
    } catch (e) { setError(String(e)); }
  };

  if (loading) return <LoadingSpinner msg="Loading auth…" />;

  const sections = [
    { key: 'users' as const, label: `Users (${users.length})` },
    { key: 'keys' as const, label: `API Keys (${apiKeys.length})` },
    { key: 'roles' as const, label: `Roles (${roles.length})` },
  ];

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-medium">Auth & Access</h2>
      {error && <p className="text-red-400 text-sm">{error}</p>}

      {/* Section tabs */}
      <div className="flex gap-1 border-b border-gray-800">
        {sections.map(s => (
          <button
            key={s.key}
            onClick={() => setSection(s.key)}
            className={`px-4 py-2 text-sm border-b-2 transition-colors ${
              section === s.key
                ? 'border-indigo-500 text-indigo-400'
                : 'border-transparent text-gray-500 hover:text-gray-300'
            }`}
          >
            {s.label}
          </button>
        ))}
        {section === 'users' && (
          <button onClick={() => setShowCreateUser(true)} className="ml-auto btn-primary text-sm">
            + New User
          </button>
        )}
        {section === 'keys' && (
          <button onClick={() => setShowCreateKey(true)} className="ml-auto btn-primary text-sm">
            + New Key
          </button>
        )}
      </div>

      {/* Users */}
      {section === 'users' && (
        <div className="card overflow-hidden">
          {users.length === 0 ? (
            <p className="p-4 text-gray-500 text-sm text-center">No users</p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-800 text-left text-gray-500 text-xs">
                  <th className="px-4 py-2 font-medium">Username</th>
                  <th className="px-4 py-2 font-medium">Role</th>
                  <th className="px-4 py-2 font-medium">Status</th>
                  <th className="px-4 py-2 font-medium">Last Login</th>
                  <th className="px-4 py-2 font-medium"></th>
                </tr>
              </thead>
              <tbody>
                {users.map(u => (
                  <tr key={u.id} className="border-b border-gray-800/50 hover:bg-gray-800/30">
                    <td className="px-4 py-3 font-mono text-indigo-300">{u.username}</td>
                    <td className="px-4 py-3"><span className="badge badge-pending">{u.role}</span></td>
                    <td className="px-4 py-3">
                      <span className={`badge ${u.active ? 'badge-completed' : 'badge-failed'}`}>
                        {u.active ? 'active' : 'locked'}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-gray-500 text-xs">{u.last_login ? timeAgo(u.last_login) : 'never'}</td>
                    <td className="px-4 py-3">
                      <button onClick={() => handleDeleteUser(u.id)} className="text-xs text-red-400 hover:text-red-300">Delete</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* API Keys */}
      {section === 'keys' && (
        <div className="card overflow-hidden">
          {apiKeys.length === 0 ? (
            <p className="p-4 text-gray-500 text-sm text-center">No API keys</p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-800 text-left text-gray-500 text-xs">
                  <th className="px-4 py-2 font-medium">Name</th>
                  <th className="px-4 py-2 font-medium">Client ID</th>
                  <th className="px-4 py-2 font-medium">Scopes</th>
                  <th className="px-4 py-2 font-medium">Last Used</th>
                  <th className="px-4 py-2 font-medium"></th>
                </tr>
              </thead>
              <tbody>
                {apiKeys.map(k => (
                  <tr key={k.id} className="border-b border-gray-800/50 hover:bg-gray-800/30">
                    <td className="px-4 py-3 text-indigo-300">{k.name}</td>
                    <td className="px-4 py-3 font-mono text-xs text-gray-400">{k.client_id}</td>
                    <td className="px-4 py-3">
                      <div className="flex flex-wrap gap-1">
                        {k.scopes?.map(s => (
                          <span key={s} className="badge badge-pending text-xs">{s}</span>
                        ))}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-gray-500 text-xs">{k.last_used ? timeAgo(k.last_used) : 'never'}</td>
                    <td className="px-4 py-3">
                      <button onClick={() => handleDeleteKey(k.id)} className="text-xs text-red-400 hover:text-red-300">Delete</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* New Key Display */}
      {newKeyDisplay && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="card p-6 w-full max-w-md">
            <h3 className="text-lg font-semibold mb-2">API Key Created</h3>
            <p className="text-sm text-yellow-400 mb-3">⚠️ Copy this key now. It won't be shown again.</p>
            <div className="bg-black/50 border border-gray-700 rounded p-3 font-mono text-xs text-green-400 break-all">
              {newKeyDisplay}
            </div>
            <button
              onClick={() => setNewKeyDisplay(null)}
              className="btn-primary w-full mt-4"
            >
              Done
            </button>
          </div>
        </div>
      )}

      {/* Roles */}
      {section === 'roles' && (
        <div className="space-y-2">
          {roles.length === 0 ? (
            <p className="text-gray-500 text-sm text-center py-8">No roles defined</p>
          ) : roles.map(r => (
            <div key={r.name} className="card p-4">
              <div className="flex items-center gap-2 mb-2">
                <span className="font-medium text-indigo-300">{r.name}</span>
              </div>
              {r.description && <p className="text-xs text-gray-400 mb-2">{r.description}</p>}
              <div className="flex flex-wrap gap-1">
                {r.permissions?.map(p => (
                  <span key={p} className="badge badge-pending text-xs">{p}</span>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Create User Modal */}
      {showCreateUser && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="card p-6 w-full max-w-md">
            <h2 className="text-xl font-semibold mb-4">Create User</h2>
            <CreateUserForm
              onSubmit={handleCreateUser}
              onCancel={() => setShowCreateUser(false)}
            />
          </div>
        </div>
      )}

      {/* Create API Key Modal */}
      {showCreateKey && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="card p-6 w-full max-w-md">
            <h2 className="text-xl font-semibold mb-4">Create API Key</h2>
            <CreateAPIKeyForm
              onSubmit={handleCreateKey}
              onCancel={() => setShowCreateKey(false)}
            />
          </div>
        </div>
      )}
    </div>
  );
}

function CreateUserForm({
  onSubmit,
  onCancel,
}: {
  onSubmit: (username: string, password: string, role: string) => Promise<void>;
  onCancel: () => void;
}) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [role, setRole] = useState('viewer');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!username.trim() || !password) { setError('Username and password required'); return; }
    setLoading(true); setError('');
    try { await onSubmit(username.trim(), password, role); }
    catch (err) { setError(String(err)); }
    finally { setLoading(false); }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <label className="block text-sm text-gray-400 mb-1">Username</label>
        <input value={username} onChange={e => setUsername(e.target.value)}
          className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 focus:border-indigo-500 outline-none" />
      </div>
      <div>
        <label className="block text-sm text-gray-400 mb-1">Password</label>
        <input type="password" value={password} onChange={e => setPassword(e.target.value)}
          className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 focus:border-indigo-500 outline-none" />
      </div>
      <div>
        <label className="block text-sm text-gray-400 mb-1">Role</label>
        <select value={role} onChange={e => setRole(e.target.value)}
          className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 focus:border-indigo-500 outline-none"
        >
          <option value="admin">Admin</option>
          <option value="operator">Operator</option>
          <option value="viewer">Viewer</option>
        </select>
      </div>
      {error && <p className="text-red-400 text-sm">{error}</p>}
      <div className="flex gap-3 pt-2">
        <button type="submit" disabled={loading} className="btn-primary flex-1">
          {loading ? 'Creating…' : 'Create User'}
        </button>
        <button type="button" onClick={onCancel} className="btn-secondary">Cancel</button>
      </div>
    </form>
  );
}

function CreateAPIKeyForm({
  onSubmit,
  onCancel,
}: {
  onSubmit: (name: string, scopes: string) => Promise<void>;
  onCancel: () => void;
}) {
  const [name, setName] = useState('');
  const [scopes, setScopes] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) { setError('Name is required'); return; }
    setLoading(true); setError('');
    try { await onSubmit(name.trim(), scopes); }
    catch (err) { setError(String(err)); }
    finally { setLoading(false); }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <label className="block text-sm text-gray-400 mb-1">Key Name</label>
        <input value={name} onChange={e => setName(e.target.value)}
          placeholder="e.g. ci-pipeline"
          className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 focus:border-indigo-500 outline-none" />
      </div>
      <div>
        <label className="block text-sm text-gray-400 mb-1">Scopes (comma-separated)</label>
        <input value={scopes} onChange={e => setScopes(e.target.value)}
          placeholder="jobs.read, jobs.write"
          className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 focus:border-indigo-500 outline-none" />
      </div>
      {error && <p className="text-red-400 text-sm">{error}</p>}
      <div className="flex gap-3 pt-2">
        <button type="submit" disabled={loading} className="btn-primary flex-1">
          {loading ? 'Creating…' : 'Create Key'}
        </button>
        <button type="button" onClick={onCancel} className="btn-secondary">Cancel</button>
      </div>
    </form>
  );
}

// ── Main App ──────────────────────────────────────────────────────────────────

export default function App() {
  const [tab, setTab] = useState<Tab>('jobs');
  const [jobs, setJobs] = useState<Job[]>([]);
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [selectedJob, setSelectedJob] = useState<Job | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [jobFilter, setJobFilter] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [gatewayHealth, setGatewayHealth] = useState<{ status: string; version: string } | null>(null);
  const [gatewayStats, setGatewayStats] = useState<Record<string, unknown> | null>(null);
  const [timeseries, setTimeseries] = useState<StatsBucket[]>([]);

  const loadJobs = useCallback(async () => {
    try {
      const list = await listJobs({ limit: 100 });
      setJobs(list); setError('');
    } catch (e) { setError(String(e)); }
  }, []);

  const loadStats = useCallback(async () => {
    try { setGatewayStats(await getStats()); } catch { /* optional */ }
    try { setTimeseries(await getStatsTimeseries(24)); } catch { /* optional */ }
  }, []);

  const loadProfiles = useCallback(async () => {
    try { setProfiles(await listProfiles()); } catch { /* optional */ }
  }, []);

  // ── SSE: coordinator events → refresh job list + stats ──
  useEffect(() => {
    if (!gatewayHealth) return;
    const unsub = subscribeCoordinatorEvents((event) => {
      const et = event.event_type || event.type;
      if (et === 'job_created') { loadJobs(); loadStats(); return; }
      if (et === 'job_status_changed' || et === 'job_completed' || et === 'job_failed') {
        const jobId = (event.job_id || event.jobId) as string;
        if (!jobId) return;
        getJob(jobId).then(updated => {
          setJobs(prev => prev.map(j => j.id === updated.id ? updated : j));
          if (selectedJob?.id === updated.id) setSelectedJob(updated);
        }).catch(() => {});
        loadStats();
      }
    }, { onDisconnect: () => {} });
    return unsub;
  }, [gatewayHealth, loadJobs, loadStats, selectedJob?.id]);

  useEffect(() => {
    const init = async () => {
      setLoading(true);
      const health = await healthCheck().catch(() => null);
      setGatewayHealth(health);
      await Promise.all([loadJobs(), loadProfiles(), loadStats()]);
      setLoading(false);
    };
    init();
  }, [loadJobs, loadProfiles, loadStats]);

  const handleJobCreated = (job: Job) => setJobs(prev => [job, ...prev]);
  const handleJobRefresh = (updated: Job) => {
    setJobs(prev => prev.map(j => j.id === updated.id ? updated : j));
    if (selectedJob?.id === updated.id) setSelectedJob(updated);
  };

  const tabs: { key: Tab; label: string }[] = [
    { key: 'jobs', label: 'Jobs' },
    { key: 'knowledge', label: 'Knowledge' },
    { key: 'governance', label: 'Governance' },
    { key: 'tenants', label: 'Tenants' },
    { key: 'auth', label: 'Auth' },
    { key: 'compare', label: 'Compare' },
    { key: 'plugins', label: 'Plugins' },
    { key: 'audit', label: 'Audit' },
    { key: 'config', label: 'Config' },
  ];

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center text-gray-500">
        <span>Loading Curriculum-Forge…</span>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex flex-col">
      {/* Header */}
      <header className="border-b border-gray-800 px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-xl font-bold text-indigo-400">⚡ Curriculum-Forge</h1>
          {gatewayHealth && (
            <span className="badge badge-completed text-xs">v{gatewayHealth.version}</span>
          )}
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs text-gray-500">Gateway :8765</span>
          <button onClick={() => { setTab('jobs'); setShowCreate(true); }} className="btn-primary text-sm">
            + New Job
          </button>
        </div>
      </header>

      {/* Tab bar */}
      <div className="flex gap-1 px-6 pt-4 border-b border-gray-800">
        {tabs.map(t => (
          <button
            key={t.key}
            onClick={() => { setTab(t.key); setSelectedJob(null); }}
            className={`px-4 py-2 text-sm border-b-2 transition-colors ${
              tab === t.key
                ? 'border-indigo-500 text-indigo-400'
                : 'border-transparent text-gray-500 hover:text-gray-300'
            }`}
          >
            {t.label}
            {t.key === 'jobs' && jobs.filter(j => j.status === 'running').length > 0 && (
              <span className="ml-2 bg-blue-600 text-white text-xs rounded-full px-1.5 py-0.5">
                {jobs.filter(j => j.status === 'running').length}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Error banner */}
      {error && (
        <div className="mx-6 mt-4 px-4 py-2 bg-red-900/30 border border-red-800 rounded text-red-300 text-sm">
          {error}
          <button onClick={() => setError('')} className="ml-3 underline">Dismiss</button>
        </div>
      )}

      {/* Content */}
      <main className="flex-1 p-6 max-w-5xl mx-auto w-full">
        {tab === 'jobs' && (
          selectedJob ? (
            <JobDetail job={selectedJob} onBack={() => setSelectedJob(null)} onRefresh={handleJobRefresh} />
          ) : (
            <>
              <StatsCard stats={gatewayStats} timeseries={timeseries} loading={loading} />
              <JobsList
                jobs={jobs}
                onSelect={setSelectedJob}
                onRefresh={loadJobs}
                filter={jobFilter}
                setFilter={setJobFilter}
              />
            </>
          )
        )}
        {tab === 'plugins' && <PluginsTab />}
        {tab === 'audit' && <AuditTab />}
        {tab === 'config' && <ConfigTab />}
        {tab === 'compare' && <CompareTab />}
        {tab === 'knowledge' && <KnowledgeTab />}
        {tab === 'governance' && <GovernanceTab />}
        {tab === 'tenants' && <TenantsTab />}
        {tab === 'auth' && <AuthTab />}
      </main>

      {/* Create modal */}
      {showCreate && (
        <CreateJobModal
          profiles={profiles}
          onClose={() => setShowCreate(false)}
          onCreated={handleJobCreated}
        />
      )}
    </div>
  );
}
