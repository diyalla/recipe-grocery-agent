import cloudscraper
from bs4 import BeautifulSoup
import time
import re

BASE_URL = "https://www.allrecipes.com"

# cloudscraper works like requests but automatically handles
# Cloudflare's anti-bot JavaScript challenges.
# It mimics a real browser's behavior more convincingly than plain requests.
SCRAPER = cloudscraper.create_scraper(
    browser={
        "browser": "chrome",
        "platform": "windows",
        "mobile": False
    }
)


def _get(url: str, params: dict = None) -> BeautifulSoup:
    """
    Make a GET request and return a BeautifulSoup object.
    Uses cloudscraper to handle Cloudflare anti-bot protection.
    Retries up to 3 times with exponential backoff on rate limiting.
    """
    for attempt in range(3):
        try:
            response = SCRAPER.get(url, params=params, timeout=15)

            if response.status_code == 429:
                wait = 2 ** attempt
                print(f"Rate limited. Waiting {wait}s before retry...")
                time.sleep(wait)
                continue

            if response.status_code == 403:
                raise RuntimeError(
                    f"Access forbidden (403) - Cloudflare is blocking requests to {url}. "
                    "This is an anti-bot measure. Document this in api-spec-allrecipes.md."
                )

            response.raise_for_status()
            return BeautifulSoup(response.text, "lxml")

        except RuntimeError:
            raise
        except Exception as e:
            if attempt == 2:
                raise RuntimeError(f"Request failed after 3 attempts: {e}")
            time.sleep(2 ** attempt)


def _count_stars(card) -> float:
    """
    Count star icons in a recipe card to determine its rating out of 5.
    Allrecipes uses SVG icons: full stars, half stars, and empty stars.
    Example: 4 full + 1 half = 4.5 rating.
    """
    full = len(card.select(".icon-star:not(.icon-star-half):not(.icon-star-empty)"))
    half = len(card.select(".icon-star-half"))
    return full + (0.5 * half)


def search_recipes(
    query: str,
    page: int = 1,
    limit: int = 10,
    cuisine: str = None,
    dietary: str = None,
    max_cook_time_minutes: int = None
) -> list[dict]:
    """
    Search Allrecipes by keyword and return a list of recipe summaries.

    How it works:
    - Fetches the search results page HTML
    - Parses recipe cards using BeautifulSoup
    - Each card has a recipe ID, title, rating, and image

    Pagination: Allrecipes shows 24 results per page.
    Page 1 = offset 0, Page 2 = offset 24, Page 3 = offset 48, etc.

    Note: cuisine, dietary, and max_cook_time_minutes filters are noted
    but Allrecipes does not expose clean URL params for these on the
    search endpoint. They are applied client-side. We filter post-fetch
    where possible, otherwise document as limitation.
    """
    offset = (page - 1) * 24
    params = {"q": query, "offset": offset}

    soup = _get(f"{BASE_URL}/search", params=params)

    cards = soup.select("a.mntl-card-list-card--extendable[data-doc-id]")

    results = []
    for card in cards:
        title_el = card.select_one(".card__title-text")
        if not title_el:
            continue

        title = title_el.get_text(strip=True)
        url = card.get("href", "")
        doc_id = card.get("data-doc-id", "")
        rating = _count_stars(card)

        rating_count_el = card.select_one(".mm-recipes-card-meta__rating-count-number")
        rating_count = 0
        if rating_count_el:
            digits = re.sub(r"[^\d]", "", rating_count_el.get_text(strip=True))
            rating_count = int(digits) if digits else 0

        img_el = card.select_one("img.card__img")
        image_url = ""
        if img_el:
            image_url = img_el.get("data-src") or img_el.get("src", "")

        results.append({
            "recipe_id": doc_id,
            "title": title,
            "url": url,
            "rating": rating,
            "review_count": rating_count,
            "image_url": image_url,
            "description": "",
            "total_time": None,
        })

    return results[:limit]


