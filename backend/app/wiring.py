"""Everything the API needs that depends on settings, built in one place so a
settings change can rebuild it all without a restart."""

import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from app.coaching.cards import SCHEMA_FILE, Extractor, PhraseCardExtractor
from app.coaching.example_feedback import TEMPLATES, ExampleCoach
from app.coaching.phrasing import PhrasingMarker
from app.config.settings import SPEC_BY_KEY, Settings
from app.config.skills import host_skills
from app.generation.generator import ClaudeGenerator, Generator
from app.pictures.illustrator import Illustrator
from app.pictures.painters import PictureLog, painter_for
from app.pictures.scenes import SceneWriter
from app.topics.daily import ClaudeTopicSource, TopicSource
from app.voice.assessor import AzureAssessor
from app.voice.speech import Speaker, speaker_for
from app.voice.live import (
    AgentDefinition,
    GeminiVoice,
    LiveAgent,
    OpenAIVoice,
    VoiceProvider,
)

log = logging.getLogger(__name__)

# Each coach: the env var that points at its definition folder, and its folder under agents/ by default.
AGENTS: dict[str, tuple[str, str]] = {
    "read-aloud": ("READ_ALOUD_AGENT_DIR", "read-aloud-coach"),
    "phrase": ("PHRASE_AGENT_DIR", "phrase-coach"),
    "example": ("EXAMPLE_AGENT_DIR", "example-coach"),
}


@dataclass
class Services:
    generator: Generator
    topic_source: TopicSource | None = None
    agents: dict[str, LiveAgent] = field(default_factory=dict)
    extractor: Extractor | None = None
    example_coach: ExampleCoach | None = None
    illustrator: Illustrator | None = None
    scene_writer: SceneWriter | None = None
    phrasing: PhrasingMarker | None = None
    assessor: AzureAssessor | None = None
    speaker: Speaker | None = None
    voice_key_name: str = "OPENAI_API_KEY"


def agent_dirs(env: Mapping[str, str], agents_dir: Path) -> dict[str, Path]:
    return {name: Path(env.get(var) or agents_dir / folder) for name, (var, folder) in AGENTS.items()}


EffortsOf = Callable[[str], tuple[str, ...] | None]


def effort(settings: Settings, key: str, efforts_of: EffortsOf) -> str | None:
    """The effort setting, or None when its model takes no effort (Haiku), so the run does not fail on it."""
    levels = efforts_of(settings.get(SPEC_BY_KEY[key].effort_of or ""))
    return None if levels == () else settings.get(key)


def build_services(
    settings: Settings,
    agent_dirs: dict[str, Path],
    image_dir: Path | None = None,
    efforts_of: EffortsOf = lambda _: None,
    pictures: PictureLog | None = None,
    speech_dir: Path | None = None,
) -> Services:
    """`agent_dirs` maps read-aloud / phrase / example to their folders; `image_dir` is
    where the vocabulary pictures land (none: no pictures); `efforts_of` gives a Claude
    model's effort levels as Claude Code reported them (None: not known); `pictures`
    keeps how long each picture took and what it cost; `speech_dir` keeps sentences
    read aloud (none: no reading aloud)."""
    return Services(
        generator=ClaudeGenerator(
            model=settings.get("CLAUDE_MODEL"),
            effort=effort(settings, "CLAUDE_EFFORT", efforts_of),
            skills=tuple(s for s in settings.claude_skills if s in host_skills()),  # a vanished skill would fail the run
            firecrawl_key=settings.get("FIRECRAWL_API_KEY"),
        ),
        topic_source=ClaudeTopicSource(
            settings.get("TOPICS_MODEL"), effort(settings, "TOPICS_EFFORT", efforts_of), settings.get("FIRECRAWL_API_KEY")
        ),
        agents=_live_agents(settings, agent_dirs),
        extractor=_extractor(settings, agent_dirs["phrase"]),
        example_coach=_example_coach(settings, agent_dirs["example"], effort(settings, "EXAMPLE_EFFORT", efforts_of)),
        illustrator=_illustrator(settings, image_dir, pictures),
        scene_writer=SceneWriter.with_cli(settings.get("EXAMPLE_MODEL")),
        phrasing=_phrasing(settings, agent_dirs["read-aloud"], effort(settings, "EXAMPLE_EFFORT", efforts_of)),
        assessor=_assessor(settings),
        speaker=speaker_for(
            settings.get("VOICE_PROVIDER"),
            {"openai": settings.get("OPENAI_API_KEY"), "gemini": settings.get("GEMINI_API_KEY")},
            settings.get("VOICE_NAME"),
            speech_dir,
        ),
        voice_key_name=settings.voice_api_key_name,
    )


