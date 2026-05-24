import os


def test_ensure_api_key_sets_env_when_present(monkeypatch):
    from app.core.config import Settings
    from app.llm.runtime import ensure_api_key
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    ensure_api_key(Settings(google_api_key="abc123"))
    assert os.environ["GOOGLE_API_KEY"] == "abc123"
    # ensure_api_key writes to os.environ directly (bypasses monkeypatch),
    # so clean up explicitly to avoid leaking into other tests.
    os.environ.pop("GOOGLE_API_KEY", None)
