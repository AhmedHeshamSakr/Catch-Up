import pytest

from app.services.net import UnsafeURLError, validate_public_url


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
