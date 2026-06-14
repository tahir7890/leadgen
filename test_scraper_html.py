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
    if not target:
        print("Company stripe.com not found")
        sys.exit(1)
        
    print(f"Starting job for {target['domain']} (id: {target['id']})")
    
    try:
        mcp = create_local_browser_client(headless=True)
        # We need to evaluate JS to get the innerHTML of the first card
        JS = """
        () => {
           const cb = document.querySelector('input[id^="profile-selection-"]');
           if (!cb) return 'No checkbox found';
           let parent = cb.parentElement;
           let depth = 0;
           while (parent && parent !== document.body && depth < 10) {
             if (parent.innerText && parent.innerText.length > 30 && parent.innerText.includes('\\n')) {
               return { text: parent.innerText, html: parent.innerHTML };
             }
             parent = parent.parentElement;
             depth++;
           }
           return 'No card found';
        }
        """
        
        # Navigate to a search page
        url = f"https://rocketreach.co/person?employer%5B%5D={target['domain']}&start=1&pageSize=10"
        mcp.navigate(url)
        import time
        time.sleep(10) # wait for page to load
        result = mcp.evaluate(JS)
        print("First card text:")
        print(result.get('text', ''))
        print("First card HTML:")
        print(result.get('html', ''))
        
        mcp.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
