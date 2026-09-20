"""The pronunciation assessor the browser streams the reader's microphone to.
Azure scores each recognised segment against the paragraph; the backend only
mints the short-lived token so the key never leaves the server, and passes
along the thresholds the browser judges with."""

import json
import urllib.error
import urllib.request

TOKEN_URL = "https://{region}.api.cognitive.microsoft.com/sts/v1.0/issueToken"


class AssessorError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(f"{status}: {message}")
        self.status = status
        self.message = message


class AzureAssessor:
    name = "azure"

    def __init__(
        self,
        key: str,
        region: str,
        word_score: int,
        break_confidence: float,
        url: str = TOKEN_URL,
    ):
        self.key = key
        self.region = region
        self.word_score = word_score
        self.break_confidence = break_confidence
        self.url = url

    def session(self) -> dict:
        """A ten-minute token plus everything the browser needs to judge with it."""
        req = urllib.request.Request(
            self.url.format(region=self.region),
            method="POST",
            data=b"",
            headers={"Ocp-Apim-Subscription-Key": self.key, "Content-Length": "0"},
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as res:
                token = res.read().decode()
        except urllib.error.HTTPError as e:
            raise AssessorError(e.code, _error_message(e.read())) from e
        except urllib.error.URLError as e:
            raise AssessorError(502, str(e.reason)) from e
        return {
            "token": token,
            "region": self.region,
            "word_score": self.word_score,
            "break_confidence": self.break_confidence,
        }


def _error_message(raw: bytes) -> str:
    try:
        return json.loads(raw)["error"]["message"]
    except (ValueError, KeyError, TypeError):
        return raw.decode(errors="replace")[:300]
