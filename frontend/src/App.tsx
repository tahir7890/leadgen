import { BrowserRouter, NavLink, Route, Routes, useNavigate } from 'react-router-dom';
import {
  Building2, LayoutDashboard, Play, Users, Zap,
  RefreshCw, Plus, Trash2, ChevronRight, Download,
  AlertTriangle, CheckCircle2, Clock, BarChart3, Mail, Linkedin
} from 'lucide-react';
import { useCallback, useEffect, useRef, useState, FormEvent } from 'react';
import { api } from './api';
import type { Company, DashboardStats, Job, Lead } from './types';

// ─────────────────────────────────────────────
// Shared Components
// ─────────────────────────────────────────────

function Badge({ status }: { status: string | null | undefined }) {
  const s = (status ?? 'pending').toLowerCase().replace(/\s+/g, '_');
  return (
    <span className={`badge badge-${s}`}>
      {s.replace(/_/g, ' ')}
    </span>
  );
}

function Spinner({ size = '' }: { size?: string }) {
  return <div className={`spinner ${size}`} />;
}

function Alert({ type, message, onClose }: {
  type: 'error' | 'success' | 'warning';
  message: string;
  onClose?: () => void;
}) {
  return (
    <div className={`alert alert-${type} fade-in`}>
      {type === 'error' && <AlertTriangle size={15} style={{ flexShrink: 0 }} />}
      {type === 'success' && <CheckCircle2 size={15} style={{ flexShrink: 0 }} />}
      {type === 'warning' && <AlertTriangle size={15} style={{ flexShrink: 0 }} />}
      <span style={{ flex: 1 }}>{message}</span>
      {onClose && (
        <button onClick={onClose} style={{ background: 'none', border: 'none', color: 'inherit', cursor: 'pointer', opacity: 0.6 }}>✕</button>
      )}
    </div>
  );
}

function SkeletonRows({ count = 5 }: { count?: number }) {
  return (
    <>
      {Array.from({ length: count }).map((_, i) => (
        <tr key={i}>
          <td colSpan={10}>
            <div className="skeleton skeleton-row" style={{ margin: '4px 12px' }} />
          </td>
        </tr>
      ))}
    </>
  );
}

function EmptyState({ icon, title, desc }: { icon: string; title: string; desc: string }) {
  return (
    <div className="empty-state">
      <div className="empty-state-icon">{icon}</div>
      <div className="empty-state-title">{title}</div>
      <div className="empty-state-desc">{desc}</div>
    </div>
  );
}

function ProgressBar({ value, total }: { value: number; total: number }) {
  const pct = total > 0 ? Math.round((value / total) * 100) : 0;
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
      <div className="progress-bar" style={{ flex: 1 }}>
        <div className="progress-fill" style={{ width: `${pct}%` }} />
      </div>
      <span style={{ fontSize: 12, color: 'var(--text-muted)', minWidth: 36 }}>{pct}%</span>
    </div>
  );
}

// ─────────────────────────────────────────────
// Dashboard Page
// ─────────────────────────────────────────────

