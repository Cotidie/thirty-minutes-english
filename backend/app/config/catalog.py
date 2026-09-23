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
from dataclasses import asdict, dataclass, fields

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
    efforts: tuple[str, ...] | None = None  # Claude only: the effort levels it takes; () = none
    created: float | None = None  # release time (unix) when the provider says; sorts the list
    resolved: str = ""  # the dated model an alias points at (Claude Code's resolvedModel); sorts the list
    image_per_m: float | None = None  # list price, dollars per million image-output tokens
    text_per_m: float | None = None  # list price, dollars per million prompt tokens


NEWEST = 10  # a list keeps its newest models only (a saved older one still works)
VERSION = re.compile(r"(?<![\d.])(\d+)(?:[.-](\d{1,2})(?!\d))?")  # 3.8, 5-5 (Claude ids), 2
MONTH_YEAR = re.compile(r"(\d{2})-(\d{4})")


def recency(o: ModelOption) -> tuple:
    """Newer sorts higher. With a release time, that; else the version in the name ("Opus 5.5",
    "gemini-3.8-live", "flux-2-pro"), a month-year ("preview-09-2025") breaking ties. A name
    without a number is an alias for the latest release ("default", "nano-banana-pro"): on top."""
    if o.created:
        return (2, o.created)
    name = o.resolved or o.label or o.id.split("/")[-1]
    version = VERSION.search(name)
    if not version:
        return (3,)
    month_year = MONTH_YEAR.search(o.id)
    return (1, float(f"{version.group(1)}.{version.group(2) or 0}"), (int(month_year.group(2)), int(month_year.group(1))) if month_year else (0, 0))


def newest_first(options: list[ModelOption]) -> list[ModelOption]:
    """Newest first; ties keep the provider's order."""
    return sorted(options, key=recency, reverse=True)


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
            tuple(m.get("supportedEffortLevels") or ()) if m.get("supportsEffort") else (),
            resolved=m.get("resolvedModel", ""),
        )
        for m in asyncio.run(fetch())
    ]


def openai_models(keys: Keys) -> list[ModelOption]:
    key = keys.get("OPENAI_API_KEY", "")
    if not key:
        return []
    data = get_json("https://api.openai.com/v1/models", {"Authorization": f"Bearer {key}"})["data"]
    return [ModelOption(m["id"], created=m.get("created")) for m in data if not DATED.search(m["id"])]


def openai_voice(keys: Keys) -> list[ModelOption]:
    """Speech-to-speech models: GPT-Live and the realtime line, minus transcription and translation."""
    return [o for o in openai_models(keys) if ("live" in o.id or "realtime" in o.id) and not re.search(r"transcribe|translate", o.id)]


def openai_text(keys: Keys) -> list[ModelOption]:
    """GPT text models for the Summary tab: no audio, image, realtime, search or code variants."""
    skip = re.compile(r"audio|realtime|live|image|tts|transcribe|search|codex|embedding|moderation|instruct")
    return [o for o in openai_models(keys) if o.id.startswith("gpt-") and not skip.search(o.id)]


def gemini_live(keys: Keys) -> list[ModelOption]:
    key = keys.get("GEMINI_API_KEY", "")
    if not key:
        return []
    models = get_json(f"https://generativelanguage.googleapis.com/v1beta/models?pageSize=1000&key={key}").get("models", [])
    return [
        ModelOption(m["name"].removeprefix("models/"), m.get("displayName", ""))
        for m in models
        if "bidiGenerateContent" in m.get("supportedGenerationMethods", [])
        and not re.search(r"transcribe|translate|robotics", m["name"])
    ]


def openrouter_images(_: Keys) -> list[ModelOption]:
    data = get_json("https://openrouter.ai/api/v1/models?output_modalities=image")["data"]
    return [
        ModelOption(
            m["id"],
            m.get("name", ""),
            created=m.get("created"),
            image_per_m=per_million((m.get("pricing") or {}).get("image_output")),
            text_per_m=per_million((m.get("pricing") or {}).get("prompt")),
        )
        for m in data
    ]


def per_million(per_token: str | None) -> float | None:
    """OpenRouter quotes dollars per token as a string; the menu reads dollars per million."""
    try:
        return round(float(per_token) * 1_000_000, 4) if per_token is not None else None
    except ValueError:
        return None


def comfy_images(keys: Keys) -> list[ModelOption]:
    """comfy's partner text-to-image models; edit-only ones (inpaint, expand) are left out."""
    key = keys.get("COMFY_API_KEY", "")
    if not key:
        return []

    async def fetch() -> dict:
        async with McpHttp(COMFY_MCP, key).session() as session:
            return payload(await session.call("search_models", {"source": "partner", "type": "image", "limit": 100}))

    return [
        ModelOption(m["model_name"])
        for m in asyncio.run(fetch()).get("data", [])
        if "text-to-image" in m.get("tags", [])
    ]


FETCHERS: dict[str, Fetcher] = {
    "claude": claude_models,
    "openai_voice": openai_voice,
    "openai_text": openai_text,
    "gemini_live": gemini_live,
    "openrouter_images": openrouter_images,
    "comfy_images": comfy_images,
}


FIELDS = {f.name for f in fields(ModelOption)}


def from_cache(stored: dict) -> ModelOption:
    """A cached option; fields an older version stored and this one dropped are ignored."""
    known = {k: v for k, v in stored.items() if k in FIELDS}
    return ModelOption(**{**known, "efforts": None if known.get("efforts") is None else tuple(known["efforts"])})


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

    def options(self, source: str, keys: Keys, keep: tuple[str, ...] = ()) -> list[ModelOption]:
        """The newest `NEWEST` models, plus any in `keep` (the default, the saved one) that are
        older, so they keep their name and price; the cache holds the whole list."""
        cached = self._caches.get_model_list(source)
        if cached is None or self._clock() - cached["at"] > self.TTL_S:
            self.refresh_later(keys, [source])
        every = [from_cache(o) for o in (cached or {}).get("options", [])]
        return every[:NEWEST] + [o for o in every[NEWEST:] if o.id in keep]

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
                found = newest_first(self._fetchers[source](keys))
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
