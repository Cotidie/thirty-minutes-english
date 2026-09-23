import pytest
from fastapi.testclient import TestClient

from app.db import Database
from app.main import create_app
from app.net import HttpError
from app.voice.assessor import AzureAssessor
from app.wiring import Services
from tests.test_api import FakeGenerator, InlineExecutor


def test_session_carries_the_token_region_and_thresholds(http):
    http.json = "eyJ.token"
    assessor = AzureAssessor("az-key", "koreacentral", word_score=60, break_confidence=0.75)
    assert assessor.session() == {"token": "eyJ.token", "region": "koreacentral", "word_score": 60, "break_confidence": 0.75}
    req = http.requests[0]
    assert (req.method, str(req.url)) == ("POST", "https://koreacentral.api.cognitive.microsoft.com/sts/v1.0/issueToken")
    assert req.headers["Ocp-Apim-Subscription-Key"] == "az-key"


def test_azure_errors_become_http_errors(http):
    http.status, http.json = 401, {"error": {"message": "bad key"}}
    with pytest.raises(HttpError) as e:
        AzureAssessor("az-key", "koreacentral", 60, 0.75).session()
    assert (e.value.status, e.value.message) == (401, "bad key")


def test_token_endpoint_is_503_until_azure_is_configured(tmp_path):
    app = create_app(Database(tmp_path / "s.db"), Services(FakeGenerator()), InlineExecutor())
    with TestClient(app) as c:
        res = c.get("/api/assessor/token")
    assert res.status_code == 503
    assert "AZURE_SPEECH_KEY" in res.json()["detail"]


def token_client(tmp_path) -> TestClient:
    services = Services(FakeGenerator(), assessor=AzureAssessor("k", "koreacentral", 55, 0.8))
    return TestClient(create_app(Database(tmp_path / "s.db"), services, InlineExecutor()))


def test_token_endpoint_returns_the_azure_session(tmp_path, http):
    http.json = "eyJ.t"
    with token_client(tmp_path) as c:
        body = c.get("/api/assessor/token").json()
    assert body == {"token": "eyJ.t", "region": "koreacentral", "word_score": 55, "break_confidence": 0.8}


def test_token_endpoint_relays_azure_failures_as_502(tmp_path, http):
    http.status, http.json = 401, {"error": {"message": "bad key"}}
    with token_client(tmp_path) as c:
        res = c.get("/api/assessor/token")
    assert res.status_code == 502
    assert "bad key" in res.json()["detail"]
