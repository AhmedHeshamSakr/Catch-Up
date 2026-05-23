import pytest

from app.adapters.storage.sqlite_backend import SqliteBackend
from tests.unit.storage_contract import StorageContract


class TestSqliteBackend(StorageContract):
    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path):
        self.backend = SqliteBackend(str(tmp_path / "t.db"))
        self.backend.init_schema()
