# FitFindr

A multi-tool AI agent that helps users find secondhand clothing and figure out how to wear it. Given a natural-language request, FitFindr searches a mock listings dataset, suggests an outfit that pairs the find with the user's existing wardrobe, and writes a short, shareable caption for the look, handling the cases where a tool returns nothing or gets incomplete input.

## How to run

```bash
pip install -r requirements.txt
# add your Groq key to a .env file in the repo root:
# GROQ_API_KEY=your_key_here

python app.py            # launch the Gradio interface
python agent.py          # run the planning loop from the terminal (happy path + no-results path)
pytest tests/            # run the tool tests
```

Open the URL printed in your terminal when you run `python app.py` (it is not always `localhost:7860`).

---

## Tool Inventory

All three tools live in `tools.py`. The documented signatures below match the actual function definitions.

### `search_listings(description, size, max_price) -> list[dict]`

- **Inputs:**
  - `description` (str): keywords describing the desired item, e.g. `"vintage graphic tee"`.
  - `size` (str | None, default `None`): a size to filter by; matched case-insensitively as a substring so `"M"` matches `"S/M"`. `None` skips the size filter.
  - `max_price` (float | None, default `None`): inclusive price ceiling; listings priced above it are dropped. `None` skips the price filter.
- **Output:** a `list[dict]` of matching listings, sorted by relevance score (best first). Each dict has the `listings.json` fields: `id`, `title`, `description`, `category`, `style_tags` (list), `size`, `condition`, `price` (float), `colors` (list), `brand`, `platform`. Returns `[]` if nothing matches.
- **Purpose:** It finds candidate items and ranks them so the loop can select the top result. No LLM call, pure filtering and scoring over the mock dataset.

### `suggest_outfit(new_item, wardrobe) -> str`

- **Inputs:**
  - `new_item` (dict): a listing dict (the selected item from `search_listings`).
  - `wardrobe` (dict): a wardrobe with an `"items"` key holding a list of item dicts (`id`, `name`, `category`, `colors`, `style_tags`, optional `notes`). May be empty.
- **Output:** a non-empty `str` with 1-2 outfit suggestions naming specific wardrobe pieces.
- **Purpose:** evaluates the find against what the user already owns and proposes concrete ways to wear it. Calls the LLM (Groq `llama-3.3-70b-versatile`).

### `create_fit_card(outfit, new_item) -> str`

- **Inputs:**
  - `outfit` (str): the suggestion string from `suggest_outfit`.
  - `new_item` (dict): the same selected listing dict, used to reference the item's title, price, and platform.
- **Output:** a `str` of 2-4 sentence casual caption that mentions the item name, price, and platform once each and captures the outfit vibe.
- **Purpose:** turns the outfit into something shareable (an OOTD-style post). Calls the LLM with a higher temperature so repeated calls produce varied captions.

---

## How the Planning Loop Works

The loop lives in `run_agent(query, wardrobe)` in `agent.py`. It is **conditional**, not a fixed three-call sequence. What `search_listings` returns determines whether the later tools run at all.

1. **Initialize** a session dict with `_new_session(query, wardrobe)`.

2. **Parse** the raw query string into `description`, `size`, and `max_price` using lightweight deterministic Python (regex). A price is pulled from patterns like `"under $30"`/`"$30"`; a size token (XS/S/M/L/XL, "size M") is pulled if present; the remaining cleaned text becomes the description. Results are stored in `session["parsed"]`.

3. **Search.** Call `search_listings(description, size, max_price)`; store the list in `session["search_results"]`.

4. **Branch on the result:**
   - **Empty list ->** set `session["error"]` to a specific, helpful message and **return early**. `suggest_outfit` and `create_fit_card` are never called; `selected_item`, `outfit_suggestion`, and `fit_card` stay `None`.
   - **Non-empty ->** set `session["selected_item"] = search_results[0]` and continue.

5. **Suggest outfit.** Call `suggest_outfit(selected_item, wardrobe)`; store the string in `session["outfit_suggestion"]`.

6. **Create fit card.** Call `create_fit_card(outfit_suggestion, selected_item)`; store the string in `session["fit_card"]`.

7. **Return** the session.

The loop terminates either when `fit_card` is populated (happy path) or early via the error branch with `error` set. The key conditional is the empty-results branch in step 4: that is what makes the agent respond to what it receives rather than blindly calling all three tools.

---

## State Management

