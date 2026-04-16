import json
import os
import time
from pathlib import Path
from datetime import datetime, timezone

# -------------------------------------------------------
# Instacart Authentication via Playwright
#
# Instacart sets __Host-instacart_sid via JavaScript after
# page load. Plain HTTP requests cannot get this cookie.
# We use Playwright (headless Chromium) to load the page,
# wait for JavaScript to run, then extract all cookies.
#
# Cookies are persisted to disk so both the foreground MCP
# server and background worker can reuse them without
# launching a browser every time.
# -------------------------------------------------------

CREDENTIALS_DIR = Path("data")
CREDENTIALS_FILE = CREDENTIALS_DIR / "instacart_session.json"

# How long before we consider the session expired and refresh
SESSION_MAX_AGE_SECONDS = 3600  # 1 hour


def _session_is_fresh() -> bool:
    """
    Check if we have a saved session that is still fresh enough to use.
    """
    if not CREDENTIALS_FILE.exists():
        return False
    try:
        with open(CREDENTIALS_FILE) as f:
            data = json.load(f)
        saved_at = data.get("saved_at", 0)
        age = time.time() - saved_at
        return age < SESSION_MAX_AGE_SECONDS
    except Exception:
        return False


def _load_saved_session() -> dict:
    """
    Load saved session cookies from disk.
    Returns dict with cookies and saved_at timestamp.
    """
    try:
        with open(CREDENTIALS_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def _save_session(cookies: list):
    """
    Save session cookies to disk.
    """
    CREDENTIALS_DIR.mkdir(exist_ok=True)
    data = {
        "cookies": cookies,
        "saved_at": time.time(),
        "saved_at_iso": datetime.now(timezone.utc).isoformat(),
    }
    with open(CREDENTIALS_FILE, "w") as f:
        json.dump(data, f, indent=2)
    print(f"  Session saved to {CREDENTIALS_FILE}")


def get_instacart_session(force_refresh: bool = False) -> dict:
    """
    Get a valid Instacart session, either from disk cache or
    by launching a headless browser to obtain fresh cookies.

    Returns a dict mapping cookie name -> cookie value.
    The most important cookie is __Host-instacart_sid.

    Args:
        force_refresh: If True, always launch browser even if cache is fresh.
    """
    # Return cached session if still fresh
    if not force_refresh and _session_is_fresh():
        print("  Using cached Instacart session")
        data = _load_saved_session()
        cookies = data.get("cookies", [])
        return {c["name"]: c["value"] for c in cookies}

    print("  Launching headless browser to obtain Instacart session...")

    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-blink-features=AutomationControlled",
                ]
            )

            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1280, "height": 800},
            )

            page = context.new_page()

            print("  Navigating to Instacart...")
            try:
                page.goto(
                    "https://www.instacart.com",
                    wait_until="domcontentloaded",
                    timeout=30000
                )
            except Exception:
                # Even if timeout, cookies may have been set
                pass

            # Wait for JavaScript to run and set session cookies
            print("  Waiting for session cookies to be set...")
            time.sleep(5)

            # Try to trigger more cookie setting by doing a search
            try:
                page.goto(
                    "https://www.instacart.com/store/s?k=chicken",
                    wait_until="domcontentloaded",
                    timeout=20000
                )
                time.sleep(3)
            except Exception:
                pass

            # Extract all cookies
            cookies = context.cookies()
            browser.close()

            # Find the important session cookie
            sid_cookie = next(
                (c for c in cookies if c["name"] == "__Host-instacart_sid"),
                None
            )

            if sid_cookie:
                print(f"  Got __Host-instacart_sid: {sid_cookie['value'][:20]}...")
            else:
                print("  Warning: __Host-instacart_sid not found in cookies")
                print(f"  Got {len(cookies)} cookies: {[c['name'] for c in cookies]}")

            # Save to disk
            _save_session(cookies)

            return {c["name"]: c["value"] for c in cookies}

    except ImportError:
        print("  Playwright not installed. Run: pip install playwright && playwright install chromium")
        return {}
    except Exception as e:
        print(f"  Browser auth failed: {e}")
        print("  Falling back to unauthenticated session")
        return {}


def apply_session_to_requests(session, cookie_dict: dict):
    """
    Apply cookies from our Playwright session to a requests.Session object.
    This lets our existing HTTP client benefit from the browser-obtained cookies.

    Args:
        session: requests.Session object
        cookie_dict: dict of cookie name -> value from get_instacart_session()
    """
    for name, value in cookie_dict.items():
        session.cookies.set(name, value, domain=".instacart.com")
    print(f"  Applied {len(cookie_dict)} cookies to requests session")


def refresh_session_if_needed(session) -> bool:
    """
    Check if we need to refresh the Instacart session and do so if needed.
    Returns True if session was refreshed, False if still valid.

    Called by the background worker at the start of each run.
    """
    if _session_is_fresh():
        # Apply existing cookies to the session
        data = _load_saved_session()
        cookies = {c["name"]: c["value"] for c in data.get("cookies", [])}
        apply_session_to_requests(session, cookies)
        return False

    # Need fresh cookies
    print("  Instacart session expired or missing. Refreshing...")
    cookies = get_instacart_session(force_refresh=True)
    if cookies:
        apply_session_to_requests(session, cookies)
        return True
    return False