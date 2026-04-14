# Instacart API Specification

## Discovery Method
Reverse engineered by intercepting browser HTTP traffic using Chrome DevTools
Network tab while searching for "chicken breast" on instacart.com.

## Anti-Bot Measures Encountered

### JavaScript Session Cookie
Instacart sets `__Host-instacart_sid` via JavaScript execution. This cookie
is required for full pricing data and authenticated cart operations.

**Problem:** Plain Python HTTP requests cannot execute JavaScript, so we
cannot obtain this cookie without a headless browser (e.g. Playwright/Selenium).

**Impact:** Product search works (names, availability). Pricing data is
limited or absent for some products. Cart mutations (add/remove) require
this cookie and fall back to a local demo cart.

**What we tried:**
- Plain requests with homepage cookie warmup → Search works, pricing limited
- Session persists 5 cookies from homepage: device_uuid, privacy_opt_out,
  ahoy_visit, ahoy_track, ahoy_visitor

**What we would do with more time:**
Use Playwright (headless browser) to obtain the full session cookie,
then pass it to our requests client.

---

## API Architecture

Instacart uses **GraphQL with Persisted Queries**.

Instead of sending full GraphQL query text, the browser sends a
`sha256Hash` that the server maps to a stored query. This is a
performance optimization that also makes reverse engineering harder.

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
| `operationName` | string | `SearchCrossRetailerGroupResults` |
| `variables` | JSON string | URL-encoded variables object |
| `extensions` | JSON string | Contains persistedQuery hash |

**Variables Object:**
```json
{
  "overrideFeatureStates": [],
  "searchSource": "cross_retailer_search",
  "query": "chicken breast",
  "pageViewId": "<uuid-v4>",
  "shopIds": ["9501", "12", "7517", ...],
  "disableAutocorrect": false,
  "includeDebugInfo": false,
  "autosuggestImpressionId": null,
  "first": 7,
  "shopId": "0",
  "zoneId": "1",
  "postalCode": "94105"
}
```

**Important:** `pageViewId` must be a fresh UUID per request.
`shopIds` must be a non-empty list — discovered from browser traffic.
Empty array causes the request to return no results.

**Response Schema:**
```json
{
  "data": {
    "searchCrossRetailerGroupResults": {
      "term": "chicken breast",
      "searchId": "<uuid>",
      "results": [
        {
          "retailerId": "542",
          "shopId": "54",
          "items": [
            {
              "id": "items_31529-19831039",
              "name": "Boneless Skinless Chicken Breast Max Pack",
              "size": "2.5 lb",
              "productId": "19831039",
              "brandName": null,
              "evergreenUrl": "19831039-peco-foods-...",
              "availability": {
                "available": true,
                "stockLevel": "inStock"
              },
              "price": {
                "viewSection": {
                  "priceString": "$2.99",
                  "priceValueString": "2.99",
                  "fullPriceString": "$4.99"
                }
              },
              "viewSection": {
                "itemImage": {
                  "url": "https://d2lnr5mha7bycj.cloudfront.net/..."
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

### 2. Get Product Details (Items operation)

**Operation:** `Items`
**Method:** GET

**Persisted Query Hash:** Discovered but not fully implemented.
Requires `ids` array in format `items_SHOPID-PRODUCTID` and
`__Host-instacart_sid` session cookie for full data.

---

### 3. Cart Operations

**Operations discovered:** `ActiveCartId`, `CartData`
**Status:** Requires `__Host-instacart_sid` — not implemented
**Fallback:** Local in-memory demo cart used instead

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

### What is required
- `__Host-instacart_sid` — main session cookie, set by JavaScript
- `device_uuid` — device identifier cookie
- `ahoy_visit` / `ahoy_visitor` — analytics cookies

### What we obtain
- `device_uuid`, `ahoy_visit`, `ahoy_visitor` via homepage GET request
- Missing: `__Host-instacart_sid` (requires JavaScript/headless browser)

### Impact of missing auth
- Product search: Works (names, availability, some pricing)
- Pricing: Limited — some products show no price
- Cart operations: Fall back to local demo cart
- Product details: Basic info only

---

## Response Compression

Instacart uses **Brotli compression** (`Content-Encoding: br`).
Requires `pip install brotli` for Python's `requests` library to
decompress responses automatically.

---

## Known Limitations

1. **No full auth without headless browser.** The `__Host-instacart_sid`
   cookie requires JavaScript execution. Full pricing and cart operations
   need this cookie.

2. **ShopIds are region-specific.** The list of shop IDs was discovered
   from a San Francisco area session. Different regions have different
   store availability.

3. **Persisted query hashes may change.** If Instacart deploys a new
   version, the sha256 hash for our operations may change, breaking
   our client. The hash should be re-discovered periodically.

4. **No pagination in cross-retailer search.** The `first` parameter
   controls results per retailer (not total). Pagination across all
   retailers is not straightforward.

5. **Store name not in search response.** We cannot reliably filter
   by store name from the SearchCrossRetailerGroupResults response.
   A separate retailer lookup would be needed.

---

## Rate Limiting

No explicit rate limiting encountered. Requests complete in
~800-1300ms (server-side processing time visible in Server-Timing header).
We add a 1-second delay on session warmup as a courtesy.
