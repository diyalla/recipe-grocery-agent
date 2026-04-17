import json
import time
import uuid
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.clients.allrecipes import search_recipes, get_recipe
from src.clients.instacart import search_products
from src.parser.ingredient_parser import parse_ingredient

# -------------------------------------------------------
# The background worker runs on a schedule and monitors:
# 1. Ingredient prices for saved recipes
# 2. Trending/seasonal recipes on Allrecipes
#
# It produces structured "digest" payloads that an AI agent
# can later evaluate and decide what to surface to the user.
#
# State is persisted to disk so the worker is idempotent —
# if it crashes and restarts, it won't produce duplicates.
# -------------------------------------------------------

# Directory where we store state between runs
STATE_DIR = Path("data")
STATE_FILE = STATE_DIR / "worker_state.json"
DIGESTS_FILE = STATE_DIR / "digests.json"
CONFIG_FILE = Path("config.json")

# Default config — will be overridden by config.json if it exists
DEFAULT_CONFIG = {
    "saved_recipe_ids": [
        "42968",   # Pad Thai
        "222350",  # Authentic Pad Thai
    ],
    "dietary_preferences": [],
    "price_change_threshold_percent": 10.0,
    "zip_code": "94105",
    "check_interval_seconds": 3600,
}


def load_config() -> dict:
    """
    Load configuration from config.json.
    Falls back to defaults if file doesn't exist.
    """
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE) as f:
                config = json.load(f)
            # Merge with defaults so missing keys use defaults
            return {**DEFAULT_CONFIG, **config}
        except Exception as e:
            print(f"Warning: Could not load config.json: {e}. Using defaults.")
    return DEFAULT_CONFIG.copy()


def load_state() -> dict:
    """
    Load persisted worker state from disk.
    State tracks last-seen prices and previously submitted digest IDs
    to prevent duplicates.
    """
    STATE_DIR.mkdir(exist_ok=True)
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except Exception as e:
            print(f"Warning: Could not load state file: {e}. Starting fresh.")
    return {
        "last_prices": {},       # ingredient -> last seen price
        "last_run": None,        # ISO timestamp of last run
        "submitted_digest_ids": []  # prevent duplicate digests
    }


