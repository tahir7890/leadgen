"""RocketReach scraper using the Playwright MCP browser automation."""
from __future__ import annotations

import json
import logging
import time
from typing import Any

from app.config import get_settings
from app.services.mcp_client import McpError, PlaywrightMcpClient

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# JavaScript: extract lead cards from RocketReach search results page
# ---------------------------------------------------------------------------
EXTRACT_JS = r"""
() => {
  const text = (el) => (el ? (el.textContent || el.innerText || '') : '').trim();
  const attr = (el, n) => (el && el.getAttribute ? el.getAttribute(n) : '') || '';

  // ---- Strategy 1: Dynamic Structural Extraction ----
  // Instead of relying on brittle CSS classes (which SPAs obfuscate),
  // we look for anchor tags pointing to person profiles, then traverse
  // up the DOM to find the container (the "card").
  let cards = [];
  const profileLinks = Array.from(document.querySelectorAll('a[href*="/person/"], a[href*="/profile/"]'));
  
  if (profileLinks.length > 0) {
    const potentialCards = new Set();
    for (const link of profileLinks) {
      let parent = link.parentElement;
      let depth = 0;
      // Traverse up to find a container element (like a row or card)
      while (parent && parent !== document.body && depth < 8) {
        // A typical result card has substantial text and usually a button to get info
        if (parent.tagName === 'LI' || parent.tagName === 'ARTICLE' || 
            (parent.tagName === 'DIV' && parent.innerText.length > 50 && 
            (parent.innerText.includes('Get Contact') || parent.innerText.includes('Add')))) {
          potentialCards.add(parent);
          break;
        }
        parent = parent.parentElement;
        depth++;
      }
      // Fallback if no obvious container was found
      if (depth === 8 && link.parentElement) {
        potentialCards.add(link.parentElement.parentElement || link.parentElement);
      }
    }
    cards = Array.from(potentialCards);
  }

  // ---- Strategy 1b: Fallback for Svelte App Checkboxes ----
  if (cards.length === 0) {
    const profileCheckboxes = Array.from(document.querySelectorAll('input[id^="profile-selection-"]')).filter(cb => cb.id !== 'profile-selection-all' && /\d+/.test(cb.id));
    if (profileCheckboxes.length > 0) {
      const potentialCards = new Set();
      for (const cb of profileCheckboxes) {
        let parent = cb.parentElement;
        let depth = 0;
        let bestParent = null;
        while (parent && parent !== document.body && depth < 10) {
          if (parent.innerText && parent.innerText.includes('\n')) {
             const cls = parent.className || '';
             if (cls.includes('bg-rr-basic-white') || cls.includes('result-items')) {
                 if (cls.includes('bg-rr-basic-white')) bestParent = parent;
                 break;
             }
          }
          parent = parent.parentElement;
          depth++;
        }
        if (bestParent) potentialCards.add(bestParent);
      }
      cards = Array.from(potentialCards);
    }
  }

  // ---- Strategy 2: Fallback to CSS Selectors ----
  if (cards.length === 0) {
    const CARD_SELECTORS = [
      '[data-testid*="result"]', '[data-testid*="person"]',
      '[class*="result" i]', '[class*="person" i]',
      '[class*="PersonCard"]', '[class*="person-card"]',
      '[class*="SearchResult"]', '[class*="search-result"]',
      '[class*="table-row"]', 'table tr', 'li.search-result'
    ];
    for (const sel of CARD_SELECTORS) {
      try {
        const found = Array.from(document.querySelectorAll(sel));
        // Ensure it actually looks like a person result
        const valid = found.filter(el => el.innerText.length > 15 && el.innerText.includes('\n'));
        if (valid.length >= 1) { cards = valid; break; }
      } catch(e) {}
    }
  }

  // ---- Strategy 3: Hidden JSON State (Next.js / Redux) ----
  if (cards.length === 0) {
    // Check for __NEXT_DATA__ (Next.js)
    try {
      const nd = document.getElementById('__NEXT_DATA__');
      if (nd) {
        const data = JSON.parse(nd.textContent || '{}');
        const props = data.props || {};
        const pageProps = props.pageProps || {};
        const people = pageProps.people || pageProps.results || pageProps.contacts || pageProps.searchResults || [];
        if (people.length > 0) {
          return {
            leads: people.slice(0, 50).map(p => ({
              fullName: p.name || p.full_name || p.fullName || null,
              jobTitle: p.title || p.current_title || p.jobTitle || null,
              companyName: p.current_employer || p.employer || p.company || p.companyName || null,
              email: Array.isArray(p.emails) ? p.emails[0] : (p.email || p.mail || null),
              phone: Array.isArray(p.phones) ? p.phones[0] : (p.phone || p.number || null),
              location: p.location || p.city || p.address || null,
              linkedinUrl: p.linkedin_url || p.linkedin || p.linkedinUrl || p['linkdin id'] || p['linkedin id'] || null,
              seniority: p.seniority || null,
              department: p.department || null,
            })).filter(l => l.fullName || l.email || l.linkedinUrl),
            hasNext: !!(pageProps.pagination && pageProps.pagination.hasNextPage),
          };
        }
      }
    } catch(e) {}

    // Check window state objects (Redux / Apollo)
    try {
      const storeKeys = ['__store', '__STATE__', '__REDUX_STATE__', 'INITIAL_STATE'];
      for (const k of storeKeys) {
        if (window[k]) {
          const raw = typeof window[k] === 'string' ? JSON.parse(window[k]) : window[k];
          const find = (obj, depth=0) => {
            if (depth > 5 || !obj || typeof obj !== 'object') return [];
            for (const key of Object.keys(obj)) {
              if (Array.isArray(obj[key]) && obj[key].length > 0 && obj[key][0] && (obj[key][0].full_name || obj[key][0].name)) {
                return obj[key];
              }
              const found = find(obj[key], depth+1);
              if (found.length > 0) return found;
            }
            return [];
          };
          const people = find(raw);
          if (people.length > 0) {
            return {
              leads: people.slice(0, 50).map(p => ({
                fullName: p.full_name || p.name || p.fullName || null,
                jobTitle: p.current_title || p.title || p.jobTitle || null,
                companyName: p.current_employer || p.employer || p.companyName || p.company || null,
                email: Array.isArray(p.emails) ? p.emails[0] : (p.email || p.mail || null),
                phone: Array.isArray(p.phones) ? p.phones[0] : (p.phone || p.number || null),
                location: p.location || p.city || p.address || null,
                linkedinUrl: p.linkedin_url || p.linkedinUrl || p.linkedin || p['linkdin id'] || p['linkedin id'] || null,
              })).filter(l => l.fullName || l.email),
              hasNext: false,
            };
          }
        }
      }
    } catch(e) {}

    return { leads: [], hasNext: false, debug: { error: 'no cards found and all extraction methods failed' } };
  }

  // ---- Extract from DOM cards ----
  let origOpen = window.open;
  for (let c of cards) {
      let liUrl = null;
      window.open = function(url) { liUrl = url; return null; };
      const liBtn = c.querySelector('button[title="LinkedIn"], button[title*="linkedin" i], button[data-testid="social-button"]');
      if (liBtn) liBtn.click();
      c._interceptedLinkedIn = liUrl;
  }
  window.open = origOpen;

  const leads = cards.slice(0, 50).map(card => {
    // Name: try multiple selectors
    const nameEl =
      card.querySelector('[data-testid*="name"]') ||
      card.querySelector('[class*="name" i]:not([class*="company" i]):not([class*="domain" i])') ||
      card.querySelector('a[href*="/person/"]') ||
      card.querySelector('a[href*="linkedin.com/in/"]') ||
      card.querySelector('h2, h3, h4');

    // Title
    const titleEl =
      card.querySelector('[data-testid*="title"]') ||
      card.querySelector('[class*="title" i]:not([class*="company" i])') ||
      card.querySelector('[class*="job" i]') ||
      card.querySelector('[class*="role" i]') ||
      card.querySelector('[class*="position" i]');

    // Company
    const companyEl =
      card.querySelector('[data-testid*="company"]') ||
      card.querySelector('[class*="company" i]') ||
      card.querySelector('[class*="employer" i]') ||
      card.querySelector('[class*="organization" i]');

    // Email
    // Email
    const emailEl =
      card.querySelector('a[href^="mailto:"]') ||
      card.querySelector('[data-testid*="email"]') ||
      card.querySelector('[class*="email" i]');

    // Phone
    const phoneEl =
      card.querySelector('a[href^="tel:"]') ||
      card.querySelector('[data-testid*="phone"]') ||
      card.querySelector('[class*="phone" i]');

    // Location
    const locEl =
      card.querySelector('[data-testid*="location"]') ||
      card.querySelector('[class*="location" i]') ||
      card.querySelector('[class*="city" i]') ||
      card.querySelector('[class*="geography" i]');

    // LinkedIn
    const liEl = card.querySelector('a[href*="linkedin.com/in/"]');

    // Seniority / department
    const senEl = card.querySelector('[class*="seniority" i], [data-testid*="seniority"]');
    const deptEl = card.querySelector('[class*="department" i], [data-testid*="department"]');

    const emailHref = attr(emailEl, 'href');
    const phoneHref = attr(phoneEl, 'href');
    const emailText = text(emailEl);
    const liHref = attr(liEl, 'href');

    const allLinks = Array.from(card.querySelectorAll('a[href]')).map(a => a.href || '');
    let fallbackLinkedIn = card._interceptedLinkedIn || allLinks.find(h => h.includes('linkedin.com')) || null;
    let fallbackEmail = allLinks.find(h => h.startsWith('mailto:')) || null;
    if (fallbackEmail) fallbackEmail = fallbackEmail.replace('mailto:', '').split('?')[0];
    let fallbackPhone = allLinks.find(h => h.startsWith('tel:')) || null;
    if (fallbackPhone) fallbackPhone = fallbackPhone.replace('tel:', '');

    const lines = (card.innerText || '').split('\n')
      .map(l => l.trim())
      .filter(l => l.length > 1 && l.toLowerCase() !== 'select' && l.toLowerCase() !== 'add' && !l.toLowerCase().includes('profile selected') && l.toLowerCase() !== 'get contact info' && !l.toLowerCase().includes('show more'));
      
    const fallbackName = lines.length > 0 ? lines[0] : null;
    const fallbackTitle = lines.length > 1 ? lines[1] : null;
    const fallbackCompany = lines.length > 2 ? lines[2] : null;
    let fallbackLocation = null;
    
    for (let i = 2; i < lines.length; i++) {
        const l = lines[i];
        if (!fallbackEmail && l.includes('@') && !l.includes(' ')) fallbackEmail = l;
        else if (!fallbackPhone && (/^\\+?[\\d\\s\\-\\(\\)]{7,20}$/.test(l) || (l.includes('+') && /\\d/.test(l) && l.length < 30))) fallbackPhone = l.replace(/[a-zA-Z]/g, '').trim();
        else if (!fallbackLinkedIn && l.includes('linkedin.com')) fallbackLinkedIn = l;
        else if (!fallbackLocation && i === 3 && l.length > 3 && l.length < 50) fallbackLocation = l;
    }

    return {
      fullName: text(nameEl) || fallbackName || null,
      jobTitle: text(titleEl) || fallbackTitle || null,
      companyName: text(companyEl) || fallbackCompany || null,
      email: emailHref ? emailHref.replace('mailto:', '') : (emailText.includes('@') ? emailText : fallbackEmail),
      phone: phoneHref ? phoneHref.replace('tel:', '') : fallbackPhone,
      location: text(locEl) || fallbackLocation || null,
      linkedinUrl: liHref || fallbackLinkedIn || null,
      seniority: text(senEl) || null,
      department: text(deptEl) || null,
    };
  }).filter(l => l.fullName || l.email || l.linkedinUrl);

  // Detect next page
  const nextEl = document.querySelector(
    'a[rel="next"], button[aria-label*="next" i], [class*="next-page" i], [data-testid*="next"], [aria-label="Next page"]'
  );
  const hasNext = !!(nextEl && !nextEl.disabled && !nextEl.classList.contains('disabled'));

  return {
    leads,
    hasNext,
    debug: { url: location.href, title: document.title, cardSelector: cards.length > 0 ? 'DOM' : 'none' },
  };
}
"""

