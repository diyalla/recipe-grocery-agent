# Recipe & Grocery Intelligence Agent

An AI-powered application that connects Allrecipes and Instacart so an AI agent
can help users plan meals, understand ingredient costs, manage a grocery cart,
and stay informed about relevant food and grocery updates.

## Setup Instructions

### Prerequisites
- Python 3.10 or higher
- Node.js (for MCP inspector testing)
- Git

### Installation

1. Clone the repository:
   git clone <your-repo-url>
   cd recipe-grocery-agent

2. Create and activate a virtual environment:
   python -m venv venv
   venv\Scripts\activate  (Windows)
   source venv/bin/activate  (Mac/Linux)

3. Install dependencies:
   pip install -r requirements.txt

4. Copy the example config:
   cp config.json.example config.json

5. Edit config.json to set your saved recipes and preferences.

---

## How to Run

### Start the MCP foreground server (HTTP transport, default)
   python src/mcp_server.py

### Start on a custom port
   python src/mcp_server.py --transport streamable-http --port 8080

### Start with stdio transport (for direct AI agent connection)
   python src/mcp_server.py --transport stdio

### Start with SSE transport
   python src/mcp_server.py --transport sse --port 8080

### Run the background worker once
   python src/worker.py --once

### Run the background worker continuously
   python src/worker.py --interval 3600

### Run the test suite
   pytest tests/ -v

### Inspect the MCP server with the visual tool
   mcp dev src/mcp_server.py

---

## Architecture Overview
recipe-grocery-agent/
├── src/
│   ├── parser/
│   │   └── ingredient_parser.py   # Parses raw ingredient strings
│   ├── clients/
│   │   ├── allrecipes.py          # Allrecipes scraping client
│   │   └── instacart.py           # Instacart GraphQL client
│   ├── mcp_server.py              # MCP tool server (10 tools)
│   └── worker.py                  # Background monitoring worker
├── tests/
│   └── test_ingredient_parser.py  # 30 ingredient parser tests
├── docs/
│   ├── api-spec-allrecipes.md     # Allrecipes API specification
│   └── api-spec-instacart.md      # Instacart API specification
├── demo/
│   ├── conversation.md            # Foreground agent demo transcript
│   ├── worker_demo.md             # Background worker demonstration
│   └── digest_triage.md          # Digest triage demonstration
├── data/                          # Worker state (auto-created)
│   ├── worker_state.json          # Persisted prices and run history
│   └── digests.json               # Produced digest payloads
├── config.json                    # User configuration
└── README.md

### How components interact

1. The user talks to a Qwen AI agent
2. Qwen connects to our MCP server via stdio transport
3. Qwen calls tools like search_recipes or estimate_recipe_cost
4. The MCP server calls our Allrecipes/Instacart clients
5. Results flow back to Qwen which presents them to the user
6. Separately, the background worker runs on a schedule
7. The worker monitors prices and trending recipes
8. It writes digest payloads to disk for the AI to evaluate

---

## Known Limitations

### Instacart
- Full pricing requires the __Host-instacart_sid session cookie which
  is set by JavaScript and cannot be obtained without a headless browser.
  Product names and availability work correctly without auth.
- Cart operations use a local demo cart rather than the real Instacart cart.
- Shop IDs are hardcoded from a San Francisco area discovery session.
  Different regions may have different store availability.
- Persisted query hashes may change if Instacart deploys updates.

### Allrecipes
- Uses cloudscraper to bypass Cloudflare protection. May break if
  Cloudflare updates its challenge mechanism.
- HTML selectors may break if Allrecipes updates their page structure.
- Cuisine/dietary filters are not available as URL parameters and
  are applied post-fetch where possible.

### Ingredient Parser
- Unit conversion between volume, weight, and count is not applied
  when estimating recipe costs. Prices are per package as listed.
- Complex compound ingredients may parse with lower confidence.

### Background Worker
- Price alerts require Instacart auth to function fully.
- Trending recipe discovery is limited to a few search terms to
  avoid rate limiting.

### General
- No real money transactions are made. Cart operations are demo only.
- The Qwen demo uses a free API tier which may have rate limits.

---

## Time Spent

- Day 1: API discovery (Allrecipes + Instacart), ingredient parser,
         both API clients — approximately 8 hours
- Day 2: MCP server (10 tools), background worker, documentation
         — approximately 7 hours
- Day 3: README, demo transcripts, Qwen integration — approximately 5 hours
- Day 4: Polish, known limitations, final cleanup — approximately 3 hours

Total: approximately 23 hours