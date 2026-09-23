"""The pronunciation assessor the browser streams the reader's microphone to.
Azure scores each recognised segment against the paragraph; the backend only
mints the short-lived token so the key never leaves the server, and passes
along the thresholds the browser judges with."""

import urllib.request

from app.net import send

TOKEN_URL = "https://{region}.api.cognitive.microsoft.com/sts/v1.0/issueToken"


def token_request(key: str, region: str, url: str = TOKEN_URL) -> urllib.request.Request:
    """Azure's token endpoint; the key check in Settings sends the same request."""
    return urllib.request.Request(
        url.format(region=region),
        method="POST",
        data=b"",
        headers={"Ocp-Apim-Subscription-Key": key, "Content-Length": "0"},
    )


class AzureAssessor:
    def __init__(self, key: str, region: str, word_score: int, break_confidence: float, url: str = TOKEN_URL):
        self.key = key
        self.region = region
        self.word_score = word_score
        self.break_confidence = break_confidence
        self.url = url

    def session(self) -> dict:
        """A ten-minute token plus everything the browser needs to judge with it. Raises HttpError."""
        token = send(token_request(self.key, self.region, self.url), timeout=15).decode()
        return {
            "token": token,
            "region": self.region,
            "word_score": self.word_score,
            "break_confidence": self.break_confidence,
        }
