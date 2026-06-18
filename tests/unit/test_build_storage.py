import pytest

from app.adapters.storage.firestore_backend import FirestoreBackend
from app.adapters.storage.sqlite_backend import SqliteBackend
from app.core.config import Settings
from app.runner import build_storage
from tests.unit.fake_firestore import FakeFirestoreClient


def test_build_storage_sqlite_default(tmp_path):
    s = Settings(_env_file=None, sqlite_path=str(tmp_path / "c.db"))
    assert isinstance(build_storage(s), SqliteBackend)


def test_build_storage_firestore(monkeypatch, tmp_path):
    import app.runner as runner_mod
    monkeypatch.setattr(runner_mod, "_firestore_client", lambda settings: FakeFirestoreClient())
    s = Settings(_env_file=None, storage_backend="firestore",
                 sqlite_path=str(tmp_path / "c.db"))
    assert isinstance(build_storage(s), FirestoreBackend)


def test_build_storage_unknown_backend(tmp_path):
    s = Settings(_env_file=None, storage_backend="mongo",
                 sqlite_path=str(tmp_path / "c.db"))
    with pytest.raises(ValueError, match="storage_backend"):
        build_storage(s)


def test_firestore_client_missing_extra_raises():
    # The [firestore] extra is not installed in the test env → actionable error.
    try:
        import google.cloud.firestore  # noqa: F401

        pytest.skip("firestore extra installed; missing-extra path not exercised")
    except ImportError:
        pass
    from app.runner import _firestore_client
    with pytest.raises(RuntimeError, match="firestore"):
        _firestore_client(Settings(_env_file=None))
