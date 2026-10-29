"""Voice coaches and the summary transcriber, on Gemini Live. An agent (its instructions and
the context of a round) is defined in its own folder outside this app; Gemini hands the browser
a one-use token and the setup message for its WebSocket."""

import copy
import json
import logging
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.net import post_json
from app.templates import fill

log = logging.getLogger(__name__)

GEMINI_TOKENS_URL = "https://generativelanguage.googleapis.com/v1beta/auth_tokens"
GEMINI_LIVE_URL = (
    "wss://generativelanguage.googleapis.com/ws/"
    "google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContentConstrained"
)
GEMINI_TOKEN_TTL = timedelta(minutes=30)
GEMINI_CONNECT_WINDOW = timedelta(minutes=2)
# The user speaks English, with a Korean word now and then; Gemini transcribes into these two only.
LANGUAGES = ["en-US", "ko-KR"]
# Google gets its best results from custom vocabulary of up to 100 terms.
VOCABULARY_SIZE = 100


class AgentDefinition:
    """prompts/live.md (the coach's instructions) and prompts/context.md (what one round is about,
    with {{name}} placeholders) from an agent folder."""

    def __init__(self, agent_dir: Path):
        self.instructions = (agent_dir / "prompts" / "live.md").read_text()
        self.context = (agent_dir / "prompts" / "context.md").read_text()

    def gemini_setup(self, model: str, voice: str, thinking_level: str | None, **values: str) -> dict:
        """The BidiGenerateContentSetup message, the round's context filled in after the instructions.
        An unknown placeholder is left alone."""
        instruction = self.instructions.rstrip()
        context = fill(self.context, **values).strip()
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
            "inputAudioTranscription": {"languageCodes": LANGUAGES},
            "outputAudioTranscription": {},
        }


def gemini_round(api_key: str, setup: dict) -> dict:
    """Mints a one-use ephemeral token locked to the whole setup, and hands the
    browser the token in the WebSocket URL plus that same setup message to send first."""
    now = datetime.now(UTC)
    body = {
        "uses": 1,
        "expireTime": _rfc3339(now + GEMINI_TOKEN_TTL),
        "newSessionExpireTime": _rfc3339(now + GEMINI_CONNECT_WINDOW),
        "bidiGenerateContentSetup": setup,
    }
    token = post_json(GEMINI_TOKENS_URL, body, {"x-goog-api-key": api_key})
    return {"url": f"{GEMINI_LIVE_URL}?access_token={token['name']}", "setup": setup}


class GeminiVoice:
    """A coach on a Gemini Live model: its setup carries the model, voice and system instruction."""

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

    def open(self, definition: AgentDefinition, **values: str) -> dict:
        return gemini_round(self.api_key, definition.gemini_setup(self.model, self.voice, self.thinking_level, **values))


class GeminiTranscriber:
    """Speech to text on Gemini's transcription model. Its setup is
    the agent folder's transcription.json. It takes no prompt and has no voice; the paragraph
    reaches it as vocabulary, so its names and terms come back spelled as the paragraph spells them."""

    def __init__(self, api_key: str, agent_dir: Path):
        self.api_key = api_key
        self.template = json.loads((agent_dir / "transcription.json").read_text())

    def start(self, paragraph: str) -> dict:
        setup = copy.deepcopy(self.template)
        setup["inputAudioTranscription"]["customVocabulary"] = vocabulary(paragraph)
        result = gemini_round(self.api_key, setup)
        log.info("transcription opened on %s", setup["model"])
        return result


def vocabulary(text: str) -> list[str]:
    """Each distinct word of the text once, in order, as written the first time. Words under
    four letters are left out unless written in capitals (AI, MIT): they are the common ones."""
    seen: dict[str, str] = {}
    for word in re.findall(r"[A-Za-z][A-Za-z'-]*[A-Za-z]", text):
        if len(word) >= 4 or word.isupper():
            seen.setdefault(word.lower(), word)
    return list(seen.values())[:VOCABULARY_SIZE]


def _rfc3339(moment: datetime) -> str:
    return moment.replace(microsecond=0).isoformat().replace("+00:00", "Z")


class LiveAgent:
    def __init__(self, name: str, definition: AgentDefinition, voice: GeminiVoice):
        self.name = name
        self.definition = definition
        self.voice = voice

    def start(self, **values: str) -> dict:
        result = self.voice.open(self.definition, **values)
        log.info("%s round opened on %s", self.name, self.voice.model)
        return result
