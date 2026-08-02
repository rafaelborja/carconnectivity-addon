"""Providers that talk to upstream cruise sources.

The upstream tool names published in blog posts could not be confirmed against a
live ``tools/list``, so nothing here hard-codes them. Each provider discovers the
upstream tool set at call time and picks the best match by intent keywords. If a
vendor renames ``searchVoyages`` to ``search_voyages`` tomorrow, this still works.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .normalize import normalize_voyage
from .sources import Source, SourceKind

DEFAULT_TIMEOUT_SECONDS = 45.0

#: Intent -> keywords that should appear in an upstream tool name, best first.
INTENT_KEYWORDS: dict[str, tuple[tuple[str, ...], ...]] = {
    "voyages": (("voyage",), ("sailing",), ("cruise", "search"), ("itinerar",)),
    "ships": (("ship",), ("vessel",)),
    "brands": (("brand",), ("line",)),
    "content": (("content",), ("knowledge",), ("port",)),
    "booking": (("booking",), ("book",), ("quote",)),
}


class ProviderError(RuntimeError):
    """Raised when an upstream source cannot satisfy a request."""


@dataclass
class ToolMatch:
    """An upstream tool selected to serve a given intent."""

    name: str
    score: int
    input_schema: Mapping[str, Any]


def select_tool(
    tools: Sequence[Any], intent: str, override: str | None = None
) -> ToolMatch | None:
    """Choose the upstream tool that best serves ``intent``.

    An explicit ``override`` always wins when present, so operators can pin a
    tool name once they have inspected a server themselves.
    """
    by_name = {getattr(t, "name", ""): t for t in tools}

    if override:
        tool = by_name.get(override)
        if tool is None:
            raise ProviderError(
                f"Pinned tool {override!r} is not exposed upstream. "
                f"Available: {sorted(by_name)}"
            )
        return ToolMatch(override, 1000, getattr(tool, "inputSchema", {}) or {})

    keyword_sets = INTENT_KEYWORDS.get(intent, ())
    best: ToolMatch | None = None
    for name, tool in by_name.items():
        lowered = name.lower()
        for rank, keywords in enumerate(keyword_sets):
            if all(k in lowered for k in keywords):
                score = len(keyword_sets) - rank
                if best is None or score > best.score:
                    best = ToolMatch(name, score, getattr(tool, "inputSchema", {}) or {})
                break
    return best


def filter_to_schema(
    arguments: Mapping[str, Any], input_schema: Mapping[str, Any]
) -> dict[str, Any]:
    """Drop arguments the upstream tool does not declare.

    Servers that set ``additionalProperties: false`` reject unknown keys
    outright, so sending our full superset of filters would fail the call.
    """
    properties = (input_schema or {}).get("properties")
    if not isinstance(properties, dict) or not properties:
        return {k: v for k, v in arguments.items() if v is not None}
    return {k: v for k, v in arguments.items() if v is not None and k in properties}


def extract_records(result: Any) -> list[dict[str, Any]]:
    """Pull a list of record dicts out of an MCP tool result.

    Handles structured content, JSON embedded in text content, and the common
    envelope shapes (``{"results": [...]}``, ``{"data": {"items": [...]}}``).
    """
    payload: Any = None

    for attr in ("data", "structured_content", "structuredContent"):
        candidate = getattr(result, attr, None)
        if candidate not in (None, {}, []):
            payload = candidate
            break

    if payload is None:
        texts = [
            getattr(block, "text", None)
            for block in getattr(result, "content", []) or []
        ]
        for text in [t for t in texts if t]:
            try:
                payload = json.loads(text)
                break
            except (TypeError, ValueError):
                continue
        else:
            return []

    return _records_from_payload(payload)


def _records_from_payload(payload: Any) -> list[dict[str, Any]]:
    """Walk common envelope shapes down to a list of dicts."""
    seen_depth = 0
    while isinstance(payload, dict) and seen_depth < 5:
        for key in ("results", "items", "voyages", "cruises", "ships", "data", "value"):
            if key in payload:
                payload = payload[key]
                break
        else:
            return [payload]
        seen_depth += 1

    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    return []


class McpSourceProvider:
    """Calls an upstream MCP server over its published HTTP endpoint."""

    def __init__(self, source: Source, timeout: float = DEFAULT_TIMEOUT_SECONDS):
        if source.kind is not SourceKind.MCP or not source.endpoint:
            raise ProviderError(f"Source {source.id!r} is not a callable MCP source")
        self.source = source
        self.timeout = timeout

    def _client(self):
        """Build a client lazily so importing the module needs no network stack."""
        from fastmcp import Client

        return Client(self.source.endpoint, timeout=self.timeout)

    async def list_tools(self) -> list[Any]:
        """Return the upstream tool list (also serves as a health check)."""
        async with self._client() as client:
            return list(await client.list_tools())

    async def call_intent(
        self, intent: str, arguments: Mapping[str, Any], override: str | None = None
    ) -> tuple[str, list[dict[str, Any]]]:
        """Resolve ``intent`` to an upstream tool, call it, return raw records."""
        async with self._client() as client:
            tools = list(await client.list_tools())
            match = select_tool(tools, intent, override)
            if match is None:
                raise ProviderError(
                    f"{self.source.id}: no tool matching intent {intent!r}. "
                    f"Exposed tools: {sorted(getattr(t, 'name', '') for t in tools)}"
                )
            payload = filter_to_schema(arguments, match.input_schema)
            result = await client.call_tool(match.name, payload)
            return match.name, extract_records(result)

    async def search_voyages(
        self, arguments: Mapping[str, Any], override: str | None = None
    ) -> list[dict[str, Any]]:
        """Search voyages and normalize the result."""
        _, records = await self.call_intent("voyages", arguments, override)
        return [normalize_voyage(r, self.source.id) for r in records]


class ApifyProvider:
    """Runs an Apify actor synchronously and returns its dataset items.

    Apify is a paid path: the CruiseMapper actor bills per result and free
    accounts are capped at 5 results per run.
    """

    def __init__(self, source: Source, token: str | None = None, timeout: float = 300.0):
        self.source = source
        self.token = token or os.environ.get("APIFY_TOKEN")
        self.timeout = timeout

    async def run(self, actor_input: Mapping[str, Any]) -> list[dict[str, Any]]:
        """Execute the actor and return raw dataset items."""
        if not self.token:
            raise ProviderError(
                "APIFY_TOKEN is not set. Export it, or omit the apify source. "
                "Note this actor is billed per result and is not a free source."
            )
        if not self.source.endpoint:
            raise ProviderError(f"Source {self.source.id!r} has no endpoint")

        import httpx

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                self.source.endpoint,
                params={"token": self.token},
                json=dict(actor_input),
            )
            response.raise_for_status()
            data = response.json()
        return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []

    async def search_voyages(self, actor_input: Mapping[str, Any]) -> list[dict[str, Any]]:
        """Run the actor and normalize its dataset items."""
        return [normalize_voyage(r, self.source.id) for r in await self.run(actor_input)]
