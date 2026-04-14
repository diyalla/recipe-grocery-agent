import re
from dataclasses import dataclass, field
from typing import Optional

# -------------------------------------------------------
# Data structure that holds one parsed ingredient
# -------------------------------------------------------
@dataclass
class ParsedIngredient:
    raw: str
    quantity: Optional[float]
    unit: Optional[str]
    item: str
    modifiers: list[str]
    preparation: Optional[str]
    notes: Optional[str]
    confidence: float


# -------------------------------------------------------
# Known units of measurement
# -------------------------------------------------------
VOLUME_UNITS = {
    "cup", "cups", "c",
    "tablespoon", "tablespoons", "tbsp", "tbs",
    "teaspoon", "teaspoons", "tsp",
    "fluid ounce", "fluid ounces", "fl oz",
    "pint", "pints", "pt",
    "quart", "quarts", "qt",
    "gallon", "gallons", "gal",
    "milliliter", "milliliters", "ml",
    "liter", "liters", "l",
}

WEIGHT_UNITS = {
    "pound", "pounds", "lb", "lbs",
    "ounce", "ounces", "oz",
    "gram", "grams", "g",
    "kilogram", "kilograms", "kg",
}

COUNT_UNITS = {
    "clove", "cloves",
    "slice", "slices",
    "piece", "pieces",
    "can", "cans",
    "package", "packages", "pkg",
    "bunch", "bunches",
    "sprig", "sprigs",
    "stalk", "stalks",
    "head", "heads",
    "ear", "ears",
    "fillet", "fillets",
    "strip", "strips",
    "sheet", "sheets",
    "envelope", "envelopes",
    "bottle", "bottles",
    "jar", "jars",
    "bag", "bags",
    "box", "boxes",
    "container", "containers",
    "loaf", "loaves",
    "stick", "sticks",
    "block", "blocks",
    "drop", "drops",
    "dash", "dashes",
    "pinch", "pinches",
}

ALL_UNITS = VOLUME_UNITS | WEIGHT_UNITS | COUNT_UNITS

# -------------------------------------------------------
# Words that describe HOW something is prepared
# -------------------------------------------------------
PREPARATION_WORDS = {
    "diced", "minced", "chopped", "sliced", "grated", "shredded",
    "crushed", "peeled", "cubed", "halved", "quartered", "julienned",
    "mashed", "pureed", "ground", "crumbled", "beaten", "whipped",
    "melted", "softened", "room temperature", "toasted", "roasted",
    "cooked", "drained", "rinsed", "rinsed and drained", "thawed",
    "divided", "sifted", "packed", "heaping", "leveled",
}

# -------------------------------------------------------
# Words that describe WHAT something is like (adjectives)
# -------------------------------------------------------
MODIFIER_WORDS = {
    "fresh", "frozen", "dried", "canned", "raw", "cooked",
    "large", "medium", "small", "extra-large", "jumbo",
    "boneless", "skinless", "lean", "thick", "thin",
    "whole", "half", "low-fat", "fat-free", "reduced-fat",
    "unsalted", "salted", "sweet", "spicy", "mild",
    "organic", "free-range", "grass-fed",
    "yellow", "white", "red", "green", "black", "purple",
}

# -------------------------------------------------------
# Written-out numbers -> actual numbers
# -------------------------------------------------------
WORD_TO_NUM = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "half": 0.5, "quarter": 0.25, "a": 1, "an": 1,
}

# -------------------------------------------------------
# Unicode fractions -> decimal
# -------------------------------------------------------
UNICODE_FRACTIONS = {
    "½": 0.5, "⅓": 0.333, "⅔": 0.667,
    "¼": 0.25, "¾": 0.75,
    "⅛": 0.125, "⅜": 0.375, "⅝": 0.625, "⅞": 0.875,
}


def parse_quantity(text: str) -> tuple[Optional[float], str]:
    """
    Pull a number out of the start of a string.
    Handles: 1, 1.5, 1/2, 1 1/2, ½, one, 3-4 (ranges take the average)
    Returns the number and whatever text is left over.
    """
    text = text.strip()

    # Replace unicode fractions first
    for uc, val in UNICODE_FRACTIONS.items():
        text = text.replace(uc, f" {val} ")
    text = text.strip()

    # Written-out number at the start (e.g. "one", "two")
    word_match = re.match(r'^(one|two|three|four|five|six|seven|eight|nine|ten|half|quarter|an?)\b', text, re.IGNORECASE)
    if word_match:
        word = word_match.group(1).lower()
        quantity = WORD_TO_NUM.get(word, 1)
        remaining = text[word_match.end():].strip()
        return quantity, remaining

    # Range like "3-4" or "2 to 3" — take the average
    range_match = re.match(r'^(\d+(?:\.\d+)?)\s*(?:-|to)\s*(\d+(?:\.\d+)?)', text)
    if range_match:
        low = float(range_match.group(1))
        high = float(range_match.group(2))
        quantity = (low + high) / 2
        remaining = text[range_match.end():].strip()
        return quantity, remaining

    # Mixed number like "1 1/2"
    mixed_match = re.match(r'^(\d+)\s+(\d+)/(\d+)', text)
    if mixed_match:
        whole = int(mixed_match.group(1))
        num = int(mixed_match.group(2))
        den = int(mixed_match.group(3))
        quantity = whole + num / den
        remaining = text[mixed_match.end():].strip()
        return quantity, remaining

    # Simple fraction like "1/2"
    frac_match = re.match(r'^(\d+)/(\d+)', text)
    if frac_match:
        quantity = int(frac_match.group(1)) / int(frac_match.group(2))
        remaining = text[frac_match.end():].strip()
        return quantity, remaining

    # Plain number like "2" or "1.5"
    num_match = re.match(r'^(\d+(?:\.\d+)?)', text)
    if num_match:
        quantity = float(num_match.group(1))
        remaining = text[num_match.end():].strip()
        return quantity, remaining

    # No number found
    return None, text


