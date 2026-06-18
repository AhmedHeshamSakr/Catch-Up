"""Pre-deploy validation hook: run FirestoreBackend against the real Firestore
emulator. SKIPPED by default — the offline suite uses FakeFirestoreClient, which
does NOT enforce real Firestore semantics, so this is the gate before any real
GCP deploy.

Pre-deploy checklist (do all before un-skipping):
1. Start the emulator (`gcloud beta emulators firestore start`) and set
   FIRESTORE_EMULATOR_HOST; install the [firestore] extra (`uv sync --extra firestore`).
2. Swap the adapter's positional `where(field, op, value)` →
   `where(filter=FieldFilter(field, op, value))` (positional is deprecated).
3. Create composite indexes for the `list_news` equality filters
   (category/importance/is_flagged) + `order_by("collected_at", DESCENDING)`;
   the fake can't surface missing-index failures.
4. Backfill `is_flagged=False` on any pre-existing docs (default queries filter
   `is_flagged == False`, which does NOT match a missing field — unlike SQLite's
   NULL-status handling).
5. Keep timestamps as UTC ISO strings (never mix native Firestore timestamps in
   the ordered fields), and consider caching one client per process under real
   API traffic (build_storage currently builds one per call).
"""
import pytest

pytestmark = pytest.mark.skip(
    reason="needs Firestore emulator + [firestore] extra; pre-deploy validation"
)


def test_firestore_backend_against_emulator():
    raise AssertionError("implement against the emulator before deploy")