def save_state(state: dict):
    """
    Persist worker state to disk.
    Called after each successful run.
    """
    STATE_DIR.mkdir(exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def load_digests() -> list:
    """Load existing digests from disk."""
    STATE_DIR.mkdir(exist_ok=True)
    if DIGESTS_FILE.exists():
        try:
            with open(DIGESTS_FILE) as f:
                return json.load(f)
        except Exception:
            return []
    return []


def save_digest(digest: dict):
    """
    Append a new digest to the digests file.
    Checks for duplicates using digest_id before saving.
    This makes the worker idempotent — safe to restart mid-run.
    """
    digests = load_digests()

    # Check for duplicate
    existing_ids = {d["digest_id"] for d in digests}
    if digest["digest_id"] in existing_ids:
        print(f"  Skipping duplicate digest: {digest['digest_id']}")
        return False

    digests.append(digest)
    STATE_DIR.mkdir(exist_ok=True)
    with open(DIGESTS_FILE, "w") as f:
        json.dump(digests, f, indent=2)
    print(f"  Saved digest: {digest['digest_id']}")
    return True


def make_digest_id(digest_type: str, subject: str, timestamp: str) -> str:
    """
    Create a deterministic digest ID from type + subject + date.
    Using the date (not full timestamp) means the same event on the
    same day produces the same ID, preventing duplicates on restart.
    """
    date_part = timestamp[:10]  # Just the date: 2026-04-15
    clean_subject = subject.lower().replace(" ", "-")[:30]
    return f"{digest_type}-{clean_subject}-{date_part}"


def check_price_changes(config: dict, state: dict) -> list[dict]:
    """
    Check current grocery prices for key ingredients in saved recipes.
    Produces price alert digests when prices change significantly.

    How it works:
    1. For each saved recipe, fetch the recipe and parse ingredients
    2. Search Instacart for each key ingredient
    3. Compare current price to last-seen price in state
    4. If change exceeds threshold, produce a digest
    """
    digests = []
    timestamp = datetime.now(timezone.utc).isoformat()
    zip_code = config.get("zip_code", "94105")
    threshold = config.get("price_change_threshold_percent", 10.0)
    saved_recipe_ids = config.get("saved_recipe_ids", [])

    if not saved_recipe_ids:
        print("  No saved recipes configured. Skipping price check.")
        return digests

    # Build a map of ingredient -> which recipes use it
    ingredient_recipe_map = {}

    print(f"  Checking prices for {len(saved_recipe_ids)} saved recipes...")

    for recipe_id in saved_recipe_ids:
        try:
            recipe = get_recipe(recipe_id=recipe_id)
            recipe_title = recipe.get("title", f"Recipe {recipe_id}")

            for raw_ingredient in recipe.get("ingredients_raw", [])[:5]:
                parsed = parse_ingredient(raw_ingredient)
                item_name = parsed.item if parsed.item else raw_ingredient

                if item_name not in ingredient_recipe_map:
                    ingredient_recipe_map[item_name] = []
                if recipe_title not in ingredient_recipe_map[item_name]:
                    ingredient_recipe_map[item_name].append(recipe_title)

        except Exception as e:
            print(f"  Warning: Could not fetch recipe {recipe_id}: {e}")
            continue

    # Check prices for each unique ingredient
    for ingredient, recipes_using_it in ingredient_recipe_map.items():
        try:
            products = search_products(query=ingredient, zip_code=zip_code, limit=1)

            if not products or products[0].get("error"):
                continue

            product = products[0]
            current_price = product.get("price_value")
            product_name = product.get("product_name", ingredient)

            if current_price is None:
                # No price available (requires auth) — skip
                continue

            # Check against last known price
            last_price = state["last_prices"].get(ingredient)

            if last_price is not None and last_price > 0:
                change_pct = ((current_price - last_price) / last_price) * 100

                if abs(change_pct) >= threshold:
                    direction = "increase" if change_pct > 0 else "decrease"
                    priority = "high" if abs(change_pct) >= 25 else "medium"

                    digest_id = make_digest_id(
                        "price-alert",
                        ingredient,
                        timestamp
                    )

                    digest = {
                        "digest_id": digest_id,
                        "type": "price_alert",
                        "priority": priority,
                        "title": f"Price {direction}: {product_name}",
                        "summary": (
                            f"{product_name} price changed from "
                            f"${last_price:.2f} to ${current_price:.2f} "
                            f"({change_pct:+.1f}%). "
                            f"Affects {len(recipes_using_it)} saved recipe(s): "
                            f"{', '.join(recipes_using_it)}."
                        ),
                        "data": {
                            "ingredient": ingredient,
                            "product_name": product_name,
                            "old_price": last_price,
                            "new_price": current_price,
                            "change_percent": round(change_pct, 1),
                            "affected_recipes": recipes_using_it,
                        },
                        "urls": [product.get("product_url", "")],
                        "timestamp": timestamp,
                    }
                    digests.append(digest)
                    print(f"  Price alert: {ingredient} changed {change_pct:+.1f}%")

            # Update last known price
            state["last_prices"][ingredient] = current_price

        except Exception as e:
            print(f"  Warning: Could not check price for {ingredient}: {e}")
            continue

    return digests


def check_trending_recipes(config: dict, state: dict) -> list[dict]:
    """
    Discover trending and seasonal recipes on Allrecipes.
    Filters by user dietary preferences from config.
    Produces recipe suggestion digests.

    How it works:
    1. Search for trending/seasonal keywords
    2. Filter results by dietary preferences
    3. Skip recipes we've already suggested recently
    4. Produce a digest with curated suggestions
    """
    digests = []
    timestamp = datetime.now(timezone.utc).isoformat()
    dietary_prefs = config.get("dietary_preferences", [])

    # Trending search terms to check
    trending_searches = [
        "spring recipes",
        "trending dinner",
        "seasonal recipe",
        "quick weeknight dinner",
        "healthy meal prep",
    ]

    print(f"  Checking trending recipes...")

    all_suggestions = []
    seen_ids = set(state.get("submitted_digest_ids", []))

    for search_term in trending_searches[:2]:  # Limit to 2 searches to be polite
        try:
            results = search_recipes(
                query=search_term,
                dietary=dietary_prefs[0] if dietary_prefs else None,
                limit=5
            )

            for recipe in results:
                recipe_id = recipe.get("recipe_id", "")
                if recipe_id and recipe_id not in seen_ids:
                    all_suggestions.append(recipe)

            time.sleep(1)  # Be polite between requests

        except Exception as e:
            print(f"  Warning: Could not fetch trending for '{search_term}': {e}")
            continue

    if all_suggestions:
        # Take top 5 unique suggestions
        top_suggestions = all_suggestions[:5]

        digest_id = make_digest_id("trending-recipes", "weekly", timestamp)

        digest = {
            "digest_id": digest_id,
            "type": "trending_recipes",
            "priority": "low",
            "title": "Trending Recipe Suggestions",
            "summary": (
                f"Found {len(top_suggestions)} trending recipes that match your preferences. "
                f"Top pick: {top_suggestions[0].get('title', 'Unknown')} "
                f"(rated {top_suggestions[0].get('rating', 'N/A')}/5 "
                f"with {top_suggestions[0].get('review_count', 0)} reviews)."
            ),
            "data": {
                "suggestions": [
                    {
                        "recipe_id": r.get("recipe_id"),
                        "title": r.get("title"),
                        "rating": r.get("rating"),
                        "review_count": r.get("review_count"),
                        "url": r.get("url"),
                        "image_url": r.get("image_url"),
                    }
                    for r in top_suggestions
                ],
                "dietary_preferences_applied": dietary_prefs,
            },
            "urls": [r.get("url", "") for r in top_suggestions],
            "timestamp": timestamp,
        }
        digests.append(digest)
        print(f"  Found {len(top_suggestions)} trending recipe suggestions")

    return digests


def run_once(config: dict = None) -> dict:
    """
    Run one complete worker cycle.

    1. Load config and state
    2. Check ingredient prices (Instacart)
    3. Check trending recipes (Allrecipes)
    4. Save all new digests
    5. Update and save state
    6. Return summary

    Per challenge requirements: if one platform fails, we report
    the error and continue checking the other platform.
    This function is idempotent — safe to call multiple times.
    """
    if config is None:
        config = load_config()

    state = load_state()
    timestamp = datetime.now(timezone.utc).isoformat()

    print(f"\n{'='*50}")
    print(f"Worker run started: {timestamp}")
    print(f"{'='*50}")

    all_digests = []
    errors = []
    platform_status = {
        "instacart": "ok",
        "allrecipes": "ok",
    }

    # Step 1: Check price changes via Instacart
    print("\n[1/2] Checking ingredient prices (Instacart)...")
    try:
        price_digests = check_price_changes(config, state)
        all_digests.extend(price_digests)
        print(f"  Instacart: OK — {len(price_digests)} price digest(s) produced")
    except Exception as e:
        error_msg = f"Instacart price check failed: {e}"
        print(f"  ERROR: {error_msg}")
        print("  Continuing to Allrecipes check...")
        errors.append(error_msg)
        platform_status["instacart"] = f"error: {e}"

        # Produce an error digest so the AI agent knows about the failure
        error_digest_id = make_digest_id("platform-error", "instacart", timestamp)
        error_digest = {
            "digest_id": error_digest_id,
            "type": "platform_error",
            "priority": "high",
            "title": "Instacart monitoring failed",
            "summary": f"Instacart price monitoring encountered an error: {e}. Price alerts may be delayed.",
            "data": {
                "platform": "instacart",
                "error": str(e),
                "affected_features": ["price_monitoring", "ingredient_search"],
            },
            "urls": [],
            "timestamp": timestamp,
        }
        all_digests.append(error_digest)

    # Step 2: Check trending recipes via Allrecipes
    print("\n[2/2] Checking trending recipes (Allrecipes)...")
    try:
        trending_digests = check_trending_recipes(config, state)
        all_digests.extend(trending_digests)
        print(f"  Allrecipes: OK — {len(trending_digests)} trending digest(s) produced")
    except Exception as e:
        error_msg = f"Allrecipes trending check failed: {e}"
        print(f"  ERROR: {error_msg}")
        errors.append(error_msg)
        platform_status["allrecipes"] = f"error: {e}"

        # Produce an error digest for Allrecipes failure too
        error_digest_id = make_digest_id("platform-error", "allrecipes", timestamp)
        error_digest = {
            "digest_id": error_digest_id,
            "type": "platform_error",
            "priority": "medium",
            "title": "Allrecipes monitoring failed",
            "summary": f"Allrecipes trending recipe discovery encountered an error: {e}. Recipe suggestions may be delayed.",
            "data": {
                "platform": "allrecipes",
                "error": str(e),
                "affected_features": ["trending_recipes", "recipe_discovery"],
            },
            "urls": [],
            "timestamp": timestamp,
        }
        all_digests.append(error_digest)

    # Save all new digests (idempotent — skips duplicates)
    saved_count = 0
    for digest in all_digests:
        if save_digest(digest):
            saved_count += 1
            state["submitted_digest_ids"].append(digest["digest_id"])

    # Update state
    state["last_run"] = timestamp
    state["last_platform_status"] = platform_status
    save_state(state)

    summary = {
        "run_timestamp": timestamp,
        "digests_produced": len(all_digests),
        "digests_saved": saved_count,
        "errors": errors,
        "platform_status": platform_status,
        "state_file": str(STATE_FILE),
        "digests_file": str(DIGESTS_FILE),
    }

    print(f"\n{'='*50}")
    print(f"Worker run complete:")
    print(f"  Instacart: {platform_status['instacart']}")
    print(f"  Allrecipes: {platform_status['allrecipes']}")
    print(f"  Digests produced: {len(all_digests)}")
    print(f"  Digests saved: {saved_count}")
    if errors:
        print(f"  Errors: {len(errors)}")
        for e in errors:
            print(f"    - {e}")
    print(f"{'='*50}\n")

    return summary


def run_continuous(interval_seconds: int = None):
    """
    Run the worker continuously on a schedule.
    Runs once immediately then waits interval_seconds between runs.
    """
    config = load_config()
    interval = interval_seconds or config.get("check_interval_seconds", 3600)

    print(f"Starting continuous worker (interval: {interval}s)")
    print("Press Ctrl+C to stop\n")

    while True:
        try:
            run_once(config)
        except KeyboardInterrupt:
            print("\nWorker stopped by user.")
            break
        except Exception as e:
            print(f"Unexpected error in worker run: {e}")
            print("Will retry on next cycle.")

        print(f"Next run in {interval} seconds...")
        try:
            time.sleep(interval)
        except KeyboardInterrupt:
            print("\nWorker stopped by user.")
            break


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Recipe & Grocery Background Worker")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run once and exit (default: run continuously)"
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=None,
        help="Interval between runs in seconds (overrides config)"
    )
    args = parser.parse_args()

    if args.once:
        run_once()
    else:
        run_continuous(interval_seconds=args.interval)