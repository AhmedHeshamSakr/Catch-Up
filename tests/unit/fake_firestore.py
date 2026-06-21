"""In-memory stand-in for a Firestore client — only the surface
FirestoreBackend uses. Offline; no real query semantics (no composite-index or
inequality-filter constraints), so it validates the adapter's logic, not the
backing store itself."""
from __future__ import annotations

import copy


class FakeSnapshot:
    def __init__(self, doc_id: str, data: dict | None) -> None:
        self.id = doc_id
        self._data = data

    @property
    def exists(self) -> bool:
        return self._data is not None

    def to_dict(self) -> dict | None:
        return copy.deepcopy(self._data) if self._data is not None else None


class FakeDocRef:
    def __init__(self, store: dict, doc_id: str) -> None:
        self._store = store
        self.id = doc_id

    def set(self, data: dict) -> None:
        self._store[self.id] = copy.deepcopy(data)

    def update(self, data: dict) -> None:
        doc = self._store.get(self.id)
        if doc is None:
            raise KeyError(self.id)  # update() requires an existing document
        doc.update(copy.deepcopy(data))

    def get(self) -> FakeSnapshot:
        return FakeSnapshot(self.id, self._store.get(self.id))


class FakeQuery:
    def __init__(self, store: dict) -> None:
        self._store = store
        self._filters: list[tuple[str, str, object]] = []
        self._order: tuple[str, bool] | None = None
        self._offset = 0
        self._limit: int | None = None

    def _clone(self) -> FakeQuery:
        q = FakeQuery(self._store)
        q._filters = list(self._filters)
        q._order = self._order
        q._offset = self._offset
        q._limit = self._limit
        return q

    def where(
        self, field: str | None = None, op: str | None = None,
        value: object = None, *, filter: object = None,
    ) -> FakeQuery:
        if filter is not None:
            # Duck-type a google FieldFilter (used when the [firestore] extra is
            # installed) without importing it — the adapter's _where passes
            # where(filter=FieldFilter(...)) only when google.cloud is present.
            field = getattr(filter, "field_path", field)
            op = getattr(filter, "op_string", op)
            value = getattr(filter, "value", value)
        if op != "==":
            raise NotImplementedError(f"fake supports only '==', got {op!r}")
        q = self._clone()
        q._filters.append((field, op, value))
        return q

    def order_by(self, field: str, direction: str = "ASCENDING") -> FakeQuery:
        q = self._clone()
        q._order = (field, direction == "DESCENDING")
        return q

    def offset(self, n: int) -> FakeQuery:
        q = self._clone()
        q._offset = n
        return q

    def limit(self, n: int) -> FakeQuery:
        q = self._clone()
        q._limit = n
        return q

    def stream(self):
        rows = list(self._store.items())
        for field, _op, value in self._filters:
            rows = [(k, v) for k, v in rows if v.get(field) == value]
        if self._order is not None:
            field, desc = self._order
            rows.sort(key=lambda kv: kv[1].get(field), reverse=desc)
        rows = rows[self._offset:]
        if self._limit is not None:
            rows = rows[: self._limit]
        return iter(FakeSnapshot(k, copy.deepcopy(v)) for k, v in rows)


class FakeCollection(FakeQuery):
    def document(self, doc_id: str) -> FakeDocRef:
        return FakeDocRef(self._store, doc_id)


class FakeBatch:
    def __init__(self) -> None:
        self._ops: list[tuple[FakeDocRef, dict]] = []

    def set(self, ref: FakeDocRef, data: dict) -> None:
        # Capture the write data now (deep copy), matching real Firestore — a
        # caller mutating `data` before commit() must not change the queued write.
        self._ops.append((ref, copy.deepcopy(data)))

    def commit(self) -> None:
        for ref, data in self._ops:
            ref.set(data)
        self._ops = []


class FakeFirestoreClient:
    def __init__(self) -> None:
        self._collections: dict[str, dict] = {}

    def collection(self, name: str) -> FakeCollection:
        return FakeCollection(self._collections.setdefault(name, {}))

    def batch(self) -> FakeBatch:
        return FakeBatch()

    def get_all(self, refs):
        """Batched multi-get, mirroring google.cloud.firestore.Client.get_all."""
        return [ref.get() for ref in refs]
