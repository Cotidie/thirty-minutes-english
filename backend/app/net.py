"""JSON over HTTP with httpx2 (the client the mcp SDK uses too), and one error type for every provider."""

import json

import httpx2

# Tests swap in an httpx2.MockTransport here.
TRANSPORT: httpx2.BaseTransport | None = None


class HttpError(Exception):
    """`status` is the provider's HTTP status, or 502 when it could not be reached."""

    def __init__(self, status: int, message: str):
        super().__init__(f"{status}: {message}")
        self.status = status
        self.message = message


def request(method: str, url: str, headers: dict[str, str] | None = None, body: dict | None = None, timeout: float = 30) -> httpx2.Response:
    """The response, once it came back 2xx. Raises HttpError."""
    try:
        with httpx2.Client(timeout=timeout, transport=TRANSPORT) as client:
            response = client.request(method, url, headers=headers, json=body)
    except httpx2.HTTPError as e:
        raise HttpError(502, str(e) or type(e).__name__) from e
    if response.is_error:
        raise HttpError(response.status_code, error_message(response.content))
    return response


def post_json(url: str, body: dict, headers: dict[str, str], timeout: float = 30) -> dict:
    return request("POST", url, headers, body, timeout).json()


def error_message(raw: bytes) -> str:
    """The provider's `error.message` (or a bare `error` string), else the start of the body."""
    try:
        error = json.loads(raw)["error"]
        return error["message"] if isinstance(error, dict) else str(error)
    except (ValueError, KeyError, TypeError):
        return raw.decode(errors="replace")[:300]
