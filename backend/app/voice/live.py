"""Voice coaches. An agent (prompt, context messages) is defined in its own
folder outside this app; a provider turns that definition into a live session
the browser can join. OpenAI answers a WebRTC offer; Gemini hands out a
one-use token and the setup message for its WebSocket."""

import copy
import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol

from app.net import HttpError, post_json
from app.templates import fill

log = logging.getLogger(__name__)

OPENAI_SESSIONS_URL = "https://api.openai.com/v1/live/sessions"
GEMINI_TOKENS_URL = "https://generativelanguage.googleapis.com/v1beta/auth_tokens"
GEMINI_LIVE_URL = (
    "wss://generativelanguage.googleapis.com/ws/"
    "google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContentConstrained"
)


class AgentDefinition:
    """session.json plus prompts/live.md from an agent folder. The session file
    is in OpenAI's shape; Gemini's setup is derived from the same two files."""

    def __init__(self, agent_dir: Path):
        self.template = json.loads((agent_dir / "session.json").read_text())
        self.instructions = (agent_dir / "prompts" / "live.md").read_text()

    def session_for(self, **values: str) -> dict:
        """The OpenAI session object with `instructions` filled in and every
        {{name}} in the input messages replaced. An unknown placeholder is left alone."""
        session = copy.deepcopy(self.template)
        session["instructions"] = self.instructions
        for message in session.get("input", []):
            for part in message.get("content", []):
                text = part.get("text")
                if text:
                    part["text"] = fill(text, **values)
        return session

    def context_for(self, **values: str) -> str:
        """The input messages' text, filled in, as one block for a system instruction."""
        texts = [
            fill(part["text"], **values)
            for message in self.template.get("input", [])
            for part in message.get("content", [])
            if part.get("text")
        ]
        return "\n\n".join(texts)

    def gemini_setup(self, model: str, voice: str, thinking_level: str | None, **values: str) -> dict:
        """The BidiGenerateContentSetup message. The developer context rides
        inside the system instruction since Gemini has no developer role."""
        instruction = self.instructions.rstrip()
        context = self.context_for(**values)
        if context:
            instruction = f"{instruction}\n\n{context}"
        generation: dict = {
            "responseModalities": ["AUDIO"],
            "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}},
        }
        if thinking_level:
            generation["thinkingConfig"] = {"thinkingLevel": thinking_level}
        return {
            "model": f"models/{model}",
            "generationConfig": generation,
            "systemInstruction": {"parts": [{"text": instruction}]},
            "inputAudioTranscription": {},
            "outputAudioTranscription": {},
        }


class VoiceProvider(Protocol):
    """Opens one live round for an agent. The answer goes to the browser as is."""

    name: str

    def open(self, definition: AgentDefinition, sdp: str | None, **values: str) -> dict: ...


class OpenAIVoice:
    """Relays the browser's WebRTC offer to OpenAI and returns its answer."""

    name = "openai"

    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model

    def open(self, definition: AgentDefinition, sdp: str | None, **values: str) -> dict:
        if not sdp or not sdp.strip():
            raise HttpError(400, "an SDP offer is required for the OpenAI provider")
        session = definition.session_for(**values)
        session["model"] = self.model
        body = {"session": session, "transport": {"type": "webrtc", "sdp": sdp}}
        answer = post_json(OPENAI_SESSIONS_URL, body, {"Authorization": f"Bearer {self.api_key}"})
        return {"provider": self.name, **answer}


class GeminiVoice:
    """Mints a one-use ephemeral token locked to the whole setup (model, voice,
    system instruction), and hands the browser the token in the WebSocket URL
    plus that same setup message to send first."""

    name = "gemini"
    TOKEN_TTL = timedelta(minutes=30)
    CONNECT_WINDOW = timedelta(minutes=2)

    def __init__(
        self,
        api_key: str,
        model: str,
        voice: str,
        thinking_level: str | None,
    ):
        self.api_key = api_key
        self.model = model
        self.voice = voice
        self.thinking_level = thinking_level

    def open(self, definition: AgentDefinition, sdp: str | None, **values: str) -> dict:
        now = datetime.now(UTC)
        setup = definition.gemini_setup(self.model, self.voice, self.thinking_level, **values)
        body = {
            "uses": 1,
            "expireTime": _rfc3339(now + self.TOKEN_TTL),
            "newSessionExpireTime": _rfc3339(now + self.CONNECT_WINDOW),
            "bidiGenerateContentSetup": setup,
        }
        token = post_json(GEMINI_TOKENS_URL, body, {"x-goog-api-key": self.api_key})
        return {"provider": self.name, "url": f"{GEMINI_LIVE_URL}?access_token={token['name']}", "setup": setup}


def _rfc3339(moment: datetime) -> str:
    return moment.replace(microsecond=0).isoformat().replace("+00:00", "Z")


class LiveAgent:
    def __init__(self, name: str, definition: AgentDefinition, provider: VoiceProvider):
        self.name = name
        self.definition = definition
        self.provider = provider

    def start(self, sdp: str | None, **values: str) -> dict:
        result = self.provider.open(self.definition, sdp, **values)
        log.info("%s round opened on %s", self.name, self.provider.name)
        return result
