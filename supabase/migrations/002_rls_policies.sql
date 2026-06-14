-- ============================================================
-- Row Level Security (RLS) Policies
-- Run this in: Supabase Dashboard → SQL Editor
-- ============================================================
--
-- IMPORTANT: The service_role key BYPASSES RLS automatically.
-- These policies are only needed if you use the anon/publishable key.
-- For production backend usage with service_role key, RLS is optional.
--
-- If you are getting "Row Level Security" errors:
--   1. Check that SUPABASE_SERVICE_ROLE_KEY is the JWT secret (starts with eyJ...)
--   2. NOT the publishable key (starts with sb_publishable_...)
-- ============================================================

ALTER TABLE public.companies ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.leads ENABLE ROW LEVEL SECURITY;

-- ---------------------------------------------------------------
-- Allow all operations when using the service_role key
-- (service_role bypasses RLS, so these are for anon key usage)
-- ---------------------------------------------------------------

DROP POLICY IF EXISTS "service_all_companies" ON public.companies;
CREATE POLICY "service_all_companies" ON public.companies
  FOR ALL
  TO service_role
  USING (true)
  WITH CHECK (true);

DROP POLICY IF EXISTS "service_all_leads" ON public.leads;
CREATE POLICY "service_all_leads" ON public.leads
  FOR ALL
  TO service_role
  USING (true)
  WITH CHECK (true);

-- ---------------------------------------------------------------
-- Optional: Allow authenticated users read access
-- Uncomment if you need frontend to read data directly from Supabase
-- ---------------------------------------------------------------
-- DROP POLICY IF EXISTS "auth_read_companies" ON public.companies;
-- CREATE POLICY "auth_read_companies" ON public.companies
--   FOR SELECT
--   TO authenticated
--   USING (true);

-- DROP POLICY IF EXISTS "auth_read_leads" ON public.leads;
-- CREATE POLICY "auth_read_leads" ON public.leads
--   FOR SELECT
--   TO authenticated
--   USING (true);
