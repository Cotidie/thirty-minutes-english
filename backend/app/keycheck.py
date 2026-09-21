"""One cheap authenticated request per provider, so the settings modal can
say whether a key works before a round depends on it."""

import json
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass

AZURE_TOKEN_URL = "https://{region}.api.cognitive.microsoft.com/sts/v1.0/issueToken"


def _openai(key: str, region: str) -> urllib.request.Request:
    return urllib.request.Request("https://api.openai.com/v1/models?limit=1", headers={"Authorization": f"Bearer {key}"})


def _gemini(key: str, region: str) -> urllib.request.Request:
    return urllib.request.Request(
        "https://generativelanguage.googleapis.com/v1beta/models?pageSize=1", headers={"x-goog-api-key": key}
    )


def _azure(key: str, region: str) -> urllib.request.Request:
    return urllib.request.Request(
        AZURE_TOKEN_URL.format(region=region),
        method="POST",
        data=b"",
        headers={"Ocp-Apim-Subscription-Key": key, "Content-Length": "0"},
    )


def _openrouter(key: str, region: str) -> urllib.request.Request:
    return urllib.request.Request("https://openrouter.ai/api/v1/key", headers={"Authorization": f"Bearer {key}"})


def _comfy(key: str, region: str) -> urllib.request.Request:
    """comfy-cloud has no REST key endpoint we know of; an MCP initialize answers 401 to a bad key."""
    body = {"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "english-speaking-claude", "version": "1"}}}
    return urllib.request.Request(
        "https://cloud.comfy.org/mcp",
        data=json.dumps(body).encode(),
        method="POST",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "User-Agent": "english-speaking-claude/1",
        },
    )


CHECKS: dict[str, Callable[[str, str], urllib.request.Request]] = {
    "OPENAI_API_KEY": _openai,
    "GEMINI_API_KEY": _gemini,
    "AZURE_SPEECH_KEY": _azure,
    "OPENROUTER_API_KEY": _openrouter,
    "COMFY_API_KEY": _comfy,
}


@dataclass(frozen=True)
class KeyCheck:
    ok: bool
    message: str


def check_key(name: str, key: str, region: str = "") -> KeyCheck:
    """`region` matters only to Azure, whose endpoint is per region."""
    if name not in CHECKS:
        raise KeyError(name)
    if not key.strip():
        return KeyCheck(False, "no key to test")
    if name == "AZURE_SPEECH_KEY" and not region.strip():
        return KeyCheck(False, "set AZURE_SPEECH_REGION first")
    req = CHECKS[name](key.strip(), region.strip())
    try:
        with urllib.request.urlopen(req, timeout=15):
            return KeyCheck(True, "key works")
    except urllib.error.HTTPError as e:
        return KeyCheck(False, f"{e.code}: {_error_message(e.read())}")
    except urllib.error.URLError as e:
        return KeyCheck(False, f"could not reach the provider: {e.reason}")


def _error_message(raw: bytes) -> str:
    try:
        return json.loads(raw)["error"]["message"]
    except (ValueError, KeyError, TypeError):
        return raw.decode(errors="replace")[:200]
