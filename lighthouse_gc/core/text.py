"""Small text helpers for user-facing strings."""

from __future__ import annotations

IRREGULAR = {
    "criterion": "criteria",
    "entry": "entries",
    "inquiry": "inquiries",
    "is": "are",
    "needs": "need",
}


def plural(n: int | float, word: str, many: str | None = None) -> str:
    """'1 candidate', '12 candidates', '1 criterion', '3 criteria' (the last word of a phrase is pluralized)."""
    if n == 1:
        return f"1 {word}"
    if many is None:
        head, _, last = word.rpartition(" ")
        last = IRREGULAR.get(last, last + ("es" if last.endswith(("s", "x", "ch", "sh")) else "s"))
        many = f"{head} {last}" if head else last
    count = f"{n:,}" if isinstance(n, int) else f"{n:g}"
    return f"{count} {many}"
