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


def test_configure_genai_vertex_sets_env(monkeypatch):
    from app.core.config import Settings
    from app.llm.runtime import configure_genai
    for k in ("GOOGLE_GENAI_USE_VERTEXAI", "GOOGLE_CLOUD_PROJECT", "GOOGLE_CLOUD_LOCATION"):
        monkeypatch.delenv(k, raising=False)
    configure_genai(Settings(_env_file=None, use_vertexai=True, google_cloud_project="proj-x"))
    assert os.environ["GOOGLE_GENAI_USE_VERTEXAI"] == "TRUE"
    assert os.environ["GOOGLE_CLOUD_PROJECT"] == "proj-x"
    assert os.environ["GOOGLE_CLOUD_LOCATION"] == "global"
    for k in ("GOOGLE_GENAI_USE_VERTEXAI", "GOOGLE_CLOUD_PROJECT", "GOOGLE_CLOUD_LOCATION"):
        os.environ.pop(k, None)


def test_configure_genai_vertex_requires_project():
    import pytest

    from app.core.config import Settings
    from app.llm.runtime import configure_genai
    with pytest.raises(ValueError, match="google_cloud_project"):
        configure_genai(Settings(_env_file=None, use_vertexai=True, google_cloud_project=""))


def test_configure_genai_vertex_respects_preset_env(monkeypatch):
    from app.core.config import Settings
    from app.llm.runtime import configure_genai
    # Operator already set the location; setdefault must NOT overwrite it.
    monkeypatch.setenv("GOOGLE_CLOUD_LOCATION", "us-central1")
    monkeypatch.delenv("GOOGLE_GENAI_USE_VERTEXAI", raising=False)
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    configure_genai(Settings(
        _env_file=None, use_vertexai=True,
        google_cloud_project="proj-x", google_cloud_location="global",
    ))
    assert os.environ["GOOGLE_CLOUD_LOCATION"] == "us-central1"
