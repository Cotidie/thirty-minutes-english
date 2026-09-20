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


CHECKS: dict[str, Callable[[str, str], urllib.request.Request]] = {
    "OPENAI_API_KEY": _openai,
    "GEMINI_API_KEY": _gemini,
    "AZURE_SPEECH_KEY": _azure,
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
