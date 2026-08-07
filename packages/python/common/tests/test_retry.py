from common.retry import RetryPolicy


def test_retry_policy_is_exponential_jittered_and_bounded() -> None:
    policy = RetryPolicy(base_seconds=10, maximum_seconds=25, jitter_ratio=0.2)
    assert policy.delay(1, random_value=0.5) == 10
    assert policy.delay(2, random_value=1) == 24
    assert policy.delay(8, random_value=1) == 25
