# Authentication Documentation

## Overview

Both Allrecipes and Instacart use anti-bot measures that affect how
we obtain and maintain sessions. This document covers our approach,
the tradeoffs involved, and how authentication failures are handled.

---

## Allrecipes

### Authentication Requirements
Allrecipes does not require user authentication for read operations
(search, browse, get recipe). However, it uses Cloudflare's anti-bot
system which acts as a form of access control.

### How We Obtain Access
We use the `cloudscraper` library which mimics a real browser's
JavaScript challenge response. On startup, `cloudscraper` automatically
handles the Cloudflare challenge and maintains a valid session.

```pythonSCRAPER = cloudscraper.create_scraper(
browser={
"browser": "chrome",
"platform": "windows",
"mobile": False
}
)

### Session Persistence
The cloudscraper session is module-level — it persists for the lifetime
of the Python process. Both the foreground MCP server and background
worker create their own session on startup.

### Session Expiry
Cloudflare sessions expire after a period of inactivity. If a 403 is
received, the scraper automatically re-challenges. We detect 403 errors
and raise a structured RuntimeError:

```pythonif response.status_code == 403:
raise RuntimeError(
"Access forbidden (403) - Cloudflare is blocking requests. "
"Document this in api-spec-allrecipes.md."
)

### Tradeoffs
- `cloudscraper` works well but may break if Cloudflare updates its
  challenge mechanism. This is an inherent risk of scraping.
- No credentials are stored on disk for Allrecipes — no credential
  management needed.

---

## Instacart

### Authentication Requirements
Instacart has two tiers of access:

**Tier 1 — Unauthenticated (what we implement):**
- Product search: works
- Product names and availability: works
- Pricing: limited or unavailable
- Cart operations: not available on real cart

**Tier 2 — Authenticated (requires JavaScript):**
- Full pricing data
- Real cart operations (add, remove, checkout)
- Order history and saved items

### How We Obtain Tier 1 Access
We visit the Instacart homepage to collect basic cookies, then make
GraphQL GET requests with the required headers:

```pythondef _ensure_session():
if not SESSION.cookies:
SESSION.get(BASE_URL, headers={"User-Agent": ...}, timeout=15)
time.sleep(1)

This gives us: `device_uuid`, `ahoy_visit`, `ahoy_visitor`,
`privacy_opt_out`, `ahoy_track`.

### The Authentication Gap — __Host-instacart_sid

The main session cookie `__Host-instacart_sid` is set by JavaScript
running in the browser. It cannot be obtained with plain HTTP requests.

**What it enables:** Full pricing, authenticated cart operations,
personalized store inventory.

**Why we cannot get it:** The `__Host-instacart_sid` cookie is set via
a JavaScript fetch call after page load. Python's `requests` library
does not execute JavaScript. Obtaining it would require a headless
browser like Playwright or Selenium.

**Our approach:** We document this limitation honestly and implement
a local demo cart for cart operations. Product search and availability
work without this cookie.

**What a production implementation would do:**
```pythonUsing Playwright to obtain the session cookie
from playwright.async_api import async_playwrightasync def get_instacart_session():
async with async_playwright() as p:
browser = await p.chromium.launch(headless=True)
page = await browser.new_page()
await page.goto("https://www.instacart.com")
await page.wait_for_timeout(3000)  # Wait for JS to run
cookies = await page.context.cookies()
sid = next(
(c["value"] for c in cookies
if c["name"] == "__Host-instacart_sid"),
None
)
await browser.close()
return sid

### Credential Storage
We do not store Instacart credentials on disk. The session cookies
obtained from the homepage visit are kept in memory in the `SESSION`
object. If the process restarts, the session is re-established
automatically on the next request via `_ensure_session()`.

### Session Expiry Detection
We detect auth failures by HTTP status code:

```pythonif response.status_code == 403:
raise RuntimeError(
"Instacart 403 Forbidden - missing session cookie. "
"__Host-instacart_sid requires JavaScript execution."
)

### Error Handling
Both foreground and background components handle auth errors gracefully:

**Foreground MCP server:** Returns a structured error JSON with an
explanation rather than crashing:
```json{
"error": "Instacart search error: ...",
"note": "See api-spec-instacart.md for details"
}

**Background worker:** Catches auth errors per-platform and continues:
```pythontry:
price_digests = check_price_changes(config, state)
except Exception as e:
errors.append(f"Price check failed: {e}")
# Worker continues to check trending recipes

### Retry Logic
All Instacart requests use exponential backoff on rate limiting:
```pythonif response.status_code == 429:
wait = 2 ** attempt
time.sleep(wait)
continue

### Tradeoffs Summary

| Approach | Pros | Cons |
|----------|------|------|
| Plain requests (current) | Simple, no browser dependency | No pricing, no real cart |
| Playwright headless browser | Full auth, real pricing | Complex, slower, detectable |
| Official Instacart API | Stable, supported | Does not exist publicly |
| Stored session cookie | Fast, works until expiry | Expires, security risk |

We chose plain requests because it satisfies the core requirement
(product discovery, ingredient matching) while keeping the implementation
simple and dependency-light. The limitation is documented honestly.