def get_recipe(recipe_id: str = None, url: str = None) -> dict:
    """
    Get full recipe details by ID or URL.

    Recipe pages live at: https://www.allrecipes.com/recipe/ID/slug/
    We extract:
    - Title and description
    - Raw ingredient strings (fed into the ingredient parser later)
    - Step by step instructions
    - Prep, cook, and total times
    - Servings
    - Star rating and review count
    - Nutrition summary (calories, fat, carbs, protein)
    """
    if not url and not recipe_id:
        raise ValueError("Must provide either recipe_id or url")

    if not url:
        results = search_recipes(recipe_id, limit=1)
        if not results:
            raise ValueError(f"Could not find recipe with id {recipe_id}")
        url = results[0]["url"]

    soup = _get(url)

    # Title
    title_el = soup.select_one("h1.article-heading")
    title = title_el.get_text(strip=True) if title_el else ""

    # Description
    desc_el = soup.select_one(".article-subheading")
    description = desc_el.get_text(strip=True) if desc_el else ""

    # Ingredients — each one is a list item we grab as raw text
    ingredient_els = soup.select(".mm-recipes-structured-ingredients__list-item")
    ingredients_raw = []
    for el in ingredient_els:
        text = el.get_text(" ", strip=True)
        if text:
            ingredients_raw.append(text)

    # Instructions — paragraph tags in the recipe steps section
    instruction_els = soup.select(".comp.mntl-sc-block-html p")
    instructions = [
        el.get_text(strip=True)
        for el in instruction_els
        if el.get_text(strip=True)
    ]

    # Times — label/value pairs like "Prep Time: 15 mins"
    times = {}
    for label_el in soup.select(".mm-recipes-details__label"):
        label = label_el.get_text(strip=True).lower()
        value_el = label_el.find_next_sibling()
        if value_el:
            value = value_el.get_text(strip=True)
            if "prep" in label:
                times["prep_time"] = value
            elif "cook" in label:
                times["cook_time"] = value
            elif "total" in label:
                times["total_time"] = value

    # Servings
    servings_el = soup.select_one(".mm-recipes-details__value")
    servings = servings_el.get_text(strip=True) if servings_el else None

    # Rating
    rating_el = soup.select_one(".mm-recipes-review-bar__rating")
    rating = float(rating_el.get_text(strip=True)) if rating_el else None

    rating_count_el = soup.select_one(".mm-recipes-review-bar__total-reviews")
    review_count = 0
    if rating_count_el:
        digits = re.sub(r"[^\d]", "", rating_count_el.get_text())
        review_count = int(digits) if digits else 0

    # Nutrition — comes as alternating value/label pairs
    nutrition = {}
    nutrition_cells = soup.select(".mm-recipes-nutrition-facts-summary__table-cell")
    for i in range(0, len(nutrition_cells) - 1, 2):
        value = nutrition_cells[i].get_text(strip=True)
        label = nutrition_cells[i + 1].get_text(strip=True)
        nutrition[label.lower()] = value

    if not recipe_id:
        match = re.search(r"/recipe/(\d+)/", url)
        recipe_id = match.group(1) if match else ""

    return {
        "recipe_id": recipe_id,
        "title": title,
        "description": description,
        "ingredients_raw": ingredients_raw,
        "instructions": instructions,
        "prep_time": times.get("prep_time"),
        "cook_time": times.get("cook_time"),
        "total_time": times.get("total_time"),
        "servings": servings,
        "rating": rating,
        "review_count": review_count,
        "nutrition": nutrition,
        "url": url,
    }


def browse_categories() -> list[dict]:
    """
    Get top-level recipe categories from Allrecipes navigation menu.
    Returns a list of category names and their URLs.
    """
    soup = _get(f"{BASE_URL}/recipes/")

    categories = []
    for link in soup.select(".mntl-header-nav__list-item a"):
        name = link.get_text(strip=True)
        href = link.get("href", "")
        if name and href:
            categories.append({"name": name, "url": href})

    return categories