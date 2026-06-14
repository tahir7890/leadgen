import type { Company, DashboardStats, Job, Lead } from './types';

const BASE = import.meta.env.VITE_API_URL ?? '';

async function req<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}/api${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(options?.headers ?? {}),
    },
    ...options,
  });

  let data: any = {};
  try {
    const text = await res.text();
    data = text ? JSON.parse(text) : {};
  } catch {
    data = {};
  }

  if (!res.ok) {
    const message =
      data?.detail ??
      data?.message ??
      data?.error ??
      `${res.status} ${res.statusText}`;
    throw new Error(typeof message === 'string' ? message : JSON.stringify(message));
  }

  return data as T;
}

export const api = {
  // ── Stats ────────────────────────────────────────────────
  stats: () => req<DashboardStats>('/stats'),

  // ── Companies ────────────────────────────────────────────
  companies: (limit = 200) =>
    req<Company[]>(`/companies?limit=${limit}`),

  addCompany: (domain: string) =>
    req<Company>('/companies', {
      method: 'POST',
      body: JSON.stringify({ domain }),
    }),

  bulkCompanies: (domains: string[]) =>
    req<Company[]>('/companies/bulk', {
      method: 'POST',
      body: JSON.stringify({ domains }),
    }),

  resetCompany: (id: string) =>
    req<{ message: string }>(`/companies/${id}/reset`, { method: 'POST' }),

  processCompany: (id: string) =>
    req<{ job_id: string }>(`/companies/${id}/process`, { method: 'POST' }),

  deleteCompany: (id: string) =>
    req<{ message: string }>(`/companies/${id}`, { method: 'DELETE' }),

  // ── Leads ─────────────────────────────────────────────────
  leads: (params?: { company_id?: string; limit?: number }) => {
    const qs = new URLSearchParams();
    if (params?.company_id) qs.set('company_id', params.company_id);
    if (params?.limit) qs.set('limit', String(params.limit));
    const query = qs.toString() ? `?${qs}` : '';
    return req<Lead[]>(`/leads${query}`);
  },

  exportLeadsCsv: (company_id?: string) => {
    const qs = company_id ? `?company_id=${company_id}` : '';
    window.open(`${BASE}/api/leads/export/csv${qs}`, '_blank');
  },

  deleteLead: (id: string) =>
    req<{ message: string }>(`/leads/${id}`, { method: 'DELETE' }),

  // ── Jobs ──────────────────────────────────────────────────
  runJob: (opts?: { batch_size?: number; concurrency?: number }) =>
    req<Job>('/jobs/run', {
      method: 'POST',
      body: JSON.stringify(opts ?? {}),
    }),

  jobs: (limit = 20) => req<Job[]>(`/jobs?limit=${limit}`),

  getJob: (id: string) => req<Job>(`/jobs/${id}`),

  getJobLogs: (id: string, since = 0) =>
    req<{ job_id: string; status: string; logs: string[]; total_logs: number }>(
      `/jobs/${id}/logs?since=${since}`
    ),

  // ── Health ────────────────────────────────────────────────
  health: () =>
    req<{
      status: string;
      supabase_configured: boolean;
      apify_configured: boolean;
      rocketreach_configured: boolean;
    }>('/health'),
};
