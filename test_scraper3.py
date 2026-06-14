import asyncio
import sys
import logging
logging.basicConfig(level=logging.INFO, format="%(message)s")

def main():
    from app.services.local_browser_client import create_local_browser_client
    from app.services.rocketreach import RocketReachService
    
    try:
        mcp = create_local_browser_client(headless=True)
        rr = RocketReachService(mcp)
        rr.ensure_authenticated()
        
        url = f"https://rocketreach.co/person?employer%5B%5D=stripe.com&start=1&pageSize=10"
        mcp.navigate(url)
        import time
        time.sleep(8)
        
        JS = """
        () => {
           let captured = [];
           let origOpen = window.open;
           window.open = function(u) { captured.push(u); return null; };
           // We might also want to intercept window.location.href setters, but usually it's open()
           // Click all LinkedIn buttons
           document.querySelectorAll('button[title="LinkedIn"]').forEach(b => {
               // mock the click
               b.click();
           });
           
           // Click all Get Contact Info buttons to see if they reveal emails
           document.querySelectorAll('button').forEach(b => {
               if (b.innerText && b.innerText.toLowerCase().includes('get contact info')) {
                   // actually clicking this might trigger a modal, let's see
                   // b.click();
               }
           });
           
           return { capturedUrls: captured };
        }
        """
        res = mcp.evaluate(JS)
        print("CAPTURED:", res)
        
        # let's try reading href from <a> tags just in case
        res2 = mcp.evaluate("""
        () => {
            return Array.from(document.querySelectorAll('a')).map(a => a.href).filter(h => h.includes('linkedin.com'));
        }
        """)
        print("A TAGS LINKEDIN:", res2)
        
        mcp.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
