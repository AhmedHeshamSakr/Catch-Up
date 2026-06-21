import httpx
import pytest

from app.services import net
from app.services.net import UnsafeURLError, is_http_url, safe_get, validate_public_url


def _resolver(ips):
    return lambda host: ips


def test_rejects_non_http_scheme():
    with pytest.raises(UnsafeURLError):
        validate_public_url("file:///etc/passwd", resolver=_resolver(["1.1.1.1"]))


def test_rejects_missing_host():
    with pytest.raises(UnsafeURLError):
        validate_public_url("http://", resolver=_resolver(["1.1.1.1"]))


def test_rejects_loopback_and_private():
    for ip in ("127.0.0.1", "10.0.0.5", "192.168.1.1", "169.254.1.1"):
        with pytest.raises(UnsafeURLError):
            validate_public_url("http://internal.example", resolver=_resolver([ip]))


def test_rejects_non_global_cgnat():
    """100.64.0.0/10 (CGNAT) is not private/loopback but is NOT globally routable —
    the is_global check must reject it."""
    with pytest.raises(UnsafeURLError):
        validate_public_url("http://internal.example", resolver=_resolver(["100.64.0.1"]))


def test_rejects_ipv4_mapped_ipv6_private():
    """An IPv4-mapped IPv6 (::ffff:10.0.0.1) must be normalized + rejected."""
    with pytest.raises(UnsafeURLError):
        validate_public_url("http://internal.example", resolver=_resolver(["::ffff:10.0.0.1"]))


def test_allows_public_host_and_returns_pinned_ip():
    url, ip = validate_public_url(
        "https://news.example.com/feed", resolver=_resolver(["93.184.216.34"])
    )
    assert url == "https://news.example.com/feed"
    assert ip == "93.184.216.34"  # returns the IP to pin the connection to


def test_safe_get_connects_to_the_validated_ip_not_a_reresolved_one(monkeypatch):
    # resolver returns a public IP; if the code re-resolved via the hostname at
    # connect time it could hit a DIFFERENT (attacker) IP. Pinning proves it doesn't.
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url_host"] = request.url.host
        seen["host_header"] = request.headers.get("host")
        seen["sni"] = request.extensions.get("sni_hostname")
        return httpx.Response(200, text="ok")

    real_client = httpx.Client

    def fake_client(**kwargs):
        kwargs.pop("transport", None)
        return real_client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(net.httpx, "Client", fake_client)
    resp = safe_get("https://example.com/x", resolver=_resolver(["93.184.216.34"]))
    assert resp.status_code == 200
    assert seen["url_host"] == "93.184.216.34"   # connected to the pinned IP
    assert seen["host_header"] == "example.com"  # original Host preserved
    assert seen["sni"] == "example.com"          # TLS SNI = real hostname


def _mock_client_factory(handler):
    real_client = httpx.Client

    def fake_client(**kwargs):
        kwargs.pop("transport", None)
        return real_client(transport=httpx.MockTransport(handler), **kwargs)

    return fake_client


def test_safe_get_brackets_ipv6_host_header(monkeypatch):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["host"] = request.headers.get("host")
        return httpx.Response(200, text="ok")

    monkeypatch.setattr(net.httpx, "Client", _mock_client_factory(handler))
    ip6 = "2606:2800:220:1:248:1893:25c8:1946"
    safe_get(f"https://[{ip6}]:8443/x", resolver=_resolver([ip6]))
    assert seen["host"] == f"[{ip6}]:8443"  # IPv6 literal bracketed, port kept


def test_safe_get_strips_caller_supplied_host_header(monkeypatch):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["host"] = request.headers.get("host")
        seen["host_count"] = sum(1 for k, _ in request.headers.raw if k.lower() == b"host")
        return httpx.Response(200, text="ok")

    monkeypatch.setattr(net.httpx, "Client", _mock_client_factory(handler))
    safe_get(
        "https://example.com/x",
        resolver=_resolver(["93.184.216.34"]),
        headers={"host": "evil.example"},
    )
    assert seen["host"] == "example.com"  # caller's host overridden, not duplicated
    assert seen["host_count"] == 1


def test_safe_get_rejects_oversized_content_length(monkeypatch):
    # A response advertising a body over the cap is rejected before download.
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"x" * 2000)  # httpx sets content-length=2000

    monkeypatch.setattr(net.httpx, "Client", _mock_client_factory(handler))
    with pytest.raises(UnsafeURLError, match="too large"):
        safe_get("https://example.com/x", resolver=_resolver(["93.184.216.34"]), max_bytes=1000)


def test_safe_get_rejects_oversized_stream(monkeypatch):
    # No content-length (chunked); the streamed body crosses the cap mid-read.
    class _Stream(httpx.SyncByteStream):
        def __iter__(self):
            yield b"x" * 50
            yield b"x" * 50

        def close(self) -> None:
            pass

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=_Stream())

    monkeypatch.setattr(net.httpx, "Client", _mock_client_factory(handler))
    with pytest.raises(UnsafeURLError, match="exceeds"):
        safe_get("https://example.com/x", resolver=_resolver(["93.184.216.34"]), max_bytes=10)


def test_safe_get_allows_body_under_cap(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="ok")

    monkeypatch.setattr(net.httpx, "Client", _mock_client_factory(handler))
    resp = safe_get("https://example.com/x", resolver=_resolver(["93.184.216.34"]), max_bytes=1000)
    assert resp.status_code == 200
    assert resp.text == "ok"


def test_rejects_empty_resolution():
    with pytest.raises(UnsafeURLError):
        validate_public_url("http://news.example.com", resolver=_resolver([]))


def test_rejects_multicast_reserved_unspecified():
    for ip in ("224.0.0.1", "240.0.0.1", "0.0.0.0"):
        with pytest.raises(UnsafeURLError):
            validate_public_url("http://x.example", resolver=_resolver([ip]))


def test_is_http_url_accepts_http_and_https():
    assert is_http_url("http://img.example/a.jpg")
    assert is_http_url("https://img.example/a.jpg")


def test_is_http_url_rejects_other_schemes_and_relative_and_none():
    assert not is_http_url("javascript:alert(1)")
    assert not is_http_url("data:image/png;base64,AAAA")
    assert not is_http_url("/relative/path.jpg")
    assert not is_http_url("ftp://img.example/a.jpg")
    assert not is_http_url("")
    assert not is_http_url(None)
