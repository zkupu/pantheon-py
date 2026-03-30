"""Tests for shared inference rate limiting and gateway wiring."""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from pantheon.gateway import Client, Message
from pantheon.rate_limit import (
    RateLimitExceededError,
    _clear_config_cache,
    acquire_rate_limit,
    load_rate_limit_config,
    reset_rate_limiter_for_tests,
)


@pytest.fixture(autouse=True)
def _reset_rate_limiter(monkeypatch):
    for key in (
        "INFERENCE_RATE_LIMIT_DISABLE",
        "INFERENCE_RATE_LIMIT_PER_SECOND",
        "INFERENCE_RATE_LIMIT_PER_MINUTE",
        "INFERENCE_RATE_LIMIT_PER_HOUR",
        "INFERENCE_RATE_LIMIT_PER_DAY",
        "INFERENCE_RATE_LIMIT_MAX_REQUESTS_PER_RUN",
        "INFERENCE_RATE_LIMIT_STATE_DIR",
        "INFERENCE_RATE_LIMIT_STALE_LOCK_SECONDS",
    ):
        monkeypatch.delenv(key, raising=False)
    reset_rate_limiter_for_tests()
    yield
    reset_rate_limiter_for_tests()


class _FakeClock:
    def __init__(self, start: float = 1000.0) -> None:
        self.now = start
        self.sleeps: list[float] = []

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def _configure_limits(
    monkeypatch, tmp_path, *, per_second: int = 10, max_per_run: int = 0
) -> None:
    monkeypatch.setenv("INFERENCE_RATE_LIMIT_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("INFERENCE_RATE_LIMIT_PER_SECOND", str(per_second))
    monkeypatch.setenv("INFERENCE_RATE_LIMIT_PER_MINUTE", "100")
    monkeypatch.setenv("INFERENCE_RATE_LIMIT_PER_HOUR", "1000")
    monkeypatch.setenv("INFERENCE_RATE_LIMIT_PER_DAY", "10000")
    if max_per_run:
        monkeypatch.setenv("INFERENCE_RATE_LIMIT_MAX_REQUESTS_PER_RUN", str(max_per_run))


def test_acquire_rate_limit_enforces_per_run_budget(monkeypatch, tmp_path):
    _configure_limits(monkeypatch, tmp_path, max_per_run=1)

    acquire_rate_limit("https://example.test/v1", "secret")
    with pytest.raises(RateLimitExceededError, match="request budget exhausted"):
        acquire_rate_limit("https://example.test/v1", "secret")


def test_acquire_rate_limit_waits_for_the_blocking_window(monkeypatch, tmp_path):
    _configure_limits(monkeypatch, tmp_path, per_second=1)
    fake_clock = _FakeClock()
    monkeypatch.setattr("pantheon.rate_limit.time.time", fake_clock.time)
    monkeypatch.setattr("pantheon.rate_limit.time.sleep", fake_clock.sleep)

    acquire_rate_limit("https://example.test/v1", "secret")
    acquire_rate_limit("https://example.test/v1", "secret")

    assert fake_clock.sleeps
    assert fake_clock.sleeps[0] == pytest.approx(1.0)


def test_config_is_cached(monkeypatch):
    _clear_config_cache()
    monkeypatch.setenv("INFERENCE_RATE_LIMIT_PER_MINUTE", "10")
    c1 = load_rate_limit_config("http://test")
    c2 = load_rate_limit_config("http://test")
    assert c1 is c2
    _clear_config_cache()


def test_config_cache_differs_by_base_url(monkeypatch):
    _clear_config_cache()
    monkeypatch.setenv("INFERENCE_RATE_LIMIT_PER_MINUTE", "10")
    c1 = load_rate_limit_config("http://alpha")
    c2 = load_rate_limit_config("http://bravo")
    assert c1 is not c2
    _clear_config_cache()


def test_gateway_chat_respects_the_rate_limit_budget(monkeypatch, tmp_path):
    _configure_limits(monkeypatch, tmp_path, max_per_run=1)
    client = Client("https://example.test/v1", "test-key", timeout=42)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }
    client.session.post = MagicMock(return_value=mock_resp)

    result = client.chat(model="test-model", messages=[Message(role="user", content="hello")])

    assert result.content == "ok"
    with pytest.raises(RateLimitExceededError, match="request budget exhausted"):
        client.chat(model="test-model", messages=[Message(role="user", content="again")])
    assert client.session.post.call_count == 1


