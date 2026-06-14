<<<<<<< HEAD
# LeadGen — RocketReach + Apify MCP + Supabase

Full-stack automated lead generation:
- **Backend:** Python FastAPI
- **Frontend:** React dashboard
- **Browser:** [nexgendata/playwright-mcp-server](https://apify.com/nexgendata/playwright-mcp-server)
- **Database:** Supabase

## Fix Supabase 401 / RLS errors

Your error means the wrong API key is configured:

1. Open **Supabase Dashboard → Settings → API**
2. Copy the **`service_role`** secret (long JWT starting with `eyJ...`)
3. Set it in `.env` as `SUPABASE_SERVICE_ROLE_KEY`
4. **Do NOT** use the `publishable` / `anon` key (`sb_publishable_...`)

Also run in SQL Editor:
- `supabase/migrations/001_create_tables.sql`
- `supabase/migrations/002_rls_policies.sql` (if RLS still blocks writes)

## Quick Start

```bash
cp .env.example .env   # fill credentials

# Backend
cd backend
python -m venv .venv; .venv\Scripts\Activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend && npm install && npm run dev
```

Open http://localhost:5173

## Apify setup

Approve `nexgendata/playwright-mcp-server` in Apify Console on first run. Start with `CONCURRENCY=1`.
=======
# leadgen
>>>>>>> 58bc01c6ba3a47d2e1d430591ffd59e7718ab659
