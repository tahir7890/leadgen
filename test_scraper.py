import asyncio
import sys
import logging
logging.basicConfig(level=logging.INFO, format="%(message)s")

from app.services.job_runner import JobRunner

def main():
    runner = JobRunner()
    # Let's test stripe.com or openai.com
    # We will search the database for 'stripe.com'
    from app.repositories.companies import CompaniesRepository
    repo = CompaniesRepository()
    try:
        repo.add("stripe.com")
    except Exception:
        pass # Already exists
    
    companies = repo.list_all(limit=100)
    target = next((c for c in companies if c['domain'] == 'stripe.com'), None)
    if not target:
        print("Company stripe.com not found")
        sys.exit(1)
        
    print(f"Starting job for {target['domain']} (id: {target['id']})")
    
    import app.services.job_runner
    # We will call _process_company directly to get synchronous output
    # First we need an MCP client
    from app.services.local_browser_client import create_local_browser_client
    try:
        mcp = create_local_browser_client(headless=True)
        result = runner._process_company(target, mcp, "test-job-id")
        print(f"Result: {result}")
        mcp.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
