#!/usr/bin/env python3
"""Shared helpers for the ad hoc model probe scripts from this thread."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

DEFAULT_BASE_URL = os.environ.get("GATEWAY_URL", "")
DEFAULT_TIMEOUT = 30
REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
DEFAULT_ENV_PATH = REPO_ROOT / ".env"
DEFAULT_SKILLGRADE_CLI = REPO_ROOT.parents[1] / "skillgrade" / "dist" / "cli.js"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from pantheon.gateway import Client, Message  # noqa: E402

KNOWN_ENV_KEYS = {
    "API_KEY",
    "GATEWAY_URL",
    "INFERENCE_API_KEY",
    "INFERENCE_RATE_LIMIT_DISABLE",
    "INFERENCE_RATE_LIMIT_MAX_REQUESTS_PER_RUN",
    "INFERENCE_RATE_LIMIT_PER_DAY",
    "INFERENCE_RATE_LIMIT_PER_HOUR",
    "INFERENCE_RATE_LIMIT_PER_MINUTE",
    "INFERENCE_RATE_LIMIT_PER_SECOND",
    "INFERENCE_RATE_LIMIT_STALE_LOCK_SECONDS",
    "INFERENCE_RATE_LIMIT_STATE_DIR",
    "NIM_API_KEY",
    "NIM_BASE_URL",
    "NIM_MODEL",
    "SKILLGRADE_CLI",
}

BLOCKED_CHAT_TERMS = (
    "audio",
    "asr",
    "embed",
    "embedding",
    "guardrail",
    "moderation",
    "nemoretriever",
    "ranking",
    "rerank",
    "safety",
    "speech",
    "transcribe",
    "tts",
)


def load_env(env_path: Path | None = None) -> None:
    """Load key/value pairs from .env without overriding existing env vars."""
    from pantheon.config import parse_env_file

    env_path = env_path or DEFAULT_ENV_PATH
    for key, value in parse_env_file(env_path).items():
        if key and key in KNOWN_ENV_KEYS and key not in os.environ:
            os.environ[key] = value


def api_key() -> str:
    load_env()
    for name in ("INFERENCE_API_KEY", "API_KEY"):
        value = os.environ.get(name, "").strip()
        if value:
            return value
    raise SystemExit("Missing INFERENCE_API_KEY or API_KEY in environment or .env")


def base_url() -> str:
    load_env()
    url = (
        os.environ.get("NIM_BASE_URL") or os.environ.get("GATEWAY_URL") or DEFAULT_BASE_URL
    ).rstrip("/")
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise SystemExit(f"Invalid gateway URL: {url}")
    if parsed.scheme != "https" and parsed.hostname not in {
        "127.0.0.1",
        "localhost",
        "::1",
    }:
        raise SystemExit("Gateway URL must use https unless it targets localhost/loopback")
    return url


def _json_request(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> tuple[int | str, dict[str, Any] | str]:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers={
            "Authorization": f"Bearer {api_key()}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as exc:
        try:
            detail = exc.read().decode("utf-8", "replace")
        except Exception:  # pragma: no cover - defensive only
            detail = str(exc)
        return exc.code, detail
    except Exception as exc:  # pragma: no cover - network/runtime issues
        return "ERR", str(exc)


def fetch_model_catalog(timeout: int = DEFAULT_TIMEOUT) -> list[dict[str, Any]]:
    status, payload = _json_request(f"{base_url()}/models", timeout=timeout)
    if status != 200:
        raise SystemExit(f"Failed to fetch model catalog: {status} {payload}")
    models = payload.get("data", [])
    return sorted(models, key=lambda item: item.get("id", ""))


def model_ids(catalog: list[dict[str, Any]]) -> list[str]:
    return [item.get("id", "") for item in catalog if item.get("id")]


def shorten(text: Any, limit: int = 160) -> str:
    value = str(text).replace("\n", " ").strip()
    if len(value) <= limit:
        return value
    return f"{value[: limit - 3]}..."


def filter_chat_like_models(
    catalog: list[dict[str, Any]],
    *,
    extras: list[str] | None = None,
) -> list[str]:
    extras = extras or []
    candidates: list[str] = []
    for model_id in model_ids(catalog):
        lowered = model_id.lower()
        if any(term in lowered for term in BLOCKED_CHAT_TERMS):
            continue
        if any(
            marker in lowered
            for marker in (
                "instruct",
                "chat",
                "claude",
                "gpt",
                "gemini",
                "qwen",
                "llama",
                "nemotron",
            )
        ):
            candidates.append(model_id)
    for extra in extras:
        if extra not in candidates:
            candidates.append(extra)
    return sorted(dict.fromkeys(candidates))


def chat_probe(
    model_id: str,
    *,
    message: str = "Reply with exactly OK.",
    max_tokens: int = 8,
    timeout: int = DEFAULT_TIMEOUT,
) -> tuple[int | str, str]:
    try:
        with Client(base_url(), api_key(), timeout=timeout) as client:
            response = client.chat(
                model=model_id,
                messages=[Message(role="user", content=message)],
                temperature=0.0,
                max_tokens=max_tokens,
            )
        return 200, shorten(response.content)
    except requests.HTTPError as exc:
        response = exc.response
        if response is None:
            return "ERR", shorten(str(exc))
        return response.status_code, shorten(response.text)
    except Exception as exc:  # pragma: no cover - network/runtime issues
        return "ERR", shorten(str(exc))


def probe_many(
    models: list[str],
    *,
    max_workers: int = 1,
    message: str = "Reply with exactly OK.",
    max_tokens: int = 8,
    timeout: int = DEFAULT_TIMEOUT,
) -> list[dict[str, Any]]:
    def run_one(model_id: str) -> dict[str, Any]:
        status, detail = chat_probe(
            model_id,
            message=message,
            max_tokens=max_tokens,
            timeout=timeout,
        )
        return {"model": model_id, "status": status, "detail": detail}

    if max_workers <= 1:
        return [run_one(model_id) for model_id in models]

    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(run_one, model_id): model_id for model_id in models}
        for future in as_completed(futures):
            results.append(future.result())
    return sorted(results, key=lambda item: item["model"])


def classify_probe(result: dict[str, Any]) -> str:
    status = result["status"]
    detail = str(result["detail"]).lower()
    if status == 200:
        return "usable"
    if status == 401:
        return "unauthorized"
    if status == 400 or "unsupported" in detail or "not supported" in detail:
        return "unsupported"
    return "other"


def safe_model_slug(model_id: str) -> str:
    return model_id.replace("/", "__").replace(":", "__")


def resolve_skillgrade_cli(path: Path | None = None) -> Path:
    candidate = path
    if candidate is None:
        if configured := os.environ.get("SKILLGRADE_CLI"):
            candidate = Path(configured)
        else:
            candidate = DEFAULT_SKILLGRADE_CLI
    if candidate.exists():
        return candidate
    raise SystemExit("Missing skillgrade CLI. Set SKILLGRADE_CLI=/path/to/skillgrade/dist/cli.js")


def run_skillgrade_trial(
    model_id: str,
    skill: str,
    *,
    timeout: int = 300,
    output_root: Path | None = None,
    skillgrade_cli: Path | None = None,
) -> dict[str, Any]:
    load_env()
    output_root = output_root or Path(tempfile.mkdtemp(prefix="thread-benchmark-"))
    skillgrade_cli = resolve_skillgrade_cli(skillgrade_cli)
    skill_path = REPO_ROOT / ".agents" / "skills" / skill
    output_dir = output_root / skill / safe_model_slug(model_id)

    env = os.environ.copy()
    env["NIM_MODEL"] = model_id
    env["NIM_API_KEY"] = api_key()
    env["INFERENCE_API_KEY"] = api_key()
    env["NIM_BASE_URL"] = base_url()

    command = [
        "node",
        str(skillgrade_cli),
        "run",
        str(skill_path),
        "--agent",
        "nim",
        "--provider",
        "local",
        "--trials",
        "1",
        "--output",
        str(output_dir),
    ]

    started = time.perf_counter()
    completed = subprocess.run(
        command,
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    wall_s = time.perf_counter() - started

    summary_path = output_dir / "summary.json"
    summary: dict[str, Any] = {}
    if summary_path.exists():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))

    return {
        "model": model_id,
        "skill": skill,
        "returncode": completed.returncode,
        "wall_s": wall_s,
        "reward": summary.get("reward"),
        "trial_s": (summary.get("duration_ms") or 0) / 1000
        if summary.get("duration_ms") is not None
        else None,
        "input_tokens": summary.get("input_tokens"),
        "output_tokens": summary.get("output_tokens"),
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "output_dir": str(output_dir),
    }


def summarize_model_runs(model: str, runs: list[dict[str, Any]]) -> dict[str, Any]:
    count = len(runs)
    reward_sum = sum((run["reward"] or 0.0) for run in runs)
    duration_sum = sum(
        run["trial_s"] if run["trial_s"] is not None else run["wall_s"] for run in runs
    )
    passes = sum(1 for run in runs if run["returncode"] == 0 and run["reward"] is not None)
    return {
        "model": model,
        "avg_reward": reward_sum / count if count else 0.0,
        "avg_trial_s": duration_sum / count if count else 0.0,
        "passes": passes,
        "total": count,
    }


def benchmark_models(
    models: list[str],
    skills: list[str],
    *,
    timeout: int = 300,
    run_label: str = "thread-benchmark",
) -> list[dict[str, Any]]:
    output_root = Path(tempfile.mkdtemp(prefix=f"{run_label}-"))
    grouped: dict[str, list[dict[str, Any]]] = {}

    for model in models:
        print(f"=== {model} ===")
        model_runs: list[dict[str, Any]] = []
        for skill in skills:
            print(f"  -> {skill}")
            result = run_skillgrade_trial(
                model,
                skill,
                timeout=timeout,
                output_root=output_root,
            )
            model_runs.append(result)
            reward = "None" if result["reward"] is None else f"{result['reward']:.4f}"
            trial_s = result["trial_s"] if result["trial_s"] is not None else result["wall_s"]
            print(f"     return={result['returncode']} reward={reward} trial_s={trial_s:.3f}")
        grouped[model] = model_runs

    summary = [summarize_model_runs(model, model_runs) for model, model_runs in grouped.items()]
    summary.sort(key=lambda item: (-item["avg_reward"], item["avg_trial_s"], item["model"]))

    print()
    print("| Model | Avg Reward | Avg Trial Time | Passes |")
    print("| --- | ---: | ---: | ---: |")
    for item in summary:
        print(
            f"| `{item['model']}` | `{item['avg_reward']:.4f}` | "
            f"`{item['avg_trial_s']:.3f}s` | `{item['passes']}/{item['total']}` |"
        )
    print()
    print(f"Raw skillgrade outputs: {output_root}")
    return summary


def print_json_line(data: dict[str, Any]) -> None:
    print(json.dumps(data, sort_keys=True))


def print_results_table(results: list[dict[str, Any]]) -> None:
    print("model\tstatus\tdetail")
    for result in results:
        print(f"{result['model']}\t{result['status']}\t{result['detail']}")
