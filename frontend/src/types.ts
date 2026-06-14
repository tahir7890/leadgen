export interface Company {
  id: string;
  domain: string;
  processed: boolean;
  leads_found: number | null;
  processed_at: string | null;
  status: string | null;
  created_at: string;
}

export interface Lead {
  id: string;
  company_id: string;
  full_name: string | null;
  first_name: string | null;
  last_name: string | null;
  job_title: string | null;
  seniority: string | null;
  department: string | null;
  company_name: string | null;
  company_domain: string | null;
  linkedin_url: string | null;
  email: string | null;
  phone: string | null;
  location: string | null;
  source: string;
  confidence_score: number | null;
  created_at: string;
}

export interface Job {
  id: string;
  status: string;
  total: number;
  completed: number;
  failed: number;
  leads_found: number;
  leads_inserted: number;
  started_at: string | null;
  finished_at: string | null;
  message: string | null;
  logs: string[];
}

export interface DashboardStats {
  total_companies: number;
  processed_companies: number;
  pending_companies: number;
  total_leads: number;
  leads_with_email: number;
  leads_with_linkedin: number;
  last_job_status: string | null;
}

export interface HealthStatus {
  status: string;
  supabase_configured: boolean;
  apify_configured: boolean;
  rocketreach_configured: boolean;
}
