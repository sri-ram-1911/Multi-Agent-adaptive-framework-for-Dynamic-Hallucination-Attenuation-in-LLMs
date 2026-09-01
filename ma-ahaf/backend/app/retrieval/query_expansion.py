"""Query expansion for ambiguous / under-specified claims (proposal §11)."""

from __future__ import annotations

from app.llm.gateway import Gateway

_SYS = (
    "You expand a search query for a retrieval system. Given a claim or question, "
    "return JSON {\"queries\": [...]} with 2-4 diverse reformulations that would "
    "surface supporting AND contradicting evidence. Keep them short."
)


def expand(gateway: Gateway, query: str, *, enabled: bool) -> list[str]:
    if not enabled:
        return [query]
    data = gateway.complete_json(
        "expander",
        [{"role": "system", "content": _SYS}, {"role": "user", "content": query}],
        temperature=0.3,
        max_tokens=200,
    )
    queries = [q for q in data.get("queries", []) if isinstance(q, str)]
    out = [query, *queries]
    # de-dup preserving order
    seen: set[str] = set()
    return [q for q in out if not (q.lower() in seen or seen.add(q.lower()))][:4]
