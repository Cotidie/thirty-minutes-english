"""The pronunciation assessor the browser streams the reader's microphone to.
Azure scores each recognised segment against the paragraph; the backend only
mints the short-lived token so the key never leaves the server, and passes
along the thresholds the browser judges with."""

from app.net import request

TOKEN_URL = "https://{region}.api.cognitive.microsoft.com/sts/v1.0/issueToken"


def issue_token(key: str, region: str) -> str:
    """A ten-minute Azure Speech token; the key check in Settings asks for one too. Raises HttpError."""
    return request("POST", TOKEN_URL.format(region=region), {"Ocp-Apim-Subscription-Key": key}, timeout=15).text


class AzureAssessor:
    def __init__(self, key: str, region: str, word_score: int, break_confidence: float):
        self.key = key
        self.region = region
        self.word_score = word_score
        self.break_confidence = break_confidence

    def session(self) -> dict:
        """A ten-minute token plus everything the browser needs to judge with it. Raises HttpError."""
        return {
            "token": issue_token(self.key, self.region),
            "region": self.region,
            "word_score": self.word_score,
            "break_confidence": self.break_confidence,
        }
