import re
from dataclasses import dataclass
from typing import Optional

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

PREPARATION_WORDS = {
    "diced", "minced", "chopped", "sliced", "grated", "shredded",
    "crushed", "peeled", "cubed", "halved", "quartered", "julienned",
    "mashed", "pureed", "ground", "crumbled", "beaten", "whipped",
    "melted", "softened", "toasted", "roasted", "cooked", "drained",
    "rinsed", "thawed", "divided", "sifted", "packed", "heaping",
    "leveled", "softened", "room temperature", "cubes", "chunks",
    "pieces", "strips", "rings", "florets", "wedges",
}

# Phrases that indicate preparation instructions — words after these
# should not be considered part of the item name
PREPARATION_TRIGGERS = {
    "cut", "into", "bite-sized", "bite", "sized",
}

MODIFIER_WORDS = {
    "fresh", "frozen", "dried", "canned", "raw", "cooked",
    "large", "medium", "small", "extra-large", "jumbo",
    "unsalted", "salted", "sweet", "spicy", "mild",
    "organic", "free-range", "grass-fed",
    "yellow", "white", "red", "green", "black", "purple",
    "low-fat", "fat-free", "reduced-fat",
    "boneless", "skinless", "lean", "thick", "thin",
    "whole", "bone-in", "skin-on",
}

# Words that are never the item name on their own
FILLER_WORDS = {
    "halves", "half", "pieces", "piece", "chunks", "chunk",
    "strips", "strip", "bits", "bite-sized", "sized",
    "inch", "inches", "cm", "centimeter", "centimeters",
    "1", "2", "3", "4", "5",
}

WORD_TO_NUM = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "half": 0.5, "quarter": 0.25, "a": 1, "an": 1,
}

UNICODE_FRACTIONS = {
    "½": 0.5, "⅓": 0.333, "⅔": 0.667,
    "¼": 0.25, "¾": 0.75,
    "⅛": 0.125, "⅜": 0.375, "⅝": 0.625, "⅞": 0.875,
}


def parse_quantity(text: str) -> tuple[Optional[float], str]:
    text = text.strip()
    for uc, val in UNICODE_FRACTIONS.items():
        text = text.replace(uc, f" {val} ")
    text = text.strip()

    word_match = re.match(r'^(one|two|three|four|five|six|seven|eight|nine|ten|half|quarter|an?)\b', text, re.IGNORECASE)
    if word_match:
        word = word_match.group(1).lower()
        return WORD_TO_NUM.get(word, 1), text[word_match.end():].strip()

    range_match = re.match(r'^(\d+(?:\.\d+)?)\s*(?:-|to)\s*(\d+(?:\.\d+)?)', text)
    if range_match:
        low, high = float(range_match.group(1)), float(range_match.group(2))
        return (low + high) / 2, text[range_match.end():].strip()

    mixed_match = re.match(r'^(\d+)\s+(\d+)/(\d+)', text)
    if mixed_match:
        whole = int(mixed_match.group(1))
        num = int(mixed_match.group(2))
        den = int(mixed_match.group(3))
        return whole + num / den, text[mixed_match.end():].strip()

    frac_match = re.match(r'^(\d+)/(\d+)', text)
    if frac_match:
        return int(frac_match.group(1)) / int(frac_match.group(2)), text[frac_match.end():].strip()

    num_match = re.match(r'^(\d+(?:\.\d+)?)', text)
    if num_match:
        return float(num_match.group(1)), text[num_match.end():].strip()

    return None, text


def parse_unit(text: str) -> tuple[Optional[str], str]:
    text = text.strip()
    sorted_units = sorted(ALL_UNITS, key=len, reverse=True)
    for unit in sorted_units:
        if re.match(rf'^{re.escape(unit)}\b', text, re.IGNORECASE):
            remaining = text[len(unit):].strip()
            remaining = re.sub(r'^of\b', '', remaining).strip()
            return unit.lower(), remaining
    return None, text


def extract_parenthetical(text: str) -> tuple[Optional[str], str]:
    paren_match = re.search(r'\(([^)]+)\)', text)
    if paren_match:
        inside = paren_match.group(1)
        cleaned = (text[:paren_match.start()] + " " + text[paren_match.end():]).strip()
        return inside, cleaned
    return None, text


