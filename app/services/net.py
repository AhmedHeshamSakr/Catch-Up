from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable
from urllib.parse import urlparse

import httpx

# Shared User-Agent for all outbound fetches (kept identical to the collectors).
_HEADERS = {"User-Agent": "CatchUp/0.1 (+https://github.com/AhmedHeshamSakr/Catch-Up)"}


class UnsafeURLError(ValueError):
    """Raised when a URL is not safe to fetch (bad scheme or non-public address)."""


def _default_resolver(host: str) -> list[str]:
    return [info[4][0] for info in socket.getaddrinfo(host, None)]


def validate_public_url(
    url: str, *, resolver: Callable[[str], list[str]] = _default_resolver
) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise UnsafeURLError(f"scheme not allowed: {parsed.scheme!r}")
    host = parsed.hostname
    if not host:
        raise UnsafeURLError("missing host")
    try:
        addresses = resolver(host)
    except socket.gaierror as exc:
        raise UnsafeURLError(f"cannot resolve host: {host}") from exc
    if not addresses:
        raise UnsafeURLError(f"no addresses resolved for host: {host}")
    for addr in addresses:
        ip = ipaddress.ip_address(addr)
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            raise UnsafeURLError(f"{host} resolves to non-public address {ip}")
    return url


def safe_get(
    url: str,
    *,
    timeout: float = 15.0,
    resolver: Callable[[str], list[str]] = _default_resolver,
    headers: dict[str, str] | None = None,
    params: dict | None = None,
    max_redirects: int = 3,
) -> httpx.Response:
    """SSRF-safe HTTP GET: validates the public-ness of EVERY hop.

    Redirects are NOT auto-followed by httpx. Instead each hop is re-validated
    via ``validate_public_url`` before the request is issued, so a 302 to a
    private/loopback/link-local address (e.g. cloud metadata at
    ``169.254.169.254``) cannot bypass the guard. Returns the final
    non-redirect ``httpx.Response``.

    Residual risk: there is a DNS-TOCTOU window between the resolver check and
    the actual connection (the host could re-resolve to a private IP after
    validation). Per-hop re-validation plus disabling auto-redirects closes the
    *exploitable redirect bypass*; full IP-pinning (connecting to the validated
    IP directly) is a follow-up.
    """
    merged_headers = {**_HEADERS, **(headers or {})}
    current_url = url
    # ``params`` only apply to the initial request; redirect targets carry their
    # own query string, so we drop them after the first hop.
    next_params = params
    for _ in range(max_redirects + 1):
        validate_public_url(current_url, resolver=resolver)
        resp = httpx.get(
            current_url,
            timeout=timeout,
            follow_redirects=False,
            headers=merged_headers,
            params=next_params,
        )
        if resp.is_redirect and resp.headers.get("location"):
            location = resp.headers["location"]
            current_url = str(httpx.URL(current_url).join(location))
            next_params = None
            continue
        return resp
    raise UnsafeURLError(f"too many redirects (>{max_redirects}) for {url}")
