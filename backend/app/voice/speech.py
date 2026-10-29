"""A sentence read aloud by Gemini's text-to-speech model, kept on disk so a
sentence is paid for once however often it is played."""

import base64
import hashlib
import logging
from pathlib import Path
from typing import Protocol

import httpx2

from app.llm import GenerationError

log = logging.getLogger(__name__)

GEMINI_TTS_MODEL = "gemini-3.8-flash-tts"


class Voice(Protocol):
    """One text-to-speech call; `name` tells cached sentences of different voices apart."""

    name: str
    media_type: str

    def speak(self, text: str) -> bytes: ...


class GeminiTts:
    media_type = "audio/wav"

    def __init__(self, key: str, voice: str, model: str = GEMINI_TTS_MODEL, transport: httpx2.BaseTransport | None = None) -> None:
        self._key = key
        self._voice = voice
        self._model = model
        self._transport = transport
        self.name = f"gemini-{model}-{voice}"

    def speak(self, text: str) -> bytes:
        body = {
            "contents": [{"parts": [{"text": text}]}],
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": self._voice}}},
            },
        }
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self._model}:generateContent"
        with httpx2.Client(timeout=60, transport=self._transport) as client:
            response = client.post(url, headers={"x-goog-api-key": self._key}, json=body)
        response.raise_for_status()
        parts = response.json()["candidates"][0]["content"]["parts"]
        return base64.b64decode(next(p["inlineData"]["data"] for p in parts if "inlineData" in p))


class Speaker:
    """Reads sentences in one voice; a sentence already read comes from the folder."""

    def __init__(self, voice: Voice, folder: Path) -> None:
        self._voice = voice
        self._folder = folder

    @property
    def media_type(self) -> str:
        return self._voice.media_type

    def read(self, text: str) -> bytes:
        """Raises GenerationError when the provider does not read it."""
        text = " ".join(text.split())
        path = self._folder / hashlib.sha256(f"{self._voice.name}\n{text}".encode()).hexdigest()[:32]
        if path.is_file():
            return path.read_bytes()
        try:
            audio = self._voice.speak(text)
        except (httpx2.HTTPError, KeyError, IndexError, StopIteration, ValueError) as e:
            log.warning("text-to-speech (%s) failed: %s", self._voice.name, e)
            raise GenerationError(f"{self._voice.name}: {e}") from e
        self._folder.mkdir(parents=True, exist_ok=True)
        path.write_bytes(audio)
        return audio


def speaker_for(key: str, voice_name: str, folder: Path | None) -> Speaker | None:
    """Gemini's reader in `voice_name`, or None without the Gemini key or a folder to keep sentences in."""
    if folder is None or not key:
        return None
    return Speaker(GeminiTts(key, voice_name), folder)
