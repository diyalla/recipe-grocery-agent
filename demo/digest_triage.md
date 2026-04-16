# Digest Triage Demonstration

This document shows the Qwen model evaluating a batch of digests
and deciding which are worth surfacing to the user.

---

## Prompt sent to Qwen
You are a helpful meal planning assistant. Below are digest payloads
produced by a background monitoring worker. Evaluate each digest and
decide which ones are worth surfacing to the user. For each digest you
choose to surface, explain why it is relevant and how you would present
it to the user.
Digests:
[
{
"digest_id": "price-alert-chicken-breast-2026-04-16",
"type": "price_alert",
"priority": "high",
"title": "Price increase: Chicken Breast at Safeway",
"summary": "Chicken breast price increased from $4.99 to $7.99 (+60%). Affects 2 saved recipes: Pad Thai, Green Curry."
},
{
"digest_id": "trending-recipes-weekly-2026-04-16",
"type": "trending_recipes",
"priority": "low",
"title": "Trending Recipe Suggestions",
"summary": "Found 5 trending recipes. Top pick: Spring Pasta Salad rated 4.7/5 with 892 reviews."
},
{
"digest_id": "price-alert-fish-sauce-2026-04-16",
"type": "price_alert",
"priority": "medium",
"title": "Price decrease: Fish Sauce",
"summary": "Fish sauce price decreased from $3.99 to $2.49 (-38%). Affects 2 saved recipes."
}
]

---

## Qwen Response

I've reviewed the 3 digests. Here's my triage:

**Surface immediately (High Priority):**

1. **Chicken Breast Price Increase (+60%)**
   This is significant and directly impacts your meal plan. A 60% price
   increase on chicken breast affects both your Pad Thai and Green Curry
   recipes. I'd recommend either buying chicken breast now before prices
   rise further, or considering a substitute like tofu for this week's
   meals.

**Surface as a helpful tip (Medium Priority):**

2. **Fish Sauce Price Decrease (-38%)**
   Good news — fish sauce is on sale. Since it's used in both your saved
   recipes and has a long shelf life, this is a good time to stock up.

**Skip for now (Low Priority):**

3. **Trending Recipe Suggestions**
   While interesting, you already have meals planned for this weekend.
   I'll save these suggestions for next week's meal planning session.

---

**Summary:** 2 of 3 digests are worth surfacing. The price alerts are
actionable, while the trending recipes can wait.