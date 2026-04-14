import requests
import json
import time
import uuid

BASE_URL = "https://www.instacart.com"
GRAPHQL_URL = f"{BASE_URL}/graphql"

SEARCH_HASH = "edb3181e1e0bf2b2b8e377d2c2082b82eee2448a4bf417a3ca549647a39b28d5"

DEFAULT_POSTAL_CODE = "94105"

# Shop IDs discovered from browser traffic analysis
# These are the stores Instacart searches across in the SF area
DEFAULT_SHOP_IDS = [
    "9501", "521051", "12", "7517", "40", "47", "12802", "21", "55", "56",
    "11", "8719", "21340", "342541", "5895", "1", "38", "367645", "86095",
    "13", "521021", "4", "74", "24441", "415024", "8784", "14432", "6",
    "219", "10828", "14686", "42", "5153", "54", "59", "2198", "46",
    "6819", "1437", "1438", "27", "396578", "625", "39", "16643968",
    "26077", "13399", "15869", "11325", "19", "20", "36", "10861",
    "92271", "9", "3", "14", "2154", "64", "13985", "17557", "2125",
    "518350", "33", "17796", "157400", "513506", "94970", "35", "52",
    "86016", "396062", "99460", "48", "67", "13820", "68", "129784",
    "129785", "103131", "136070", "166309", "128141", "125749", "418860",
    "222765", "358085", "315224", "317437", "319164", "318339", "376290",
    "396213", "358500", "360486", "374732", "374719", "402387", "514691",
    "415594", "483360", "508770", "502082", "500068", "504483", "502699",
    "555920", "538308", "540379", "550442", "540595", "555455", "598116",
    "595347", "743451", "748276", "762581", "769275", "16638953",
    "16643311", "16667185", "16643491", "16657732", "16666593", "16668155",
    "16692106", "16699676", "16702472", "16704803", "16703705", "16712663",
    "16713645", "16715683", "16717695", "16723061", "75"
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "content-type": "application/json",
    "Referer": "https://www.instacart.com/store/s?k=chicken+breast",
    "sec-ch-ua": '"Chromium";v="140", "Not=A?Brand";v="24", "Brave";v="140"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "sec-gpc": "1",
    "x-client-identifier": "web",
    "x-ic-view-layer": "true",
}

SESSION = requests.Session()


def _ensure_session():
    """
    Visit Instacart homepage to pick up cookies.

    Note: The __Host-instacart_sid session cookie requires JavaScript
    execution and cannot be obtained with plain HTTP requests.
    This is a known limitation documented in api-spec-instacart.md.
    Without this cookie, some features may be limited.
    """
    if not SESSION.cookies:
        print("Warming up Instacart session...")
        SESSION.get(
            BASE_URL,
            headers={"User-Agent": HEADERS["User-Agent"], "Accept": "text/html"},
            timeout=15
        )
        time.sleep(1)


def _graphql_get(operation_name: str, variables: dict, sha256_hash: str) -> dict:
    """
    Make a GraphQL GET request to Instacart using a persisted query.

    Key findings from browser analysis:
    - Instacart uses GET (not POST) for search queries
    - Variables and extensions are URL-encoded query parameters
    - Requires x-client-identifier, x-ic-view-layer, x-page-view-id headers
    - Response is Brotli compressed (requires brotli pip package)
    - A unique pageViewId UUID must be included per request
    """
    _ensure_session()

    page_view_id = str(uuid.uuid4())
    variables["pageViewId"] = page_view_id

    params = {
        "operationName": operation_name,
        "variables": json.dumps(variables, separators=(",", ":")),
        "extensions": json.dumps({
            "persistedQuery": {
                "version": 1,
                "sha256Hash": sha256_hash
            }
        }, separators=(",", ":")),
    }

    headers = {
        **HEADERS,
        "x-page-view-id": page_view_id,
        "x-ic-qp": str(uuid.uuid4()),
    }

    for attempt in range(3):
        try:
            response = SESSION.get(
                GRAPHQL_URL,
                headers=headers,
                params=params,
                timeout=15
            )

            if response.status_code == 429:
                wait = 2 ** attempt
                print(f"Rate limited by Instacart. Waiting {wait}s...")
                time.sleep(wait)
                continue

            if response.status_code == 403:
                raise RuntimeError(
                    "Instacart 403 Forbidden - missing session cookie. "
                    "__Host-instacart_sid requires JavaScript execution."
                )

            if response.status_code == 400:
                raise RuntimeError(
                    f"Instacart 400 Bad Request. Response: {response.text[:200]}"
                )

            response.raise_for_status()
            data = response.json()

            if "errors" in data:
                raise RuntimeError(f"GraphQL errors: {data['errors']}")

            return data

        except RuntimeError:
            raise
        except Exception as e:
            if attempt == 2:
                raise RuntimeError(f"Instacart request failed after 3 attempts: {e}")
            time.sleep(2 ** attempt)


