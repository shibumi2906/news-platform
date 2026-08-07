from common.rate_limit import SlidingWindowLimiter


def test_sliding_window_limiter_recovers_after_window() -> None:
    limiter = SlidingWindowLimiter(limit=2, window_seconds=10)
    assert limiter.allow("anonymous", now=1)
    assert limiter.allow("anonymous", now=2)
    assert not limiter.allow("anonymous", now=3)
    assert limiter.allow("anonymous", now=12)


def test_sliding_window_limiter_discards_stale_untrusted_keys() -> None:
    limiter = SlidingWindowLimiter(limit=1, window_seconds=10)
    for index in range(100):
        assert limiter.allow(f"untrusted-{index}", now=0)
    assert len(limiter._events) == 100
    assert limiter.allow("current", now=11)
    assert list(limiter._events) == ["current"]