def _classify_word(word: str) -> str:
    """
    Classify a single word as: modifier, prep, filler, or item.
    Returns one of: 'modifier', 'prep', 'filler', 'item'
    """
    w = word.lower().strip(".,")
    if w in MODIFIER_WORDS:
        return 'modifier'
    if w in PREPARATION_WORDS:
        return 'prep'
    if w in FILLER_WORDS:
        return 'filler'
    if w in PREPARATION_TRIGGERS:
        return 'filler'
    return 'item'


def _extract_from_words(words: list[str]) -> tuple[list[str], Optional[str], list[str]]:
    """
    Given a list of words, return (modifiers, preparation, item_words).
    Item words are only words classified as 'item'.
    """
    modifiers = []
    preparation = None
    item_words = []

    for word in words:
        cls = _classify_word(word)
        if cls == 'modifier':
            modifiers.append(word.lower().strip(".,"))
        elif cls == 'prep' and preparation is None:
            preparation = word.lower().strip(".,")
        elif cls == 'item':
            item_words.append(word.strip(".,"))

    return modifiers, preparation, item_words


def parse_ingredient(raw: str) -> ParsedIngredient:
    """
    Main parsing function. Takes a raw ingredient string and returns
    a structured ParsedIngredient.

    Key improvement: Instead of splitting on the first comma and losing
    the ingredient name, we now split ALL commas and classify each
    segment. This correctly handles cases like:
    '1 pound boneless, skinless chicken breast halves, cut into pieces'
    where the ingredient name spans across a comma.
    """
    confidence = 1.0
    text = raw.strip()

    # Handle no-quantity phrases
    no_qty_phrases = ["to taste", "as needed", "for serving", "for garnish", "cooking spray", "optional"]
    for phrase in no_qty_phrases:
        if phrase in text.lower():
            return ParsedIngredient(
                raw=raw, quantity=None, unit=None, item=text,
                modifiers=[], preparation=None, notes=phrase, confidence=0.95,
            )

    # Extract parenthetical
    paren_info, text = extract_parenthetical(text)

    # Parse quantity
    quantity, text = parse_quantity(text)
    if quantity is None:
        confidence -= 0.2

    # Parse unit
    paren_unit = None
    if paren_info:
        paren_unit, _ = parse_unit(paren_info)

    unit, text = parse_unit(text)
    if unit is None and paren_unit:
        unit = paren_unit

    # Split ALL segments by comma or dash (dash often separates prep instructions)
    # e.g. "chicken breast halves - cut into 1 inch cubes"
    # First normalize " - " to a comma so our existing logic handles it
    text = re.sub(r'\s+-\s+', ', ', text)
    # e.g. "boneless, skinless chicken breast halves, cut into pieces"
    # becomes ["boneless", "skinless chicken breast halves", "cut into pieces"]
    segments = [s.strip() for s in text.split(",")]

    all_modifiers = []
    all_prep = None
    all_item_words = []
    notes = None

    for i, segment in enumerate(segments):
        words = segment.split()
        mods, prep, item_words = _extract_from_words(words)

        all_modifiers.extend(mods)

        if prep and all_prep is None:
            all_prep = prep

        if item_words:
            # If this is the last segment and we already have item words,
            # this might be a note rather than more item words
            if i > 0 and all_item_words and not item_words:
                pass
            else:
                all_item_words.extend(item_words)
        elif not item_words and not mods and prep is None and i > 0:
            # This segment is unclassified — treat as notes
            notes = segment

    item = " ".join(all_item_words).strip().lower()

    # Final fallback — if item is still empty use the full text
    if not item:
        all_skip = MODIFIER_WORDS | PREPARATION_WORDS | FILLER_WORDS
        fallback = [w.strip(".,") for w in text.split() if w.lower().strip(".,") not in all_skip]
        item = " ".join(fallback).strip().lower()
        if not item:
            item = text.lower()
            confidence -= 0.1

    return ParsedIngredient(
        raw=raw,
        quantity=quantity,
        unit=unit,
        item=item,
        modifiers=list(set(all_modifiers)),
        preparation=all_prep,
        notes=notes,
        confidence=round(confidence, 2),
    )