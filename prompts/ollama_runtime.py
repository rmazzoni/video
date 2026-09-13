"""Helpers for talking to a local Ollama server."""

from __future__ import annotations

import ipaddress
import json
import re
from urllib.parse import urlparse
from typing import Any, Dict, List, Optional, Sequence

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


def response_text(response: Any) -> str:
    message = getattr(response, "message", None)
    if message is None and isinstance(response, dict):
        message = response.get("message")
    if message is None:
        return ""
    if isinstance(message, dict):
        content = message.get("content") or ""
        thinking = message.get("thinking") or ""
    else:
        content = getattr(message, "content", None) or ""
        thinking = getattr(message, "thinking", None) or ""
    text = str(content or "").strip()
    if text:
        return str(content)
    return str(thinking or "")


def parse_model_json(content: str) -> Any:
    text = _THINK_RE.sub("", str(content or "")).strip()
    text = _FENCE_RE.sub("", text).strip()
    if not text:
        raise ValueError("Ollama returned an empty response.")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start:end + 1])
        raise


def normalize_ollama_host(host: str) -> str:
    """Force loopback names onto 127.0.0.1 so Windows DNS suffixes cannot leak."""
    raw = str(host or "").strip() or "http://127.0.0.1:11434"
    if "://" not in raw:
        raw = f"http://{raw}"
    parsed = urlparse(raw)
    hostname = (parsed.hostname or "127.0.0.1").lower()
    if hostname in {"localhost", "0.0.0.0", "::1", "[::1]"}:
        hostname = "127.0.0.1"
    port = parsed.port or 11434
    path = (parsed.path or "").rstrip("/")
    return f"{parsed.scheme or 'http'}://{hostname}:{port}{path}"


def is_loopback_host(host: str) -> bool:
    hostname = urlparse(normalize_ollama_host(host)).hostname or ""
    if hostname in {"127.0.0.1", "localhost"}:
        return True
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False


def make_ollama_client(host: str):
    """Local Ollama must not inherit HTTP_PROXY / LAN proxies from the environment."""
    import ollama

    return ollama.Client(host=normalize_ollama_host(host), trust_env=False)


def chat_json_object(
    *,
    host: str,
    model: str,
    messages: Sequence[Dict[str, str]],
    options: Optional[Dict[str, Any]] = None,
) -> Any:
    """Chat with Qwen the same way prompt enhancement does, then parse JSON.

    Nested JSON-schema `format=` is skipped. Qwen3 often fails that grammar and
    returns empty content, which previously looked like a silent first-sentence
    fallback with almost no GPU use.
    """
    client = make_ollama_client(host)
    chat_options = options or {"temperature": 0.1, "top_p": 0.8}
    errors: List[str] = []
    last_text = ""
    for fmt in ("json", None):
        kwargs: Dict[str, Any] = {
            "model": model,
            "messages": list(messages),
            "options": chat_options,
            "think": False,
        }
        if fmt is not None:
            kwargs["format"] = fmt
        try:
            response = client.chat(**kwargs)
        except TypeError:
            kwargs.pop("think", None)
            try:
                response = client.chat(**kwargs)
            except Exception as exc:
                errors.append(f"format={fmt!r}: {exc}")
                continue
        except Exception as exc:
            errors.append(f"format={fmt!r}: {exc}")
            continue
        last_text = response_text(response)
        try:
            payload = parse_model_json(last_text)
        except Exception as exc:
            errors.append(f"format={fmt!r} parse: {exc}")
            continue
        if isinstance(payload, dict):
            return payload
        errors.append(f"format={fmt!r}: JSON was {type(payload).__name__}, not an object")
    snippet = (last_text or "")[:400]
    detail = " | ".join(errors) or "no response"
    raise RuntimeError(
        f"Qwen did not return usable JSON ({detail})"
        + (f" Last text: {snippet!r}" if snippet else "")
    )


def _model_names(listed: Any) -> List[str]:
    models = getattr(listed, "models", None)
    if models is None and isinstance(listed, dict):
        models = listed.get("models") or []
    names: List[str] = []
    for item in models or []:
        name = getattr(item, "model", None) or getattr(item, "name", None)
        if not name and isinstance(item, dict):
            name = item.get("model") or item.get("name")
        if name:
            names.append(str(name))
    return names


def model_is_available(names: List[str], model: str) -> bool:
    wanted = str(model or "").strip()
    if not wanted:
        return False
    return any(wanted == name or wanted in name or name.startswith(wanted) for name in names)


def ensure_ollama_ready(host: str, model: str) -> List[str]:
    """Raise a user-facing error if Ollama is down or the model is missing."""
    host = normalize_ollama_host(host)
    model = str(model or "").strip() or "qwen3:8b"
    try:
        client = make_ollama_client(host)
        listed = client.list()
    except Exception as exc:
        raise RuntimeError(
            f"Cannot reach Ollama at {host} ({type(exc).__name__}: {exc}). "
            f"Qwen beat extraction uses that host. If Qwen works from another "
            f"tool, check the Ollama host in Settings."
        ) from exc
    names = _model_names(listed)
    if not model_is_available(names, model):
        available = ", ".join(names) if names else "none"
        raise RuntimeError(
            f"Ollama is running at {host}, but model '{model}' is not installed. "
            f"Available models: {available}. Run: ollama pull {model}"
        )
    return names