A single `session` dict, created by `_new_session()`, is the single source of truth for one interaction. Every step reads its inputs from this dict and writes its outputs back, so nothing is re-entered by the user between tools. Keys (defined in `agent.py`):

| Key | Written by | Read by |
|-----|-----------|---------|
| `query` | caller / init | (reference) |
| `parsed` | parse step | `search_listings` |
| `search_results` | `search_listings` | branch logic |
| `selected_item` | branch (`results[0]`) | `suggest_outfit`, `create_fit_card` |
| `wardrobe` | caller / init | `suggest_outfit` |
| `outfit_suggestion` | `suggest_outfit` | `create_fit_card` |
| `fit_card` | `create_fit_card` | final output |
| `error` | branch (on empty results) | final output |

The flow is: parse -> `parsed` -> search -> `search_results` -> `selected_item` -> `outfit_suggestion` -> `fit_card`. Because the exact same `selected_item` dict is passed into both `suggest_outfit` and `create_fit_card`, the item found in the search reaches the caption step without the user re-describing it. `app.py`'s `handle_query()` reads the finished session and maps it to the three output panels (or shows `error` in the first panel and leaves the others empty when the search failed).

---

## Error Handling

Every tool handles its own failure mode — none fail silently and none crash the agent.

| Tool | Failure mode | Handling |
|------|--------------|----------|
| `search_listings` | No listing matches | Returns `[]` (never raises erros, never `None`). The loop sets `session["error"]` to a message telling the user what to adjust and returns early, so the later tools never receive empty input. |
| `suggest_outfit` | Wardrobe is empty (`wardrobe["items"] == []`) | Detects the empty list and asks the LLM for general styling advice for the item on its own, returning a useful non-empty string instead of crashing. |
| `create_fit_card` | Outfit string is empty/whitespace | Guards the input *before* any LLM call and returns a descriptive error string instead of raising. |

**Example from testing.** Running the impossible-query check:

```bash
python -c "from tools import search_listings; print(search_listings('designer ballgown', size='XXS', max_price=5))"
```

returned `[]` with no exception, and running the full agent on the same query produced the user-facing error message:

```
I couldn't find anything matching that. Try raising your price cap, removing the size filter, or using broader keywords (e.g. 'graphic tee' instead of 'vintage band tee')
```

while leaving `session["fit_card"]` as `None` and never calling `suggest_outfit`.

---

## Spec Reflection

**One way the spec helped:**  
Writing the tool interfaces in `planning.md` before any code meant each tool had a fixed signature, return shape, and failure mode up front. When I implemented `search_listings`, I could check the generated code against the spec line by line seeing if it does filter on all three parameters, and return `[]` rather than raising errors. The clear separation of "filter" (price/size, which drop listings) from "score" (keywords, which rank them) came straight from the spec and kept the implementation simple.

**One way implementation diverged:**  
My first planning draft assumed `run_agent` received already-parsed parameters, so it had no query-parsing step. The actual `agent.py` stub takes a raw natural-language string and requires parsing `description`/`size`/`max_price` out of it as step 2. I added a deterministic regex-based parse step and a `session["parsed"]` key to match the real signature. I chose regex over asking the LLM to parse so the behavior stays deterministic and testable, and so the loop doesn't make a fourth (slow, non-reproducible) LLM call just to read a price out of a sentence.

---

## AI Usage

I used Claude (Claude Code) during implementation. Two specific instances:

**1. `search_listings` scoring method.** I gave Claude my Tool 1 spec block from `planning.md` (inputs, return shape, failure mode) and asked it to implement the function using `load_listings()`. In planning mode it paused and asked how a query keyword should count as a match,  whole-word set overlap, substring match, or frequency-weighted. I chose **whole-word set overlap** (case-insensitive `\w+` tokenization, set intersection, each distinct query word worth at most 1), because the 40-item dataset is small enough that substring matching's extra recall wasn't worth its false positives, and whole-word scoring is predictable enough to verify by eye. I then updated the planning.md Tool 1 line to document that choice so the spec matched the code.

**2. The planning loop (`run_agent`).** I gave Claude my Architecture (Mermaid) diagram plus the Planning Loop and State Management sections, and asked it to implement `run_agent()`. Before running its output I reviewed it against my spec: does it branch on the `search_listings` result and return early on `[]`, does it write each value into the session dict, and does it avoid calling all three tools unconditionally.


