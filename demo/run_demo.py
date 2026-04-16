import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from groq import Groq

load_dotenv()

from src.mcp_server import (
    search_recipes,
    get_recipe,
    search_products,
    estimate_recipe_cost,
    find_substitutions,
    compare_recipes,
    add_to_cart,
    get_cart,
    remove_from_cart,
)

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
MODEL = "qwen/qwen3-32b"

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_recipes",
            "description": "Search Allrecipes for recipes by keyword. Returns a list of recipes with titles, ratings, and URLs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search phrase"},
                    "cuisine": {"type": "string", "description": "Optional cuisine filter"},
                    "dietary": {"type": "string", "description": "Optional dietary filter"},
                    "limit": {"type": "integer", "description": "Number of results"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_recipe",
            "description": "Get full recipe details including ingredients and instructions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "recipe_id": {"type": "string", "description": "Allrecipes recipe ID"},
                    "url": {"type": "string", "description": "Full Allrecipes recipe URL"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "estimate_recipe_cost",
            "description": "Estimate grocery cost of a recipe by searching Instacart for each ingredient.",
            "parameters": {
                "type": "object",
                "properties": {
                    "recipe_id": {"type": "string", "description": "Allrecipes recipe ID"},
                    "url": {"type": "string", "description": "Full Allrecipes recipe URL"},
                    "zip_code": {"type": "string", "description": "ZIP code for pricing"},
                    "store": {"type": "string", "description": "Preferred store"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "find_substitutions",
            "description": "Find ingredient substitutions for allergies or dietary needs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ingredient": {"type": "string", "description": "Ingredient to substitute"},
                    "reason": {"type": "string", "description": "Reason: allergy, dietary, unavailable, preference"},
                    "dietary_constraint": {"type": "string", "description": "Specific constraint e.g. nut-free"},
                    "zip_code": {"type": "string", "description": "ZIP code for pricing"}
                },
                "required": ["ingredient", "reason"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "compare_recipes",
            "description": "Compare 2-3 recipes side by side with a combined shopping list.",
            "parameters": {
                "type": "object",
                "properties": {
                    "recipe_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of 2-3 recipe IDs"
                    },
                    "zip_code": {"type": "string", "description": "ZIP code for pricing"}
                },
                "required": ["recipe_ids"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "add_to_cart",
            "description": "Add a product to the Instacart cart.",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {"type": "string", "description": "Product ID to add"},
                    "quantity": {"type": "integer", "description": "Quantity to add"}
                },
                "required": ["product_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_cart",
            "description": "Get current Instacart cart contents.",
            "parameters": {
                "type": "object",
                "properties": {
                    "zip_code": {"type": "string"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "remove_from_cart",
            "description": "Remove a product from the Instacart cart.",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {"type": "string", "description": "Product ID to remove"}
                },
                "required": ["product_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_products",
            "description": "Search Instacart for grocery products.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Product search phrase"},
                    "zip_code": {"type": "string", "description": "ZIP code"},
                    "limit": {"type": "integer", "description": "Number of results"}
                },
                "required": ["query"]
            }
        }
    },
]

TOOL_FUNCTIONS = {
    "search_recipes": search_recipes,
    "get_recipe": get_recipe,
    "estimate_recipe_cost": estimate_recipe_cost,
    "find_substitutions": find_substitutions,
    "compare_recipes": compare_recipes,
    "add_to_cart": add_to_cart,
    "get_cart": get_cart,
    "remove_from_cart": remove_from_cart,
    "search_products": search_products,
}


def execute_tool(tool_name: str, tool_args: dict) -> str:
    """
    Execute a tool call and return the result as a string.
    Truncates large results to stay within Groq free tier token limits.
    """
    if tool_name not in TOOL_FUNCTIONS:
        return json.dumps({"error": f"Unknown tool: {tool_name}"})

    try:
        print(f"\n  [Tool call: {tool_name}({json.dumps(tool_args, indent=None)})]")
        result = TOOL_FUNCTIONS[tool_name](**tool_args)

        # Truncate large results to stay within Groq free tier limits
        try:
            parsed = json.loads(result)
            if isinstance(parsed, list) and len(parsed) > 3:
                parsed = parsed[:3]
                result = json.dumps(parsed, indent=2)
            elif isinstance(parsed, dict):
                if "ingredients_raw" in parsed:
                    parsed["ingredients_raw"] = parsed["ingredients_raw"][:8]
                if "ingredients_parsed" in parsed:
                    parsed["ingredients_parsed"] = parsed["ingredients_parsed"][:8]
                if "instructions" in parsed:
                    parsed["instructions"] = parsed["instructions"][:3]
                if "ingredient_breakdown" in parsed:
                    parsed["ingredient_breakdown"] = parsed["ingredient_breakdown"][:6]
                if "combined_shopping_list" in parsed:
                    parsed["combined_shopping_list"] = parsed["combined_shopping_list"][:10]
                if "recipes" in parsed:
                    for r in parsed["recipes"]:
                        if "ingredients" in r:
                            r["ingredients"] = r["ingredients"][:5]
                result = json.dumps(parsed, indent=2)
        except Exception:
            pass

        # Hard truncate if still too large
        if len(result) > 2000:
            result = result[:2000] + "\n... (truncated for brevity)"

        print(f"  [Tool returned {len(result)} chars]")
        return result

    except Exception as e:
        error = {"error": str(e), "tool": tool_name}
        print(f"  [Tool error: {e}]")
        return json.dumps(error)


def chat(messages: list) -> tuple[str, list]:
    """
    Send messages to Qwen and handle tool calls.
    Returns the final text response and updated message history.
    """
    while True:
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
            max_tokens=1024,
        )

        message = response.choices[0].message

        # Add assistant response to history
        # Only include tool_calls key if there are actual tool calls
        # Groq rejects messages with tool_calls: None
        assistant_message = {
            "role": "assistant",
            "content": message.content or "",
        }
        if message.tool_calls:
            assistant_message["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments
                    }
                }
                for tc in message.tool_calls
            ]
        messages.append(assistant_message)

        # If no tool calls we are done
        if not message.tool_calls:
            return message.content, messages

        # Execute each tool call
        for tool_call in message.tool_calls:
            tool_name = tool_call.function.name
            try:
                tool_args = json.loads(tool_call.function.arguments)
            except Exception:
                tool_args = {}

            result = execute_tool(tool_name, tool_args)

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": result
            })


