import pytest

from cliff_house.storage import retry


def _flaky(failures: int, exc=ConnectionError):
    calls = {"n": 0}

    def fn(x):
        calls["n"] += 1
        if calls["n"] <= failures:
            raise exc("dropped")
        return x * 2
    return fn, calls


def test_retries_transient_failures_with_doubling_waits():
    fn, calls = _flaky(2)
    waits = []
    assert retry(fn, 21, attempts=4, first_wait_s=1, sleep=waits.append) == 42
    assert calls["n"] == 3 and waits == [1, 2]


def test_gives_up_after_the_last_attempt_with_context():
    fn, calls = _flaky(10)
    with pytest.raises(ConnectionError, match="failed after 3 attempts"):
        retry(fn, 1, attempts=3, first_wait_s=0, sleep=lambda s: None)
    assert calls["n"] == 3


def test_non_transient_errors_are_not_retried():
    fn, calls = _flaky(1, exc=ValueError)
    with pytest.raises(ValueError):
        retry(fn, 1, attempts=5, sleep=lambda s: None)
    assert calls["n"] == 1
