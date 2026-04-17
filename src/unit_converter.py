# -------------------------------------------------------
# Unit Conversion for Recipe Cost Estimation
#
# The challenge requires documenting our approach to
# ingredient-to-grocery matching with unit conversion.
#
# Problem: A recipe says "2 cups flour" but Instacart
# sells flour in 5lb bags. We need to convert between
# recipe units and grocery package units to estimate
# how much of a package is needed.
#
# Our approach:
# 1. Normalize all quantities to a base unit (grams or ml)
# 2. Look up the package size from Instacart
# 3. Calculate what fraction of the package is needed
# 4. Multiply package price by that fraction
#
# Coverage:
# - Volume: cups, tablespoons, teaspoons, ml, liters
# - Weight: pounds, ounces, grams, kilograms
# - Count: eggs, cloves, cans (no conversion needed)
#
# Limitations:
# - Cannot convert between volume and weight without
#   knowing ingredient density (e.g. 1 cup flour ≠ 1 cup water)
# - Package size parsing is best-effort (regex on size string)
# - Some units (pinch, dash, to taste) cannot be converted
# -------------------------------------------------------

import re
from typing import Optional

# Volume conversions to milliliters
VOLUME_TO_ML = {
    "ml": 1.0,
    "milliliter": 1.0,
    "milliliters": 1.0,
    "l": 1000.0,
    "liter": 1000.0,
    "liters": 1000.0,
    "tsp": 4.929,
    "teaspoon": 4.929,
    "teaspoons": 4.929,
    "tbsp": 14.787,
    "tablespoon": 14.787,
    "tablespoons": 14.787,
    "fl oz": 29.574,
    "fluid ounce": 29.574,
    "fluid ounces": 29.574,
    "cup": 236.588,
    "cups": 236.588,
    "pt": 473.176,
    "pint": 473.176,
    "pints": 473.176,
    "qt": 946.353,
    "quart": 946.353,
    "quarts": 946.353,
    "gal": 3785.41,
    "gallon": 3785.41,
    "gallons": 3785.41,
}

# Weight conversions to grams
WEIGHT_TO_GRAMS = {
    "g": 1.0,
    "gram": 1.0,
    "grams": 1.0,
    "kg": 1000.0,
    "kilogram": 1000.0,
    "kilograms": 1000.0,
    "oz": 28.3495,
    "ounce": 28.3495,
    "ounces": 28.3495,
    "lb": 453.592,
    "lbs": 453.592,
    "pound": 453.592,
    "pounds": 453.592,
}


def normalize_to_base(quantity: float, unit: str) -> tuple[Optional[float], str]:
    """
    Convert a quantity and unit to a base unit.
    Returns (normalized_quantity, base_unit) where base_unit is 'ml' or 'g'.
    Returns (None, 'count') for count units that cannot be converted.
    """
    unit_lower = unit.lower().strip() if unit else ""

    if unit_lower in VOLUME_TO_ML:
        return quantity * VOLUME_TO_ML[unit_lower], "ml"

    if unit_lower in WEIGHT_TO_GRAMS:
        return quantity * WEIGHT_TO_GRAMS[unit_lower], "g"

    return None, "count"


def parse_package_size(size_str: str) -> tuple[Optional[float], Optional[str]]:
    """
    Parse a package size string like "16 oz", "2.5 lb", "500 ml", "1 l"
    Returns (quantity, unit) or (None, None) if parsing fails.
    """
    if not size_str:
        return None, None

    size_str = size_str.lower().strip()

    # Match patterns like "16 oz", "2.5 lb", "500ml", "1.5 l"
    patterns = [
        r'(\d+(?:\.\d+)?)\s*(fl oz|fluid ounce[s]?|oz|ounce[s]?|lb[s]?|pound[s]?|g|gram[s]?|kg|kilogram[s]?|ml|milliliter[s]?|l|liter[s]?)',
    ]

    for pattern in patterns:
        match = re.search(pattern, size_str)
        if match:
            qty = float(match.group(1))
            unit = match.group(2).strip()
            return qty, unit

    return None, None


def estimate_fraction_needed(
    recipe_quantity: float,
    recipe_unit: str,
    package_size_str: str,
) -> Optional[float]:
    """
    Estimate what fraction of a grocery package is needed for a recipe.

    Example:
        recipe needs 2 cups flour
        package is 5 lb bag
        → cannot convert (volume vs weight) → returns None

        recipe needs 8 oz chicken
        package is 2.5 lb
        → 8 oz = 226.8g, 2.5 lb = 1134g → needs 226.8/1134 = 0.2 of package

    Returns a float between 0 and 1+ representing fraction of package needed.
    Returns None if conversion is not possible.
    """
    # Normalize recipe quantity
    recipe_base, recipe_base_unit = normalize_to_base(recipe_quantity, recipe_unit)
    if recipe_base is None:
        return None

    # Parse and normalize package size
    pkg_qty, pkg_unit = parse_package_size(package_size_str)
    if pkg_qty is None:
        return None

    pkg_base, pkg_base_unit = normalize_to_base(pkg_qty, pkg_unit)
    if pkg_base is None:
        return None

    # Can only compare same base units
    if recipe_base_unit != pkg_base_unit:
        return None

    if pkg_base == 0:
        return None

    return recipe_base / pkg_base


def calculate_ingredient_cost(
    recipe_quantity: float,
    recipe_unit: str,
    package_price: float,
    package_size_str: str,
) -> dict:
    """
    Calculate the cost of an ingredient given recipe quantity and package info.

    Returns a dict with:
    - cost: estimated cost in dollars
    - fraction_used: fraction of package needed (None if conversion failed)
    - conversion_applied: whether unit conversion was used
    - note: explanation of the calculation
    """
    fraction = estimate_fraction_needed(recipe_quantity, recipe_unit, package_size_str)

    if fraction is not None:
        cost = package_price * min(fraction, 1.0)
        return {
            "cost": round(cost, 2),
            "fraction_used": round(fraction, 3),
            "conversion_applied": True,
            "note": f"Used {fraction:.1%} of package ({package_size_str}) at ${package_price:.2f}",
        }
    else:
        # Fall back to full package price
        return {
            "cost": package_price,
            "fraction_used": None,
            "conversion_applied": False,
            "note": f"Could not convert {recipe_quantity} {recipe_unit} to package unit ({package_size_str}). Using full package price.",
        }
