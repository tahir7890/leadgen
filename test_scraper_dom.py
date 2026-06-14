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
        rr.ensure_authenticated()
        
        url = f"https://rocketreach.co/person?employer%5B%5D={target['domain']}&start=1&pageSize=10"
        mcp.navigate(url)
        import time
        time.sleep(8)
        
        JS = """
        () => {
           const cb = document.querySelector('input[id^="profile-selection-"]');
           if (!cb) return 'No checkbox found';
           let parent = cb.parentElement;
           let depth = 0;
           let out = [];
           while (parent && parent !== document.body && depth < 10) {
               out.push({
                   depth: depth,
                   tag: parent.tagName,
                   className: parent.className,
                   text: parent.innerText.replace(/\\n/g, ' ').substring(0, 100),
                   htmlLength: parent.innerHTML.length
               });
               parent = parent.parentElement;
               depth++;
           }
           return out;
        }
        """
        res = mcp.evaluate(JS)
        import pprint
        pprint.pprint(res)
        mcp.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
