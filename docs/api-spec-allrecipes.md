# Allrecipes API Specification

## Discovery Method
Reverse engineered by intercepting browser HTTP traffic using Chrome DevTools
Network tab while browsing allrecipes.com.

## Anti-Bot Measures Encountered

### Cloudflare Protection
Allrecipes is protected by Cloudflare's anti-bot system. Initial attempts
using Python's `requests` library with realistic headers returned 403 Forbidden
on the search endpoint.

**What we tried:**
- Plain `requests` with browser-like headers → 403 Forbidden
- `requests.Session()` with homepage cookie warmup → 403 Forbidden
- `cloudscraper` library (mimics browser JS challenges) → SUCCESS

**Resolution:** Used `cloudscraper` with `browser=chrome, platform=windows`
configuration. This library handles Cloudflare's JavaScript challenge by
simulating browser fingerprints.

**Documented per challenge rules:** Being blocked is not a failure.
How we responded is what matters.

---

## Endpoints

### 1. Search Recipes

**URL:** `https://www.allrecipes.com/search`
**Method:** GET
**Type:** HTML document (not a JSON API)

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `q` | string | yes | Search query |
| `offset` | integer | no | Pagination offset (24 per page) |

**Example Request:**
GET https://www.allrecipes.com/search?q=pad+thai&offset=0

**Authentication:** None required for search

**Response Format:** Full HTML page (not JSON)
The search results are embedded directly in the HTML as
`<a class="mntl-card-list-card--extendable">` elements.
There is no separate JSON API for search results.

**Key HTML Selectors:**
Recipe cards:     a.mntl-card-list-card--extendable[data-doc-id]
Recipe ID:        data-doc-id attribute
Recipe title:     .card__title-text
Recipe URL:       href attribute
Rating (stars):   .icon-star, .icon-star-half, .icon-star-empty
Review count:     .mm-recipes-card-meta__rating-count-number
Image URL:        img.card__img[data-src]

**Pagination:**
- 24 results per page
- Page 2: `?offset=24`
- Page 3: `?offset=48`

**Rate Limiting:** Not observed during testing. cloudscraper handles
Cloudflare throttling automatically.

---

### 2. Get Recipe

**URL:** `https://www.allrecipes.com/recipe/{ID}/{slug}/`
**Method:** GET
**Type:** HTML document

**Example:**
GET https://www.allrecipes.com/recipe/42968/pad-thai/

**Authentication:** None required

**Key HTML Selectors:**
Title:            h1.article-heading
Description:      .article-subheading
Ingredients:      .mm-recipes-structured-ingredients__list-item
Instructions:     .comp.mntl-sc-block-html p
Time labels:      .mm-recipes-details__label
Time values:      .mm-recipes-details__value
Servings:         .mm-recipes-details__value (first occurrence)
Rating:           .mm-recipes-review-bar__rating
Review count:     .mm-recipes-review-bar__total-reviews
Nutrition cells:  .mm-recipes-nutrition-facts-summary__table-cell

**Nutrition Format:**
Nutrition data comes as alternating value/label pairs:
cell[0] = "524"     cell[1] = "Calories"
cell[2] = "21g"     cell[3] = "Fat"
cell[4] = "59g"     cell[5] = "Carbs"
cell[6] = "26g"     cell[7] = "Protein"

---

### 3. Browse Categories

**URL:** `https://www.allrecipes.com/recipes/`
**Method:** GET
**Type:** HTML document

**Key HTML Selectors:**
Category links:   .mntl-header-nav__list-item a

---

## Headers Required
User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36
Accept: text/html,application/xhtml+xml,application/xml;q=0.9,/;q=0.8
Accept-Language: en-US,en;q=0.9
Referer: https://www.allrecipes.com/
sec-ch-ua: "Chromium";v="140"
sec-ch-ua-platform: "Windows"

**Note:** cloudscraper automatically manages these headers and adds
Cloudflare challenge response tokens.

---

## Authentication

None required for read operations (search, browse, get recipe).

---

## Known Limitations

1. **No filter parameters in URL:** Cuisine, dietary, and cook time filters
   are applied client-side via JavaScript. The URL does not accept these
   as query parameters. We apply post-fetch filtering where possible.

2. **Cloudflare dependency:** cloudscraper may break if Cloudflare updates
   its challenge mechanism. This is an inherent risk of scraping.

3. **HTML structure may change:** Allrecipes can update their HTML class
   names at any time, breaking our selectors. Selectors should be
   re-verified periodically.

4. **No official API:** Allrecipes does not provide a public API.
   The POST endpoint at `/search` returns UI component data (SVG icons,
   JavaScript bundles), not recipe results. The actual results are
   server-side rendered HTML.

---

## Rate Limiting Observed

No explicit rate limiting encountered during testing. cloudscraper adds
a natural delay by handling Cloudflare challenges. We add a 1-second
delay between requests as a courtesy.