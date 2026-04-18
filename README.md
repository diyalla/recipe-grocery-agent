# Recipe & Grocery Intelligence Agent

An AI-powered application that connects Allrecipes and Instacart so an AI agent
can help users plan meals, understand ingredient costs, manage a grocery cart,
and stay informed about relevant food and grocery updates.

Built as a take-home engineering challenge. The application has two modes:
- **Foreground** — an MCP tool server (streamable-http) that Qwen3.5-35B-A3B calls interactively
- **Background** — a scheduled worker that monitors prices and trending recipes

---

## Setup Instructions

### Prerequisites
- Python 3.10 or higher
- Node.js (for MCP inspector)
- Git

### Installation

Clone the repository:
   git clone <your-repo-url>
   cd recipe-grocery-agent

Create and activate a virtual environment:
   python -m venv venv
   venv\Scripts\activate        # Windows
   source venv/bin/activate     # Mac/Linux

Install dependencies:
   pip install -r requirements.txt

Install Playwright browser (for Instacart authentication):
   playwright install chromium

Copy and configure the example files:
   cp config.json.example config.json
   cp .env.example .env

Edit `.env` and add your API keys:
   GROQ_API_KEY=your_groq_key_here
   OPENROUTER_API_KEY=your_openrouter_key_here

Get a free Groq key at console.groq.com
Get a free OpenRouter key at openrouter.ai (required for the exact Qwen3.5-35B-A3B model)

---

## How to Run

### Start the MCP foreground server (streamable-http, default)
   python src/mcp_server.py

### Start on a specific port
   python src/mcp_server.py --transport streamable-http --port 8080

### Start with stdio transport
   python src/mcp_server.py --transport stdio

### Start with SSE transport
   python src/mcp_server.py --transport sse --port 8080

### Run the background worker once
   python src/worker.py --once

### Run the background worker continuously
   python src/worker.py --interval 3600

### Run the test suite
   pytest tests/ -v

### Run the live Qwen demo
   python demo/run_demo.py

   Uses qwen/qwen3.5-35b-a3b via OpenRouter API (exact model specified in challenge).
   Requires OPENROUTER_API_KEY in .env file.
   Get a free key at openrouter.ai

### Inspect the MCP server
   mcp dev src/mcp_server.py

### Refresh Instacart session manually
   python -c "from src.auth import get_instacart_session; get_instacart_session(force_refresh=True)"

---

## Architecture Overview
   recipe-grocery-agent/
   ├── src/
   │   ├── auth.py                    # Playwright-based Instacart authentication
   │   ├── parser/
   │   │   └── ingredient_parser.py   # Parses raw ingredient strings into structured data
   │   ├── clients/
   │   │   ├── allrecipes.py          # Allrecipes scraping client (cloudscraper)
   │   │   └── instacart.py           # Instacart GraphQL client (reverse engineered)
   │   ├── mcp_server.py              # FastMCP server exposing 10 tools (streamable-http)
   │   └── worker.py                  # Background monitoring worker
   ├── tests/
   │   └── test_ingredient_parser.py  # 30 ingredient parser tests
   ├── docs/
   │   ├── api-spec-allrecipes.md     # Full Allrecipes API specification
   │   ├── api-spec-instacart.md      # Full Instacart API specification
   │   ├── authentication.md          # Authentication approach and tradeoffs
   │   └── design-decisions.md        # Engineering decisions and rationale
   ├── demo/
   │   ├── run_demo.py                # Script to run the live Qwen demo
   │   ├── conversation.md            # Written demo transcript
   │   ├── conversation_live.md       # Live Qwen demo transcript (auto-generated)
   │   ├── worker_demo.md             # Background worker demonstration
   │   └── digest_triage.md           # Digest triage demonstration
   ├── data/                          # Auto-created on first run
   │   ├── instacart_session.json     # Playwright session cookies (expires 1hr)
   │   ├── worker_state.json          # Persisted prices and run history
   │   └── digests.json               # Produced digest payloads
   ├── config.json                    # User configuration
   ├── config.json.example            # Example configuration
   ├── .env.example                   # Example environment variables
   └── README.md

### How Components Interact