def test_per_minute_window_blocks_when_full(monkeypatch, tmp_path):
    """Per-minute window blocks after limit is reached, then unblocks after sliding."""
    monkeypatch.setenv("INFERENCE_RATE_LIMIT_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("INFERENCE_RATE_LIMIT_PER_SECOND", "100")
    monkeypatch.setenv("INFERENCE_RATE_LIMIT_PER_MINUTE", "3")
    monkeypatch.setenv("INFERENCE_RATE_LIMIT_PER_HOUR", "10000")
    monkeypatch.setenv("INFERENCE_RATE_LIMIT_PER_DAY", "100000")

    fake_clock = _FakeClock()
    monkeypatch.setattr("pantheon.rate_limit.time.time", fake_clock.time)
    monkeypatch.setattr("pantheon.rate_limit.time.sleep", fake_clock.sleep)

    url = "https://minute-test.test/v1"
    for _ in range(3):
        acquire_rate_limit(url, "key")

    # 4th call should require a sleep (minute window full)
    acquire_rate_limit(url, "key")
    assert fake_clock.sleeps, "expected a sleep when minute window is full"
    # Sleep should be <= 60s (slides within the minute window)
    assert fake_clock.sleeps[-1] <= 60.0


def test_per_hour_window_blocks_when_full(monkeypatch, tmp_path):
    """Per-hour window blocks after limit is reached."""
    monkeypatch.setenv("INFERENCE_RATE_LIMIT_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("INFERENCE_RATE_LIMIT_PER_SECOND", "100")
    monkeypatch.setenv("INFERENCE_RATE_LIMIT_PER_MINUTE", "100")
    monkeypatch.setenv("INFERENCE_RATE_LIMIT_PER_HOUR", "2")
    monkeypatch.setenv("INFERENCE_RATE_LIMIT_PER_DAY", "100000")

    fake_clock = _FakeClock()
    monkeypatch.setattr("pantheon.rate_limit.time.time", fake_clock.time)
    monkeypatch.setattr("pantheon.rate_limit.time.sleep", fake_clock.sleep)

    url = "https://hour-test.test/v1"
    acquire_rate_limit(url, "key")
    acquire_rate_limit(url, "key")

    # 3rd call should block on the hour window
    acquire_rate_limit(url, "key")
    assert fake_clock.sleeps, "expected a sleep when hour window is full"
    assert fake_clock.sleeps[-1] <= 3600.0


def test_per_day_window_blocks_when_full(monkeypatch, tmp_path):
    """Per-day window blocks after limit is reached."""
    monkeypatch.setenv("INFERENCE_RATE_LIMIT_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("INFERENCE_RATE_LIMIT_PER_SECOND", "100")
    monkeypatch.setenv("INFERENCE_RATE_LIMIT_PER_MINUTE", "100")
    monkeypatch.setenv("INFERENCE_RATE_LIMIT_PER_HOUR", "100")
    monkeypatch.setenv("INFERENCE_RATE_LIMIT_PER_DAY", "2")

    fake_clock = _FakeClock()
    monkeypatch.setattr("pantheon.rate_limit.time.time", fake_clock.time)
    monkeypatch.setattr("pantheon.rate_limit.time.sleep", fake_clock.sleep)

    url = "https://day-test.test/v1"
    acquire_rate_limit(url, "key")
    acquire_rate_limit(url, "key")

    acquire_rate_limit(url, "key")
    assert fake_clock.sleeps, "expected a sleep when day window is full"
    assert fake_clock.sleeps[-1] <= 86400.0


def test_stale_lock_recovery(monkeypatch, tmp_path):
    """A stale lock directory is automatically removed so acquisition proceeds."""
    _configure_limits(monkeypatch, tmp_path, per_second=10)
    monkeypatch.setenv("INFERENCE_RATE_LIMIT_STALE_LOCK_SECONDS", "1")

    from pantheon.rate_limit import _bucket_name

    bucket = _bucket_name("https://stale.test/v1", "key")
    state_path = tmp_path / f"{bucket}.json"
    lock_dir = state_path.with_name(f"{state_path.name}.lock")

    # Create a stale lock directory with an old mtime
    import os

    lock_dir.mkdir(parents=True)
    old_time = time.time() - 10  # 10 seconds ago, well past the 1s stale threshold
    os.utime(str(lock_dir), (old_time, old_time))

    # Should succeed despite the stale lock
    acquire_rate_limit("https://stale.test/v1", "key")
