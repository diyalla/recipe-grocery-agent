import sys
sys.path.insert(0, '.')
from src.clients.instacart import search_products
from src.clients.allrecipes import get_recipe
from src.parser.ingredient_parser import parse_ingredient
import json

recipe = get_recipe(url='https://www.allrecipes.com/recipe/42968/pad-thai/')
print('Recipe:', recipe['title'])
print('Ingredients found:', len(recipe['ingredients_raw']))
print()

for raw in recipe['ingredients_raw'][:5]:
    parsed = parse_ingredient(raw)
    search_query = parsed.item if parsed.item else raw
    products = search_products(query=search_query, limit=1)
    if products and not products[0].get('error'):
        p = products[0]
        print(f'Ingredient: {raw}')
        print(f'  Parsed item: {parsed.item}')
        print(f'  Matched product: {p["product_name"]}')
        print(f'  Size: {p["size"]}')
        print(f'  Available: {p["available"]}')
        print(f'  Price: {p["price"] or "requires auth"}')
        print()