# JS to click next page button
CLICK_NEXT_JS = r"""
() => {
  const el = document.querySelector(
    'a[rel="next"], button[aria-label*="next" i], [class*="next-page" i], [data-testid*="next"], [aria-label="Next page"]'
  );
  if (el && !el.disabled && !el.classList.contains('disabled')) {
    el.click();
    return true;
  }
  return false;
}
"""

# Diagnostic dump — call this when 0 leads are found to understand the page structure
PAGE_DUMP_JS = r"""
() => {
  const body  = document.body;
  const text  = (body ? body.innerText : '').substring(0, 1500);

  // Collect unique class tokens from ALL elements (helps find the real card class names)
  const allClasses = new Set();
  document.querySelectorAll('*').forEach(el => {
    el.classList.forEach(c => allClasses.add(c));
  });
  const classTokens = Array.from(allClasses)
    .filter(c => c.length > 3 && c.length < 60)
    .slice(0, 120);

  // Collect all hrefs (helps find person profile links)
  const links = Array.from(document.querySelectorAll('a[href]'))
    .map(a => a.getAttribute('href'))
    .filter(h => h && (h.includes('/person') || h.includes('linkedin') || h.includes('/profile')))
    .slice(0, 30);

  // Check for embedded JSON data in Next.js
  let nextData = null;
  try {
    const nd = document.getElementById('__NEXT_DATA__');
    if (nd) {
      const parsed = JSON.parse(nd.textContent || '{}');
      // Return just the keys at each level so we can see the structure
      const summarize = (obj, depth=0) => {
        if (!obj || typeof obj !== 'object' || depth > 3) return typeof obj;
        if (Array.isArray(obj)) return `Array(${obj.length})`;
        const out = {};
        for (const k of Object.keys(obj).slice(0, 20)) {
          out[k] = summarize(obj[k], depth + 1);
        }
        return out;
      };
      nextData = summarize(parsed);
    }
  } catch(e) { nextData = 'parse error: ' + e.message; }

  return {
    url: location.href,
    title: document.title,
    textSnippet: text,
    classTokens,
    personLinks: links,
    nextDataStructure: nextData,
    inputsFound: Array.from(document.querySelectorAll('input')).map(i => ({
      type: i.type, placeholder: i.placeholder, name: i.name, id: i.id,
      ariaLabel: i.getAttribute('aria-label'),
    })),
  };
}
"""

