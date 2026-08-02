"""Shared resilient HTTP client for the orchestrator's model gateways.

All providers (mcpmart / antigravity / literouter / pydantic — all local) are wired
to a single `httpx.AsyncClient` built here so the pool, HTTP/2, TLS and timeout config
live in ONE place. Retries on transient 429/5xx faults are handled at the TRANSPORT
layer via `AsyncTenacityTransport` (pydantic-ai) using `validate_retryable_response` as
the gate — not at the agent layer — so a single model call is retried in-place with
jittered exponential backoff and NO context loss.
"""

from __future__ import annotations

import asyncio
import json
import threading
from collections.abc import Callable, Mapping
from typing import Any

import httpx
from pydantic_ai.retries import AsyncTenacityTransport, RetryConfig
from tenacity import retry_if_exception_type, stop_after_attempt, stop_after_delay, wait_exponential

# Status codes that are safe to retry on (transient provider/gateway faults).
RETRYABLE_STATUS: frozenset[int] = frozenset({408, 409, 429, 500, 502, 503, 504})

# Transport-level validator set: transient HTTP statuses only (no permanent 4xx).
RETRYABLE_STATUS_CODES: frozenset[int] = frozenset({429, 500, 502, 503, 504})

# How many times the transport retries a transient response before giving up.
MAX_MODEL_RETRIES: int = 3

# connect=15s fails fast on unreachable gateways; read=300s covers slow models
# (deepseek-v4-pro); write=30s / pool=60s match a chatty multi-agent run.
ORCH_HTTP_TIMEOUT: httpx.Timeout = httpx.Timeout(
    connect=15.0, read=300.0, write=30.0, pool=60.0
)

# Generous pool: up to 200 connections, 60 kept alive (operator has RAM headroom
# and runs up to MAX_AGENTS concurrent agents).
ORCH_HTTP_LIMITS: httpx.Limits = httpx.Limits(
    max_connections=200, max_keepalive_connections=60
)


def _fix_openrouter_error_finish_reason(response: httpx.Response) -> None:
    """Convert OpenRouter ``finish_reason: "error"`` to ``"stop"`` so pydantic-ai
    can parse the response instead of raising ``UnexpectedModelBehavior``.

    OpenRouter sets ``finish_reason`` to ``"error"`` when the endpoint fails or
    returns an error status. Pydantic-AI's OpenAI provider only accepts
    ``stop``, ``length``, ``tool_calls``, ``content_filter`` or ``function_call``.

    If the body contains an ``"error"`` field, or if ``choices`` is missing,
    ``None``, not a list, or an empty list, the response is treated as a
    transient gateway error (status 502) so that ``AsyncTenacityTransport``
    retries the request.
    """
    if response.status_code != 200:
        return
    content_type = response.headers.get("content-type", "")
    if "application/json" not in content_type:
        return
    try:
        body = response.json()
    except (ValueError, json.JSONDecodeError):
        return
    if "error" in body:
        response.status_code = 502
        return
    choices = body.get("choices")
    if not isinstance(choices, list) or len(choices) == 0:
        response.status_code = 502
        return
    changed = False
    for choice in choices:
        if isinstance(choice, dict) and choice.get("finish_reason") == "error":
            choice["finish_reason"] = "stop"
            changed = True
    if changed:
        response._content = json.dumps(body).encode("utf-8")


def validate_retryable_response(response: httpx.Response) -> None:
    """Raise only for transient HTTP statuses so the retry transport re-attempts.

    Permanent 4xx (401/403/400) pass through untouched — no wasted retries on
    bad-key / bad-request errors.
    """
    _fix_openrouter_error_finish_reason(response)
    if response.status_code in RETRYABLE_STATUS_CODES:
        response.raise_for_status()


def _build_retry_config() -> RetryConfig:
    """Transport retry policy: 90/120/240s exponential backoff, 3 attempts, reraise.

    Retries both transient HTTP statuses (via `validate_retryable_response` raising
    `HTTPStatusError`) and transport-level faults (connect/timeout/network errors),
    so the transport is the single source of retries — the agent layer needs none.
    """
    return RetryConfig(
        wait=wait_exponential(multiplier=90, min=90, max=240),
        stop=(stop_after_attempt(MAX_MODEL_RETRIES) | stop_after_delay(600)),
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.TransportError)),
        reraise=True,
    )


def create_resilient_http_client(
    *,
    event_hooks: Mapping[str, list[Callable[..., Any]]] | None = None,
) -> httpx.AsyncClient:
    """Build the shared orchestrator HTTP client with transport-level retries.

    Uses HTTP/2 with a self-signed cert (all providers are local LiteRouter-style
    proxies) and the shared pool/timeout config. `event_hooks` (request/response
    traffic logging) are passed in by the caller because they depend on orchestrator
    runtime paths.
    """
    inner = httpx.AsyncHTTPTransport(
        verify=False,  # all providers are local self-signed proxies
        limits=ORCH_HTTP_LIMITS,
        http2=False,
    )
    transport = AsyncTenacityTransport(
        _build_retry_config(),
        wrapped=inner,
        validate_response=validate_retryable_response,
    )
    merged_hooks: dict[str, list[Callable[..., Any]]] = {}
    for key, hooks in (event_hooks or {}).items():
        merged_hooks[key] = list(hooks)
    merged_hooks.setdefault("response", []).insert(0, _fix_openrouter_error_finish_reason)
    return httpx.AsyncClient(
        transport=transport,
        timeout=ORCH_HTTP_TIMEOUT,
        event_hooks=merged_hooks,
    )


_orch_http_client: httpx.AsyncClient | None = None
_orch_http_client_lock = threading.Lock()
_orch_http_client_loop: int | None = None


def get_orch_http_client() -> httpx.AsyncClient:
    """Return a loop-aware singleton `httpx.AsyncClient` for the orchestrator.

    The client is lazily created on first access (so it binds to the running
    event loop if one exists) and re-created if the event loop changes
    (e.g. after a fork or when switching threads).  Thread-safe via a mutex.
    """
    global _orch_http_client, _orch_http_client_loop
    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None
    current_loop_id = id(current_loop) if current_loop is not None else None
    with _orch_http_client_lock:
        if _orch_http_client is None or _orch_http_client_loop != current_loop_id:
            if _orch_http_client is not None:
                _orch_http_client.aclose()
            _orch_http_client = create_resilient_http_client()
            _orch_http_client_loop = current_loop_id
    return _orch_http_client