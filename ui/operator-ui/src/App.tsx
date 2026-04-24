import { useState, useEffect, useCallback, useRef } from 'react';
import {
  listJobs, getJob, createJob, resumeJob, abortJob,
  listProfiles, healthCheck, subscribeJob, subscribeCoordinatorEvents,
  listPlugins, enablePlugin, disablePlugin, updatePluginConfig,
  getAuditLogs, getAuditStats,
  type Job, type Profile,
} from './api';

// ── Types ─────────────────────────────────────────────────────────────────────

type Tab = 'jobs' | 'plugins' | 'audit' | 'config';

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
        <div className="card p-4">
          {job.metrics && Object.keys(job.metrics).length > 0 ? (
            <pre className="text-xs text-gray-300 overflow-x-auto">
              {JSON.stringify(job.metrics, null, 2)}
            </pre>
          ) : (
            <p className="text-gray-500 text-sm">No metrics recorded yet.</p>
          )}
        </div>
      )}
    </div>
  );
}

// ── Jobs List ─────────────────────────────────────────────────────────────────

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

  const loadJobs = useCallback(async () => {
    try {
      const list = await listJobs({ limit: 100 });
      setJobs(list); setError('');
    } catch (e) { setError(String(e)); }
  }, []);

  const loadProfiles = useCallback(async () => {
    try { setProfiles(await listProfiles()); } catch { /* optional */ }
  }, []);

  // ── SSE: coordinator events → refresh job list ──
  useEffect(() => {
    if (!gatewayHealth) return;
    const unsub = subscribeCoordinatorEvents((event) => {
      const et = event.event_type || event.type;
      if (et === 'job_created') { loadJobs(); return; }
      if (et === 'job_status_changed' || et === 'job_completed' || et === 'job_failed') {
        const jobId = (event.job_id || event.jobId) as string;
        if (!jobId) return;
        getJob(jobId).then(updated => {
          setJobs(prev => prev.map(j => j.id === updated.id ? updated : j));
          if (selectedJob?.id === updated.id) setSelectedJob(updated);
        }).catch(() => {});
      }
    }, { onDisconnect: () => {} });
    return unsub;
  }, [gatewayHealth, loadJobs, selectedJob?.id]);

  useEffect(() => {
    const init = async () => {
      setLoading(true);
      const health = await healthCheck().catch(() => null);
      setGatewayHealth(health);
      await Promise.all([loadJobs(), loadProfiles()]);
      setLoading(false);
    };
    init();
  }, [loadJobs, loadProfiles]);

  const handleJobCreated = (job: Job) => setJobs(prev => [job, ...prev]);
  const handleJobRefresh = (updated: Job) => {
    setJobs(prev => prev.map(j => j.id === updated.id ? updated : j));
    if (selectedJob?.id === updated.id) setSelectedJob(updated);
  };

  const tabs: { key: Tab; label: string }[] = [
    { key: 'jobs', label: 'Jobs' },
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
            <JobsList
              jobs={jobs}
              onSelect={setSelectedJob}
              onRefresh={loadJobs}
              filter={jobFilter}
              setFilter={setJobFilter}
            />
          )
        )}
        {tab === 'plugins' && <PluginsTab />}
        {tab === 'audit' && <AuditTab />}
        {tab === 'config' && <ConfigTab />}
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