# JS to trigger Next.js client-side router navigation (avoids server 404 on deep routes)
NEXTJS_NAV_JS = """
(path) => {
  // Method 1: Next.js router (most reliable for Next.js apps)
  if (window.next && window.next.router) {
    window.next.router.push(path);
    return 'next-router';
  }
  // Method 2: React Router via popstate
  window.history.pushState(null, '', path);
  window.dispatchEvent(new PopStateEvent('popstate', {state: null}));
  return 'pushstate';
}
"""

# Detect current page state
PAGE_STATE_JS = r"""
() => {
  const url = location.href.toLowerCase();
  const t = (document.title || '').toLowerCase();
  const b = (document.body ? document.body.innerText : '').toLowerCase().substring(0, 3000);

  // URL-based detection (most reliable — not fooled by UI text changes)
  const isLoginUrl  = url.includes('/login') || url.includes('/signin') || url.includes('/sign-in');
  const isDashboard = url.includes('/dashboard') || url.includes('/person/search') ||
                      url.includes('/people-search') || url.includes('/company/') ||
                      url.includes('/account') || url.includes('/settings') ||
                      t.includes('dashboard') || t.includes('search');

  // Text-based detection as backup
  const loggedInText = b.includes('log out') || b.includes('sign out') ||
                       b.includes('my account') || b.includes('upgrade plan') ||
                       b.includes('search results') || b.includes('people found') ||
                       b.includes('credits') || b.includes('profile lookup');
  const loginFormPresent = !!(document.querySelector('input[type="email"]') &&
                              document.querySelector('input[type="password"]'));

  return {
    title: document.title,
    url: location.href,
    isLoginPage: isLoginUrl || (loginFormPresent && !isDashboard),
    isLoggedIn: isDashboard || loggedInText,
    isCaptcha: b.includes('captcha') || b.includes('robot') ||
               b.includes('cloudflare') || b.includes('verify you') ||
               t.includes('just a moment'),
    isRateLimited: b.includes('too many requests') || b.includes('rate limit') || b.includes('429'),
    is404: t.includes('404') || t.includes('not found') || b.includes('page not found'),
    hasResults: document.querySelectorAll('[class*="result" i], [class*="PersonCard" i], [data-testid*="result"]').length > 0,
    resultCount: document.querySelectorAll('[class*="result" i], [class*="PersonCard" i], [data-testid*="result"]').length,
  };
}
"""


