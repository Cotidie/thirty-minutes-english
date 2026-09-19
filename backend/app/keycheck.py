"""One cheap authenticated request per provider, so the settings modal can
say whether a key works before a round depends on it."""

import json
import urllib.error
import urllib.request
from dataclasses import dataclass

CHECKS = {
    "OPENAI_API_KEY": ("https://api.openai.com/v1/models?limit=1", "Authorization", "Bearer {key}"),
    "GEMINI_API_KEY": ("https://generativelanguage.googleapis.com/v1beta/models?pageSize=1", "x-goog-api-key", "{key}"),
}


@dataclass(frozen=True)
class KeyCheck:
    ok: bool
    message: str


def check_key(name: str, key: str) -> KeyCheck:
    if name not in CHECKS:
        raise KeyError(name)
    if not key.strip():
        return KeyCheck(False, "no key to test")
    url, header, fmt = CHECKS[name]
    req = urllib.request.Request(url, headers={header: fmt.format(key=key.strip())})
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
