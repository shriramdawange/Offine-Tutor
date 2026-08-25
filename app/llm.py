import json

import requests

from . import config


class LLMError(RuntimeError):
    pass


def _post(payload: dict, timeout: int = 300):
    try:
        return requests.post(
            f"{config.OLLAMA_URL}/api/chat",
            json=payload,
            stream=payload.get("stream", False),
            timeout=timeout,
        )
    except requests.ConnectionError:
        raise LLMError("Cannot reach Ollama. Start it with: ollama serve")


def stream_chat(messages: list[dict], temperature: float = 0.5):
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
    resp = _post(payload)
    if resp.status_code != 200:
        raise LLMError(f"Ollama error {resp.status_code}: {resp.text[:200]}")
    for line in resp.iter_lines():
        if not line:
            continue
        data = json.loads(line)
        if "error" in data:
            raise LLMError(data["error"])
        token = (data.get("message") or {}).get("content", "")
        if token:
            yield token
        if data.get("done"):
            break


def complete(messages: list[dict], temperature: float = 0.4) -> str:
    parts = []
    for tok in stream_chat(messages, temperature=temperature):
        parts.append(tok)
    return "".join(parts)


def model_available() -> bool:
    try:
        r = requests.get(f"{config.OLLAMA_URL}/api/tags", timeout=3)
        names = [m.get("name", "") for m in r.json().get("models", [])]
        base = config.MODEL.split(":")[0]
        return any(n == config.MODEL or n.startswith(base) for n in names)
    except Exception:
        return False
