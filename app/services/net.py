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


def is_http_url(url: str | None) -> bool:
    """Return True only for absolute http(s) URLs.

    Used to validate per-article image URLs before storing them: rejects None,
    empty, relative paths, and dangerous schemes (javascript:, data:, file:, ...)
    so the browser only ever loads http(s) thumbnails. This is a cheap scheme
    check, NOT an SSRF guard — we never server-side fetch the image.
    """
    if not url:
        return False
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def _default_resolver(host: str) -> list[str]:
    return [info[4][0] for info in socket.getaddrinfo(host, None)]


def validate_public_url(
    url: str, *, resolver: Callable[[str], list[str]] = _default_resolver
) -> tuple[str, str]:
    """Validate the URL is http(s) and resolves only to public IPs.

    Returns ``(url, first_safe_ip)`` — the caller connects to ``first_safe_ip``
    directly (IP-pinning) so the host can't re-resolve to a private address
    between this check and the connection (DNS-rebinding / TOCTOU).
    """
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
    return url, addresses[0]


def safe_get(
    url: str,
    *,
    timeout: float = 15.0,
    resolver: Callable[[str], list[str]] = _default_resolver,
    headers: dict[str, str] | None = None,
    params: dict | None = None,
    max_redirects: int = 3,
    max_bytes: int = 5_000_000,
) -> httpx.Response:
    """SSRF-safe HTTP GET: validates the public-ness of EVERY hop AND pins the IP.

    Redirects are NOT auto-followed by httpx. Each hop is re-validated via
    ``validate_public_url`` before the request, so a 302 to a private/loopback/
    link-local address (e.g. cloud metadata at ``169.254.169.254``) cannot bypass
    the guard. We then connect to the *validated IP* directly (with the original
    Host header and TLS SNI = the real hostname), closing the DNS-rebinding /
    TOCTOU window where the host could re-resolve to a private IP between the
    check and the connection. Returns the final non-redirect ``httpx.Response``.
    """
    # Drop any caller-supplied Host so we never emit a duplicate Host header
    # alongside the computed one below.
    merged_headers = {
        k: v for k, v in {**_HEADERS, **(headers or {})}.items() if k.lower() != "host"
    }
    current_url = url
    # ``params`` only apply to the initial request; redirect targets carry their
    # own query string, so we drop them after the first hop.
    next_params = params
    for _ in range(max_redirects + 1):
        _, safe_ip = validate_public_url(current_url, resolver=resolver)
        parsed = httpx.URL(current_url)
        pinned = parsed.copy_with(host=safe_ip)  # connect to the validated IP
        # Keep the original Host (with non-default port) for vhost routing; SNI
        # uses the bare hostname so the TLS cert validates against the real name.
        # Bracket IPv6 literals in the Host header (httpx.URL.host is unbracketed).
        bare_host = parsed.host
        host_for_header = f"[{bare_host}]" if ":" in bare_host else bare_host
        host_header = (
            host_for_header if parsed.port is None else f"{host_for_header}:{parsed.port}"
        )
        req_headers = {**merged_headers, "Host": host_header}
        extensions = {"sni_hostname": parsed.host} if parsed.scheme == "https" else {}
        # httpx 0.28's httpx.get() has no extensions= kwarg — build via a Client.
        # trust_env=False: ignore *_PROXY env — a proxy tunnel ignores
        # sni_hostname (TLS would validate against the pinned IP) AND a proxy
        # would defeat the IP-pin (it re-resolves the host), reopening SSRF.
        with httpx.Client(timeout=timeout, follow_redirects=False, trust_env=False) as client:
            request = client.build_request(
                "GET", str(pinned), headers=req_headers,
                params=next_params, extensions=extensions,
            )
            # Stream so we can abort an oversized body BEFORE pulling it all into
            # memory — a user-supplied URL returning a multi-GB response from a
            # legit public host would otherwise OOM the process.
            resp = client.send(request, stream=True)
            try:
                if resp.is_redirect and resp.headers.get("location"):
                    location = resp.headers["location"]
                    current_url = str(httpx.URL(current_url).join(location))
                    next_params = None
                    continue
                declared = resp.headers.get("content-length")
                if declared is not None and declared.isdigit() and int(declared) > max_bytes:
                    raise UnsafeURLError(
                        f"response too large: {declared} bytes (> {max_bytes})"
                    )
                body = bytearray()
                # Bound each chunk (64 KiB) so a lying/chunked/decoded (e.g. gzip)
                # response can't hand us one giant chunk, and check the PROJECTED
                # size before extending — we never hold more than max_bytes + 64 KiB.
                for chunk in resp.iter_bytes(chunk_size=65536):
                    if len(body) + len(chunk) > max_bytes:
                        raise UnsafeURLError(f"response exceeds {max_bytes} bytes")
                    body.extend(chunk)
                # Return a fully-read Response so callers use .text/.json/.content.
                return httpx.Response(
                    status_code=resp.status_code,
                    headers=resp.headers,
                    content=bytes(body),
                    request=resp.request,
                )
            finally:
                resp.close()
    raise UnsafeURLError(f"too many redirects (>{max_redirects}) for {url}")
