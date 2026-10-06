"""Redaction: currency amounts (plus emails and phone numbers) are removed; plain numbers always pass through."""

from __future__ import annotations

import pytest

from lighthouse_gc.agent.redact import redact

PLAIN = [
    "1,840 stars, 212 forks, 37 contributors, 12 releases",
    "118,000 downloads (15,400 last 30d) · ♥ 233 · 14 derivative models",
    "63 citations; h-index 12; i10-index 9",
    "2026-10-14", "Oct 14, 2026", "14 October 2026", "10/14/2026", "2026-10-06T18:30:00+00:00",
    "v0.12.0", "arXiv:2509.04321", "arxiv.org/abs/2502.01234v2", "ICML 2025", "NeurIPS 2026",
    "+89 since 09-21", "14.8k downloads", "100k stars", "1.2M downloads", "3 of 8 criteria", "top 5%",
    "1 of 12 judges; 140 teams", "observation obs_e3b0c44298fc1c14", "run_9e2afd96d325", "sha256 0efd94182118",
    "8 CFR 214.2(o)(3)(iii)", "I-129", "Form I-140", "port 7777", "score 4.5/5", "rank #3 of 2,300",
    "https://github.com/arivera-demo/fastgrad/releases/tag/v1.2.3",
    "12 months, 365 days, 2 weeks", "build 20261006.1",
]  # fmt: skip

CURRENCY = [
    ("salary $185,000/yr", "salary [amount]/yr"),
    ("offer of $185k", "offer of [amount]"),
    ("$92,000.50 base", "[amount] base"),
    ("USD 92,000", "[amount]"),
    ("92,000 USD", "[amount]"),
    ("€4.5M round", "[amount] round"),
    ("£60,000", "[amount]"),
    ("₹12,00,000", "[amount]"),
    ("US$140,000", "[amount]"),
    ("CA$90,000", "[amount]"),
    ("1,200 dollars", "[amount]"),
    ("3 million euros", "[amount]"),
    ("$2 million grant", "[amount] grant"),
]


@pytest.mark.parametrize("text", PLAIN)
def test_plain_numbers_pass_through(text):
    assert redact(text) == text


@pytest.mark.parametrize(("text", "expected"), CURRENCY)
def test_currency_amounts_are_redacted(text, expected):
    assert redact(text) == expected


def test_emails_and_phones_are_redacted_but_nearby_numbers_survive():
    text = "Contact a.b@c.org or +1 (412) 555-0100 / 412-555-0100 about the 1,840-star repo (63 citations)."
    assert redact(text) == "Contact [email] or [phone] / [phone] about the 1,840-star repo (63 citations)."


def test_redaction_is_idempotent():
    once = redact("pay $185,000, mail x@y.io, 118,000 downloads")
    assert redact(once) == once == "pay [amount], mail [email], 118,000 downloads"


def test_punctuation_after_an_amount_is_kept():
    assert redact("Paid $185,000, then £5. Done!") == "Paid [amount], then [amount]. Done!"
