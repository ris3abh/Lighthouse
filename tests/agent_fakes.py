"""The test suite's engine: the real OpenAI engine (ADR 0015) talking to a scripted fake Responses API. Every agent,
guardrail, budget, search-policy and prompt-injection test runs through the real adapter's request building,
streaming, tool loop and usage accounting; no test calls OpenAI."""

from __future__ import annotations

import json
from typing import Any

import httpx

from areao1.engine.base import AgentTool, Emit, EngineRequest, EngineResult
from areao1.engine.openai_engine import OpenAIEngine

SEARCH_TEXT = "3 results (fake)"


def openai_usage(u: dict[str, int]) -> dict[str, Any]:
    """The runner's counters as OpenAI reports them (input_tokens includes cached reads and cache writes)."""
    cr, cw = int(u.get("cache_read_input_tokens", 0)), int(u.get("cache_creation_input_tokens", 0))
    return {"input_tokens": int(u.get("input_tokens", 0)) + cr + cw, "output_tokens": int(u.get("output_tokens", 0)),
            "input_tokens_details": {"cached_tokens": cr, "cache_write_tokens": cw},
            "output_tokens_details": {"reasoning_tokens": 0}}  # fmt: skip


def sse(events: list[dict[str, Any]]) -> bytes:
    return "".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in events).encode()


class ScriptedResponses:
    """A fake ``POST /v1/responses``. ``script`` steps: ("text", str) | ("tool", name, args) | ("search", args)
    (our web_search tool, through the request's guard) | ("usage", {...}) | ("fail", message). ``args`` may be a
    callable taking the earlier tool outputs, for ids only known at run time (an observation_id from read_page).
    A tool or search step ends the model's turn with a function call; the next request carries its output."""

    def __init__(self, script: list[tuple[Any, ...]]):
        self.script = script
        self.pos = 0
        self.bodies: list[dict[str, Any]] = []
        self.calls: dict[str, str] = {}  # call_id -> tool name
        self.tool_outputs: list[tuple[str, bool, str]] = []
        self.searches: list[dict[str, Any]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.bodies.append(body)
        if any(t.get("type") == "web_search" for t in body.get("tools") or []):
            return self._search(body)
        for item in body.get("input") or []:
            if (
                isinstance(item, dict)
                and item.get("type") == "function_call_output"
                and item["call_id"] in self.calls
            ):
                out = item["output"]
                self.tool_outputs.append((self.calls.pop(item["call_id"]), not out.startswith(("Error:", "Denied:")),
                                          out))  # fmt: skip
        events: list[dict[str, Any]] = [{"type": "response.created"}]
        output: list[dict[str, Any]] = []
        usage: dict[str, int] = {}
        while self.pos < len(self.script):
            step = self.script[self.pos]
            self.pos += 1
            if step[0] == "text":
                n = len(output)
                events.append({"type": "response.output_text.delta", "output_index": n, "delta": step[1]})
                item = {"type": "message", "id": f"msg_{self.pos}", "role": "assistant", "status": "completed",
                        "content": [{"type": "output_text", "text": step[1], "annotations": []}]}  # fmt: skip
                output.append(item)
                events.append({"type": "response.output_item.done", "output_index": n, "item": item})
            elif step[0] == "usage":
                for k, v in step[1].items():
                    usage[k] = usage.get(k, 0) + int(v)
            elif step[0] == "fail":
                events.append({"type": "error", "message": step[1], "code": "server_error"})
                return httpx.Response(200, content=sse(events), headers={"content-type": "text/event-stream"})
            elif step[0] in ("tool", "search"):
                name, args = ("web_search", step[1]) if step[0] == "search" else (step[1], step[2])
                if callable(args):
                    args = args(self.tool_outputs)
                cid = f"call_{self.pos}"
                self.calls[cid] = name
                item = {"type": "function_call", "id": f"fc_{self.pos}", "call_id": cid, "name": name,
                        "arguments": json.dumps(args), "status": "completed"}  # fmt: skip
                n = len(output)
                output.append(item)
                events.append({"type": "response.output_item.done", "output_index": n, "item": item})
                break
        events.append({"type": "response.completed", "response": {"status": "completed", "output": output,
                                                                   "usage": openai_usage(usage)}})  # fmt: skip
        return httpx.Response(200, content=sse(events), headers={"content-type": "text/event-stream"})

    def _search(self, body: dict[str, Any]) -> httpx.Response:
        self.searches.append(body)
        url = "https://example.org/result"
        return httpx.Response(200, json={
            "status": "completed",
            "output": [{"type": "web_search_call", "status": "completed",
                        "action": {"type": "search", "queries": [body["input"]], "sources": [{"url": url}]}},
                       {"type": "message", "role": "assistant",
                        "content": [{"type": "output_text", "text": SEARCH_TEXT,
                                     "annotations": [{"type": "url_citation", "url": url}]}]}],
            "usage": openai_usage({"input_tokens": 10, "output_tokens": 5}),
        })  # fmt: skip


class FakeEngine(OpenAIEngine):
    """The OpenAI engine over ScriptedResponses. ``requests`` are the EngineRequests it was given, ``tool_names``
    the tools offered, ``tool_outputs`` (name, ok, output) what each call returned, ``api.bodies`` the raw API
    requests. A run costs ``cost`` dollars, so budget tests don't depend on the price table."""

    name = "fake"

    def __init__(self, script: list[tuple[Any, ...]] | None = None, cost: float = 0.01):
        self.api = ScriptedResponses(script or [("text", "Hello from the fake engine.")])
        super().__init__(transport=httpx.MockTransport(self.api), key="sk-test-fake")
        self.cost = cost
        self.requests: list[EngineRequest] = []
        self.tool_names: list[str] = []

    @property
    def script(self) -> list[tuple[Any, ...]]:
        return self.api.script

    @script.setter
    def script(self, value: list[tuple[Any, ...]]) -> None:
        self.api.script, self.api.pos = value, 0

    @property
    def tool_outputs(self) -> list[tuple[str, bool, str]]:
        return self.api.tool_outputs

    def available(self) -> tuple[bool, str]:
        return True, "fake"

    async def run(self, request: EngineRequest, tools: list[AgentTool], emit: Emit) -> EngineResult:
        self.requests.append(request)
        self.tool_names = [t.name for t in tools]
        self.api.pos, self.api.calls = 0, {}  # each run replays the script from the start
        result = await super().run(request, tools, emit)
        result.cost_usd = self.cost
        return result