1. On startup, `src/auth.py` launches headless Chromium via Playwright
2. Playwright loads instacart.com and extracts the `__Host-instacart_sid` cookie
3. Session cookies are cached to `data/instacart_session.json` for 1 hour
4. The Instacart client applies these cookies to all GraphQL requests
5. Real pricing data is now available for all product searches
6. The user talks to Qwen3.5-35B-A3B via OpenRouter API
7. Qwen connects to our MCP server and sees 10 available tools
8. Qwen calls tools like `search_recipes` or `estimate_recipe_cost`
9. The MCP server calls our Allrecipes and Instacart clients
10. Results with real prices flow back to Qwen
11. Separately, the background worker runs on a configurable schedule
12. The worker monitors ingredient prices and discovers trending recipes
13. It writes structured digest payloads to disk for AI triage

---

## MCP Tools

| Tool | Description |
|------|-------------|
| `search_recipes` | Search Allrecipes by keyword with optional cuisine/dietary filters |
| `get_recipe` | Get full recipe with parsed ingredients, instructions, nutrition |
| `search_products` | Search Instacart for grocery products with real pricing |
| `get_product_details` | Get full product details by ID or URL |
| `estimate_recipe_cost` | Match ingredients to Instacart products and estimate total cost |
| `find_substitutions` | Find ingredient substitutions with grocery pricing |
| `compare_recipes` | Compare 2-3 recipes with per-recipe costs and combined shopping list |
| `add_to_cart` | Add a product to the cart with name and price tracking |
| `get_cart` | Get cart contents with per-item prices, line totals, and subtotal |
| `remove_from_cart` | Remove an item from the cart |

---

## Real Pricing Results

With Playwright authentication, `estimate_recipe_cost` returns real prices:

**Pad Thai (13 ingredients):** $44.27 total
- Rice noodles: $4.50
- Butter: $3.06
- Chicken breast: $4.99
- Vegetable oil: $3.93
- Eggs: $4.19
- Sugar: $5.99
- Fish sauce: $6.29
- And more...

**Thai Green Curry Chicken (13 ingredients):** $56.00 total

---

## Known Limitations

### Instacart
- Cart operations use a local demo cart. Real cart mutations require
  additional authenticated GraphQL operations (ActiveCartId, CartData).
- Shop IDs are hardcoded from a San Francisco area session. Different
  regions may have different store availability.
- Persisted GraphQL query hashes may change on Instacart deploys.
- Playwright may be detected as a bot — we mitigate with realistic
  user agent and viewport settings.
- Session expires after 1 hour and must be refreshed.

### Allrecipes
- Uses cloudscraper to bypass Cloudflare. May break on Cloudflare updates.
- HTML selectors may break if Allrecipes updates their page structure.
  Updated selector from `.comp.mntl-sc-block-html p` to `[class*=step] p`
  after Allrecipes updated their HTML in April 2026.
- Cuisine and dietary filters applied post-fetch where possible.

### Ingredient Parser
- Unit conversion is implemented for volume and weight units.
  Cross-dimension conversion (e.g. cups to oz) requires ingredient
  density data and is not applied — falls back to full package price.
- Complex compound ingredients may parse with lower confidence scores.

### Background Worker
- Price monitoring now works with Playwright auth.
- Trending recipe discovery limited to a few search terms to avoid
  rate limiting Allrecipes.

### Demo
- Uses Groq free tier (6000 TPM limit). Automatic retries add delay
  between turns. Full demo takes approximately 10 minutes.
- Conversation history trimmed to stay within token limits.

---

## Known Non-Official APIs

### Allrecipes
No official public API exists. We use HTML scraping. Third-party wrappers
(Spoonacular, Edamam) exist but we reverse engineered the platform directly
as required by the challenge.

### Instacart
No official public API exists. We reverse engineered the GraphQL endpoint
used by their web frontend. See `docs/api-spec-instacart.md` for details.

---

## Time Spent

- Days 1-3: Research and learning phase — studying MCP protocol, learning
            web scraping fundamentals, investigating Allrecipes and Instacart
            platform behavior, reading Cloudflare and GraphQL documentation,
            setting up development environment — approximately 6 hours

- Day 4: API discovery, reverse engineering Instacart GraphQL endpoint,
         building Allrecipes scraping client, ingredient parser with
         30 tests — approximately 8 hours

- Day 5: MCP server (10 tools), background worker, API specification
         docs — approximately 7 hours

- Day 6: Live Qwen demo integration, Groq API setup, demo transcripts,
         Playwright authentication for real Instacart pricing
         — approximately 7 hours

- Day 7: HTTP transport, compare_recipes cost estimates, cart improvements,
         authentication docs, design decisions, README polish,
         final cleanup — approximately 5 hours

Total: approximately 33 hours over 7 days
