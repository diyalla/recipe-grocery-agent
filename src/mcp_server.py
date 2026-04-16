import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp.server.fastmcp import FastMCP
from src.clients.allrecipes import search_recipes as ar_search, get_recipe as ar_get_recipe
from src.clients.instacart import (
    search_products as ic_search,
    get_product_details as ic_get_product,
    add_to_cart as ic_add_to_cart,
    get_cart as ic_get_cart,
    remove_from_cart as ic_remove_from_cart,
)
from src.parser.ingredient_parser import parse_ingredient

# -------------------------------------------------------
# FastMCP is a simpler way to build MCP servers.
# Instead of manually defining tool schemas, we just write
# normal Python functions with type hints and docstrings.
# FastMCP reads those and automatically builds the tool
# definitions that the AI agent sees.
# -------------------------------------------------------
mcp = FastMCP("recipe-grocery-agent")


@mcp.tool()
def search_recipes(
    query: str,
    cuisine: str = None,
    dietary: str = None,
    max_cook_time_minutes: int = None,
    page: int = 1,
    limit: int = 10
) -> str:
    """
    Search Allrecipes for recipes by keyword.
    Returns a list of recipes with titles, ratings, and URLs.

    Args:
        query: Search phrase e.g. 'pad thai', 'chocolate cake'
        cuisine: Optional cuisine filter e.g. 'thai', 'italian'
        dietary: Optional dietary filter e.g. 'vegetarian', 'vegan'
        max_cook_time_minutes: Optional maximum cook time in minutes
        page: Page number, default 1
        limit: Number of results, default 10
    """
    results = ar_search(
        query=query,
        page=page,
        limit=limit,
        cuisine=cuisine,
        dietary=dietary,
        max_cook_time_minutes=max_cook_time_minutes
    )
    return json.dumps(results, indent=2)


@mcp.tool()
def get_recipe(recipe_id: str = None, url: str = None) -> str:
    """
    Get full recipe details including ingredients, instructions,
    cook time, nutrition info, and parsed ingredient breakdown.

    Args:
        recipe_id: Allrecipes recipe ID
        url: Full Allrecipes recipe URL
    """
    result = ar_get_recipe(recipe_id=recipe_id, url=url)

    # Parse ingredients using our ingredient parser
    if result.get("ingredients_raw"):
        parsed = []
        for raw in result["ingredients_raw"]:
            p = parse_ingredient(raw)
            parsed.append({
                "raw": p.raw,
                "quantity": p.quantity,
                "unit": p.unit,
                "item": p.item,
                "modifiers": p.modifiers,
                "preparation": p.preparation,
                "confidence": p.confidence
            })
        result["ingredients_parsed"] = parsed

    return json.dumps(result, indent=2)


@mcp.tool()
def search_products(
    query: str,
    zip_code: str = None,
    store: str = None,
    page: int = 1,
    limit: int = 10
) -> str:
    """
    Search Instacart for grocery products.
    Returns product names, prices, and availability.

    Args:
        query: Product search phrase e.g. 'chicken breast', 'olive oil'
        zip_code: ZIP code for store and pricing context
        store: Optional store name filter e.g. 'Safeway', 'Costco'
        page: Page number, default 1
        limit: Number of results, default 10
    """
    results = ic_search(
        query=query,
        zip_code=zip_code,
        store=store,
        page=page,
        limit=limit
    )
    return json.dumps(results, indent=2)


@mcp.tool()
def get_product_details(product_id: str = None, url: str = None) -> str:
    """
    Get full details for a specific Instacart product.

    Args:
        product_id: Instacart product ID
        url: Full Instacart product URL
    """
    result = ic_get_product(product_id=product_id, url=url)
    return json.dumps(result, indent=2)


