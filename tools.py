"""
tools.py

The three required FitFindr tools. Each tool is a standalone function that
can be called and tested independently before being wired into the agent loop.

Complete and test each tool before moving to agent.py.

Tools:
    search_listings(description, size, max_price)  → list[dict]
    suggest_outfit(new_item, wardrobe)              → str
    create_fit_card(outfit, new_item)               → str
"""

import os
import re

from dotenv import load_dotenv
from groq import Groq

from utils.data_loader import load_listings

load_dotenv()


# ── Groq client ───────────────────────────────────────────────────────────────

def _get_groq_client():
    """Initialize and return a Groq client using GROQ_API_KEY from .env."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Add it to a .env file in the project root."
        )
    return Groq(api_key=api_key)


# ── Tool 1: search_listings ───────────────────────────────────────────────────

def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Search the mock listings dataset for items matching the description,
    optional size, and optional price ceiling.

    Args:
        description: Keywords describing what the user is looking for
                     (e.g., "vintage graphic tee").
        size:        Size string to filter by, or None to skip size filtering.
                     Matching is case-insensitive (e.g., "M" matches "S/M").
        max_price:   Maximum price (inclusive), or None to skip price filtering.

    Returns:
        A list of matching listing dicts, sorted by relevance (best match first).
        Returns an empty list if nothing matches — does NOT raise an exception.

    Each listing dict has the following fields:
        id, title, description, category, style_tags (list), size,
        condition, price (float), colors (list), brand, platform

    TODO:
        1. Load all listings with load_listings().
        2. Filter by max_price and size (if provided).
        3. Score each remaining listing by keyword overlap with `description`.
        4. Drop any listings with a score of 0 (no relevant matches).
        5. Sort by score, highest first, and return the listing dicts.

    Before writing code, fill in the Tool 1 section of planning.md.
    """
    try:
        listings = load_listings()

        # Step 2: filter by price ceiling and size (each skipped when None).
        filtered = []
        for listing in listings:
            if max_price is not None and listing["price"] > max_price:
                continue
            if size is not None and size.lower() not in listing["size"].lower():
                continue
            filtered.append(listing)

        # Step 3: score each survivor by whole-word keyword overlap. Each
        # distinct query word that appears as a whole word anywhere in the
        # listing's title, description, or style_tags counts once.
        query_words = set(re.findall(r"\w+", description.lower()))

        scored = []
        for listing in filtered:
            searchable = " ".join(
                [listing["title"], listing["description"], *listing["style_tags"]]
            ).lower()
            listing_words = set(re.findall(r"\w+", searchable))
            score = len(query_words & listing_words)
            if score > 0:  # Step 4: drop listings with no relevant keywords.
                scored.append((score, listing))

        # Step 5: sort by score (highest first), return the listing dicts.
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [listing for _, listing in scored]
    except Exception:
        # Failure mode: never raise, never return None — fall back to no matches.
        return []


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1–2 complete outfits.

    Args:
        new_item: A listing dict (the item the user is considering buying).
        wardrobe: A wardrobe dict with an 'items' key containing a list of
                  wardrobe item dicts. May be empty — handle this gracefully.

    Returns:
        A non-empty string with outfit suggestions.
        If the wardrobe is empty, offer general styling advice for the item
        rather than raising an exception or returning an empty string.

    TODO:
        1. Check whether wardrobe['items'] is empty.
        2. If empty: call the LLM with a prompt for general styling ideas
           (what kinds of items pair well, what vibe it suits, etc.).
        3. If not empty: format the wardrobe items into a prompt and ask
           the LLM to suggest specific outfit combinations using the new item
           and named pieces from the wardrobe.
        4. Return the LLM's response as a string.

    Before writing code, fill in the Tool 2 section of planning.md.
    """
    try:
        items = wardrobe.get("items", []) if isinstance(wardrobe, dict) else []

        # Summarize the thrifted item the user is considering.
        item_summary = (
            f"Item: {new_item.get('title', 'Unknown item')}\n"
            f"Category: {new_item.get('category', 'unknown')}\n"
            f"Colors: {', '.join(new_item.get('colors', [])) or 'unspecified'}\n"
            f"Style tags: {', '.join(new_item.get('style_tags', [])) or 'unspecified'}\n"
            f"Description: {(new_item.get('description') or '').strip() or 'n/a'}"
        )

        if not items:
            # Empty wardrobe: ask for general styling advice for the item alone.
            prompt = (
                "A shopper is considering buying this second-hand item, but they "
                "haven't added any wardrobe pieces yet:\n\n"
                f"{item_summary}\n\n"
                "Give general styling advice for this item on its own. Suggest "
                "what kinds of pieces (tops, bottoms, shoes, layers, accessories) "
                "pair well with it, what colors complement it, and what vibe or "
                "occasions it suits. Keep it to a friendly paragraph or two — no "
                "need to invent specific items they don't own."
            )
        else:
            # Non-empty wardrobe: build outfits from their actual pieces.
            wardrobe_lines = []
            for it in items:
                colors = ", ".join(it.get("colors", []))
                tags = ", ".join(it.get("style_tags", []))
                notes = it.get("notes")
                line = f"- {it.get('name', 'Unnamed piece')} ({it.get('category', 'unknown')})"
                details = []
                if colors:
                    details.append(f"colors: {colors}")
                if tags:
                    details.append(f"style: {tags}")
                if notes:
                    details.append(f"notes: {notes}")
                if details:
                    line += " — " + "; ".join(details)
                wardrobe_lines.append(line)
            wardrobe_block = "\n".join(wardrobe_lines)

            prompt = (
                "A shopper is considering buying this second-hand item:\n\n"
                f"{item_summary}\n\n"
                "Here is what they already own:\n"
                f"{wardrobe_block}\n\n"
                "Suggest 1-2 complete outfits built around the new item, using "
                "specific pieces from the wardrobe above. Refer to the wardrobe "
                "pieces by name, and for each outfit briefly explain why it works "
                "(silhouette, color, or vibe). Keep it concise and practical."
            )

        client = _get_groq_client()
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a friendly, knowledgeable personal stylist who "
                        "helps people style second-hand and thrifted fashion finds."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
        )

        suggestion = (response.choices[0].message.content or "").strip()
        if not suggestion:
            raise ValueError("LLM returned an empty styling suggestion.")
        return suggestion
    except Exception:
        # Safe fallback: never raise, never return "".
        name = new_item.get("title", "this piece") if isinstance(new_item, dict) else "this piece"
        return (
            f"I couldn't generate custom styling ideas right now, but {name} is a "
            "versatile find. Try pairing it with simple neutral basics — a fitted "
            "top or tee, well-fitting denim or trousers, and clean sneakers or "
            "boots — then add one statement layer or accessory to make it yours."
        )


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Generate a short, shareable outfit caption for the thrifted find.

    Args:
        outfit:   The outfit suggestion string from suggest_outfit().
        new_item: The listing dict for the thrifted item.

    Returns:
        A 2–4 sentence string usable as an Instagram/TikTok caption.
        If outfit is empty or missing, return a descriptive error message
        string — do NOT raise an exception.

    The caption should:
    - Feel casual and authentic (like a real OOTD post, not a product description)
    - Mention the item name, price, and platform naturally (once each)
    - Capture the outfit vibe in specific terms
    - Sound different each time for different inputs (use higher LLM temperature)

    TODO:
        1. Guard against an empty or whitespace-only outfit string.
        2. Build a prompt that gives the LLM the item details and the outfit,
           and asks for a caption matching the style guidelines above.
        3. Call the LLM and return the response.

    Before writing code, fill in the Tool 3 section of planning.md.
    """
    # Step 1: guard against an empty or whitespace-only outfit — no LLM call.
    if not outfit or not outfit.strip():
        return "Can't write a fit card yet — no outfit was suggested."

    title = new_item.get("title", "this thrifted find")
    price = new_item.get("price")
    price_str = f"${price:g}" if isinstance(price, (int, float)) else "a steal"
    platform = new_item.get("platform", "secondhand")

    try:
        # Step 2: build the caption prompt from the item details + outfit.
        prompt = (
            "Write a short, shareable outfit caption for a thrifted fashion find "
            "— like a real OOTD post on Instagram or TikTok, in a casual, "
            "authentic first-person voice. NOT a product description.\n\n"
            f"Item name: {title}\n"
            f"Price: {price_str}\n"
            f"Platform: {platform}\n"
            f"How it's styled: {outfit.strip()}\n\n"
            "Requirements:\n"
            "- 2 to 4 sentences.\n"
            f"- Mention the item name, the price ({price_str}), and the platform "
            f"({platform}) naturally, exactly once each.\n"
            "- Capture the outfit's vibe in specific terms (reference the actual "
            "pieces/feel, not generic hype).\n"
            "- Sound like a person posting their fit, not an ad. Emojis are fine "
            "but keep it natural.\n\n"
            "Return only the caption text."
        )

        # Step 3: call the LLM with a higher temperature so repeated calls vary.
        client = _get_groq_client()
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You write casual, authentic OOTD-style captions for "
                        "thrifted and secondhand fashion finds."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=1.0,
        )

        caption = (response.choices[0].message.content or "").strip()
        if not caption:
            raise ValueError("LLM returned an empty caption.")
        return caption
    except Exception:
        # Safe fallback: never raise, never return "".
        return (
            f"Thrifted this {title} for {price_str} on {platform} and I'm obsessed "
            "— styled it exactly how I pictured and it's giving everything. "
            "Full look's up now."
        )
