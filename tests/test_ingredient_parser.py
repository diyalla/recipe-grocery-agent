import sys
import os

# This line lets Python find our src folder
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.parser.ingredient_parser import parse_ingredient

def test_simple_quantity_and_unit():
    result = parse_ingredient("2 cups all-purpose flour")
    assert result.quantity == 2.0
    assert result.unit == "cups"
    assert "flour" in result.item

def test_fraction_quantity():
    result = parse_ingredient("1/2 lb boneless skinless chicken breast, diced")
    assert result.quantity == 0.5
    assert result.unit == "lb"
    assert "boneless" in result.modifiers
    assert "skinless" in result.modifiers
    assert result.preparation == "diced"

def test_unicode_fraction():
    result = parse_ingredient("½ teaspoon red pepper flakes")
    assert result.quantity == 0.5
    assert result.unit == "teaspoon"

def test_mixed_number():
    result = parse_ingredient("1 1/2 cups chicken broth")
    assert result.quantity == 1.5
    assert result.unit == "cups"

def test_range_quantity():
    result = parse_ingredient("3-4 cloves garlic, minced")
    assert result.quantity == 3.5
    assert result.unit == "cloves"
    assert result.preparation == "minced"

def test_written_number():
    result = parse_ingredient("one 14-oz can diced tomatoes, drained")
    assert result.quantity == 1.0

def test_no_quantity_to_taste():
    result = parse_ingredient("salt and pepper to taste")
    assert result.quantity is None
    assert result.notes == "to taste"

def test_no_quantity_cooking_spray():
    result = parse_ingredient("cooking spray")
    assert result.quantity is None

def test_tablespoon_unit():
    result = parse_ingredient("2 tablespoons olive oil, plus more for drizzling")
    assert result.quantity == 2.0
    assert result.unit == "tablespoons"

def test_can_unit():
    result = parse_ingredient("1 (15 ounce) can black beans, rinsed and drained")
    assert result.quantity == 1.0
    assert result.unit == "can"

def test_parenthetical_size():
    result = parse_ingredient("1 (8-ounce) package cream cheese")
    assert result.quantity == 1.0
    assert result.unit == "package"

def test_fresh_modifier():
    result = parse_ingredient("1 bunch fresh cilantro, chopped")
    assert result.unit == "bunch"
    assert "fresh" in result.modifiers
    assert result.preparation == "chopped"

def test_grated_preparation():
    result = parse_ingredient("3/4 cup freshly grated Parmesan cheese")
    assert result.quantity == 0.75
    assert result.unit == "cup"

def test_large_modifier():
    result = parse_ingredient("2 large eggs")
    assert result.quantity == 2.0
    assert "large" in result.modifiers

def test_frozen_modifier():
    result = parse_ingredient("1 cup frozen peas")
    assert "frozen" in result.modifiers

def test_pound_weight_unit():
    result = parse_ingredient("1 lb ground beef")
    assert result.quantity == 1.0
    assert result.unit == "lb"

def test_ounce_unit():
    result = parse_ingredient("8 oz cream cheese, softened")
    assert result.quantity == 8.0
    assert result.unit == "oz"
    assert result.preparation == "softened"

def test_teaspoon_unit():
    result = parse_ingredient("1 teaspoon vanilla extract")
    assert result.quantity == 1.0
    assert result.unit == "teaspoon"

def test_two_to_three_range():
    result = parse_ingredient("2 to 3 cups vegetable broth")
    assert result.quantity == 2.5
    assert result.unit == "cups"

def test_dried_modifier():
    result = parse_ingredient("1 teaspoon dried oregano")
    assert "dried" in result.modifiers

def test_sliced_preparation():
    result = parse_ingredient("2 cups mushrooms, sliced")
    assert result.preparation == "sliced"

def test_crushed_preparation():
    result = parse_ingredient("2 cloves garlic, crushed")
    assert result.preparation == "crushed"

def test_raw_field_preserved():
    raw = "3 tablespoons butter, melted"
    result = parse_ingredient(raw)
    assert result.raw == raw

def test_confidence_high_for_clear_input():
    result = parse_ingredient("2 cups flour")
    assert result.confidence >= 0.8

def test_confidence_lower_for_unclear_input():
    result = parse_ingredient("some flour")
    assert result.confidence < 0.9

def test_as_needed():
    result = parse_ingredient("flour as needed")
    assert result.quantity is None
    assert result.notes == "as needed"

def test_decimal_quantity():
    result = parse_ingredient("1.5 cups milk")
    assert result.quantity == 1.5
    assert result.unit == "cups"

def test_written_half():
    result = parse_ingredient("half cup sugar")
    assert result.quantity == 0.5

def test_shredded_preparation():
    result = parse_ingredient("1 cup shredded cheddar cheese")
    assert result.preparation == "shredded"

def test_item_is_not_empty():
    result = parse_ingredient("2 tablespoons soy sauce")
    assert result.item != ""
    assert result.item is not None