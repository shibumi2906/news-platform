from common.rate_limit import SlidingWindowLimiter


def test_sliding_window_limiter_recovers_after_window() -> None:
    limiter = SlidingWindowLimiter(limit=2, window_seconds=10)
    assert limiter.allow("anonymous", now=1)
    assert limiter.allow("anonymous", now=2)
    assert not limiter.allow("anonymous", now=3)
    assert limiter.allow("anonymous", now=12)
