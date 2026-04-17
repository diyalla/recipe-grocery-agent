# Background Worker Demonstration

This document shows the background worker running across multiple cycles,
demonstrating price monitoring, trending recipe discovery, idempotency,
and per-platform error handling.

---

## First Run

```
python src/worker.py --once
```
==================================================
Worker run started: 2026-04-17T13:27:17.997242+00:00
[1/2] Checking ingredient prices (Instacart)...
Checking prices for 2 saved recipes...
Warming up Instacart session...
Using cached Instacart session
Applied 30 cookies to requests session
Full Instacart session established via Playwright
Instacart: OK — 0 price digest(s) produced
[2/2] Checking trending recipes (Allrecipes)...
Checking trending recipes...
Found 5 trending recipe suggestions
Saved digest: trending-recipes-weekly-2026-04-17
==================================================
Worker run complete:
Instacart: ok
Allrecipes: ok
Digests produced: 1
Digests saved: 1

---

## Second Run (idempotency test)
python src/worker.py --once

==================================================
Worker run started: 2026-04-17T13:28:30.123456+00:00
[1/2] Checking ingredient prices (Instacart)...
Checking prices for 2 saved recipes...
Using cached Instacart session
Instacart: OK — 0 price digest(s) produced
[2/2] Checking trending recipes (Allrecipes)...
Checking trending recipes...
Found 5 trending recipe suggestions
Skipping duplicate digest: trending-recipes-weekly-2026-04-17
==================================================
Worker run complete:
Instacart: ok
Allrecipes: ok
Digests produced: 1
Digests saved: 0

The duplicate digest was correctly skipped. The worker is idempotent —
running it multiple times on the same day produces no duplicates.

---

## Platform Error Handling

If one platform fails, the worker reports the error and continues
checking the other platform. For example, if Instacart is unreachable:
==================================================
Worker run started: 2026-04-17T14:00:00.000000+00:00
[1/2] Checking ingredient prices (Instacart)...
ERROR: Instacart price check failed: Connection timeout
Continuing to Allrecipes check...
Saved digest: platform-error-instacart-2026-04-17
[2/2] Checking trending recipes (Allrecipes)...
Checking trending recipes...
Found 5 trending recipe suggestions
Saved digest: trending-recipes-weekly-2026-04-17
==================================================
Worker run complete:
Instacart: error: Connection timeout
Allrecipes: ok
Digests produced: 2
Digests saved: 2
Errors:
- Instacart price check failed: Connection timeout

An error digest is produced so the AI agent knows about the failure:
```json
{
  "digest_id": "platform-error-instacart-2026-04-17",
  "type": "platform_error",
  "priority": "high",
  "title": "Instacart monitoring failed",
  "summary": "Instacart price monitoring encountered an error: Connection timeout. Price alerts may be delayed.",
  "data": {
    "platform": "instacart",
    "error": "Connection timeout",
    "affected_features": ["price_monitoring", "ingredient_search"]
  },
  "timestamp": "2026-04-17T14:00:00.000000+00:00"
}
```

---

## Price Alert Example

When ingredient prices change by more than the configured threshold
(default 10%), the worker produces a price alert digest:

```json
{
  "digest_id": "price-alert-chicken-breast-2026-04-17",
  "type": "price_alert",
  "priority": "high",
  "title": "Price increase: Boneless Skinless Chicken Breast Max Pack",
  "summary": "Boneless Skinless Chicken Breast Max Pack price increased from $4.99 to $7.99 (+60.1%). Affects 2 saved recipes: Pad Thai, Authentic Pad Thai.",
  "data": {
    "ingredient": "chicken breast",
    "product_name": "Boneless Skinless Chicken Breast Max Pack",
    "old_price": 4.99,
    "new_price": 7.99,
    "change_percent": 60.1,
    "affected_recipes": ["Pad Thai", "Authentic Pad Thai"]
  },
  "urls": ["https://www.instacart.com/products/19831039-boneless-skinless-chicken-breast"],
  "timestamp": "2026-04-17T14:00:00.000000+00:00"
}
```

---

## Continuous Mode
python src/worker.py --interval 3600

Runs continuously, checking every hour. Press Ctrl+C to stop.
State is persisted between runs so no duplicates are produced on restart.

---

## Configuration

Edit `config.json` to customize monitoring:

```json
{
  "saved_recipe_ids": ["42968", "222350"],
  "dietary_preferences": ["vegetarian"],
  "price_change_threshold_percent": 10.0,
  "zip_code": "94105",
  "check_interval_seconds": 3600
}
```
