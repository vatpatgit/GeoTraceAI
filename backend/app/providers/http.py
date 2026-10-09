"""HTTP helpers: bounded retries with exponential backoff, and OAuth2 client-credentials token caching."""
from __future__ import annotations

import asyncio
import logging
import random
import time
from typing import Any

import httpx

from app.config import settings
from app.providers.base import ProviderAuthError, ProviderError, ProviderRateLimited, ProviderUnavailable

logger = logging.getLogger(__name__)
RETRYABLE_STATUS = {500, 502, 503, 504}


def _client(timeout: float | None = None) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=httpx.Timeout(timeout or settings.PROVIDER_TIMEOUT_S, connect=10.0), follow_redirects=True)


async def request(method: str, url: str, *, retries: int | None = None, timeout: float | None = None, **kwargs: Any) -> httpx.Response:
    """One logical request with at most ``PROVIDER_MAX_RETRIES`` attempts.

    Retried: connection errors/timeouts, HTTP 5xx and 429 (honouring ``Retry-After`` up to 20 s). NOT retried: 4xx other
    than 429 (auth / validation problems will not heal). Errors map onto ``ProviderError`` subclasses with clear messages.
    """
    attempts = max(1, (retries if retries is not None else settings.PROVIDER_MAX_RETRIES))
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            async with _client(timeout) as client:
                resp = await client.request(method, url, **kwargs)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            last = exc
            logger.warning("provider request error (%s %s) attempt %d/%d: %s", method, url, attempt + 1, attempts, type(exc).__name__)
        else:
            if resp.status_code == 429 and attempt < attempts - 1:
                delay = min(_retry_after(resp) or 2 ** attempt, 20.0)
                await asyncio.sleep(delay)
                continue
            if resp.status_code in RETRYABLE_STATUS and attempt < attempts - 1:
                await asyncio.sleep(_backoff(attempt))
                continue
            return raise_for_status(resp)
        if attempt < attempts - 1:
            await asyncio.sleep(_backoff(attempt))
    if isinstance(last, httpx.TimeoutException):
        raise ProviderUnavailable("The imagery provider did not answer in time. Try again shortly.", code="provider_timeout", status=504) from last
    raise ProviderUnavailable("Could not reach the imagery provider (network error).") from last


def _backoff(attempt: int) -> float:
    return min(0.4 * (2 ** attempt) + random.uniform(0, 0.2), 8.0)


def _retry_after(resp: httpx.Response) -> float | None:
    try:
        return float(resp.headers.get("retry-after", ""))
    except ValueError:
        return None


def _detail(resp: httpx.Response) -> str:
    try:
        body = resp.json()
        if isinstance(body, dict):
            err = body.get("error")
            msg = (err.get("message") if isinstance(err, dict) else err) or body.get("message") or body.get("detail") or body.get("description")
            if msg:
                return str(msg)[:300]
    except ValueError:
        pass
    return resp.text[:200]


def raise_for_status(resp: httpx.Response) -> httpx.Response:
    s = resp.status_code
    if s < 400:
        return resp
    d = _detail(resp)
    if s in (401, 403):
        raise ProviderAuthError(f"The imagery provider rejected the configured credentials (HTTP {s}). Check the server's client id/secret and provider. {d}")
    if s == 429:
        raise ProviderRateLimited("The imagery provider's rate or processing quota was exceeded. Retry later.", retry_after=_retry_after(resp))
    if s == 404:
        raise ProviderError(f"Provider resource not found: {d}", code="provider_not_found", status=404)
    if s in (400, 422):
        raise ProviderError(f"The provider rejected the request: {d}", code="provider_bad_request", status=422)
    raise ProviderUnavailable(f"The imagery provider failed (HTTP {s}). {d}")


class TokenManager:
    """OAuth2 client-credentials with in-memory caching and early refresh (credentials never leave the server)."""

    def __init__(self, token_url: str, client_id: str, client_secret: str):
        self.token_url, self._id, self._secret = token_url, client_id, client_secret
        self._token: str | None = None
        self._expires = 0.0
        self._lock = asyncio.Lock()

    async def get(self, *, force: bool = False) -> str:
        async with self._lock:
            if not force and self._token and time.time() < self._expires - 60:
                return self._token
            resp = await request("POST", self.token_url, retries=2, data={
                "grant_type": "client_credentials", "client_id": self._id, "client_secret": self._secret})
            body = resp.json()
            token = body.get("access_token")
            if not token:
                raise ProviderAuthError("The provider's token endpoint did not return an access token.")
            self._token = token
            self._expires = time.time() + float(body.get("expires_in", 600))
            return token

    def invalidate(self) -> None:
        self._token, self._expires = None, 0.0