def _assessor(settings: Settings) -> AzureAssessor | None:
    """Azure pronunciation assessment, once its key is set."""
    key = settings.get("AZURE_SPEECH_KEY")
    if not key:
        return None
    return AzureAssessor(
        key,
        settings.get("AZURE_SPEECH_REGION"),
        settings.assess_word_score,
        settings.assess_break_confidence,
    )


def voice_provider(settings: Settings) -> VoiceProvider | None:
    """The configured provider, or None while its key is missing."""
    key = settings.voice_api_key
    if not key:
        return None
    if settings.get("VOICE_PROVIDER") == "gemini":
        return GeminiVoice(key, settings.voice_model, settings.get("VOICE_NAME"), settings.voice_thinking)
    return OpenAIVoice(key, settings.voice_model)


def _live_agents(settings: Settings, agent_dirs: dict[str, Path]) -> dict[str, LiveAgent]:
    provider = voice_provider(settings)
    if provider is None:
        return {}
    agents = {}
    for name in AGENTS:
        agent_dir = agent_dirs[name]
        if (agent_dir / "session.json").is_file():
            agents[name] = LiveAgent(name, AgentDefinition(agent_dir), provider)
        else:
            log.warning("%s agent folder not found: %s", name, agent_dir)
    return agents


def _extractor(settings: Settings, agent_dir: Path) -> Extractor | None:
    """Ask cards, once an OpenAI key and the phrase-coach schema exist."""
    key = settings.get("OPENAI_API_KEY")
    if not key or not (agent_dir / SCHEMA_FILE).is_file():
        return None
    return PhraseCardExtractor(key, agent_dir, settings.get("SUMMARY_MODEL"))


def _phrasing(settings: Settings, agent_dir: Path, example_effort: str | None) -> PhrasingMarker | None:
    """Thought-group marking, once the read-aloud folder carries the phrasing prompt."""
    if not (agent_dir / "prompts" / "phrasing.md").is_file():
        log.warning("read-aloud phrasing prompt not found: %s", agent_dir)
        return None
    return PhrasingMarker.with_cli(agent_dir, settings.get("EXAMPLE_MODEL"), example_effort)


def _example_coach(settings: Settings, agent_dir: Path, example_effort: str | None) -> ExampleCoach | None:
    """The text half of the example coach, once its folder carries the feedback prompt."""
    if not all((agent_dir / "prompts" / name).is_file() for name in TEMPLATES.values()):
        log.warning("example-coach feedback prompts not found: %s", agent_dir)
        return None
    return ExampleCoach.with_cli(agent_dir, settings.get("EXAMPLE_MODEL"), example_effort)


def _illustrator(settings: Settings, image_dir: Path | None, pictures: PictureLog | None) -> Illustrator | None:
    """Pictures for the words, once a provider is chosen, its key is set, and there is a folder for them."""
    if image_dir is None:
        return None
    keys = {"openrouter": settings.get("OPENROUTER_API_KEY"), "comfy": settings.get("COMFY_API_KEY")}
    painter = painter_for(settings.get("IMAGE_PROVIDER"), settings.get("IMAGE_MODEL"), keys, pictures)
    if painter is None and settings.get("IMAGE_PROVIDER") != "off":
        log.warning("pictures are off: no key for IMAGE_PROVIDER=%s", settings.get("IMAGE_PROVIDER"))
    return Illustrator(painter, image_dir, settings.get("IMAGE_STYLE")) if painter else None
