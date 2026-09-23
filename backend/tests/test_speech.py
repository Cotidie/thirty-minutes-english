import json

import httpx2
from fastapi.testclient import TestClient

from app.db import Database
from app.main import create_app
from app.voice.speech import GeminiTts, OpenAITts, Speaker, speaker_for
from app.wiring import Services
from tests.test_api import FakeGenerator, InlineExecutor


class CountingVoice:
    name = "fake-voice"
    media_type = "audio/wav"

    def __init__(self, fail: bool = False) -> None:
        self.read: list[str] = []
        self.fail = fail

    def speak(self, text: str) -> bytes:
        self.read.append(text)
        if self.fail:
            raise httpx2.ConnectError("down")
        return f"WAV:{text}".encode()


def test_a_sentence_is_read_once_then_played_from_disk(tmp_path):
    voice = CountingVoice()
    speaker = Speaker(voice, tmp_path / "speech")
    assert speaker.read("It was  flawed.") == b"WAV:It was flawed."
    assert speaker.read("It was flawed.") == b"WAV:It was flawed."
    assert voice.read == ["It was flawed."]


def test_gemini_reads_in_the_chosen_voice_and_openai_asks_for_mp3():
    seen: list[dict] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append({"url": str(request.url), **json.loads(request.content)})
        if "googleapis" in str(request.url):
            return httpx2.Response(200, json={"candidates": [{"content": {"parts": [{"inlineData": {"mimeType": "audio/wav", "data": "V0FW"}}]}}]})
        return httpx2.Response(200, content=b"MP3")

    transport = httpx2.MockTransport(handler)
    assert GeminiTts("k", "Iapetus", transport=transport).speak("Hi.") == b"WAV"
    assert OpenAITts("k", transport=transport).speak("Hi.") == b"MP3"
    gemini, openai = seen
    assert gemini["generationConfig"]["speechConfig"]["voiceConfig"]["prebuiltVoiceConfig"]["voiceName"] == "Iapetus"
    assert gemini["contents"][0]["parts"][0]["text"] == "Hi."  # nothing else, or it is read out too
    assert (openai["input"], openai["response_format"]) == ("Hi.", "mp3")


def test_no_key_or_no_folder_means_no_reading(tmp_path):
    assert speaker_for("gemini", {"gemini": ""}, "Kore", tmp_path) is None
    assert speaker_for("openai", {"openai": "k"}, "Kore", None) is None
    assert speaker_for("openai", {"openai": "k"}, "Kore", tmp_path).media_type == "audio/mpeg"


def test_the_speech_route_returns_audio_and_says_why_when_it_cannot(tmp_path):
    def app_with(speaker):
        return create_app(Database(tmp_path / "s.db"), Services(FakeGenerator(), speaker=speaker), InlineExecutor())

    with TestClient(app_with(Speaker(CountingVoice(), tmp_path / "a"))) as c:
        res = c.post("/api/speech", json={"text": "Read me."})
        assert (res.status_code, res.content, res.headers["content-type"]) == (200, b"WAV:Read me.", "audio/wav")
        assert c.post("/api/speech", json={"text": "  "}).status_code == 422
    with TestClient(app_with(Speaker(CountingVoice(fail=True), tmp_path / "b"))) as c:
        assert c.post("/api/speech", json={"text": "Read me."}).status_code == 502
    with TestClient(app_with(None)) as c:
        assert c.post("/api/speech", json={"text": "Read me."}).status_code == 503
