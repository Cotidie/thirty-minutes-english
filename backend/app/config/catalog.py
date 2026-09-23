"""Model lists as each provider reports them, so the settings modal never offers a
hardcoded list that goes stale. One fetcher per list; results are cached a day in
SQLite and refreshed in the background, so opening the modal never waits on a
provider. A list that cannot be fetched (no key, provider down) keeps its last
copy; with none, the modal offers the field's default alone."""

import asyncio
import logging
import re
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient

from app.db.caches import CacheRepo
from app.mcp_client import McpHttp, payload
from app.net import get_json
from app.pictures.painters import COMFY_MCP

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ModelOption:
    id: str
    label: str = ""
    description: str = ""
    efforts: tuple[str, ...] | None = None  # Claude only: the effort levels it takes; () = none


Keys = Mapping[str, str]
Fetcher = Callable[[Keys], list[ModelOption]]

DATED = re.compile(r"-\d{4}(-\d{2}-\d{2}|\d{4})?$")  # snapshot ids (-0125, -20250805, -2025-08-07); the alias is enough


def claude_models(_: Keys) -> list[ModelOption]:
    """What Claude Code itself offers on this subscription, with each model's effort levels."""

    async def fetch() -> list[dict]:
        async with ClaudeSDKClient(ClaudeAgentOptions(setting_sources=[])) as client:
            return ((await client.get_server_info()) or {}).get("models") or []

    return [
        ModelOption(
            m["value"],
            m.get("displayName", ""),
            m.get("description", ""),
            tuple(m.get("supportedEffortLevels") or ()) if m.get("supportsEffort") else (),
        )
        for m in asyncio.run(fetch())
    ]


def openai_ids(keys: Keys) -> list[str]:
    key = keys.get("OPENAI_API_KEY", "")
    if not key:
        return []
    data = get_json("https://api.openai.com/v1/models", {"Authorization": f"Bearer {key}"})["data"]
    return sorted(m["id"] for m in data if not DATED.search(m["id"]))


def openai_voice(keys: Keys) -> list[ModelOption]:
    """Speech-to-speech models: GPT-Live and the realtime line, minus transcription and translation."""
    return [
        ModelOption(i) for i in openai_ids(keys) if ("live" in i or "realtime" in i) and not re.search(r"transcribe|translate", i)
    ]


def openai_text(keys: Keys) -> list[ModelOption]:
    """GPT text models for the Summary tab: no audio, image, realtime, search or code variants."""
    skip = re.compile(r"audio|realtime|live|image|tts|transcribe|search|codex|embedding|moderation|instruct")
    return [ModelOption(i) for i in openai_ids(keys) if i.startswith("gpt-") and not skip.search(i)]


def gemini_live(keys: Keys) -> list[ModelOption]:
    key = keys.get("GEMINI_API_KEY", "")
    if not key:
        return []
    models = get_json(f"https://generativelanguage.googleapis.com/v1beta/models?pageSize=1000&key={key}").get("models", [])
    return [
        ModelOption(m["name"].removeprefix("models/"), m.get("displayName", ""), first_sentence(m.get("description", "")))
        for m in models
        if "bidiGenerateContent" in m.get("supportedGenerationMethods", [])
        and not re.search(r"transcribe|translate|robotics", m["name"])
    ]


def openrouter_images(_: Keys) -> list[ModelOption]:
    data = get_json("https://openrouter.ai/api/v1/models?output_modalities=image")["data"]
    return sorted(
        (ModelOption(m["id"], m.get("name", ""), first_sentence(m.get("description", ""))) for m in data),
        key=lambda o: o.id,
    )


def comfy_images(keys: Keys) -> list[ModelOption]:
    """comfy's partner text-to-image models; edit-only ones (inpaint, expand) are left out."""
    key = keys.get("COMFY_API_KEY", "")
    if not key:
        return []

    async def fetch() -> dict:
        async with McpHttp(COMFY_MCP, key).session() as session:
            return payload(await session.call("search_models", {"source": "partner", "type": "image", "limit": 100}))

    return [
        ModelOption(m["model_name"], description=f"Tiers: {', '.join(m['tiers'])}" if m.get("tiers") else "")
        for m in asyncio.run(fetch()).get("data", [])
        if "text-to-image" in m.get("tags", [])
    ]


def first_sentence(text: str, limit: int = 140) -> str:
    sentence = " ".join(text.split()).split(". ")[0]
    return sentence if len(sentence) <= limit else sentence[: limit - 1].rstrip() + "…"


FETCHERS: dict[str, Fetcher] = {
    "claude": claude_models,
    "openai_voice": openai_voice,
    "openai_text": openai_text,
    "gemini_live": gemini_live,
    "openrouter_images": openrouter_images,
    "comfy_images": comfy_images,
}


class Catalog:
    """Cached model lists. `options` answers from the cache at once and starts a
    background refresh when the copy is older than a day or missing."""

    TTL_S = 24 * 3600

    def __init__(self, caches: CacheRepo, fetchers: Mapping[str, Fetcher] = FETCHERS, clock=time.time, background: bool = True) -> None:
        self._caches = caches
        self._fetchers = fetchers
        self._clock = clock
        self._background = background
        self._running: set[str] = set()
        self._lock = threading.Lock()

    def options(self, source: str, keys: Keys) -> list[ModelOption]:
        cached = self._caches.get_model_list(source)
        if cached is None or self._clock() - cached["at"] > self.TTL_S:
            self.refresh_later(keys, [source])
        return [
            ModelOption(**{**o, "efforts": None if o.get("efforts") is None else tuple(o["efforts"])})
            for o in (cached or {}).get("options", [])
        ]

    def efforts_of(self, model: str) -> tuple[str, ...] | None:
        """A Claude model's effort levels from the cached list; None when the model is not listed."""
        cached = self._caches.get_model_list("claude") or {}
        found = next((o for o in cached.get("options", []) if o["id"] == model), None)
        return None if found is None or found.get("efforts") is None else tuple(found["efforts"])

    def refresh(self, keys: Keys, sources: list[str] | None = None) -> dict[str, str]:
        """Fetches now; the error per source that failed (its old copy stays)."""
        errors: dict[str, str] = {}
        for source in sources if sources is not None else list(self._fetchers):
            try:
                found = self._fetchers[source](keys)
            except Exception as e:  # a provider down or a key refused must not break the modal
                log.warning("model list %s: %s", source, e)
                errors[source] = str(e) or type(e).__name__
                continue
            if found:
                self._caches.set_model_list(source, {"at": self._clock(), "options": [asdict(o) for o in found]})
        return errors

    def refresh_later(self, keys: Keys, sources: list[str] | None = None) -> None:
        """Fetches in the background (a new key was saved, or a list went stale); one run per source at a time."""
        with self._lock:
            todo = [s for s in (sources if sources is not None else list(self._fetchers)) if s in self._fetchers and s not in self._running]
            self._running.update(todo)
        if not todo:
            return

        def run() -> None:
            try:
                self.refresh(dict(keys), todo)
            finally:
                with self._lock:
                    self._running.difference_update(todo)

        if self._background:
            threading.Thread(target=run, daemon=True).start()
        else:
            run()