@mcp.tool()
def estimate_recipe_cost(
    recipe_id: str = None,
    url: str = None,
    zip_code: str = "94105",
    store: str = None,
    servings: int = None
) -> str:
    """
    Estimate the grocery cost of a recipe by searching Instacart
    for each ingredient and calculating a total.

    Args:
        recipe_id: Allrecipes recipe ID
        url: Full Allrecipes recipe URL
        zip_code: ZIP code for pricing context
        store: Preferred store for pricing
        servings: Scale recipe to this many servings
    """
    if not recipe_id and not url:
        return json.dumps({"error": "Must provide recipe_id or url"})

    # Fetch the recipe
    recipe = ar_get_recipe(recipe_id=recipe_id, url=url)
    if not recipe.get("title"):
        return json.dumps({"error": "Could not fetch recipe"})

    ingredient_costs = []
    total_estimated = 0.0
    unmatched = []

    for raw_ingredient in recipe.get("ingredients_raw", []):
        parsed = parse_ingredient(raw_ingredient)

        # Search Instacart for the ingredient
        search_query = parsed.item if parsed.item else raw_ingredient
        products = ic_search(query=search_query, zip_code=zip_code, limit=3)

        # Find the first available product with a price
        matched_product = None
        for product in products:
            if product.get("available") and product.get("price_value"):
                matched_product = product
                break

        if matched_product:
            price_value = matched_product.get("price_value", 0)
            total_estimated += price_value
            ingredient_costs.append({
                "ingredient_raw": raw_ingredient,
                "ingredient_parsed": parsed.item,
                "matched_product": matched_product.get("product_name"),
                "product_price": matched_product.get("price"),
                "price_value": price_value,
                "match_confidence": parsed.confidence,
                "note": "Price is per package/unit as listed — unit conversion not applied"
            })
        else:
            unmatched.append(raw_ingredient)
            ingredient_costs.append({
                "ingredient_raw": raw_ingredient,
                "ingredient_parsed": parsed.item,
                "matched_product": None,
                "product_price": None,
                "price_value": None,
                "match_confidence": parsed.confidence,
                "note": "No matching product found on Instacart"
            })

    return json.dumps({
        "recipe_title": recipe.get("title"),
        "recipe_url": recipe.get("url"),
        "servings": recipe.get("servings"),
        "ingredient_breakdown": ingredient_costs,
        "total_estimated_cost": round(total_estimated, 2),
        "unmatched_ingredients": unmatched,
        "limitations": [
            "Prices are per package/unit as listed on Instacart",
            "Unit conversion not applied",
            "Some ingredients may not have pricing without full Instacart auth",
            "Cost is an estimate only"
        ]
    }, indent=2)


@mcp.tool()
def find_substitutions(
    ingredient: str,
    reason: str,
    dietary_constraint: str = None,
    zip_code: str = "94105"
) -> str:
    """
    Find ingredient substitutions with grocery pricing.
    Useful for allergies, dietary restrictions, or unavailable items.

    Args:
        ingredient: The ingredient to substitute e.g. 'peanuts', 'butter'
        reason: Why a substitution is needed: allergy, dietary, unavailable, preference
        dietary_constraint: Specific constraint e.g. nut-free, dairy-free, vegan
        zip_code: ZIP code for pricing context
    """
    ingredient_lower = ingredient.lower().strip()
    reason_lower = reason.lower().strip()
    constraint = (dietary_constraint or "").lower().strip()

    substitutions_db = {
        "peanuts": {
            "allergy": [
                {"substitute": "sunflower seeds", "why": "Similar crunch and protein, nut-free", "notes": "Use same quantity"},
                {"substitute": "pumpkin seeds", "why": "Nut-free, similar texture", "notes": "Use same quantity"},
            ]
        },
        "peanut butter": {
            "allergy": [
                {"substitute": "sunflower seed butter", "why": "Nut-free, same texture", "notes": "1:1 ratio"},
                {"substitute": "tahini", "why": "Nut-free, similar consistency", "notes": "1:1 ratio"},
            ]
        },
        "butter": {
            "dairy": [
                {"substitute": "vegan butter", "why": "Dairy-free, same use", "notes": "1:1 ratio"},
                {"substitute": "coconut oil", "why": "Dairy-free fat substitute", "notes": "Use 3/4 the amount"},
            ],
            "vegan": [
                {"substitute": "vegan butter", "why": "Plant-based, same use", "notes": "1:1 ratio"},
                {"substitute": "coconut oil", "why": "Vegan fat substitute", "notes": "Use 3/4 the amount"},
            ]
        },
        "milk": {
            "dairy": [
                {"substitute": "oat milk", "why": "Dairy-free, neutral flavor", "notes": "1:1 ratio"},
                {"substitute": "almond milk", "why": "Dairy-free, light flavor", "notes": "1:1 ratio"},
            ]
        },
        "eggs": {
            "vegan": [
                {"substitute": "flax egg", "why": "Vegan binder", "notes": "1 tbsp ground flax + 3 tbsp water per egg"},
                {"substitute": "applesauce", "why": "Vegan moisture substitute", "notes": "1/4 cup per egg"},
            ]
        },
        "fish sauce": {
            "vegan": [
                {"substitute": "soy sauce", "why": "Vegan umami substitute", "notes": "Use same quantity"},
                {"substitute": "coconut aminos", "why": "Vegan, slightly sweeter", "notes": "Use same quantity"},
            ],
            "dietary": [
                {"substitute": "soy sauce", "why": "Similar umami flavor", "notes": "Use same quantity"},
            ]
        },
        "chicken": {
            "vegan": [
                {"substitute": "tofu", "why": "High protein vegan alternative", "notes": "Use firm tofu"},
                {"substitute": "jackfruit", "why": "Shredded texture similar to chicken", "notes": "Use young green jackfruit"},
            ],
            "dietary": [
                {"substitute": "tofu", "why": "Plant-based protein", "notes": "Use firm tofu, press dry first"},
                {"substitute": "tempeh", "why": "Meaty texture, high protein", "notes": "Marinate before cooking"},
            ]
        }
    }

    subs = []
    if ingredient_lower in substitutions_db:
        ingredient_subs = substitutions_db[ingredient_lower]
        reason_key = None
        if reason_lower in ingredient_subs:
            reason_key = reason_lower
        elif constraint in ingredient_subs:
            reason_key = constraint
        elif "dietary" in ingredient_subs:
            reason_key = "dietary"
        if reason_key:
            subs = ingredient_subs[reason_key]

    if not subs:
        subs = [{"substitute": f"alternative to {ingredient}", "why": "No specific substitution in database", "notes": "Consult a nutritionist"}]

    result_subs = []
    for sub in subs[:3]:
        products = ic_search(query=sub["substitute"], zip_code=zip_code, limit=1)
        product_info = None
        if products and not products[0].get("error"):
            product_info = {
                "product_name": products[0].get("product_name"),
                "price": products[0].get("price"),
                "available": products[0].get("available")
            }
        result_subs.append({
            "substitute": sub["substitute"],
            "why_it_works": sub["why"],
            "usage_notes": sub["notes"],
            "grocery_match": product_info,
            "confidence": "high" if ingredient_lower in substitutions_db else "low"
        })

    return json.dumps({
        "original_ingredient": ingredient,
        "reason": reason,
        "dietary_constraint": dietary_constraint,
        "substitutions": result_subs
    }, indent=2)


