from pathlib import Path

from google.adk.sessions import DatabaseSessionService, InMemorySessionService

from app.core.config import Settings
from app.runner import _resolve_session_db_url, make_session_service


def test_resolve_derives_local_sessions_db(tmp_path):
    s = Settings(_env_file=None, sqlite_path=str(tmp_path / "catchup.db"), session_db_url="")
    url = _resolve_session_db_url(s)
    # Exact derived URL (mirror the resolve() so this is robust on macOS symlinks).
    expected_db = Path(s.sqlite_path).resolve().parent / "sessions.db"
    assert url == f"sqlite+aiosqlite:///{expected_db}"


def test_resolve_passes_explicit_url_through():
    s = Settings(_env_file=None, session_db_url="postgresql+asyncpg://h/db")
    assert _resolve_session_db_url(s) == "postgresql+asyncpg://h/db"


def test_make_memory_backend():
    s = Settings(_env_file=None, session_backend="memory")
    assert isinstance(make_session_service(s), InMemorySessionService)


def test_make_database_backend(tmp_path):
    s = Settings(
        _env_file=None, session_backend="database",
        sqlite_path=str(tmp_path / "catchup.db"),
    )
    assert isinstance(make_session_service(s), DatabaseSessionService)


def test_run_tree_uses_injected_session_service():
    import inspect

    from app import runner

    sig = inspect.signature(runner._run_tree)
    assert "session_service" in sig.parameters
