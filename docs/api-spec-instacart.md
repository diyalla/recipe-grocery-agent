# Instacart API Specification

## Discovery Method
Reverse engineered by intercepting browser HTTP traffic using Chrome DevTools
Network tab while searching for "chicken breast" on instacart.com.

## Anti-Bot Measures Encountered

### JavaScript Session Cookie
Instacart sets `__Host-instacart_sid` via JavaScript execution after page load.
This cookie is required for full pricing data and authenticated cart operations.

**Problem:** Plain Python HTTP requests cannot execute JavaScript.

**Solution:** We use Playwright (headless Chromium) to load the page, wait for
JavaScript to run, then extract all cookies including `__Host-instacart_sid`.
The cookies are persisted to `data/instacart_session.json` and reused for up
to 1 hour before refreshing.

**Implementation:** See `src/auth.py` for the full Playwright authentication flow.

```python
# Simplified auth flow
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto("https://www.instacart.com", wait_until="domcontentloaded")
    time.sleep(3)  # Wait for JS to set session cookies
    cookies = browser.context.cookies()
    sid = next(c for c in cookies if c["name"] == "__Host-instacart_sid")
```

**What we tried before Playwright:**
- Plain requests with homepage cookie warmup → Search works, no pricing
- Session persists 5 cookies from homepage: device_uuid, privacy_opt_out,
  ahoy_visit, ahoy_track, ahoy_visitor — but not __Host-instacart_sid

---

## API Architecture

Instacart uses **GraphQL with Persisted Queries**.

Instead of sending full GraphQL query text, the browser sends a sha256Hash
that the server maps to a stored query. This is a performance optimization
that also makes reverse engineering harder.

**GraphQL Endpoint:** `https://www.instacart.com/graphql`
**Method:** GET (not POST — discovered via browser analysis)

Variables and extensions are passed as URL-encoded query parameters,
not as a request body. This is unusual for GraphQL and was the cause
of our initial 400 Bad Request errors.

---

## Endpoints

### 1. Search Products

**Operation:** `SearchCrossRetailerGroupResults`
**Method:** GET
**URL:** `https://www.instacart.com/graphql`

**Persisted Query Hash:**
edb3181e1e0bf2b2b8e377d2c2082b82eee2448a4bf417a3ca549647a39b28d5

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| operationName | string | SearchCrossRetailerGroupResults |
| variables | JSON string | URL-encoded variables object |
| extensions | JSON string | Contains persistedQuery hash |

**Variables Object:**
```json
{
  "overrideFeatureStates": [],
  "searchSource": "cross_retailer_search",
  "query": "chicken breast",
  "pageViewId": "<uuid-v4>",
  "shopIds": ["9501", "12", "7517", "..."],
  "disableAutocorrect": false,
  "includeDebugInfo": false,
  "autosuggestImpressionId": null,
  "first": 7,
  "shopId": "0",
  "zoneId": "1",
  "postalCode": "94105"
}
```

**Important notes:**
- pageViewId must be a fresh UUID per request
- shopIds must be a non-empty list discovered from browser traffic
- Empty shopIds array causes the request to return no results

**Example Response:**
```json
{
  "data": {
    "searchCrossRetailerGroupResults": {
      "term": "chicken breast",
      "results": [
        {
          "retailerId": "542",
          "shopId": "54",
          "items": [
            {
              "id": "items_31529-19831039",
              "name": "Boneless Skinless Chicken Breast Max Pack",
              "size": "2.5 lb",
              "availability": {
                "available": true,
                "stockLevel": "inStock"
              },
              "price": {
                "viewSection": {
                  "priceString": "$4.99",
                  "priceValueString": "4.99"
                }
              }
            }
          ]
        }
      ]
    }
  }
}
```

---

### 2. Get Product Details

**Operation:** Items
**Method:** GET
**Status:** Requires __Host-instacart_sid — falls back to search-based lookup

---

### 3. Cart Operations

**Operations discovered:** ActiveCartId, CartData
**Status:** Requires full GraphQL mutation with authenticated session
**Current implementation:** Local demo cart with product name and price tracking

---

## Required Headers
User-Agent:          Mozilla/5.0 (Windows NT 10.0; Win64; x64)...
Accept:              /
Accept-Encoding:     gzip, deflate, br, zstd
content-type:        application/json
x-client-identifier: web
x-ic-view-layer:     true
x-page-view-id:      <fresh UUID per request>
x-ic-qp:             <fresh UUID per request>
Referer:             https://www.instacart.com/store/s?k=<query>
sec-fetch-dest:      empty
sec-fetch-mode:      cors
sec-fetch-site:      same-origin

---

## Authentication

### Tier 1 — Unauthenticated (basic session)
Obtained via plain HTTP request to homepage.
Cookies: device_uuid, ahoy_visit, ahoy_visitor, privacy_opt_out, ahoy_track
Result: Product names and availability only. No pricing.

### Tier 2 — Playwright session (what we implement)
Obtained via headless Chromium browser.
Additional cookies: __Host-instacart_sid, X-IC-bcx, forterToken, and ~25 others
Result: Full pricing data available. Product search returns real prices.

### Session Persistence
Cookies saved to `data/instacart_session.json` with timestamp.
Reused for up to 1 hour. Auto-refreshed by calling `get_instacart_session()`.

### Session Expiry Detection
```python
if response.status_code == 403:
    raise RuntimeError("Instacart 403 — session expired, refresh needed")
```

---

## Response Compression

Instacart uses Brotli compression (Content-Encoding: br).
Requires `pip install brotli` for Python requests to decompress automatically.

---

## Known Limitations

1. ShopIds are region-specific. The list was discovered from a San Francisco
   area session. Different regions may have different store availability.

2. Persisted query hashes may change on Instacart deploys. The sha256 hash
   should be re-discovered if requests start returning errors.

3. No pagination in cross-retailer search. The first parameter controls
   results per retailer, not total results.

4. Store name not in search response. Cannot reliably filter by store name.

5. Cart operations use local demo cart. Real cart mutations require
   authenticated GraphQL operations not yet implemented.

6. Playwright detection risk. Instacart may detect headless browsers.
   We mitigate with realistic user agent and viewport settings.

---

## Rate Limiting

No explicit rate limiting encountered. Requests complete in 800-1300ms.
We add exponential backoff on 429 responses and a 1-second delay on
session warmup as a courtesy.
