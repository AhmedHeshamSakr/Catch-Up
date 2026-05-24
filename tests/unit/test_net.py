import pytest

from app.services.net import UnsafeURLError, is_http_url, validate_public_url


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


def test_allows_public_host():
    assert validate_public_url(
        "https://news.example.com/feed", resolver=_resolver(["93.184.216.34"])
    ) == "https://news.example.com/feed"


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
