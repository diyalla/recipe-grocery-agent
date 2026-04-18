# Design Decisions & Engineering Tradeoffs

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

## 1. MCP Transport: stdio vs streamable-http

### Decision: streamable-http (default), with stdio and SSE also supported
The challenge specifies streamable-http or SSE transport. We implemented
streamable-http as the default, with all three transports selectable via
command line argument.

### How to run each transport
python src/mcp_server.py                                    # streamable-http on port 8080
python src/mcp_server.py --transport streamable-http --port 8080
python src/mcp_server.py --transport stdio
python src/mcp_server.py --transport sse --port 8080

### Tradeoff
stdio transport is simpler and works well when agent and server run on
the same machine. HTTP transport is required for remote deployments.
We default to streamable-http to match the challenge specification.

---

## 2. Ingredient Parser: Custom vs Library

### Decision: Custom parser
We built our own ingredient parser rather than using a library like
`ingredient-parser-nlp` or `spacy`.

### Reasoning
- The challenge specifically asks us to build the parser
- Custom code is easier to explain and extend
- We have full control over edge cases like "boneless, skinless chicken"
- No heavyweight NLP dependencies required

### Key engineering decisions in the parser
- Split on ALL commas not just the first — fixes "boneless, skinless chicken breast"
- Treat dash-separated phrases as comma-separated — fixes "chicken breast - cut into cubes"
- MEAT_MODIFIERS set prevents "boneless" from becoming the item name
- PREPARATION_TRIGGERS set prevents "cut into" from bleeding into item name

### Tradeoff
A production system would benefit from a trained NLP model. Our regex
plus word classification approach achieves high accuracy on common cases
but may struggle with highly unusual formats.

---

## 3. Instacart: GraphQL GET vs POST

### Decision: GET requests with URL-encoded parameters
This was discovered through browser traffic analysis, not a design choice.
Instacart uses GET requests for their GraphQL queries, not the more common
POST approach.

### Discovery Process
1. Opened Chrome DevTools Network tab
2. Searched for "chicken breast" on instacart.com
3. Filtered requests by graphql
4. Observed the request method was GET with variables in URL params
5. Copied the exact request format including headers and shop IDs

### Impact
Our initial implementation used POST (standard GraphQL) which returned
400 Bad Request. Switching to GET immediately resolved this.

---

## 4. Ingredient-to-Product Matching and Unit Conversion

### Decision: Direct item name search with unit conversion where possible
For `estimate_recipe_cost`, we parse the ingredient item name and search
Instacart directly. We then apply unit conversion where the recipe unit
and package unit are in the same dimension (volume or weight).

### Unit Conversion Implementation
```python
# Example: recipe needs 2 tbsp butter, package is 16 oz
# 2 tbsp = 29.574 ml, 16 oz = 473.176 ml
# fraction = 29.574 / 473.176 = 6.25%
# cost = $3.06 * 0.0625 = $0.19
```

### Coverage
- Volume to volume: cups, tablespoons, teaspoons, ml, liters
- Weight to weight: pounds, ounces, grams, kilograms
- Cross-dimension: not possible without ingredient density data

### Documented Limitation
Cannot convert between volume and weight (e.g. 1 cup flour to oz)
without knowing ingredient density. Falls back to full package price
in these cases, which is documented in the tool response.

---

## 5. Background Worker: File-based State vs Database

### Decision: JSON files on disk
Worker state is persisted in `data/worker_state.json` and
`data/digests.json`.

### Reasoning
- Simple to implement and inspect
- No database dependency
- Sufficient for a single-user local application
- Easy to reset (just delete the files)

### Idempotency
Digest IDs are deterministic: `type-subject-date`. Before saving any
digest, we check if that ID already exists. If it does, we skip it.
This means the worker is safe to restart mid-run without producing
duplicate digests.

### Tradeoff
File-based storage has race conditions if multiple workers run
simultaneously. For production we would use SQLite or a proper database.

---

## 6. Digest Design: Producer/Consumer Separation

### Decision: Worker produces digests, AI evaluates them separately
The worker does not decide what to show the user. It produces all
relevant digests and lets the AI agent triage them.

### Reasoning
This matches the challenge requirements exactly. It also makes the
system more flexible — different AI models can apply different triage
strategies to the same digest stream.

### Digest Priority Levels
- `high` — price change greater than 25%, affects multiple saved recipes
- `medium` — price change 10-25%, affects one recipe
- `low` — trending recipe suggestions, non-urgent information

---

## 7. Demo: OpenRouter vs Groq

### Decision: OpenRouter for the exact challenge model
The challenge specifies Qwen3.5-35B-A3B. This model is available on
OpenRouter but not on Groq's free tier (which only has qwen3-32b).

### Why OpenRouter
- Has the exact model: `qwen/qwen3.5-35b-a3b`
- Free tier available
- OpenAI-compatible API — easy to integrate

### Token Management
We truncate tool results to 2000 chars max and keep only the last
6 messages in conversation history to stay within context limits.

---

## 8. Allrecipes: HTML Scraping vs JSON API

### Decision: HTML scraping with BeautifulSoup
Allrecipes does not expose a public JSON API for recipe search results.

### Discovery Process
We investigated several potential API endpoints:
- `/search` POST endpoint — returns UI component bundles, not recipe data
- `/api/` paths — returned 404
- Network tab analysis — search results are server-side rendered HTML

### Selector Stability
HTML selectors can change when Allrecipes updates their frontend. We
discovered this firsthand when the instruction selector changed from
`.comp.mntl-sc-block-html p` to `[class*=step] p` in April 2026.
All selectors are documented in `docs/api-spec-allrecipes.md` so they
can be updated if needed.
