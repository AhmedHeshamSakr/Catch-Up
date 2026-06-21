"""Pre-deploy validation: run the FULL StorageContract against the REAL Firestore
emulator. SKIPPED unless FIRESTORE_EMULATOR_HOST is set (and the [firestore]
extra is installed), so CI/local runs without the emulator skip cleanly instead
of failing.

To run locally:
    gcloud beta emulators firestore start --host-port=localhost:8080
    export FIRESTORE_EMULATOR_HOST=localhost:8080
    uv sync --extra firestore
    uv run pytest tests/integration -k firestore_emulator

The in-memory fake (tests/unit/fake_firestore.py) validates the adapter's LOGIC
but not real Firestore semantics (composite-index requirements, the
missing-field == False behavior backfill_is_flagged handles); this gate covers
those before any real GCP deploy. The emulator builds composite indexes on the
fly, so firestore.indexes.json is only required in production.
"""
from __future__ import annotations

import os

import pytest

from tests.unit.storage_contract import StorageContract

pytestmark = pytest.mark.skipif(
    not os.environ.get("FIRESTORE_EMULATOR_HOST"),
    reason="set FIRESTORE_EMULATOR_HOST (+ uv sync --extra firestore) to run",
)


class TestFirestoreEmulatorContract(StorageContract):
    """Runs every StorageContract case against FirestoreBackend on the emulator."""

    @pytest.fixture(autouse=True)
    def _backend(self):
        from google.cloud import firestore  # requires the [firestore] extra

        from app.adapters.storage.firestore_backend import FirestoreBackend

        client = firestore.Client(project="catch-up-emulator-test")
        backend = FirestoreBackend(client)
        # The contract assumes a fresh store per test — clear both collections.
        for name in (backend._items_name, backend._runs_name):
            for doc in client.collection(name).stream():
                doc.reference.delete()
        backend.init_schema()
        self.backend = backend
        yield
