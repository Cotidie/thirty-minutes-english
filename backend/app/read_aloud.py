"""Read-aloud coaching sessions on GPT-Live. The agent (prompt, voice, session
shape) is defined in the read-aloud-coach folder; this module only fills the
paragraph in and relays the browser's WebRTC offer to OpenAI."""

import copy
import json
import logging
import urllib.error
import urllib.request
from pathlib import Path
from typing import Protocol

log = logging.getLogger(__name__)

LIVE_SESSIONS_URL = "https://api.openai.com/v1/live/sessions"
INSTRUCTIONS_PLACEHOLDER = "<contents of prompts/live.md>"
PARAGRAPH_PLACEHOLDER = "{{paragraph}}"


class LiveSessionError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(f"{status}: {message}")
        self.status = status
        self.message = message


class AgentDefinition:
    """session.json plus prompts/live.md from the agent folder."""

    def __init__(self, agent_dir: Path):
        self.template = json.loads((agent_dir / "session.json").read_text())
        self.instructions = (agent_dir / "prompts" / "live.md").read_text()

    def session_for(self, paragraph: str) -> dict:
        session = copy.deepcopy(self.template)
        session["instructions"] = self.instructions
        for message in session.get("input", []):
            for part in message.get("content", []):
                if PARAGRAPH_PLACEHOLDER in part.get("text", ""):
                    part["text"] = part["text"].replace(PARAGRAPH_PLACEHOLDER, paragraph)
        return session


class LiveSessions(Protocol):
    def create(self, session: dict, sdp: str) -> dict: ...


class OpenAILiveSessions:
    def __init__(self, api_key: str, url: str = LIVE_SESSIONS_URL):
        self.api_key = api_key
        self.url = url

    def create(self, session: dict, sdp: str) -> dict:
        body = json.dumps({"session": session, "transport": {"type": "webrtc", "sdp": sdp}}).encode()
        req = urllib.request.Request(
            self.url,
            data=body,
            method="POST",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as res:
                return json.load(res)
        except urllib.error.HTTPError as e:
            raise LiveSessionError(e.code, _error_message(e.read())) from e
        except urllib.error.URLError as e:
            raise LiveSessionError(502, str(e.reason)) from e


def _error_message(raw: bytes) -> str:
    try:
        return json.loads(raw)["error"]["message"]
    except (ValueError, KeyError, TypeError):
        return raw.decode(errors="replace")[:300]


class ReadAloudCoach:
    def __init__(self, definition: AgentDefinition, sessions: LiveSessions):
        self.definition = definition
        self.sessions = sessions

    def start(self, paragraph: str, sdp: str) -> dict:
        result = self.sessions.create(self.definition.session_for(paragraph), sdp)
        log.info("read-aloud session %s started", result.get("session", {}).get("id"))
        return result
