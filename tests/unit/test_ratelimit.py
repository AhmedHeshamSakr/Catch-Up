from app.services.ratelimit import TokenBucket


def test_bucket_allows_up_to_capacity_then_blocks():
    t = {"now": 0.0}
    b = TokenBucket(rate_per_sec=1.0, capacity=3, clock=lambda: t["now"])
    assert b.try_acquire() is True
    assert b.try_acquire() is True
    assert b.try_acquire() is True
    assert b.try_acquire() is False  # capacity exhausted


def test_bucket_refills_over_time():
    t = {"now": 0.0}
    b = TokenBucket(rate_per_sec=2.0, capacity=2, clock=lambda: t["now"])
    assert b.try_acquire(2) is True
    assert b.try_acquire() is False
    t["now"] = 1.0  # 1s * 2 tokens/s = 2 tokens refilled
    assert b.try_acquire() is True
    assert b.try_acquire() is True
    assert b.try_acquire() is False


def test_refill_caps_at_capacity():
    t = {"now": 0.0}
    b = TokenBucket(rate_per_sec=5.0, capacity=2, clock=lambda: t["now"])
    t["now"] = 100.0
    assert b.try_acquire(2) is True
    assert b.try_acquire() is False  # never exceeds capacity