def run_demo():
    """
    Run the full demo conversation from the challenge requirements.
    Saves the transcript to demo/conversation_live.md
    """
    print("\n" + "="*60)
    print("Recipe & Grocery Agent — Live Demo")
    print(f"Model: {MODEL}")
    print("="*60)

    system_message = {
        "role": "system",
        "content": (
            "You are a helpful meal planning and grocery assistant. "
            "You help users find recipes, estimate ingredient costs, "
            "find substitutions, compare recipes, and manage their "
            "Instacart grocery cart. "
            "Be concise and helpful. When you find recipes, present "
            "the top options clearly. When you estimate costs, be "
            "transparent about limitations. "
            "Always confirm with the user before adding items to cart."
        )
    }

    messages = [system_message]
    transcript = []

    demo_messages = [
        "I want to cook Pad Thai this weekend. Find me a good recipe.",
        "Let's go with the first one.",
        "How much will the ingredients cost me at Safeway?",
        "I'm allergic to peanuts. What can I substitute?",
        "Also find me a good green curry recipe and compare the two — what's my total shopping list going to look like?",
        "Great, add everything from the combined shopping list to my Instacart cart.",
    ]

    for user_message in demo_messages:
        print(f"\n{'='*60}")
        print(f"User: {user_message}")
        print(f"{'='*60}")

        messages.append({"role": "user", "content": user_message})
        transcript.append(f"\n**User:** {user_message}\n")

        response, messages = chat(messages)

        print(f"\nAgent: {response}")
        transcript.append(f"\n**Agent:** {response}\n")

    # Save live transcript
    transcript_path = "demo/conversation_live.md"
    with open(transcript_path, "w", encoding="utf-8") as f:
        f.write("# Live Demo Transcript\n\n")
        f.write(f"**Model:** {MODEL}\n")
        f.write(f"**Date:** 2026-04-16\n\n")
        f.write("---\n")
        f.write("\n".join(transcript))

    print(f"\n{'='*60}")
    print(f"Demo complete! Transcript saved to {transcript_path}")
    print(f"{'='*60}")


if __name__ == "__main__":
    run_demo()