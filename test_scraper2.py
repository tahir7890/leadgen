import asyncio
import sys
import logging
logging.basicConfig(level=logging.INFO, format="%(message)s")

def main():
    from app.services.job_runner import JobRunner
    from app.repositories.companies import CompaniesRepository
    from app.services.local_browser_client import create_local_browser_client
    from app.services.rocketreach import RocketReachService
    from app.services.lead_normalizer import normalize_leads
    
    repo = CompaniesRepository()
    companies = repo.list_all(limit=100)
    target = next((c for c in companies if c['domain'] == 'stripe.com'), None)
    
    try:
        mcp = create_local_browser_client(headless=True)
        rr = RocketReachService(mcp)
        raw_leads = rr.search_domain(target["domain"])
        print(f"Raw leads count: {len(raw_leads)}")
        if raw_leads:
            print("First raw lead:")
            print(raw_leads[0])
            
        clean_leads = normalize_leads(target["id"], target["domain"], raw_leads)
        print(f"Clean leads count: {len(clean_leads)}")
        if clean_leads:
            print("First clean lead:")
            print(clean_leads[0])
            
        mcp.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
