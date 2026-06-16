"""
agent.py

The FitFindr planning loop. Orchestrates the three tools in response to a
natural language user query, passing state between them via a session dict.

Complete tools.py and test each tool in isolation before implementing this file.

Usage (once implemented):
    from agent import run_agent
    from utils.data_loader import get_example_wardrobe

    result = run_agent(
        query="vintage graphic tee under $30, size M",
        wardrobe=get_example_wardrobe(),
    )
    print(result["fit_card"])
    print(result["error"])   # None on success
"""

import re

from tools import search_listings, suggest_outfit, create_fit_card


# ── session state ─────────────────────────────────────────────────────────────

def _new_session(query: str, wardrobe: dict) -> dict:
    """
    Initialize and return a fresh session dict for one user interaction.

    The session dict is the single source of truth for everything that happens
    during a run — it stores the original query, parsed parameters, tool results,
    and any error that caused early termination.

    You may add fields to this dict as needed for your implementation.
    """
    return {
        "query": query,              # original user query
        "parsed": {},                # extracted description / size / max_price
        "search_results": [],        # list of matching listing dicts
        "selected_item": None,       # top result, passed into suggest_outfit
        "wardrobe": wardrobe,        # user's wardrobe dict
        "outfit_suggestion": None,   # string returned by suggest_outfit
        "fit_card": None,            # string returned by create_fit_card
        "error": None,               # set if the interaction ended early
    }


# ── planning loop ─────────────────────────────────────────────────────────────

def run_agent(query: str, wardrobe: dict) -> dict:
    """
    Main agent entry point. Runs the FitFindr planning loop for a single
    user interaction and returns the completed session dict.

    Args:
        query:    Natural language user request
                  (e.g., "vintage graphic tee under $30, size M")
        wardrobe: User's wardrobe dict — use get_example_wardrobe() or
                  get_empty_wardrobe() from utils/data_loader.py

    Returns:
        The session dict after the interaction completes. Check session["error"]
        first — if it is not None, the interaction ended early and the other
        output fields (outfit_suggestion, fit_card) will be None.

    TODO — implement this function using the planning loop you designed in planning.md:

        Step 1: Initialize the session with _new_session().

        Step 2: Parse the user's query to extract a description, size, and
                max_price. You can use regex, string splitting, or ask the LLM
                to parse it — document your choice in planning.md.
                Store the result in session["parsed"].

        Step 3: Call search_listings() with the parsed parameters.
                Store results in session["search_results"].
                If no results: set session["error"] to a helpful message and
                return the session early. Do NOT proceed to suggest_outfit
                with empty input.

        Step 4: Select the item to use (e.g., the top result).
                Store it in session["selected_item"].

        Step 5: Call suggest_outfit() with the selected item and wardrobe.
                Store the result in session["outfit_suggestion"].

        Step 6: Call create_fit_card() with the outfit suggestion and selected item.
                Store the result in session["fit_card"].

        Step 7: Return the session.

    Before writing code, complete the Planning Loop and State Management sections
    of planning.md — your implementation should match what you described there.
    """
    # Step 1: initialize the session (single source of truth for this run).
    session = _new_session(query, wardrobe)

    # Step 2: parse the raw query deterministically (regex, no LLM call) into
    # description / size / max_price. We strip the matched price/size phrases out
    # of a working copy of the query; whatever remains becomes the description.
    working = query or ""

    # --- max_price: "under $30", "below 30", "$30", "30 dollars", ... ---
    max_price = None
    price_patterns = [
        r"\b(?:under|below|less than|maximum|max|up to|no more than)\s*\$?\s*(\d+(?:\.\d{1,2})?)",
        r"\$\s*(\d+(?:\.\d{1,2})?)",
        r"\b(\d+(?:\.\d{1,2})?)\s*(?:dollars|bucks|usd)\b",
    ]
    for pattern in price_patterns:
        match = re.search(pattern, working, flags=re.IGNORECASE)
        if match:
            max_price = float(match.group(1))
            working = re.sub(pattern, " ", working, count=1, flags=re.IGNORECASE)
            break

    # --- size: "size M" phrases, then standalone size tokens ---
    # Tokens are ordered longest-first; word boundaries stop XS matching inside XXS.
    size = None
    size_tokens = r"(?:XXXL|XXXS|XXL|XXS|XL|XS|S|M|L)"
    phrase = re.search(r"\bsize\s+(" + size_tokens + r")\b", working, flags=re.IGNORECASE)
    if phrase:
        size = phrase.group(1).upper()
        working = re.sub(
            r"\bsize\s+" + size_tokens + r"\b", " ", working, count=1, flags=re.IGNORECASE
        )
    else:
        # Multi-letter tokens are unambiguous, so match them case-insensitively.
        multi = re.search(r"\b(XXXL|XXXS|XXL|XXS|XL|XS)\b", working, flags=re.IGNORECASE)
        if multi:
            size = multi.group(1).upper()
            working = re.sub(
                r"\b" + re.escape(multi.group(1)) + r"\b", " ", working, count=1, flags=re.IGNORECASE
            )
        else:
            # Single-letter sizes only when uppercase + standalone, to avoid
            # matching ordinary lowercase words like "a"/"s" in the query.
            single = re.search(r"\b([SML])\b", working)
            if single:
                size = single.group(1).upper()
                working = re.sub(r"\b" + single.group(1) + r"\b", " ", working, count=1)

    # --- description: the cleaned remainder (collapse whitespace) ---
    description = re.sub(r"\s+", " ", working).strip()

    session["parsed"] = {
        "description": description,
        "size": size,
        "max_price": max_price,
    }

    # Step 3: search the listings with the parsed parameters.
    session["search_results"] = search_listings(description, size, max_price)

    # Step 4: branch on the result. Empty -> set a helpful error and return early,
    # WITHOUT calling suggest_outfit / create_fit_card (they stay None).
    if not session["search_results"]:
        session["error"] = (
            "I couldn't find anything matching that. Try raising your price cap, "
            "removing the size filter, or using broader keywords (e.g. 'graphic "
            "tee' instead of 'vintage band tee')."
        )
        return session

    session["selected_item"] = session["search_results"][0]
    # print("test",session["selected_item"])
    # Step 5: suggest an outfit for the selected item (tool handles empty wardrobe).
    session["outfit_suggestion"] = suggest_outfit(
        session["selected_item"], session["wardrobe"]
    )
    # print("test2",session["outfit_suggestion"])

    # Step 6: create the fit card from the outfit + the SAME selected item.
    session["fit_card"] = create_fit_card(
        session["outfit_suggestion"], session["selected_item"]
    )

    # Step 7: return the completed session.
    return session


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from utils.data_loader import get_example_wardrobe, get_empty_wardrobe

    print("=== Happy path: graphic tee ===\n")
    session = run_agent(
        query="looking for a vintage graphic tee under $30",
        wardrobe=get_example_wardrobe(),
    )
    if session["error"]:
        print(f"Error: {session['error']}")
    else:
        print(f"Found: {session['selected_item']['title']}")
        print(f"\nOutfit: {session['outfit_suggestion']}")
        print(f"\nFit card: {session['fit_card']}")

    print("\n\n=== No-results path ===\n")
    session2 = run_agent(
        query="designer ballgown size XXS under $5",
        wardrobe=get_example_wardrobe(),
    )
    print(f"Error message: {session2['error']}")

