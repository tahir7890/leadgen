import asyncio
import sys
import logging
logging.basicConfig(level=logging.INFO, format="%(message)s")

def main():
    from app.services.job_runner import JobRunner
    from app.repositories.companies import CompaniesRepository
    from app.services.local_browser_client import create_local_browser_client
    from app.services.rocketreach import RocketReachService
    
    repo = CompaniesRepository()
    companies = repo.list_all(limit=100)
    target = next((c for c in companies if c['domain'] == 'stripe.com'), None)
    
    try:
        mcp = create_local_browser_client(headless=True)
        rr = RocketReachService(mcp)
        # Call this just to authenticate
        rr._ensure_logged_in()
        
        url = f"https://rocketreach.co/person?employer%5B%5D={target['domain']}&start=1&pageSize=10"
        mcp.navigate(url)
        import time
        time.sleep(10)
        
        JS = """
        () => {
            const scripts = Array.from(document.querySelectorAll('script')).map(s => s.innerText);
            const stateScripts = scripts.filter(s => s.includes('email') && s.includes('stripe.com'));
            return {
                windowKeys: Object.keys(window).filter(k => k.toLowerCase().includes('state') || k.includes('data') || k.includes('__')),
                stateScripts: stateScripts.map(s => s.substring(0, 500))
            };
        }
        """
        result = mcp.evaluate(JS)
        print(result)
        mcp.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
