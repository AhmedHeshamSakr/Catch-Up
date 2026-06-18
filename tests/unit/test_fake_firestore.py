from tests.unit.fake_firestore import FakeFirestoreClient


def test_set_get_and_existence():
    c = FakeFirestoreClient()
    c.collection("x").document("a").set({"v": 1})
    snap = c.collection("x").document("a").get()
    assert snap.exists and snap.id == "a" and snap.to_dict() == {"v": 1}
    assert c.collection("x").document("missing").get().exists is False


def test_where_order_offset_limit():
    c = FakeFirestoreClient()
    col = c.collection("x")
    for i, k in enumerate("abcd"):
        col.document(k).set({"cat": "ai" if i < 3 else "biz", "t": f"2026-05-2{i}"})
    rows = list(
        c.collection("x").where("cat", "==", "ai")
        .order_by("t", "DESCENDING").offset(1).limit(1).stream()
    )
    # ai = a,b,c (t=20,21,22); desc → c,b,a; offset 1 → b; limit 1 → [b]
    assert [r.id for r in rows] == ["b"]


def test_query_chaining_is_immutable():
    c = FakeFirestoreClient()
    col = c.collection("x")
    col.document("a").set({"cat": "ai"})
    col.document("b").set({"cat": "biz"})
    base = c.collection("x")
    ai_only = base.where("cat", "==", "ai")
    # Deriving ai_only must not mutate base — base still streams both docs.
    assert {s.id for s in base.stream()} == {"a", "b"}
    assert {s.id for s in ai_only.stream()} == {"a"}


def test_stream_snapshots_isolated_from_store():
    c = FakeFirestoreClient()
    c.collection("x").document("a").set({"v": [1]})
    snap = next(c.collection("x").stream())
    snap.to_dict()["v"].append(2)  # mutate the returned dict
    assert c.collection("x").document("a").get().to_dict() == {"v": [1]}


def test_batch_set_commits_all():
    c = FakeFirestoreClient()
    col = c.collection("x")
    batch = c.batch()
    batch.set(col.document("a"), {"v": 1})
    batch.set(col.document("b"), {"v": 2})
    assert col.document("a").get().exists is False  # not yet committed
    batch.commit()
    assert col.document("a").get().to_dict() == {"v": 1}
    assert col.document("b").get().to_dict() == {"v": 2}
