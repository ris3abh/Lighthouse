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


def _name_tokens(name: str) -> list[str]:
    import re
    import unicodedata

    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z ]", " ", plain.lower()).split()


def names_person(text: str, names: list[str]) -> bool:
    """True when a page names the person: first and last name (of the name or an alias) next to each other,
    "Ravi Iyer" or "Iyer, Ravi". A shared surname alone is a possible namesake, not a match."""
    import re

    words = _name_tokens(text)
    pairs = set(zip(words, words[1:], strict=False))
    import unicodedata

    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    for name in names:
        tokens = _name_tokens(name)
        if len(tokens) < 2:
            continue
        first, last = tokens[0], tokens[-1]
        if (first, last) in pairs:
            return True
        # "Chen, Maya" as a listing, but not "Chen, Maya Lin" (two people)
        if re.search(rf"\b{last},\s*{first}\b(?!\s+(?!and\b|of\b|at\b)[a-z]{{2,}})", plain):
            return True
        joined = " ".join(words)
        if f"{first} {' '.join(tokens[1:-1])} {last}".replace("  ", " ") in joined:
            return True
    return False
