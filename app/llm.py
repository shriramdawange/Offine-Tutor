"""Cloud-first LLM routing with automatic Ollama fallback.

The cloud response is buffered before yielding so a mid-stream API failure cannot
leave a partial answer in the UI and then append a second, contradictory answer.
"""
import json
import shutil
import subprocess
import time
from typing import Iterator

import requests

from . import config


class LLMError(RuntimeError):
    pass


def _local_model_available() -> bool:
    try:
        response = requests.get(f"{config.OLLAMA_URL}/api/tags", timeout=3)
        response.raise_for_status()
        names = [m.get("name", "") for m in response.json().get("models", [])]
        base = config.MODEL.split(":")[0]
        return any(name == config.MODEL or name.startswith(base + ":") for name in names)
    except (requests.RequestException, ValueError):
        return False


def _ensure_local_model() -> None:
    if _local_model_available():
        return
    if not config.AUTO_PULL_LOCAL_MODEL:
        raise LLMError(
            f"Local model '{config.MODEL}' is not available. Install Ollama and run "
            f"'ollama pull {config.MODEL}', or set AUTO_PULL_LOCAL_MODEL=true."
        )
    if not shutil.which("ollama"):
        raise LLMError(
            "Cloud API failed and Ollama is not installed or not on PATH. "
            f"Install Ollama, then run 'ollama pull {config.MODEL}'."
        )

    # Start Ollama when possible. The launcher normally does this already.
    try:
        requests.get(f"{config.OLLAMA_URL}/api/tags", timeout=1)
    except requests.RequestException:
        try:
            subprocess.Popen(
                ["ollama", "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except OSError:
            pass

    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if _local_model_available():
            break
        time.sleep(1)

    if _local_model_available():
        return

    # Pull via the Ollama API so progress does not depend on parsing CLI output.
    try:
        response = requests.post(
            f"{config.OLLAMA_URL}/api/pull",
            json={"name": config.MODEL, "stream": True},
            stream=True,
            timeout=(10, config.LOCAL_PULL_TIMEOUT),
        )
        if response.status_code != 200:
            raise LLMError(f"Ollama model download failed ({response.status_code}).")
        for line in response.iter_lines():
            if not line:
                continue
            data = json.loads(line)
            if data.get("error"):
                raise LLMError(f"Ollama model download failed: {data['error']}")
        if not _local_model_available():
            raise LLMError(f"Ollama finished downloading but '{config.MODEL}' is unavailable.")
    except (requests.RequestException, ValueError) as exc:
        raise LLMError(f"Could not prepare local fallback model: {exc}") from exc


def _cloud_complete(messages: list[dict], temperature: float) -> str:
    if not config.API_KEY:
        raise LLMError("Cloud API key is not configured.")
    headers = {
        "Authorization": f"Bearer {config.API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": config.API_MODEL,
        "messages": messages,
        "temperature": temperature,
        "stream": False,
    }
    try:
        response = requests.post(
            f"{config.API_BASE_URL}/chat/completions",
            headers=headers,
            json=payload,
            timeout=(10, config.API_TIMEOUT),
        )
        if response.status_code != 200:
            detail = ""
            try:
                detail = str(response.json().get("error", {}).get("message", ""))
            except (ValueError, AttributeError):
                detail = response.text[:200]
            raise LLMError(f"Cloud API returned HTTP {response.status_code}: {detail[:200]}")
        data = response.json()
        content = data["choices"][0]["message"]["content"]
        if not isinstance(content, str) or not content.strip():
            raise LLMError("Cloud API returned an empty response.")
        return content
    except (requests.RequestException, ValueError, KeyError, IndexError, TypeError) as exc:
        raise LLMError(f"Cloud API request failed: {exc}") from exc


def _local_stream(messages: list[dict], temperature: float) -> Iterator[str]:
    _ensure_local_model()
    payload = {
        "model": config.MODEL,
        "messages": messages,
        "stream": True,
        "keep_alive": config.KEEP_ALIVE,
        "options": {
            "num_ctx": config.NUM_CTX,
            "temperature": temperature,
        },
    }
    try:
        response = requests.post(
            f"{config.OLLAMA_URL}/api/chat",
            json=payload,
            stream=True,
            timeout=(10, config.LOCAL_PULL_TIMEOUT),
        )
        if response.status_code != 200:
            raise LLMError(f"Ollama error {response.status_code}: {response.text[:200]}")
        for line in response.iter_lines():
            if not line:
                continue
            data = json.loads(line)
            if data.get("error"):
                raise LLMError(data["error"])
            token = (data.get("message") or {}).get("content", "")
            if token:
                yield token
            if data.get("done"):
                break
    except (requests.RequestException, ValueError) as exc:
        raise LLMError(f"Local Ollama generation failed: {exc}") from exc


def stream_chat(messages: list[dict], temperature: float = 0.5) -> Iterator[str]:
    """Use cloud first when configured; fall back to Ollama on any cloud failure."""
    provider = config.LLM_PROVIDER
    cloud_enabled = provider in {"auto", "api", "cloud"} and bool(config.API_KEY)

    if cloud_enabled:
        try:
            # Buffer the entire cloud response before yielding; this allows a safe
            # fallback even when the API fails after accepting the request.
            answer = _cloud_complete(messages, temperature)
            # Yield small chunks to preserve the frontend's incremental rendering.
            for start in range(0, len(answer), 32):
                yield answer[start:start + 32]
            return
        except LLMError:
            # Deliberately do not expose API credentials or provider internals.
            pass
    elif provider in {"api", "cloud"} and not config.API_KEY:
        # Explicit API-only configuration still falls back, as requested.
        pass

    yield from _local_stream(messages, temperature)


def complete(messages: list[dict], temperature: float = 0.4) -> str:
    return "".join(stream_chat(messages, temperature=temperature))


def model_available() -> bool:
    """Backward-compatible status helper: true if local model is ready."""
    return _local_model_available()


def provider_status() -> dict:
    local_ready = _local_model_available()
    cloud_configured = bool(config.API_KEY)
    preferred = "cloud" if cloud_configured and config.LLM_PROVIDER in {"auto", "api", "cloud"} else "local"
    return {
        "provider_mode": config.LLM_PROVIDER,
        "preferred_provider": preferred,
        "cloud_configured": cloud_configured,
        "local_model": config.MODEL,
        "local_available": local_ready,
        "automatic_fallback": True,
    }
