"""The mundane tier on OpenAI (ADR 0009 §2): one tool-less, single-turn request, used only for bulk, simple reading
(chat-history extraction, summarizing long chats). Same protections as the Claude path: the input is redacted
first, the monthly cap applies, and the cost is recorded. ``client`` is injectable so tests never call OpenAI."""

from __future__ import annotations

from typing import Any

import httpx

from lighthouse_gc.agent.redact import redact
from lighthouse_gc.vault.rulecheck import Judge, JudgeReply

URL = "https://api.openai.com/v1/chat/completions"
# USD per million tokens (input, output). A model not listed records tokens without a cost.
PRICES: dict[str, tuple[float, float]] = {"gpt-5-mini": (0.25, 2.0), "gpt-5-nano": (0.05, 0.4)}


def cost(model: str, usage: dict[str, int]) -> float | None:
    price = PRICES.get(model)
    if price is None:
        return None
    return round(
        (usage.get("input_tokens", 0) * price[0] + usage.get("output_tokens", 0) * price[1]) / 1e6, 6
    )


def openai_judge(key: str, client: httpx.AsyncClient | None = None, redact_input: bool = True) -> Judge:
    async def judge(system: str, prompt: str, model: str) -> JudgeReply:
        body: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": redact(system) if redact_input else system},
                {"role": "user", "content": redact(prompt) if redact_input else prompt},
            ],
        }
        headers = {"Authorization": f"Bearer {key}"}
        own = client is None
        c = client or httpx.AsyncClient(timeout=120)
        try:
            r = await c.post(URL, json=body, headers=headers)
        finally:
            if own:
                await c.aclose()
        if r.status_code != 200:
            raise RuntimeError(f"OpenAI answered {r.status_code}: {r.text[:200]}")
        data = r.json()
        u = data.get("usage") or {}
        usage = {
            "input_tokens": int(u.get("prompt_tokens", 0)),
            "output_tokens": int(u.get("completion_tokens", 0)),
        }
        text = (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""
        return JudgeReply(text, usage, cost(model, usage))

    return judge
