# Design Decisions

## 0. Instacart Authentication: Playwright vs Plain Requests

### Decision: Playwright headless browser for full auth
We initially used plain HTTP requests which gave us product names and
availability but no pricing. After discovering that `__Host-instacart_sid`
requires JavaScript execution, we implemented Playwright authentication.

### Discovery Process
1. Inspected `data/instacart_session.json` after plain HTTP warmup
2. Noticed `__Host-instacart_sid` was absent
3. Checked browser cookies after real Instacart visit — cookie was present
4. Confirmed cookie is set by JavaScript fetch call after page load
5. Implemented Playwright to automate this browser behavior

### Result
With Playwright auth, `estimate_recipe_cost` now returns real prices:
- Pad Thai (13 ingredients): **$44.27 total**
- Thai Green Curry (13 ingredients): **$56.00 total**

### Tradeoff
Playwright adds ~3-5 seconds on first run and requires installing Chromium.
We mitigate this by caching the session for 1 hour so subsequent calls
are instant.

---

## 1. MCP Transport
