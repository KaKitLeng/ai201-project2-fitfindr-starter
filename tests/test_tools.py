"""
Pytest tests for the search_listings and suggest_outfit tools.

The search_listings tests exercise filtering by size/price, keyword
scoring, and the no-match failure mode (returns [], never raises).

The suggest_outfit and create_fit_card tests call the real LLM, so they
assert TYPE and SHAPE (a non-empty string) rather than exact wording.
They require GROQ_API_KEY to be set in the environment / .env. The one
exception is create_fit_card's empty-outfit guard, which returns a fixed
error message without any LLM call — that case is asserted exactly.
"""

from tools import create_fit_card, search_listings, suggest_outfit
from utils.data_loader import get_empty_wardrobe, get_example_wardrobe


def test_returns_nonempty_list_for_matching_query():
    """A real query should return a non-empty list of listing dicts."""
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert isinstance(results, list)
    assert len(results) > 0
    assert all(isinstance(item, dict) for item in results)


def test_returns_empty_list_for_impossible_query():
    """No matches should yield exactly [] — not None, and no exception."""
    results = search_listings("designer ballgown", size="XXS", max_price=5)
    assert results == []


def test_price_filter_excludes_items_over_max_price():
    """Every returned item must be at or under the price ceiling."""
    results = search_listings("vintage", size=None, max_price=10)
    assert all(item["price"] <= 10 for item in results)


def test_size_filter_only_returns_matching_sizes():
    """Passing a size returns only items whose size contains that token."""
    size = "M"
    results = search_listings("vintage", size=size, max_price=None)
    assert len(results) > 0  # sanity: the filter shouldn't wipe everything out
    assert all(size.lower() in item["size"].lower() for item in results)


# ── suggest_outfit (real LLM — assert type/shape, not exact text) ──────────────

def test_suggest_outfit_returns_nonempty_str_with_wardrobe():
    """Real listing + populated wardrobe should yield a non-empty string."""
    item = search_listings("vintage graphic tee", size=None, max_price=50)[0]
    result = suggest_outfit(item, get_example_wardrobe())
    assert isinstance(result, str)
    assert result.strip() != ""


def test_suggest_outfit_returns_nonempty_str_with_empty_wardrobe():
    """Empty wardrobe is handled gracefully — still a non-empty string, no crash."""
    item = search_listings("vintage graphic tee", size=None, max_price=50)[0]
    result = suggest_outfit(item, get_empty_wardrobe())
    assert isinstance(result, str)
    assert result.strip() != ""


# ── create_fit_card (real LLM — assert type/shape, except the guard) ───────────

def test_create_fit_card_returns_nonempty_str_for_valid_outfit():
    """A valid outfit + real item should yield a non-empty caption string."""
    item = search_listings("vintage graphic tee", size=None, max_price=50)[0]
    outfit = (
        "Pair the tee with baggy dark-wash jeans and chunky white sneakers for a "
        "90s streetwear look, and layer a vintage black denim jacket on top."
    )
    result = create_fit_card(outfit, item)
    assert isinstance(result, str)
    assert result.strip() != ""


def test_create_fit_card_guards_empty_outfit_without_llm():
    """Empty outfit returns the fixed error message — no crash, no LLM call."""
    item = search_listings("vintage graphic tee", size=None, max_price=50)[0]
    result = create_fit_card("", item)
    assert isinstance(result, str)
    assert result == "Can't write a fit card yet — no outfit was suggested."
