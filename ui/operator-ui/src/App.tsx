import { useState, useEffect, useCallback } from 'react';
import {
  listJobs, getJob, createJob, resumeJob, abortJob,
  listProfiles, healthCheck, subscribeJob, subscribeCoordinatorEvents,
  type Job, type Profile,
} from './api';

// ── Helpers ──────────────────────────────────────────────────────────────────

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
    setLoading(true);
    setError('');
    try {
      const job = await createJob({ profile, description });
      onCreated(job);
      onClose();
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
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
              {profiles.map(p => (
                <option key={p.name} value={p.name}>{p.name}</option>
              ))}
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
              {loading ? 'Creating...' : 'Create Job'}
            </button>
            <button type="button" onClick={onClose} className="btn-secondary">Cancel</button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ── Job Detail Panel ─────────────────────────────────────────────────────────

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

  useEffect(() => {
    const unsub = subscribeJob(job.id, (event) => {
      if (event.job) setJob(event.job as Job);
      else if (event.event === 'done' || event.event === 'error') {
        // Refresh full job
        getJob(job.id).then(setJob).catch(() => {});
      }
    });
    return unsub;
  }, [job.id]);

  const handleResume = async () => {
    setLoading(true); setError('');
    try {
      const updated = await resumeJob(job.id);
      setJob(updated);
      onRefresh(updated);
    } catch (e) { setError(String(e)); }
    finally { setLoading(false); }
  };

  const handleAbort = async () => {
    setLoading(true); setError('');
    try {
      const updated = await abortJob(job.id);
      setJob(updated);
      onRefresh(updated);
    } catch (e) { setError(String(e)); }
    finally { setLoading(false); }
  };

  const phases = Object.entries(job.phases || {});

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
          {job.current_phase && (
            <span className="text-xs text-gray-500">Phase: {job.current_phase}</span>
          )}
        </div>
      </div>

      {error && <p className="text-red-400 text-sm">{error}</p>}

      {/* Actions */}
      {job.status !== 'running' && (
        <div className="flex gap-3">
          <button
            onClick={handleResume}
            disabled={loading || job.status === 'completed'}
            className="btn-primary"
          >
            {loading ? '...' : '▶ Resume'}
          </button>
          {job.status !== 'completed' && job.status !== 'failed' && (
            <button
              onClick={handleAbort}
              disabled={loading}
              className="btn-secondary"
            >
              ⬛ Abort
            </button>
          )}
        </div>
      )}

      {/* Phases */}
      <div className="card overflow-hidden">
        <div className="px-4 py-3 border-b border-gray-800 font-medium text-sm text-gray-300">
          Phases
        </div>
        {phases.length === 0 ? (
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
              {phases.map(([name, info]) => (
                <tr key={name} className="border-b border-gray-800/50 hover:bg-gray-800/30">
                  <td className="px-4 py-3 font-mono text-indigo-300">{name}</td>
                  <td className="px-4 py-3"><PhaseStatusBadge phase={info.status} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Metrics */}
      {job.metrics && Object.keys(job.metrics).length > 0 && (
        <div className="card p-4">
          <h3 className="text-sm font-medium text-gray-300 mb-2">Metrics</h3>
          <pre className="text-xs text-gray-400 overflow-x-auto">
            {JSON.stringify(job.metrics, null, 2)}
          </pre>
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
        <h2 className="text-lg font-medium">Jobs ({filtered.length})</h2>
        <button onClick={onRefresh} className="text-sm text-gray-400 hover:text-white">
          ↻ Refresh
        </button>
      </div>
      <input
        value={filter}
        onChange={e => setFilter(e.target.value)}
        placeholder="Search jobs..."
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
              {job.description && (
                <p className="text-xs text-gray-400 mt-1 truncate">{job.description}</p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Main App ──────────────────────────────────────────────────────────────────

export default function App() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [selectedJob, setSelectedJob] = useState<Job | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [filter, setFilter] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [gatewayHealth, setGatewayHealth] = useState<{ status: string; version: string } | null>(null);

  const loadJobs = useCallback(async () => {
    try {
      const list = await listJobs({ limit: 100 });
      setJobs(list);
      setError('');
    } catch (e) {
      setError(String(e));
    }
  }, []);

  const loadProfiles = useCallback(async () => {
    try {
      const list = await listProfiles();
      setProfiles(list);
    } catch { /* profiles optional */ }
  }, []);

  // ── SSE: subscribe to coordinator events for real-time job updates ──
  useEffect(() => {
    if (!gatewayHealth) return; // wait until gateway is confirmed up
    const unsub = subscribeCoordinatorEvents(
      (event) => {
        const et = event.event_type || event.type;
        if (et === 'job_created') {
          // Optimistically refresh the full list so new jobs appear immediately
          loadJobs();
        } else if (et === 'job_status_changed' || et === 'job_completed' || et === 'job_failed') {
          const jobId = (event.job_id || event.jobId) as string;
          if (!jobId) return;
          // Refresh just this job
          getJob(jobId).then((updated) => {
            setJobs(prev => prev.map(j => j.id === updated.id ? updated : j));
            if (selectedJob?.id === updated.id) setSelectedJob(updated);
          }).catch(() => {});
        }
      },
      { onDisconnect: () => {/* silently reconnect */ } },
    );
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

  const handleJobCreated = (job: Job) => {
    setJobs(prev => [job, ...prev]);
  };

  const handleJobRefresh = (updated: Job) => {
    setJobs(prev => prev.map(j => j.id === updated.id ? updated : j));
    if (selectedJob?.id === updated.id) setSelectedJob(updated);
  };

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
            <span className="badge badge-completed text-xs">
              v{gatewayHealth.version}
            </span>
          )}
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => setShowCreate(true)}
            className="btn-primary text-sm"
          >
            + New Job
          </button>
          <span className="text-xs text-gray-500">Gateway :8765</span>
        </div>
      </header>

      {/* Error banner */}
      {error && (
        <div className="mx-6 mt-4 px-4 py-2 bg-red-900/30 border border-red-800 rounded text-red-300 text-sm">
          {error}
        </div>
      )}

      {/* Content */}
      <main className="flex-1 p-6 max-w-4xl mx-auto w-full">
        {selectedJob ? (
          <JobDetail
            job={selectedJob}
            onBack={() => setSelectedJob(null)}
            onRefresh={handleJobRefresh}
          />
        ) : (
          <JobsList
            jobs={jobs}
            onSelect={setSelectedJob}
            onRefresh={loadJobs}
            filter={filter}
            setFilter={setFilter}
          />
        )}
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
