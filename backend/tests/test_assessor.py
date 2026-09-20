import io
import urllib.error

import pytest
from fastapi.testclient import TestClient

from app.assessor import AssessorError, AzureAssessor
from app.main import create_app
from app.store import SessionStore
from app.wiring import Services
from tests.test_api import FakeGenerator, InlineExecutor


class Reply:
    def __init__(self, text: str):
        self.text = text

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.text.encode()


def test_session_carries_the_token_region_and_thresholds(monkeypatch):
    seen = {}

    def fake_urlopen(req, timeout=0):
        seen["url"] = req.full_url
        seen["method"] = req.get_method()
        seen["key"] = req.get_header("Ocp-apim-subscription-key")
        return Reply("eyJ.token")

    monkeypatch.setattr("app.assessor.urllib.request.urlopen", fake_urlopen)
    assessor = AzureAssessor("az-key", "koreacentral", word_score=60, break_confidence=0.75)
    assert assessor.session() == {
        "token": "eyJ.token",
        "region": "koreacentral",
        "word_score": 60,
        "break_confidence": 0.75,
    }
    assert seen == {
        "url": "https://koreacentral.api.cognitive.microsoft.com/sts/v1.0/issueToken",
        "method": "POST",
        "key": "az-key",
    }


def test_azure_errors_become_assessor_errors(monkeypatch):
    def fail(req, timeout=0):
        raise urllib.error.HTTPError(
            req.full_url, 401, "Unauthorized", {}, io.BytesIO(b'{"error":{"message":"bad key"}}')
        )

    monkeypatch.setattr("app.assessor.urllib.request.urlopen", fail)
    with pytest.raises(AssessorError) as e:
        AzureAssessor("az-key", "koreacentral", 60, 0.75).session()
    assert e.value.status == 401
    assert "bad key" in e.value.message


def test_token_endpoint_is_503_until_azure_is_configured(tmp_path):
    app = create_app(SessionStore(tmp_path / "s.db"), Services(FakeGenerator()), InlineExecutor())
    with TestClient(app) as c:
        res = c.get("/api/assessor/token")
    assert res.status_code == 503
    assert "AZURE_SPEECH_KEY" in res.json()["detail"]


def test_token_endpoint_returns_the_azure_session(tmp_path):
    class Minted(AzureAssessor):
        def session(self):
            return {"token": "eyJ.t", "region": "koreacentral", "word_score": 55, "break_confidence": 0.8}

    services = Services(FakeGenerator(), assessor=Minted("k", "koreacentral", 55, 0.8))
    app = create_app(SessionStore(tmp_path / "s.db"), services, InlineExecutor())
    with TestClient(app) as c:
        body = c.get("/api/assessor/token").json()
    assert body == {"token": "eyJ.t", "region": "koreacentral", "word_score": 55, "break_confidence": 0.8}


def test_token_endpoint_relays_azure_failures_as_502(tmp_path):
    class Broken(AzureAssessor):
        def session(self):
            raise AssessorError(401, "bad key")

    services = Services(FakeGenerator(), assessor=Broken("k", "koreacentral", 60, 0.75, "interrupt"))
    app = create_app(SessionStore(tmp_path / "s.db"), services, InlineExecutor())
    with TestClient(app) as c:
        res = c.get("/api/assessor/token")
    assert res.status_code == 502
    assert "bad key" in res.json()["detail"]
