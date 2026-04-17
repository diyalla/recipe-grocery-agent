# Digest Triage Demonstration

This document shows the Qwen model evaluating a batch of digests
produced by the background worker and deciding which are worth
surfacing to the user.

---

## Sample Digests from Worker

After running the worker, `data/digests.json` contains entries like:

```json
[
  {
    "digest_id": "price-alert-chicken-breast-2026-04-17",
    "type": "price_alert",
    "priority": "high",
    "title": "Price increase: Boneless Skinless Chicken Breast Max Pack",
    "summary": "Price increased from $4.99 to $7.99 (+60.1%). Affects 2 saved recipes: Pad Thai, Authentic Pad Thai.",
    "data": {
      "ingredient": "chicken breast",
      "old_price": 4.99,
      "new_price": 7.99,
      "change_percent": 60.1,
      "affected_recipes": ["Pad Thai", "Authentic Pad Thai"]
    },
    "timestamp": "2026-04-17T14:00:00Z"
  },
  {
    "digest_id": "trending-recipes-weekly-2026-04-17",
    "type": "trending_recipes",
    "priority": "low",
    "title": "Trending Recipe Suggestions",
    "summary": "Found 5 trending recipes. Top pick: Spring Pasta Salad (4.7★, 892 reviews).",
    "data": {
      "suggestions": [
        {
          "recipe_id": "12345",
          "title": "Spring Pasta Salad",
          "rating": 4.7,
          "review_count": 892,
          "url": "https://www.allrecipes.com/recipe/12345/spring-pasta-salad/"
        }
      ]
    },
    "timestamp": "2026-04-17T14:00:00Z"
  },
  {
    "digest_id": "price-alert-fish-sauce-2026-04-17",
    "type": "price_alert",
    "priority": "medium",
    "title": "Price decrease: Thai Kitchen Fish Sauce",
    "summary": "Price decreased from $6.29 to $3.99 (-36.6%). Affects 2 saved recipes.",
    "data": {
      "ingredient": "fish sauce",
      "old_price": 6.29,
      "new_price": 3.99,
      "change_percent": -36.6,
      "affected_recipes": ["Pad Thai", "Authentic Pad Thai"]
    },
    "timestamp": "2026-04-17T14:00:00Z"
  }
]
```

---

## Qwen Triage Prompt
You are a helpful meal planning assistant. Below are digest payloads
produced by a background monitoring worker. Evaluate each digest and
decide which are worth surfacing to the user today. For each digest
you surface, explain why it is relevant and how you would present it.
Digests: [see above]

---

## Qwen Triage Response

I've reviewed the 3 digests. Here's my triage:

**Surface immediately (High Priority):**

1. **Chicken Breast Price Increase (+60%)**
   This directly impacts your meal plan. A 60% increase on chicken breast
   affects both your saved Pad Thai recipes. I'd recommend either buying
   chicken breast now before further increases, or substituting tofu this
   week. Sunflower seeds can replace peanuts as a topping if needed.

**Surface as a helpful tip (Medium Priority):**

2. **Fish Sauce Price Decrease (-37%)**
   Good news — fish sauce dropped significantly. Since it's used in both
   your saved recipes and has a long shelf life, this is a great time to
   stock up. I can add it to your cart if you'd like.

**Skip for now (Low Priority):**

3. **Trending Recipe Suggestions**
   You already have meals planned for this weekend. I'll hold these
   suggestions for your next meal planning session.

---

**Summary:** 2 of 3 digests are actionable today. The price alerts
are time-sensitive, while the trending recipes can wait.
