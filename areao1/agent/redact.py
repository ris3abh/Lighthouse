"""Redact before LLM (SPEC 10): strip emails, phone numbers and currency amounts from text sent to the engine.

Only *currency* amounts are numeric redactions. Plain numbers (downloads, stars, citations, counts, versions,
ids, dates, percentages) pass through untouched, because the agent needs them to reason about the case.
"""

from __future__ import annotations

import re

EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
# Phone numbers in common written forms: +1 (412) 555-0100, 412-555-0100, 412.555.0100. Separators are required,
# so plain digit runs (ids, counts) never match.
PHONE = re.compile(
    r"(?<![\w/.:-])(?:\+\d{1,3}[\s.-]?)?(?:\(\d{3}\)\s?|\d{3}[\s.-])\d{3}[\s.-]\d{4}(?![\w/-])"
)

_NUM = r"\d+(?:,\d+)*(?:\.\d+)?"  # a comma only counts when digits follow it
_SCALE = r"(?:\s?(?:[kKmM]\b|bn\b|million\b|billion\b|thousand\b|lakh\b|crore\b))?"
_SYMBOL = r"(?:US\$|CA\$|C\$|AU\$|A\$|\$|€|£|₹|¥)"
_CODE = r"(?:USD|EUR|GBP|INR|CAD|AUD|JPY|CNY)"
_WORD = r"(?:dollars?|euros?|pounds?(?:\s+sterling)?|rupees?)"
MONEY = re.compile(
    rf"{_SYMBOL}\s?{_NUM}{_SCALE}"  # $185,000  $185k  €4.5M  ₹12,00,000
    rf"|\b{_CODE}\s?{_NUM}{_SCALE}"  # USD 92,000
    rf"|\b{_NUM}{_SCALE}\s?(?:{_CODE}\b|{_WORD}\b)",  # 92,000 USD  1,200 dollars  3 million euros
    re.IGNORECASE,
)


def redact(text: str) -> str:
    text = EMAIL.sub("[email]", text)
    text = PHONE.sub("[phone]", text)
    return MONEY.sub("[amount]", text)
