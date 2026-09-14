"""GPT-Live voice agents. An agent (prompt, voice, session shape) is defined in
its own folder outside this app; this module fills the template's placeholders
in and relays the browser's WebRTC offer to OpenAI."""

import copy
import json
import logging
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Protocol

log = logging.getLogger(__name__)

LIVE_SESSIONS_URL = "https://api.openai.com/v1/live/sessions"
INSTRUCTIONS_PLACEHOLDER = "<contents of prompts/live.md>"
PLACEHOLDER = re.compile(r"\{\{(\w+)\}\}")


class LiveSessionError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(f"{status}: {message}")
        self.status = status
        self.message = message


class AgentDefinition:
    """session.json plus prompts/live.md from an agent folder."""

    def __init__(self, agent_dir: Path):
        self.template = json.loads((agent_dir / "session.json").read_text())
        self.instructions = (agent_dir / "prompts" / "live.md").read_text()

    def session_for(self, **values: str) -> dict:
        """The session object with `instructions` filled in and every {{name}}
        in the input messages replaced. An unknown placeholder is left alone."""
        session = copy.deepcopy(self.template)
        session["instructions"] = self.instructions
        for message in session.get("input", []):
            for part in message.get("content", []):
                text = part.get("text")
                if text:
                    part["text"] = PLACEHOLDER.sub(lambda m: values.get(m.group(1), m.group(0)), text)
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


class LiveAgent:
    def __init__(self, name: str, definition: AgentDefinition, sessions: LiveSessions):
        self.name = name
        self.definition = definition
        self.sessions = sessions

    def start(self, sdp: str, **values: str) -> dict:
        result = self.sessions.create(self.definition.session_for(**values), sdp)
        log.info("%s session %s started", self.name, result.get("session", {}).get("id"))
        return result