def search_products(
    query: str,
    zip_code: str = None,
    store: str = None,
    page: int = 1,
    limit: int = 10
) -> list[dict]:
    """
    Search for grocery products on Instacart.

    Uses the SearchCrossRetailerGroupResults GraphQL operation discovered
    via browser traffic analysis. Results are grouped by retailer then
    flattened into a single list.

    Known limitations:
    - Full session auth requires JavaScript execution
    - Without __Host-instacart_sid some stores return empty item arrays
    - Shop IDs are hardcoded from SF area discovery session
    - Store name filtering is not available in the response data
    - Postal code affects pricing but shopIds list may not match your area
    """
    postal_code = zip_code or DEFAULT_POSTAL_CODE

    variables = {
        "overrideFeatureStates": [],
        "searchSource": "cross_retailer_search",
        "query": query,
        "shopIds": DEFAULT_SHOP_IDS,
        "disableAutocorrect": False,
        "includeDebugInfo": False,
        "autosuggestImpressionId": None,
        "first": 7,
        "shopId": "0",
        "zoneId": "1",
        "postalCode": postal_code,
    }

    try:
        data = _graphql_get(
            "SearchCrossRetailerGroupResults",
            variables,
            SEARCH_HASH
        )
    except RuntimeError as e:
        print(f"Instacart search error: {e}")
        return [{
            "error": str(e),
            "query": query,
            "note": "Instacart search encountered an error. See api-spec-instacart.md."
        }]

    results = []
    search_results = data.get("data", {}).get(
        "searchCrossRetailerGroupResults", {}
    )

    for retailer_group in search_results.get("results", []):
        retailer_id = retailer_group.get("retailerId", "")
        shop_id = retailer_group.get("shopId", "")

        for item in retailer_group.get("items", []):
            # Skip None or items with no name
            if not item or not item.get("name"):
                continue

            # Safely extract price — can be None for some items
            price_data = item.get("price") or {}
            price_section = price_data.get("viewSection") or {}
            price_str = price_section.get("priceString", "")
            price_value = price_section.get("priceValueString", "")

            # Safely extract availability
            availability = item.get("availability") or {}
            available = availability.get("available", False)
            stock_level = availability.get("stockLevel", "unknown")

            # Safely extract image
            view_section = item.get("viewSection") or {}
            item_image = view_section.get("itemImage") or {}
            image_url = item_image.get("url", "")

            results.append({
                "product_id": item.get("id", ""),
                "product_name": item.get("name", ""),
                "brand": item.get("brandName", ""),
                "price": price_str,
                "price_value": float(price_value) if price_value else None,
                "size": item.get("size", ""),
                "available": available,
                "stock_level": stock_level,
                "retailer_id": retailer_id,
                "shop_id": shop_id,
                "image_url": image_url,
                "product_url": f"{BASE_URL}/products/{item.get('evergreenUrl', '')}",
            })

    offset = (page - 1) * limit
    return results[offset:offset + limit]


def get_product_details(product_id: str = None, url: str = None) -> dict:
    """
    Get full product details by ID or URL.

    Falls back to search-based lookup since the Items GraphQL operation
    requires a valid authenticated session with __Host-instacart_sid.
    This is a known limitation documented in api-spec-instacart.md.
    """
    if not product_id and not url:
        raise ValueError("Must provide either product_id or url")

    if url and not product_id:
        parts = url.rstrip("/").split("/")
        product_id = parts[-1] if parts else None

    results = search_products(product_id or "", limit=1)
    if results and not results[0].get("error"):
        return results[0]

    return {
        "product_id": product_id,
        "error": "Could not fetch product details",
        "note": "Full product details require Instacart authentication"
    }


def list_departments(postal_code: str = None) -> list[dict]:
    """
    Return known Instacart product departments.
    Discovered from site navigation structure analysis.
    """
    return [
        {"id": "fresh", "name": "Fresh"},
        {"id": "produce", "name": "Produce"},
        {"id": "meat", "name": "Meat & Seafood"},
        {"id": "dairy", "name": "Dairy & Eggs"},
        {"id": "bakery", "name": "Bakery"},
        {"id": "frozen", "name": "Frozen"},
        {"id": "pantry", "name": "Pantry"},
        {"id": "snacks", "name": "Snacks & Candy"},
        {"id": "beverages", "name": "Beverages"},
        {"id": "household", "name": "Household"},
        {"id": "personal_care", "name": "Personal Care"},
        {"id": "baby", "name": "Baby"},
        {"id": "pets", "name": "Pets"},
    ]


# -------------------------------------------------------
# Cart operations
# Without __Host-instacart_sid we use a local demo cart.
# Real cart operations require authenticated Instacart session.
# -------------------------------------------------------

_local_cart = {}


def add_to_cart(product_id: str, quantity: int = 1,
                zip_code: str = None, store: str = None) -> dict:
    """
    Add a product to the cart.

    DESTRUCTIVE OPERATION — modifies cart state.

    Uses local demo cart since real Instacart cart mutations require
    the __Host-instacart_sid session cookie which needs JavaScript.
    Real implementation would use the ActiveCartId + CartData GraphQL
    operations discovered during API analysis.
    """
    if not product_id:
        raise ValueError("product_id is required")

    if product_id in _local_cart:
        _local_cart[product_id]["quantity"] += quantity
    else:
        _local_cart[product_id] = {
            "product_id": product_id,
            "quantity": quantity,
            "added_at": time.time()
        }

    return {
        "success": True,
        "message": f"Added {quantity}x {product_id} to cart",
        "note": "Using local demo cart — real cart requires authentication",
        "cart": get_cart()
    }


def get_cart(zip_code: str = None, store: str = None) -> dict:
    """
    Get current cart contents.
    Returns local demo cart state.
    """
    items = list(_local_cart.values())
    return {
        "items": items,
        "item_count": sum(i["quantity"] for i in items),
        "subtotal": None,
        "note": "Using local demo cart — real cart requires authentication",
    }


def remove_from_cart(product_id: str,
                     zip_code: str = None, store: str = None) -> dict:
    """
    Remove a product from the cart.

    DESTRUCTIVE OPERATION — modifies cart state.
    """
    if not product_id:
        raise ValueError("product_id is required")

    if product_id in _local_cart:
        del _local_cart[product_id]
        return {
            "success": True,
            "message": f"Removed {product_id} from cart",
            "cart": get_cart()
        }

    return {
        "success": False,
        "message": f"{product_id} not found in cart",
        "cart": get_cart()
    }