function Dashboard() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [runLoading, setRunLoading] = useState(false);
  const [err, setErr] = useState('');
  const [success, setSuccess] = useState('');
  const navigate = useNavigate();

  const load = useCallback(async () => {
    try {
      const s = await api.stats();
      setStats(s);
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Failed to load stats');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const runBatch = async () => {
    setRunLoading(true);
    setErr('');
    setSuccess('');
    try {
      const job = await api.runJob();
      setSuccess(`Batch job started! Job ID: ${job.id.slice(0, 8)}...`);
      setTimeout(() => navigate('/jobs'), 1500);
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Failed to start job');
    } finally {
      setRunLoading(false);
    }
  };

  const statItems = [
    { label: 'Total Companies', value: stats?.total_companies, icon: <Building2 size={28} /> },
    { label: 'Processed', value: stats?.processed_companies, icon: <CheckCircle2 size={28} /> },
    { label: 'Pending', value: stats?.pending_companies, icon: <Clock size={28} /> },
    { label: 'Total Leads', value: stats?.total_leads, icon: <Users size={28} /> },
    { label: 'With Email', value: stats?.leads_with_email, icon: <Mail size={28} /> },
    { label: 'With LinkedIn', value: stats?.leads_with_linkedin, icon: <Linkedin size={28} /> },
  ];

  return (
    <div className="fade-in">
      <div className="page-header">
        <div>
          <h1 className="page-title">Dashboard</h1>
          <p className="page-subtitle">Lead generation overview and controls</p>
        </div>
        <div style={{ display: 'flex', gap: 10 }}>
          <button onClick={load} className="btn btn-secondary btn-sm">
            <RefreshCw size={14} /> Refresh
          </button>
          <button onClick={runBatch} disabled={runLoading} className="btn btn-primary">
            {runLoading ? <Spinner size="spinner-sm" /> : <Play size={15} />}
            {runLoading ? 'Starting...' : 'Run Batch'}
          </button>
        </div>
      </div>

      {err && <Alert type="error" message={err} onClose={() => setErr('')} />}
      {success && <Alert type="success" message={success} onClose={() => setSuccess('')} />}

      {/* Stats last job */}
      {stats?.last_job_status && (
        <div style={{ marginBottom: 20, display: 'flex', alignItems: 'center', gap: 8, fontSize: 13.5, color: 'var(--text-secondary)' }}>
          Last job: <Badge status={stats.last_job_status} />
          <button onClick={() => navigate('/jobs')} className="btn btn-ghost btn-sm" style={{ gap: 4 }}>
            View jobs <ChevronRight size={12} />
          </button>
        </div>
      )}

      <div className="stat-grid">
        {statItems.map(({ label, value, icon }) => (
          <div key={label} className="stat-card">
            <div className="stat-icon">{icon}</div>
            <div className="stat-label">{label}</div>
            <div className="stat-value">
              {loading ? (
                <div className="skeleton" style={{ height: 36, width: 60 }} />
              ) : (
                (value ?? 0).toLocaleString()
              )}
            </div>
          </div>
        ))}
      </div>

      {/* Quick add company */}
      <div className="table-container" style={{ padding: 24 }}>
        <h2 style={{ fontSize: 16, fontWeight: 600, marginBottom: 16, color: 'var(--text-primary)' }}>
          Quick Add Company
        </h2>
        <QuickAddForm onAdded={load} />
      </div>
    </div>
  );
}

function QuickAddForm({ onAdded }: { onAdded?: () => void }) {
  const [domain, setDomain] = useState('');
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState('');
  const [success, setSuccess] = useState('');

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!domain.trim()) return;
    setLoading(true);
    setErr('');
    setSuccess('');
    try {
      const d = domain.trim();
      await api.addCompany(d);
      setSuccess(`✓ Added ${d}`);
      setDomain('');
      onAdded?.();
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Error';
      setErr(msg.includes('already exists') ? `Domain already added` : msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      {err && <Alert type="error" message={err} onClose={() => setErr('')} />}
      {success && <Alert type="success" message={success} onClose={() => setSuccess('')} />}
      <form onSubmit={submit} className="input-group">
        <input
          value={domain}
          onChange={(e) => setDomain(e.target.value)}
          placeholder="example.com"
          className="input"
          style={{ maxWidth: 360 }}
        />
        <button type="submit" disabled={loading || !domain.trim()} className="btn btn-primary">
          {loading ? <Spinner size="spinner-sm" /> : <Plus size={15} />}
          Add Company
        </button>
      </form>
    </div>
  );
}

// ─────────────────────────────────────────────
// Companies Page
// ─────────────────────────────────────────────

function CompaniesPage() {
  const [list, setList] = useState<Company[]>([]);
  const [loading, setLoading] = useState(true);
  const [domain, setDomain] = useState('');
  const [bulkText, setBulkText] = useState('');
  const [bulkMode, setBulkMode] = useState(false);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [err, setErr] = useState('');
  const [success, setSuccess] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setList(await api.companies());
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Failed to load companies');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const addSingle = async (e: FormEvent) => {
    e.preventDefault();
    if (!domain.trim()) return;
    setActionLoading('add');
    setErr('');
    try {
      await api.addCompany(domain.trim());
      setDomain('');
      setSuccess(`Added ${domain.trim()}`);
      await load();
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Error';
      setErr(msg.includes('409') || msg.includes('already') ? 'Domain already exists' : msg);
    } finally {
      setActionLoading(null);
    }
  };

  const addBulk = async (e: FormEvent) => {
    e.preventDefault();
    const domains = bulkText.split(/[\n,;]+/).map((d) => d.trim()).filter(Boolean);
    if (!domains.length) return;
    setActionLoading('bulk');
    setErr('');
    try {
      const added = await api.bulkCompanies(domains);
      setSuccess(`Added ${added.length} of ${domains.length} domains`);
      setBulkText('');
      setBulkMode(false);
      await load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Error');
    } finally {
      setActionLoading(null);
    }
  };

  const process = async (id: string, domain: string) => {
    setActionLoading(`process-${id}`);
    try {
      const r = await api.processCompany(id);
      setSuccess(`Processing ${domain} — Job: ${r.job_id.slice(0, 8)}...`);
      await load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Error');
    } finally {
      setActionLoading(null);
    }
  };

  const reset = async (id: string, domain: string) => {
    setActionLoading(`reset-${id}`);
    try {
      await api.resetCompany(id);
      setSuccess(`Reset ${domain} to pending`);
      await load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Error');
    } finally {
      setActionLoading(null);
    }
  };

  const del = async (id: string, domain: string) => {
    if (!confirm(`Delete ${domain} and all its leads?`)) return;
    setActionLoading(`del-${id}`);
    try {
      await api.deleteCompany(id);
      setSuccess(`Deleted ${domain}`);
      await load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Error');
    } finally {
      setActionLoading(null);
    }
  };

  return (
    <div className="fade-in">
      <div className="page-header">
        <div>
          <h1 className="page-title">Companies</h1>
          <p className="page-subtitle">{list.length} companies · click Process to generate leads</p>
        </div>
        <div style={{ display: 'flex', gap: 10 }}>
          <button onClick={() => setBulkMode((b) => !b)} className="btn btn-secondary btn-sm">
            {bulkMode ? 'Single Mode' : 'Bulk Import'}
          </button>
          <button onClick={load} className="btn btn-secondary btn-sm">
            <RefreshCw size={13} />
          </button>
        </div>
      </div>

      {err && <Alert type="error" message={err} onClose={() => setErr('')} />}
      {success && <Alert type="success" message={success} onClose={() => setSuccess('')} />}

      {/* Add form */}
      <div className="table-container" style={{ padding: 20, marginBottom: 20 }}>
        {bulkMode ? (
          <form onSubmit={addBulk}>
            <div style={{ marginBottom: 10, fontSize: 13.5, color: 'var(--text-secondary)' }}>
              Paste domains (one per line, or comma-separated):
            </div>
            <textarea
              value={bulkText}
              onChange={(e) => setBulkText(e.target.value)}
              placeholder="example.com&#10;acme.io&#10;stripe.com"
              className="input textarea"
              style={{ marginBottom: 10 }}
            />
            <button
              type="submit"
              disabled={actionLoading === 'bulk' || !bulkText.trim()}
              className="btn btn-primary"
            >
              {actionLoading === 'bulk' ? <Spinner size="spinner-sm" /> : <Plus size={15} />}
              Import Domains
            </button>
          </form>
        ) : (
          <form onSubmit={addSingle} className="input-group">
            <input
              value={domain}
              onChange={(e) => setDomain(e.target.value)}
              placeholder="example.com"
              className="input"
              style={{ maxWidth: 360 }}
            />
            <button
              type="submit"
              disabled={actionLoading === 'add' || !domain.trim()}
              className="btn btn-primary"
            >
              {actionLoading === 'add' ? <Spinner size="spinner-sm" /> : <Plus size={15} />}
              Add Company
            </button>
          </form>
        )}
      </div>

      {/* Table */}
      <div className="table-container">
        <table className="data-table">
          <thead>
            <tr>
              <th>Domain</th>
              <th>Status</th>
              <th>Leads Found</th>
              <th>Processed At</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <SkeletonRows count={8} />
            ) : list.length === 0 ? (
              <tr>
                <td colSpan={5}>
                  <EmptyState icon="🏢" title="No companies yet" desc="Add a domain above to get started" />
                </td>
              </tr>
            ) : (
              list.map((c) => (
                <tr key={c.id} className="fade-in">
                  <td className="td-primary td-mono">{c.domain}</td>
                  <td><Badge status={c.status} /></td>
                  <td style={{ fontVariantNumeric: 'tabular-nums' }}>{c.leads_found ?? 0}</td>
                  <td style={{ fontSize: 12.5, color: 'var(--text-muted)' }}>
                    {c.processed_at ? new Date(c.processed_at).toLocaleString() : '—'}
                  </td>
                  <td>
                    <div style={{ display: 'flex', gap: 6 }}>
                      <button
                        onClick={() => process(c.id, c.domain)}
                        disabled={actionLoading === `process-${c.id}`}
                        className="btn btn-ghost btn-sm"
                        style={{ color: 'var(--accent)' }}
                      >
                        {actionLoading === `process-${c.id}` ? <Spinner size="spinner-sm" /> : <Play size={12} />}
                        Run
                      </button>
                      <button
                        onClick={() => reset(c.id, c.domain)}
                        disabled={actionLoading === `reset-${c.id}`}
                        className="btn btn-ghost btn-sm"
                      >
                        {actionLoading === `reset-${c.id}` ? <Spinner size="spinner-sm" /> : <RefreshCw size={12} />}
                        Reset
                      </button>
                      <button
                        onClick={() => del(c.id, c.domain)}
                        disabled={actionLoading === `del-${c.id}`}
                        className="btn btn-ghost btn-sm btn-danger"
                      >
                        {actionLoading === `del-${c.id}` ? <Spinner size="spinner-sm" /> : <Trash2 size={12} />}
                      </button>
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────
// Leads Page
// ─────────────────────────────────────────────

function LeadsPage() {
  const [leads, setLeads] = useState<Lead[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState('');
  const [search, setSearch] = useState('');

  useEffect(() => {
    api.leads({ limit: 1000 })
      .then(setLeads)
      .catch((e) => setErr(e instanceof Error ? e.message : 'Failed to load leads'))
      .finally(() => setLoading(false));
  }, []);

  const delLead = async (id: string, name: string) => {
    if (!confirm(`Delete lead ${name || 'Unknown'}?`)) return;
    try {
      await api.deleteLead(id);
      setLeads((prev) => prev.filter(l => l.id !== id));
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Error deleting lead');
    }
  };

  const filtered = search
    ? leads.filter((l) => {
        const q = search.toLowerCase();
        return (
          l.full_name?.toLowerCase().includes(q) ||
          l.email?.toLowerCase().includes(q) ||
          l.company_domain?.toLowerCase().includes(q) ||
          l.job_title?.toLowerCase().includes(q)
        );
      })
    : leads;

  return (
    <div className="fade-in">
      <div className="page-header">
        <div>
          <h1 className="page-title">Leads</h1>
          <p className="page-subtitle">{filtered.length.toLocaleString()} leads{search ? ' (filtered)' : ''}</p>
        </div>
        <div style={{ display: 'flex', gap: 10 }}>
          <button onClick={() => api.exportLeadsCsv()} className="btn btn-secondary btn-sm">
            <Download size={13} /> Export CSV
          </button>
        </div>
      </div>

      {err && <Alert type="error" message={err} onClose={() => setErr('')} />}

      {/* Search */}
      <div style={{ marginBottom: 16 }}>
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search by name, email, domain, title..."
          className="input"
          style={{ maxWidth: 420 }}
        />
      </div>

      <div className="table-container" style={{ overflowX: 'auto' }}>
        <table className="data-table" style={{ minWidth: 900 }}>
          <thead>
            <tr>
              <th>Name</th>
              <th>Title</th>
              <th>Company</th>
              <th>Email</th>
              <th>Phone</th>
              <th>LinkedIn</th>
              <th>Location</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <SkeletonRows count={10} />
            ) : filtered.length === 0 ? (
              <tr>
                <td colSpan={8}>
                  <EmptyState
                    icon="👥"
                    title={search ? 'No matching leads' : 'No leads yet'}
                    desc={search ? 'Try a different search term' : 'Process some companies to generate leads'}
                  />
                </td>
              </tr>
            ) : (
              filtered.map((l) => (
                <tr key={l.id}>
                  <td className="td-primary">{l.full_name || '—'}</td>
                  <td>{l.job_title || '—'}</td>
                  <td className="td-mono" style={{ fontSize: 12.5 }}>{l.company_domain || l.company_name || '—'}</td>
                  <td style={{ fontSize: 12.5 }}>
                    {l.email ? (
                      <a href={`mailto:${l.email}`} style={{ color: 'var(--accent)', textDecoration: 'none' }}>
                        {l.email}
                      </a>
                    ) : '—'}
                  </td>
                  <td style={{ fontSize: 12.5 }}>{l.phone || '—'}</td>
                  <td>
                    {l.linkedin_url ? (
                      <a href={l.linkedin_url} target="_blank" rel="noopener noreferrer" className="btn btn-ghost btn-sm" style={{ fontSize: 12 }}>
                        View ↗
                      </a>
                    ) : '—'}
                  </td>
                  <td style={{ fontSize: 12.5 }}>{l.location || '—'}</td>
                  <td>
                    <button
                      onClick={() => delLead(l.id, l.full_name || '')}
                      className="btn btn-ghost btn-sm btn-danger"
                      title="Delete lead"
                    >
                      <Trash2 size={12} />
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────
// Jobs Page
// ─────────────────────────────────────────────

function JobsPage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [sel, setSel] = useState<Job | null>(null);
  const [runLoading, setRunLoading] = useState(false);
  const [err, setErr] = useState('');
  const [success, setSuccess] = useState('');
  const logsRef = useRef<HTMLDivElement>(null);

  const load = useCallback(async () => {
    try {
      const j = await api.jobs();
      setJobs(j);
      if (sel) {
        const updated = j.find((x) => x.id === sel.id);
        if (updated) setSel(updated);
      }
    } catch (e) {
      // Silently fail polling
    }
  }, [sel?.id]);

  // Initial load
  useEffect(() => { load(); }, [load]);

  // Poll every 3 seconds
  useEffect(() => {
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
  }, [load]);

  // Auto-scroll logs to bottom
  useEffect(() => {
    if (logsRef.current) {
      logsRef.current.scrollTop = logsRef.current.scrollHeight;
    }
  }, [sel?.logs]);

  const runBatch = async () => {
    setRunLoading(true);
    setErr('');
    try {
      const job = await api.runJob();
      setSuccess(`Started job ${job.id.slice(0, 8)}...`);
      await load();
      setSel(job);
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Failed to start job');
    } finally {
      setRunLoading(false);
    }
  };

  const getLogClass = (log: string) => {
    if (log.includes('✓') || log.includes('inserted') || log.includes('complete')) return 'log-entry log-success';
    if (log.includes('✗') || log.includes('error') || log.includes('failed')) return 'log-entry log-error';
    if (log.includes('Processing') || log.includes('Batch')) return 'log-entry log-info';
    return 'log-entry';
  };

  return (
    <div className="fade-in">
      <div className="page-header">
        <div>
          <h1 className="page-title">Jobs</h1>
          <p className="page-subtitle">Lead generation job history and live logs</p>
        </div>
        <button onClick={runBatch} disabled={runLoading} className="btn btn-primary">
          {runLoading ? <Spinner size="spinner-sm" /> : <Play size={15} />}
          {runLoading ? 'Starting...' : 'Run Batch'}
        </button>
      </div>

      {err && <Alert type="error" message={err} onClose={() => setErr('')} />}
      {success && <Alert type="success" message={success} onClose={() => setSuccess('')} />}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
        {/* Job List */}
        <div>
          {jobs.length === 0 ? (
            <div className="table-container">
              <EmptyState icon="⚙️" title="No jobs yet" desc='Click "Run Batch" to start generating leads' />
            </div>
          ) : (
            jobs.map((j) => {
              const isSelected = sel?.id === j.id;
              const pct = j.total > 0 ? Math.round((j.completed / j.total) * 100) : 0;
              return (
                <div
                  key={j.id}
                  onClick={() => setSel(j)}
                  style={{
                    padding: 16,
                    marginBottom: 10,
                    borderRadius: 12,
                    border: `1px solid ${isSelected ? 'var(--accent)' : 'var(--border)'}`,
                    background: isSelected ? 'var(--accent-glow)' : 'var(--bg-card)',
                    cursor: 'pointer',
                    transition: 'all 0.15s',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
                    <Badge status={j.status} />
                    <span style={{ fontSize: 11.5, color: 'var(--text-muted)', fontFamily: 'monospace' }}>
                      {j.id.slice(0, 8)}
                    </span>
                  </div>

                  {j.total > 0 && (
                    <div style={{ marginBottom: 10 }}>
                      <ProgressBar value={j.completed} total={j.total} />
                    </div>
                  )}

                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8, fontSize: 12, color: 'var(--text-secondary)' }}>
                    <span>✓ {j.completed}/{j.total}</span>
                    <span>✗ {j.failed}</span>
                    <span>📥 {j.leads_inserted}</span>
                  </div>

                  {j.message && (
                    <div style={{ marginTop: 8, fontSize: 12, color: 'var(--text-muted)', fontStyle: 'italic' }}>
                      {j.message}
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>

        {/* Logs Panel */}
        <div>
          <div
            ref={logsRef}
            className="logs-panel"
            style={{ background: '#0d111e' }}
          >
            {sel ? (
              sel.logs.length > 0 ? (
                sel.logs.map((log, i) => (
                  <div key={i} className={getLogClass(log)}>
                    {log}
                  </div>
                ))
              ) : (
                <div style={{ color: 'var(--text-muted)', fontStyle: 'italic' }}>
                  Waiting for logs...
                </div>
              )
            ) : (
              <div style={{ color: 'var(--text-muted)', fontStyle: 'italic' }}>
                ← Select a job to view logs
              </div>
            )}
          </div>

          {sel && (
            <div style={{ marginTop: 12, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 10, padding: 12, textAlign: 'center' }}>
                <div style={{ fontSize: 22, fontWeight: 700, color: 'var(--success)' }}>{sel.leads_found}</div>
                <div style={{ fontSize: 11.5, color: 'var(--text-muted)', marginTop: 2 }}>Leads Found</div>
              </div>
              <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 10, padding: 12, textAlign: 'center' }}>
                <div style={{ fontSize: 22, fontWeight: 700, color: 'var(--accent)' }}>{sel.leads_inserted}</div>
                <div style={{ fontSize: 11.5, color: 'var(--text-muted)', marginTop: 2 }}>Leads Inserted</div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────
// Navigation
// ─────────────────────────────────────────────

const NAV = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/companies', label: 'Companies', icon: Building2 },
  { to: '/leads', label: 'Leads', icon: Users },
  { to: '/jobs', label: 'Jobs', icon: BarChart3 },
];

// ─────────────────────────────────────────────
// App Root
// ─────────────────────────────────────────────

export default function App() {
  return (
    <BrowserRouter>
      <div className="app-layout">
        {/* Sidebar */}
        <aside className="sidebar">
          <div className="sidebar-logo">
            <div className="sidebar-logo-icon">
              <Zap size={18} color="white" />
            </div>
            <span className="sidebar-logo-text">LeadGen</span>
          </div>

          <nav>
            {NAV.map(({ to, label, icon: Icon }) => (
              <NavLink
                key={to}
                to={to}
                end={to === '/'}
                className={({ isActive }) =>
                  `nav-link${isActive ? ' active' : ''}`
                }
              >
                <Icon size={16} />
                {label}
              </NavLink>
            ))}
          </nav>

          <div style={{ marginTop: 'auto', padding: '16px 12px', borderTop: '1px solid var(--border)', fontSize: 12, color: 'var(--text-muted)' }}>
            <div>Lead Gen v2.0</div>
            <div style={{ marginTop: 4 }}>
              <a
                href="/docs"
                target="_blank"
                rel="noopener noreferrer"
                style={{ color: 'var(--accent)', textDecoration: 'none' }}
              >
                API Docs ↗
              </a>
            </div>
          </div>
        </aside>

        {/* Main */}
        <main className="main-content">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/companies" element={<CompaniesPage />} />
            <Route path="/leads" element={<LeadsPage />} />
            <Route path="/jobs" element={<JobsPage />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}