class RocketReachService:
    """Scrapes RocketReach people search using Playwright MCP browser automation."""

    def __init__(self, mcp: PlaywrightMcpClient) -> None:
        self.mcp = mcp
        self.settings = get_settings()
        self._logged_in = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def ensure_authenticated(self) -> None:
        """Navigate to RocketReach and log in if needed."""
        if self._logged_in:
            return

        logger.info("Checking RocketReach authentication...")
        self.mcp.navigate("https://rocketreach.co/")
        time.sleep(3)

        state = self._page_state()
        current_url = state.get("url", "").lower()
        logger.info(
            "Page state: url=%s isLoggedIn=%s isLoginPage=%s",
            state.get("url"),
            state.get("isLoggedIn"),
            state.get("isLoginPage"),
        )

        # URL-based check: if we're already on the dashboard, we're logged in
        if state.get("isLoggedIn") or "dashboard" in current_url:
            logger.info("Already authenticated on RocketReach (url=%s)", state.get("url"))
            self._logged_in = True
            return

        if state.get("isCaptcha"):
            state = self._wait_for_captcha(state)

        # Navigate to login page
        self.mcp.navigate("https://rocketreach.co/login")
        time.sleep(4)

        # Check if /login redirected us to the dashboard (already logged in via cookie)
        post_nav_state = self._page_state()
        post_url = post_nav_state.get("url", "").lower()
        if post_nav_state.get("isLoggedIn") or "dashboard" in post_url or "login" not in post_url:
            logger.info(
                "Already logged in — /login redirected to %s", post_nav_state.get("url")
            )
            self._logged_in = True
            return

        self._login()
        self._logged_in = True

    def search_domain(self, domain: str, _is_retry: bool = False) -> list[dict[str, Any]]:
        """Search RocketReach for people at the given domain.

        Uses a fully UI-driven approach:
          1. Ensure we are on the dashboard (app is loaded)
          2. Find + click the 'People Search' nav link  (React Router handles nav)
          3. Fill the employer/company filter in the sidebar
          4. Wait for results and extract leads

        We never hard-navigate directly to /people-search because that route is
        not served server-side by RocketReach's CDN and always returns 404.
        """
        self.ensure_authenticated()

        import re
        raw_query = domain.strip().lower()
        
        # 1. Parse Domain vs Job Title
        domain_match = re.search(r"([a-z0-9-]+\.(?:com|org|net|co|io|ai|gov|edu)[a-z]*)", raw_query)
        company_query = ""
        job_title = ""
        if domain_match:
            company_query = domain_match.group(1).replace("www.", "")
            job_title = raw_query.replace(domain_match.group(0), "").replace("www.", "").strip()
        else:
            parts = raw_query.split()
            if parts:
                company_query = parts[0]
                job_title = " ".join(parts[1:])
                
        logger.info("Parsed Search Query -> Employer: %r | Job Title: %r", company_query, job_title)

        # ------------------------------------------------------------------
        # Step 1 — Make sure we are on the RocketReach app (dashboard)
        # ------------------------------------------------------------------
        current = self._page_state()
        if "rocketreach.co" not in current.get("url", "").lower():
            logger.info("Not on RocketReach — navigating to dashboard...")
            self.mcp.navigate("https://rocketreach.co/dashboard")
            time.sleep(5)

        # ------------------------------------------------------------------
        # Step 2 — Navigate to the people-search page via the UI nav link
        # ------------------------------------------------------------------
        on_search_page = self._get_to_people_search_page()
        if not on_search_page:
            logger.warning(
                "Could not reach the people-search page via nav. "
                "The browser is open — please click 'People Search' manually if needed."
            )
            time.sleep(6)   # give user a moment to click manually

        state = self._page_state()
        logger.info(
            "After nav: title=%r  url=%s  is404=%s",
            state.get("title"), state.get("url"), state.get("is404"),
        )

        # ------------------------------------------------------------------
        # Step 3 — Fill the employer and job title filters
        # ------------------------------------------------------------------
        filled_employer = self._fill_employer_filter(company_query)
        if filled_employer:
            logger.info("Employer filter filled with: %s", company_query)
            time.sleep(2)
        else:
            logger.warning(
                "Could not fill employer filter. "
                "If the browser is open, please type %r manually.",
                company_query,
            )
            
        filled_title = False
        if job_title:
            filled_title = self._fill_job_title_filter(job_title)
            if filled_title:
                logger.info("Job title filter filled with: %s", job_title)
            time.sleep(2)
            
        if filled_employer or filled_title:
            logger.info("Filters applied — waiting for results...")
            time.sleep(6)
            state = self._page_state()
            logger.info(
                "After filter: hasResults=%s  resultCount=%d  url=%s",
                state.get("hasResults"), state.get("resultCount", 0), state.get("url"),
            )
        else:
            time.sleep(8)
            state = self._page_state()

        # ------------------------------------------------------------------
        # Step 4 — Standard checks
        # ------------------------------------------------------------------
        if state.get("isCaptcha"):
            state = self._wait_for_captcha(state)

        if state.get("isLoginPage"):
            logger.warning("Session expired — re-authenticating...")
            self._logged_in = False
            self.mcp.navigate("https://rocketreach.co/login")
            time.sleep(3)
            self._login()
            # After re-login, restart the search
            return self.search_domain(domain)

        if state.get("isRateLimited"):
            raise McpError(
                f"RocketReach rate limited while searching {domain}. "
                "Wait a few minutes before retrying.",
                retryable=True,
            )

        # ------------------------------------------------------------------
        # Step 5 — Extract leads across pages
        # ------------------------------------------------------------------
        all_leads: list[dict[str, Any]] = []
        max_pages = 5
        delay = max(self.settings.request_delay_ms / 1000, 2.0)

        for page_num in range(max_pages):
            logger.debug("Extracting leads from page %d for %s", page_num + 1, domain)
            
            # --- Robust Pre-Extraction Wait & Scroll ---
            # Wait for loading spinners to disappear and for results to mount
            try:
                self.mcp.evaluate("""() => {
                    return new Promise((resolve) => {
                        // Scroll down slowly to trigger lazy-loading of all cards
                        let totalHeight = 0;
                        const distance = 300;
                        const timer = setInterval(() => {
                            const scrollHeight = document.body.scrollHeight;
                            window.scrollBy(0, distance);
                            totalHeight += distance;
                            if(totalHeight >= scrollHeight - window.innerHeight || totalHeight > 4000){
                                clearInterval(timer);
                                // Scroll back to top to ensure nothing broke
                                window.scrollTo(0, 0);
                                resolve(true);
                            }
                        }, 200);
                    });
                }""")
            except Exception as e:
                logger.debug("Scroll execution interrupted: %s", e)
            
            result = self._extract_leads_from_page()
            page_leads = result.get("leads", [])
            has_next   = result.get("hasNext", False)
            debug      = result.get("debug", {})

            logger.info(
                "Page %d: %d leads | hasNext=%s | url=%s",
                page_num + 1, len(page_leads), has_next, debug.get("url", "?"),
            )

            if page_num == 0 and not page_leads:
                self._dump_page_debug(domain)

            if page_leads:
                all_leads.extend(page_leads)

            if not has_next or not page_leads:
                break

            try:
                clicked = self.mcp.evaluate(CLICK_NEXT_JS)
                if not clicked:
                    break
                time.sleep(delay)
            except McpError as e:
                logger.warning("Failed to click next page for %s: %s", domain, e)
                break

        logger.info("Total leads for %s: %d", domain, len(all_leads))
        
        # If 0 results and we used BOTH filters, retry with employer only
        if not all_leads and job_title and not _is_retry:
            logger.info("0 results found for combined query. Retrying with employer only...")
            # Navigate back to dashboard to clear filters
            self.mcp.navigate("https://rocketreach.co/dashboard")
            time.sleep(4)
            return self.search_domain(company_query, _is_retry=True)
            
        return all_leads

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _page_state(self) -> dict[str, Any]:
        """Run PAGE_STATE_JS and return a safe dict."""
        try:
            result = self.mcp.evaluate(PAGE_STATE_JS)
            if isinstance(result, dict):
                return result
            return {}
        except McpError as e:
            logger.warning("Failed to get page state: %s", e)
            return {}

    def _fill_employer_filter(self, company_query: str) -> bool:
        """Try to fill the employer/company filter in the RocketReach search UI.

        RocketReach's people-search page has a sidebar with filter inputs.
        We look for an input labelled 'Employer', 'Company', or 'Current Employer'
        and type the company name, then press Enter to trigger the search.

        Returns True if an input was found and filled, False otherwise.
        """
        filter_labels = [
            "Employer", "Company", "Current Employer",
            "Organization", "Search by employer", "Add employer",
            "current_employerFilter", "e.g. LinkedIn URL",
        ]
        for label in filter_labels:
            try:
                self.mcp.type_text(label, company_query, submit=True)
                logger.info("Filled employer filter (%r) with: %s", label, company_query)
                return True
            except Exception:
                continue

        # Fallback: look for any visible text input that isn't email/password
        safe_query = json.dumps(company_query)
        filter_js = """
() => {{
  const inputs = Array.from(document.querySelectorAll(
    'input[type="text"], input[type="search"], input:not([type])'
  )).filter(i => i.offsetParent !== null);
  for (const inp of inputs) {{
    const lbl = (inp.placeholder || inp.getAttribute('aria-label') || inp.name || '').toLowerCase();
    // Match 'employer', 'company', or the giant global search bar placeholder
    if (lbl.includes('employer') || lbl.includes('company') || 
        lbl.includes('search') || lbl.includes('linkedin url')) {{
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
      setter.call(inp, {query});
      inp.dispatchEvent(new Event('input', {{bubbles: true}}));
      inp.dispatchEvent(new Event('change', {{bubbles: true}}));
      inp.dispatchEvent(new KeyboardEvent('keydown', {{key: 'Enter', bubbles: true}}));
      
      // Also try to find and click a submit button next to it just in case
      setTimeout(() => {{
        const btn = inp.parentElement.querySelector('button[type="submit"]');
        if (btn) btn.click();
      }}, 500);
      
      return 'filled:' + (inp.placeholder || inp.name || 'unknown');
    }}
  }}
  return null;
}}
""".format(query=safe_query)
        try:
            result = self.mcp.evaluate(filter_js)
            if result:
                logger.info("Filled employer filter via JS fallback: %s", result)
                return True
        except Exception as e:
            logger.warning("JS employer filter fallback failed: %s", e)

        logger.warning(
            "Could not find an employer filter input for: %s. "
            "The search page may require manual interaction.",
            company_query,
        )
        return False

    def _fill_job_title_filter(self, job_title: str) -> bool:
        """Try to fill the job title filter in the RocketReach search UI."""
        if not job_title:
            return False
        filter_labels = [
            "Job Title", "Title", "Enter Job Title", "Keyword",
        ]
        for label in filter_labels:
            try:
                self.mcp.type_text(label, job_title, submit=True)
                return True
            except Exception:
                continue
        return False

    def _get_to_people_search_page(self) -> bool:
        """Navigate to the RocketReach people-search page using UI nav links.

        Inspects the current page's navigation links to find the real internal
        href for the people-search section, then clicks it.  This triggers
        Next.js client-side routing (no server request → no 404).

        Returns True if we successfully reached a page that looks like a
        search page, False otherwise.
        """
        # Step A: inspect nav links to find the real people-search path
        find_nav_js = r"""
() => {
  const candidates = Array.from(document.querySelectorAll(
    'nav a, header a, [role="navigation"] a, aside a, [class*="nav" i] a, [class*="sidebar" i] a'
  ));
  const results = candidates
    .map(a => ({
      href: a.getAttribute('href') || '',
      text: (a.textContent || '').trim().toLowerCase(),
    }))
    .filter(item =>
      item.href && !item.href.startsWith('http') &&   // internal links only
      (item.text.includes('people') || item.text.includes('search') ||
       item.text.includes('prospect') || item.text.includes('contact') ||
       item.href.includes('search') || item.href.includes('people'))
    );
  return results.slice(0, 10);
}
"""
        nav_links: list[dict] = []
        try:
            nav_links = self.mcp.evaluate(find_nav_js) or []
        except Exception as e:
            logger.warning("Nav link inspection failed: %s", e)

        logger.info("Candidate nav links for people-search: %s", nav_links)

        # Step B: click the most relevant nav link
        for item in nav_links:
            href = item.get("href", "")
            text = item.get("text", "")
            # Prefer links that contain 'people' or 'search'
            priority = ("people" in text or "people" in href or
                        "search" in text or "search" in href)
            if not priority:
                continue

            click_js = f"""
() => {{
  const el = document.querySelector('a[href="{href}"]');
  if (el) {{ el.click(); return true; }}
  return false;
}}
"""
            try:
                clicked = self.mcp.evaluate(click_js)
                if clicked:
                    logger.info("Clicked nav link: href=%r text=%r", href, text)
            except Exception as e:
                if "context was destroyed" in str(e).lower() or "navigation" in str(e).lower():
                    logger.info("Clicked nav link (triggered full navigation): href=%r", href)
                else:
                    logger.warning("Nav link click failed for %r: %s", href, e)
                    continue

            # Check if we landed on a search page
            time.sleep(5)   # wait for React to render the search page
            state = self._page_state()
            url = state.get("url", "").lower()
            # Accept if url changed away from dashboard to something search-like
            if "search" in url or "person" in url or state.get("hasResults"):
                logger.info("On people-search page: %s", state.get("url"))
                return True

        # Step C: fallback — click by text label using local browser client
        fallback_labels = [
            "People Search", "People", "Search People", "Find People",
            "Person Search", "Advanced Search", "Prospects",
        ]
        for label in fallback_labels:
            try:
                self.mcp.click(label)
                logger.info("Clicked nav item by text label: %r", label)
                time.sleep(5)
                state = self._page_state()
                url = state.get("url", "").lower()
                if "search" in url or "person" in url or state.get("hasResults"):
                    logger.info("On people-search page via label click: %s", url)
                    return True
            except Exception:
                continue

        logger.warning(
            "Could not navigate to people-search via UI. "
            "Will attempt employer filter on current page."
        )
        return False

    def _dump_page_debug(self, domain: str) -> None:
        """Run PAGE_DUMP_JS and log the result to help diagnose zero-lead pages."""
        try:
            dump = self.mcp.evaluate(PAGE_DUMP_JS)
            if not isinstance(dump, dict):
                return
            logger.warning(
                "[DEBUG] Zero leads for %s. Page dump:\n"
                "  URL: %s\n"
                "  Title: %s\n"
                "  Text snippet: %.400s\n"
                "  Person links found: %s\n"
                "  Input fields: %s\n"
                "  CSS class tokens (first 60): %s\n"
                "  __NEXT_DATA__ structure: %s",
                domain,
                dump.get("url"),
                dump.get("title"),
                dump.get("textSnippet", ""),
                dump.get("personLinks", []),
                dump.get("inputsFound", []),
                dump.get("classTokens", [])[:60],
                dump.get("nextDataStructure"),
            )
        except Exception as e:
            logger.warning("Page dump failed: %s", e)

    def _wait_for_captcha(self, state: dict[str, Any]) -> dict[str, Any]:
        """Pause execution and wait for the user to solve a CAPTCHA manually.

        Local browser mode (LOCAL_BROWSER_MODE=true):
            The browser window is already visible.  Prints a banner to the
            console, then polls until the CAPTCHA page is gone.  Resumes
            automatically.

        Apify cloud mode:
            Prints the Apify Live View URL and polls for up to 5 minutes.
        """
        if not state.get("isCaptcha"):
            return state

        timeout = self.settings.captcha_wait_timeout  # default 300 s

        if self.settings.is_local_browser_mode():
            # ── Local visible browser ──────────────────────────────────────
            # The LocalBrowserClient exposes wait_for_human_captcha_solve().
            # We call it directly on the underlying client object.
            from app.services.local_browser_client import LocalBrowserClient
            if isinstance(self.mcp, LocalBrowserClient):
                self.mcp.wait_for_human_captcha_solve(timeout=timeout)
                state = self._page_state()
                return state
            # Fallback: treat as Apify path below

        # ── Apify cloud browser ────────────────────────────────────────────
        sep = "=" * 65
        print(f"""
{sep}
  🔴  CAPTCHA DETECTED — HUMAN ACTION REQUIRED
{sep}

  A CAPTCHA or verification challenge appeared on RocketReach.

  👉  Open the Apify Live View in your browser:
      https://console.apify.com  →  Your actor run  →  Live View

  👉  Complete the CAPTCHA in the Live View tab.

  ⏱️  You have {timeout // 60} minutes ({timeout}s) to solve it.
      Automation resumes automatically once the page is clear.

{sep}
""", flush=True)
        logger.warning(
            "CAPTCHA detected on RocketReach — waiting up to %ds for manual solve.",
            timeout,
        )

        poll_interval = 10
        steps = timeout // poll_interval
        for i in range(steps):
            time.sleep(poll_interval)
            state = self._page_state()
            if not state.get("isCaptcha"):
                remaining_msg = ""
                print(f"""
{sep}
  ✅  CAPTCHA SOLVED — Resuming automation...
{sep}
""", flush=True)
                logger.info("CAPTCHA resolved after %ds — resuming.", (i + 1) * poll_interval)
                return state
            remaining = timeout - (i + 1) * poll_interval
            logger.info(
                "⏳ Still waiting for CAPTCHA to be solved... %ds remaining",
                remaining,
            )

        raise McpError(
            f"CAPTCHA was not solved within {timeout}s. "
            "Please solve it faster and retry the job.",
            retryable=False,
        )

    def _extract_leads_from_page(self) -> dict[str, Any]:
        """Run the extraction JS and safely parse the result."""
        try:
            result = self.mcp.evaluate(EXTRACT_JS)
        except McpError as e:
            logger.warning("JS evaluation failed: %s", e)
            return {"leads": [], "hasNext": False}

        if isinstance(result, str):
            result = result.strip()
            if result:
                try:
                    result = json.loads(result)
                except json.JSONDecodeError:
                    logger.warning("Could not parse JS result as JSON: %.200s", result)
                    return {"leads": [], "hasNext": False}
            else:
                return {"leads": [], "hasNext": False}

        if not isinstance(result, dict):
            return {"leads": [], "hasNext": False}

        return result

    def _login(self) -> None:
        """Perform RocketReach login using browser_type (most reliable method)."""
        email = self.settings.rocketreach_email
        password = self.settings.rocketreach_password

        if not email or not password:
            raise McpError(
                "RocketReach credentials not set. "
                "Add ROCKETREACH_EMAIL and ROCKETREACH_PASSWORD to .env",
                retryable=False,
            )

        logger.info("Logging into RocketReach as %s...", email)

        # Try browser_type first (most reliable for React forms)
        try:
            self._login_with_type_tool(email, password)
        except McpError as e:
            logger.warning("browser_type login failed (%s), trying JS injection...", e)
            try:
                self._login_with_js(email, password)
            except McpError as e2:
                raise McpError(
                    f"All login methods failed: type={e} js={e2}",
                    retryable=False,
                ) from e2

        # Wait for post-login navigation
        time.sleep(6)

        state = self._page_state()
        logger.info(
            "Post-login state: isLoggedIn=%s isLoginPage=%s isCaptcha=%s url=%s",
            state.get("isLoggedIn"),
            state.get("isLoginPage"),
            state.get("isCaptcha"),
            state.get("url"),
        )

        if state.get("isCaptcha"):
            state = self._wait_for_captcha(state)

        if state.get("isLoginPage") and not state.get("isLoggedIn"):
            # Still on login page — wrong credentials
            raise McpError(
                "RocketReach login failed — still on login page after submission. "
                "Check ROCKETREACH_EMAIL and ROCKETREACH_PASSWORD in .env",
                retryable=False,
            )

        logger.info("RocketReach login successful (url=%s)", state.get("url"))

    def _login_with_type_tool(self, email: str, password: str) -> None:
        """Use browser actions to fill the login form (accessibility labels)."""
        # Type into fields by their accessible names
        try:
            self.mcp.type_text("Email", email)
            self.mcp.type_text("Password", password)
        except McpError as e:
            raise McpError(f"Email or Password input field not found on RocketReach login page: {e}")

        # Click submit button — try many variants RocketReach uses
        submit_labels = [
            "Log in", "Log In", "Login",
            "Sign in", "Sign In", "Signin",
            "Submit", "Continue",
        ]
        for label in submit_labels:
            try:
                self.mcp.click(label)
                logger.debug("Clicked submit using label: %s", label)
                return
            except McpError:
                continue

        raise McpError("Submit button not found on RocketReach login page")

    def _login_with_js(self, email: str, password: str) -> None:
        """Fallback: fill login form via JavaScript evaluation with safe encoding."""
        # Use json.dumps to safely encode credentials (handles quotes, backslashes, etc.)
        safe_email = json.dumps(email)     # returns '"email@example.com"'
        safe_password = json.dumps(password)  # returns '"P@ssw0rd"'

        js = f"""
() => {{
  const email = {safe_email};
  const password = {safe_password};

  const emailInput =
    document.querySelector('input[type="email"]') ||
    document.querySelector('input[name="email"]') ||
    document.querySelector('input[name="username"]') ||
    document.querySelector('input[placeholder*="email" i]');

  const pwdInput =
    document.querySelector('input[type="password"]') ||
    document.querySelector('input[name="password"]');

  if (!emailInput || !pwdInput) {{
    return {{ ok: false, reason: 'form not found: email=' + !!emailInput + ' pwd=' + !!pwdInput }};
  }}

  const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
  setter.call(emailInput, email);
  emailInput.dispatchEvent(new Event('input', {{ bubbles: true }}));
  emailInput.dispatchEvent(new Event('change', {{ bubbles: true }}));

  setter.call(pwdInput, password);
  pwdInput.dispatchEvent(new Event('input', {{ bubbles: true }}));
  pwdInput.dispatchEvent(new Event('change', {{ bubbles: true }}));

  const submit =
    document.querySelector('button[type="submit"]') ||
    document.querySelector('input[type="submit"]') ||
    document.querySelector('button[class*="login" i]');

  if (submit) {{
    submit.click();
    return {{ ok: true, method: 'click' }};
  }}
  pwdInput.dispatchEvent(new KeyboardEvent('keydown', {{ key: 'Enter', bubbles: true }}));
  return {{ ok: true, method: 'enter' }};
}}
"""
        result = self.mcp.evaluate(js)
        if isinstance(result, dict) and not result.get("ok"):
            reason = result.get("reason", "unknown")
            raise McpError(f"JS login failed: {reason}")
