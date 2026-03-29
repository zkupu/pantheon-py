"""Shared inference API rate limiting for the Pantheon runtime and scripts."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from urllib.parse import urlparse

from ._types import PantheonError

_DEFAULT_LOCK_POLL_S = 0.05
_DEFAULT_STALE_LOCK_S = 300

_KNOWN_INFERENCE_HOSTS: set[str] = set(
    filter(None, os.environ.get("INFERENCE_RATE_LIMIT_HOSTS", "").split(","))
)

_EXPLICIT_CONFIG_KEYS = {
    "INFERENCE_RATE_LIMIT_PER_SECOND",
    "INFERENCE_RATE_LIMIT_PER_MINUTE",
    "INFERENCE_RATE_LIMIT_PER_HOUR",
    "INFERENCE_RATE_LIMIT_PER_DAY",
    "INFERENCE_RATE_LIMIT_MAX_REQUESTS_PER_RUN",
}

_RUN_COUNTS: dict[str, int] = {}
_RUN_COUNTS_LOCK = Lock()

_config_cache: dict[str, RateLimitConfig] = {}


@dataclass(frozen=True)
class RateLimitWindow:
    label: str
    seconds: int
    limit: int


@dataclass(frozen=True)
class RateLimitConfig:
    enabled: bool
    windows: tuple[RateLimitWindow, ...]
    state_dir: Path
    stale_lock_seconds: int
    max_requests_per_run: int


DEFAULT_WINDOWS = (
    RateLimitWindow("second", 1, 4),
    RateLimitWindow("minute", 60, 45),
    RateLimitWindow("hour", 3600, 900),
    RateLimitWindow("day", 86400, 7000),
)


class RateLimitExceededError(PantheonError):
    """Raised when a process exceeds its configured inference request budget."""


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, fallback: int, *, allow_zero: bool = False) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return fallback
    try:
        parsed = int(raw)
    except ValueError:
        return fallback
    if allow_zero and parsed >= 0:
        return parsed
    return parsed if parsed > 0 else fallback


def _has_explicit_config() -> bool:
    return any(os.environ.get(key, "").strip() for key in _EXPLICIT_CONFIG_KEYS)


def _default_state_dir() -> Path:
    if explicit := os.environ.get("INFERENCE_RATE_LIMIT_STATE_DIR", "").strip():
        return Path(explicit)
    cache_root = (
        os.environ.get("XDG_CACHE_HOME")
        or (str(Path.home() / ".cache") if str(Path.home()) else "")
        or tempfile.gettempdir()
    )
    return Path(cache_root) / "inference-rate-limit"


def _host_for(base_url: str) -> str:
    try:
        return (urlparse(base_url).hostname or "").lower()
    except ValueError:
        return ""


def load_rate_limit_config(base_url: str) -> RateLimitConfig:
    if base_url in _config_cache:
        return _config_cache[base_url]

    disabled = _env_truthy("INFERENCE_RATE_LIMIT_DISABLE")
    enabled = not disabled and (
        _has_explicit_config() or _host_for(base_url) in _KNOWN_INFERENCE_HOSTS
    )
    config = RateLimitConfig(
        enabled=enabled,
        windows=(
            RateLimitWindow(
                "second",
                1,
                _env_int("INFERENCE_RATE_LIMIT_PER_SECOND", DEFAULT_WINDOWS[0].limit),
            ),
            RateLimitWindow(
                "minute",
                60,
                _env_int("INFERENCE_RATE_LIMIT_PER_MINUTE", DEFAULT_WINDOWS[1].limit),
            ),
            RateLimitWindow(
                "hour",
                3600,
                _env_int("INFERENCE_RATE_LIMIT_PER_HOUR", DEFAULT_WINDOWS[2].limit),
            ),
            RateLimitWindow(
                "day",
                86400,
                _env_int("INFERENCE_RATE_LIMIT_PER_DAY", DEFAULT_WINDOWS[3].limit),
            ),
        ),
        state_dir=_default_state_dir(),
        stale_lock_seconds=_env_int(
            "INFERENCE_RATE_LIMIT_STALE_LOCK_SECONDS",
            _DEFAULT_STALE_LOCK_S,
        ),
        max_requests_per_run=_env_int(
            "INFERENCE_RATE_LIMIT_MAX_REQUESTS_PER_RUN",
            0,
            allow_zero=True,
        ),
    )
    _config_cache[base_url] = config
    return config


def _bucket_name(base_url: str, api_key: str | None) -> str:
    base_hash = hashlib.sha256(base_url.encode("utf-8")).hexdigest()[:12]
    key_hash = hashlib.sha256((api_key or "anonymous").encode("utf-8")).hexdigest()[:12]
    return f"{base_hash}-{key_hash}"


def _is_stale_lock(lock_dir: Path, stale_lock_seconds: int) -> bool:
    try:
        stat = lock_dir.stat()
    except FileNotFoundError:
        return False
    return (time.time() - stat.st_mtime) > stale_lock_seconds


@contextmanager
def _directory_lock(lock_dir: Path, stale_lock_seconds: int):
    while True:
        try:
            lock_dir.mkdir()
            break
        except FileExistsError:
            if _is_stale_lock(lock_dir, stale_lock_seconds):
                shutil.rmtree(lock_dir, ignore_errors=True)
                continue
            time.sleep(_DEFAULT_LOCK_POLL_S)

    try:
        yield
    finally:
        shutil.rmtree(lock_dir, ignore_errors=True)


def _load_state(state_path: Path) -> dict[str, list[float]]:
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {"requests": []}
    requests = data.get("requests", [])
    if not isinstance(requests, list):
        return {"requests": []}
    return {"requests": sorted(float(ts) for ts in requests if isinstance(ts, (int, float)))}


def _save_state(state_path: Path, state: dict[str, list[float]]) -> None:
    tmp_path = state_path.with_suffix(f"{state_path.suffix}.tmp")
    tmp_path.write_text(f"{json.dumps(state)}\n", encoding="utf-8")
    tmp_path.replace(state_path)


def _trim_requests(
    requests: list[float],
    now_seconds: float,
    max_window_seconds: int,
) -> list[float]:
    threshold = now_seconds - max_window_seconds
    return sorted(ts for ts in requests if ts > threshold)


def _compute_wait_seconds(
    requests: list[float],
    now_seconds: float,
    windows: tuple[RateLimitWindow, ...],
) -> float:
    wait_seconds = 0.0
    for window in windows:
        recent = [ts for ts in requests if ts > now_seconds - window.seconds]
        if len(recent) < window.limit:
            continue
        blocking_index = len(recent) - window.limit
        blocking_ts = recent[blocking_index]
        candidate = max(0.0, blocking_ts + window.seconds - now_seconds)
        wait_seconds = max(wait_seconds, candidate)
    return wait_seconds


def acquire_rate_limit(base_url: str, api_key: str | None = None) -> None:
    """Block until the next request may proceed within the configured windows."""
    config = load_rate_limit_config(base_url)
    if not config.enabled:
        return

    config.state_dir.mkdir(parents=True, exist_ok=True)
    bucket = _bucket_name(base_url, api_key)
    state_path = config.state_dir / f"{bucket}.json"
    lock_dir = Path(f"{state_path}.lock")
    max_window_seconds = max(window.seconds for window in config.windows)

    while True:
        with _directory_lock(lock_dir, config.stale_lock_seconds):
            with _RUN_COUNTS_LOCK:
                current_run_count = _RUN_COUNTS.get(bucket, 0)
            if (
                config.max_requests_per_run > 0
                and current_run_count >= config.max_requests_per_run
            ):
                raise RateLimitExceededError(
                    "inference request budget exhausted for "
                    f"{base_url}: {current_run_count}/"
                    f"{config.max_requests_per_run} requests in this process"
                )

            now_seconds = time.time()
            state = _load_state(state_path)
            state["requests"] = _trim_requests(
                state["requests"],
                now_seconds,
                max_window_seconds,
            )

            wait_seconds = _compute_wait_seconds(
                state["requests"],
                now_seconds,
                config.windows,
            )
            if wait_seconds <= 0:
                state["requests"].append(now_seconds)
                state["requests"].sort()
                _save_state(state_path, state)
                with _RUN_COUNTS_LOCK:
                    _RUN_COUNTS[bucket] = current_run_count + 1
                return

        time.sleep(wait_seconds)


def _clear_config_cache() -> None:
    """Clear the cached rate-limit configurations (for test isolation)."""
    _config_cache.clear()


def reset_rate_limiter_for_tests() -> None:
    """Reset process-local counters for deterministic unit tests."""
    _clear_config_cache()
    with _RUN_COUNTS_LOCK:
        _RUN_COUNTS.clear()
