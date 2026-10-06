"""Redact before LLM (SPEC 10): strip emails, phone numbers and money amounts from text sent to the engine."""

from __future__ import annotations

import re

EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PHONE = re.compile(r"(?<![\w/.-])(?:\+?\d{1,3}[\s.-]?)?(?:\(\d{3}\)|\d{3})[\s.-]\d{3}[\s.-]\d{4}(?![\w/-])")
MONEY = re.compile(
    r"(?:[$€£₹]\s?\d[\d,]*(?:\.\d+)?\s?(?:[kKmM](?![a-zA-Z]))?|\b\d[\d,]*(?:\.\d+)?\s?(?:USD|EUR|GBP|INR)\b)"
)


def redact(text: str) -> str:
    text = EMAIL.sub("[email]", text)
    text = PHONE.sub("[phone]", text)
    return MONEY.sub("[amount]", text)
