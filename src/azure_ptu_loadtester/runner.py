from __future__ import annotations

import asyncio
import json
import math
from dataclasses import dataclass
from time import perf_counter
from typing import Any

import aiohttp

from .config import EndpointConfig


@dataclass(frozen=True, slots=True)
class RequestResult:
    endpoint: str
    sequence: int
    scheduled_offset_ms: float
    queue_delay_ms: float
    latency_ms: float
    status: int | None
    success: bool
    error: str | None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


@dataclass(frozen=True, slots=True)
class RunOptions:
    rps: float
    duration_seconds: float
    prompt: str
    max_tokens: int
    timeout_seconds: float
    max_concurrency: int


@dataclass(frozen=True, slots=True)
class EndpointRun:
    endpoint: EndpointConfig
    elapsed_seconds: float
    results: list[RequestResult]


async def run_comparison(
    endpoints: tuple[EndpointConfig, EndpointConfig],
    options: RunOptions,
) -> tuple[EndpointRun, EndpointRun]:
    start_at = perf_counter() + 0.1
    first, second = await asyncio.gather(
        run_endpoint(endpoints[0], options, start_at),
        run_endpoint(endpoints[1], options, start_at),
    )
    return first, second


async def run_endpoint(
    endpoint: EndpointConfig,
    options: RunOptions,
    start_at: float | None = None,
) -> EndpointRun:
    start = perf_counter() if start_at is None else start_at
    request_count = math.ceil(options.rps * options.duration_seconds)
    semaphore = asyncio.Semaphore(options.max_concurrency)
    timeout = aiohttp.ClientTimeout(total=options.timeout_seconds)
    connector = aiohttp.TCPConnector(limit=options.max_concurrency)
    tasks: list[asyncio.Task[RequestResult]] = []

    async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
        for sequence in range(request_count):
            scheduled_at = start + sequence / options.rps
            await asyncio.sleep(max(0.0, scheduled_at - perf_counter()))
            tasks.append(
                asyncio.create_task(
                    _send_request(
                        session,
                        semaphore,
                        endpoint,
                        options,
                        sequence + 1,
                        start,
                        scheduled_at,
                    )
                )
            )

        results = await asyncio.gather(*tasks)

    elapsed_seconds = max(0.0, perf_counter() - start)
    return EndpointRun(endpoint=endpoint, elapsed_seconds=elapsed_seconds, results=results)


async def _send_request(
    session: aiohttp.ClientSession,
    semaphore: asyncio.Semaphore,
    endpoint: EndpointConfig,
    options: RunOptions,
    sequence: int,
    run_start: float,
    scheduled_at: float,
) -> RequestResult:
    async with semaphore:
        request_started = perf_counter()
        status: int | None = None
        try:
            async with session.post(
                endpoint.request_url,
                headers={"api-key": endpoint.api_key, "Content-Type": "application/json"},
                json={
                    "model": endpoint.model,
                    "messages": [{"role": "user", "content": options.prompt}],
                    endpoint.token_limit_parameter: options.max_tokens,
                },
            ) as response:
                status = response.status
                response_bytes = await response.read()
                latency_ms = (perf_counter() - request_started) * 1000
                if 200 <= status < 300:
                    usage = _read_usage(response_bytes)
                    return RequestResult(
                        endpoint=endpoint.name,
                        sequence=sequence,
                        scheduled_offset_ms=(scheduled_at - run_start) * 1000,
                        queue_delay_ms=(request_started - scheduled_at) * 1000,
                        latency_ms=latency_ms,
                        status=status,
                        success=True,
                        error=None,
                        prompt_tokens=usage.get("prompt_tokens"),
                        completion_tokens=usage.get("completion_tokens"),
                    )

                detail = response_bytes.decode("utf-8", errors="replace")[:200]
                detail = detail.replace(endpoint.api_key, "[REDACTED_KEY]")
                detail = detail.replace(options.prompt, "[REDACTED_PROMPT]")
                error = f"HTTP {status}: {detail}"
        except (aiohttp.ClientError, TimeoutError) as exception:
            latency_ms = (perf_counter() - request_started) * 1000
            error = f"{type(exception).__name__}: {exception}"

        return RequestResult(
            endpoint=endpoint.name,
            sequence=sequence,
            scheduled_offset_ms=(scheduled_at - run_start) * 1000,
            queue_delay_ms=(request_started - scheduled_at) * 1000,
            latency_ms=latency_ms,
            status=status,
            success=False,
            error=error,
        )


def _read_usage(response_bytes: bytes) -> dict[str, int | None]:
    try:
        document: Any = json.loads(response_bytes)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}
    usage = document.get("usage") if isinstance(document, dict) else None
    if not isinstance(usage, dict):
        return {}
    return {
        "prompt_tokens": _optional_int(usage.get("prompt_tokens")),
        "completion_tokens": _optional_int(usage.get("completion_tokens")),
    }


def _optional_int(value: object) -> int | None:
    return value if isinstance(value, int) else None