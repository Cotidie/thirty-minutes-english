"""JSON over HTTP with the standard library, and one error type for every provider."""

import json
import urllib.error
import urllib.request


class HttpError(Exception):
    """`status` is the provider's HTTP status, or 502 when it could not be reached."""

    def __init__(self, status: int, message: str):
        super().__init__(f"{status}: {message}")
        self.status = status
        self.message = message


def send(req: urllib.request.Request, timeout: float) -> bytes:
    """The response body. Raises HttpError."""
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return res.read()
    except urllib.error.HTTPError as e:
        raise HttpError(e.code, error_message(e.read())) from e
    except urllib.error.URLError as e:
        raise HttpError(502, str(e.reason)) from e


def post_json(url: str, body: dict, headers: dict[str, str], timeout: float = 30) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        method="POST",
        headers={"Content-Type": "application/json", **headers},
    )
    return json.loads(send(req, timeout))


def error_message(raw: bytes) -> str:
    """The provider's `error.message`, else the start of the body."""
    try:
        return json.loads(raw)["error"]["message"]
    except (ValueError, KeyError, TypeError):
        return raw.decode(errors="replace")[:300]