def parse_unit(text: str) -> tuple[Optional[str], str]:
    """
    Look for a unit of measurement at the start of the text.
    Returns the unit found and whatever text is left over.
    """
    text = text.strip()

    # Try longest units first so "fluid ounce" matches before "ounce"
    sorted_units = sorted(ALL_UNITS, key=len, reverse=True)
    for unit in sorted_units:
        pattern = rf'^{re.escape(unit)}\b'
        if re.match(pattern, text, re.IGNORECASE):
            remaining = text[len(unit):].strip()
            # Clean up leading punctuation like "of" after unit
            remaining = re.sub(r'^of\b', '', remaining).strip()
            return unit.lower(), remaining

    return None, text


def extract_parenthetical(text: str) -> tuple[Optional[str], str]:
    """
    Pull out parenthetical sizes like "(15 ounce)" or "(8-ounce)".
    Returns what was inside the parentheses and the cleaned text.
    """
    paren_match = re.search(r'\(([^)]+)\)', text)
    if paren_match:
        inside = paren_match.group(1)
        cleaned = text[:paren_match.start()].strip() + " " + text[paren_match.end():].strip()
        cleaned = cleaned.strip()
        return inside, cleaned
    return None, text


def split_on_comma(text: str) -> tuple[str, Optional[str]]:
    """
    Split ingredient text on the first comma.
    Everything before = the ingredient itself.
    Everything after = likely preparation or notes.
    """
    if "," in text:
        parts = text.split(",", 1)
        return parts[0].strip(), parts[1].strip()
    return text.strip(), None


def extract_modifiers_and_prep(words: list[str]) -> tuple[list[str], Optional[str], list[str]]:
    """
    Given a list of words, separate out:
    - modifier adjectives (fresh, frozen, boneless...)
    - preparation words (diced, minced, chopped...)
    - the remaining words that form the actual ingredient name
    """
    modifiers = []
    prep = None
    remaining = []

    for word in words:
        w = word.lower().strip(".,")
        if w in MODIFIER_WORDS:
            modifiers.append(w)
        elif w in PREPARATION_WORDS:
            prep = w
        else:
            remaining.append(word)

    return modifiers, prep, remaining


def parse_ingredient(raw: str) -> ParsedIngredient:
    """
    Main function — takes a raw ingredient string and returns
    a fully structured ParsedIngredient object.
    """
    confidence = 1.0
    text = raw.strip()

    # Handle "no quantity" items like "salt and pepper to taste"
    no_qty_phrases = ["to taste", "as needed", "for serving", "for garnish", "cooking spray", "optional"]
    for phrase in no_qty_phrases:
        if phrase in text.lower():
            return ParsedIngredient(
                raw=raw,
                quantity=None,
                unit=None,
                item=text,
                modifiers=[],
                preparation=None,
                notes=phrase,
                confidence=0.95,
            )

    # Pull out parenthetical size info like "(15 ounce)"
    paren_info, text = extract_parenthetical(text)

    # Parse the quantity (number at the start)
    quantity, text = parse_quantity(text)
    if quantity is None:
        confidence -= 0.2

    # If there was parenthetical info with a unit inside (like "15 ounce"),
    # try to parse that as the unit
    if paren_info:
        paren_unit, _ = parse_unit(paren_info)
    else:
        paren_unit = None

    # Parse the unit
    unit, text = parse_unit(text)
    if unit is None and paren_unit:
        unit = paren_unit

    # Split on comma — after the comma is usually prep/notes
    main_part, after_comma = split_on_comma(text)

    # Break remaining text into words and find modifiers/prep
    words = main_part.split()
    modifiers, preparation, item_words = extract_modifiers_and_prep(words)

    # If no prep found before comma, check after comma
    if preparation is None and after_comma:
        after_words = after_comma.split()
        after_mods, preparation, extra_words = extract_modifiers_and_prep(after_words)
        modifiers.extend(after_mods)
        notes = " ".join(extra_words) if extra_words else None
    else:
        notes = after_comma if after_comma and after_comma not in PREPARATION_WORDS else None

    item = " ".join(item_words).strip().lower()
    if not item:
        item = main_part.lower()
        confidence -= 0.1

    return ParsedIngredient(
        raw=raw,
        quantity=quantity,
        unit=unit,
        item=item,
        modifiers=modifiers,
        preparation=preparation,
        notes=notes,
        confidence=round(confidence, 2),
    )