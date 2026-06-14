-- Lead Gen Database Schema
-- Run this in: Supabase Dashboard → SQL Editor

-- ============================================================
-- companies table
-- ============================================================
CREATE TABLE IF NOT EXISTS public.companies (
  id          UUID      PRIMARY KEY DEFAULT gen_random_uuid(),
  domain      TEXT      NOT NULL UNIQUE,
  processed   BOOLEAN   NOT NULL DEFAULT FALSE,
  leads_found INTEGER   DEFAULT 0,
  processed_at TIMESTAMPTZ,
  status      TEXT      DEFAULT 'pending'
              CHECK (status IN ('pending', 'processing', 'completed', 'failed', 'no_results')),
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_companies_processed ON public.companies (processed);
CREATE INDEX IF NOT EXISTS idx_companies_status    ON public.companies (status);
CREATE INDEX IF NOT EXISTS idx_companies_created   ON public.companies (created_at);

-- ============================================================
-- leads table
-- ============================================================
CREATE TABLE IF NOT EXISTS public.leads (
  id               UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id       UUID    NOT NULL REFERENCES public.companies(id) ON DELETE CASCADE,
  full_name        TEXT,
  first_name       TEXT,
  last_name        TEXT,
  job_title        TEXT,
  seniority        TEXT,
  department       TEXT,
  company_name     TEXT,
  company_domain   TEXT,
  linkedin_url     TEXT,
  email            TEXT,
  phone            TEXT,
  location         TEXT,
  source           TEXT    NOT NULL DEFAULT 'rocketreach',
  confidence_score NUMERIC(5,2),
  dedupe_key       TEXT    NOT NULL,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Deduplication constraint — must be unique
CREATE UNIQUE INDEX IF NOT EXISTS idx_leads_dedupe_key  ON public.leads (dedupe_key);

-- Performance indexes
CREATE INDEX IF NOT EXISTS idx_leads_company_id  ON public.leads (company_id);
CREATE INDEX IF NOT EXISTS idx_leads_email       ON public.leads (email) WHERE email IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_leads_linkedin    ON public.leads (linkedin_url) WHERE linkedin_url IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_leads_created     ON public.leads (created_at);
CREATE INDEX IF NOT EXISTS idx_leads_domain      ON public.leads (company_domain);

-- ============================================================
-- Auto-update updated_at trigger
-- ============================================================
CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_leads_updated_at ON public.leads;
CREATE TRIGGER trg_leads_updated_at
  BEFORE UPDATE ON public.leads
  FOR EACH ROW
  EXECUTE FUNCTION public.set_updated_at();