@mcp.tool()
def compare_recipes(
    recipe_ids: list,
    zip_code: str = "94105",
    store: str = None
) -> str:
    """
    Compare 2-3 recipes side by side with a deduplicated combined
    shopping list and shared ingredients highlighted.

    Args:
        recipe_ids: List of 2-3 Allrecipes recipe IDs to compare
        zip_code: ZIP code for pricing context
        store: Preferred store for pricing
    """
    if len(recipe_ids) < 2:
        return json.dumps({"error": "Must provide at least 2 recipe IDs"})
    if len(recipe_ids) > 3:
        return json.dumps({"error": "Maximum 3 recipes for comparison"})

    recipes = []
    all_ingredients = {}

    for recipe_id in recipe_ids:
        recipe = ar_get_recipe(recipe_id=recipe_id)
        if not recipe.get("title"):
            continue

        parsed_ingredients = []
        for raw in recipe.get("ingredients_raw", []):
            parsed = parse_ingredient(raw)
            parsed_ingredients.append({
                "raw": raw,
                "item": parsed.item,
                "quantity": parsed.quantity,
                "unit": parsed.unit
            })

            item_key = (parsed.item or raw).lower().strip()
            if item_key not in all_ingredients:
                all_ingredients[item_key] = {
                    "item": parsed.item or raw,
                    "quantity": parsed.quantity,
                    "unit": parsed.unit,
                    "used_in": [recipe.get("title")]
                }
            else:
                if recipe.get("title") not in all_ingredients[item_key]["used_in"]:
                    all_ingredients[item_key]["used_in"].append(recipe.get("title"))

        recipes.append({
            "recipe_id": recipe_id,
            "title": recipe.get("title"),
            "total_time": recipe.get("total_time"),
            "servings": recipe.get("servings"),
            "rating": recipe.get("rating"),
            "review_count": recipe.get("review_count"),
            "nutrition": recipe.get("nutrition"),
            "url": recipe.get("url"),
            "ingredient_count": len(parsed_ingredients),
            "ingredients": parsed_ingredients
        })

    shared = [
        item for item in all_ingredients.values()
        if len(item["used_in"]) > 1
    ]

    return json.dumps({
        "recipes": recipes,
        "combined_shopping_list": list(all_ingredients.values()),
        "shared_ingredients": shared,
        "total_unique_ingredients": len(all_ingredients),
        "note": "Quantities are per recipe and not merged"
    }, indent=2)


@mcp.tool()
def add_to_cart(
    product_id: str,
    quantity: int = 1,
    zip_code: str = None
) -> str:
    """
    Add a product to the Instacart cart.
    WARNING: This is a destructive operation that modifies cart state.

    Args:
        product_id: Instacart product ID to add
        quantity: Number of units to add, default 1
        zip_code: ZIP code for store context
    """
    result = ic_add_to_cart(
        product_id=product_id,
        quantity=quantity,
        zip_code=zip_code
    )
    return json.dumps(result, indent=2)


@mcp.tool()
def get_cart(zip_code: str = None) -> str:
    """
    Get the current contents of the Instacart cart.

    Args:
        zip_code: ZIP code for store context
    """
    result = ic_get_cart(zip_code=zip_code)
    return json.dumps(result, indent=2)


@mcp.tool()
def remove_from_cart(product_id: str, zip_code: str = None) -> str:
    """
    Remove an item from the Instacart cart.
    WARNING: This is a destructive operation that modifies cart state.

    Args:
        product_id: Product ID of the item to remove
        zip_code: ZIP code for store context
    """
    result = ic_remove_from_cart(
        product_id=product_id,
        zip_code=zip_code
    )
    return json.dumps(result, indent=2)


if __name__ == "__main__":
    mcp.run()