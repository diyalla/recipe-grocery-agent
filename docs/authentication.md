# Authentication Documentation

## Overview

Both Allrecipes and Instacart use anti-bot measures that affect how
we obtain and maintain sessions. This document covers our approach,
the tradeoffs involved, and how authentication failures are handled.

---

## Allrecipes

### Authentication Requirements
Allrecipes does not require user authentication for read operations.
However, it uses Cloudflare's anti-bot system as a form of access control.

### How We Obtain Access
We use the `cloudscraper` library which mimics a real browser's JavaScript
challenge response. On startup, `cloudscraper` automatically handles the
Cloudflare challenge and maintains a valid session.

```python
SCRAPER = cloudscraper.create_scraper(
    browser={"browser": "chrome", "platform": "windows", "mobile": False}
)
```

### Session Persistence
The cloudscraper session is module-level — persists for the lifetime of
the Python process. Both the MCP server and background worker create their
own session on startup.

### Session Expiry
If a 403 is received, we raise a structured RuntimeError:
```python
if response.status_code == 403:
    raise RuntimeError("Access forbidden (403) - Cloudflare blocking requests")
```

### Tradeoffs
- cloudscraper works well but may break if Cloudflare updates its challenge
- No credentials stored on disk for Allrecipes

---

## Instacart

### Authentication Requirements
Instacart has two tiers of access:

**Tier 1 — Unauthenticated:**
- Product search: works
- Product names and availability: works
- Pricing: not available

**Tier 2 — Playwright session (implemented):**
- Full pricing data: works
- Product search with prices: works
- Real cart operations: requires additional GraphQL auth

### How We Obtain Full Auth — Playwright

We use Playwright (headless Chromium) to load Instacart, wait for JavaScript
to run, then extract all cookies including `__Host-instacart_sid`.

**Implementation in `src/auth.py`:**

```python
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=True,
        args=["--no-sandbox", "--disable-blink-features=AutomationControlled"]
    )
    context = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)...",
        viewport={"width": 1280, "height": 800}
    )
    page = context.new_page()
    page.goto("https://www.instacart.com", wait_until="domcontentloaded")
    time.sleep(3)  # Wait for JS session setup
    cookies = context.cookies()
    browser.close()
```

### Session Persistence
Cookies are saved to `data/instacart_session.json` with a timestamp.
The session is reused for up to 1 hour before auto-refreshing.

```python
def _session_is_fresh() -> bool:
    data = json.load(open(CREDENTIALS_FILE))
    age = time.time() - data["saved_at"]
    return age < SESSION_MAX_AGE_SECONDS  # 3600 seconds
```

### Session Integration
The Playwright cookies are applied to the requests.Session used for
all GraphQL calls:

```python
def apply_session_to_requests(session, cookie_dict):
    for name, value in cookie_dict.items():
        session.cookies.set(name, value, domain=".instacart.com")
```

### Results With Full Auth
With __Host-instacart_sid we now get real pricing:
Boneless Skinless Chicken Breast Max Pack | $4.99 | True
Foster Farms Free Range Chicken Breast    | $8.59 | True
Foster Farms Thin-Sliced Chicken Breast   | $9.49 | False

### Error Handling
Auth failures are caught and fall back gracefully:

```python
try:
    cookies = get_instacart_session()
    if cookies.get("__Host-instacart_sid"):
        apply_session_to_requests(SESSION, cookies)
        return
except Exception as e:
    print(f"Playwright auth failed: {e}. Falling back to basic session.")

# Fallback: plain HTTP session
SESSION.get(BASE_URL, headers={...}, timeout=15)
```

**Background worker error handling:**
```python
try:
    price_digests = check_price_changes(config, state)
except Exception as e:
    errors.append(f"Price check failed: {e}")
    # Worker continues to check trending recipes
```

### Retry Logic
All Instacart requests use exponential backoff on rate limiting:
```python
if response.status_code == 429:
    wait = 2 ** attempt
    time.sleep(wait)
    continue
```

### Tradeoffs Summary

| Approach | Pros | Cons | Status |
|----------|------|------|--------|
| Plain requests | Simple, fast | No pricing | Fallback |
| Playwright headless | Full pricing, real auth | Slower startup, detectable | Implemented |
| Official Instacart API | Stable, supported | Does not exist publicly | N/A |

### Credential Security
- Session cookies are stored in `data/instacart_session.json`
- This file is excluded from git via `.gitignore`
- No username/password stored anywhere
- Cookies expire naturally and are refreshed automatically
