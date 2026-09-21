"""Everything the API needs that depends on settings, built in one place so a
settings change can rebuild it all without a restart."""

import logging
from dataclasses import dataclass
from pathlib import Path

from app.assessor import AzureAssessor
from app.cards import Extractor, PhraseCardExtractor
from app.daily_topics import ClaudeTopicSource, TopicSource
from app.example_feedback import TEMPLATES, ExampleCoach
from app.generator import ClaudeCliGenerator, Generator
from app.illustrator import Illustrator
from app.painters import painter_for
from app.live import AgentDefinition, GeminiVoice, LiveAgent, OpenAIVoice, VoiceProvider
from app.phrasing import PhrasingMarker
from app.settings import Settings

log = logging.getLogger(__name__)

AGENT_NAMES = ("read-aloud", "phrase", "example")


@dataclass
class Services:
    generator: Generator
    topic_source: TopicSource | None = None
    agents: dict[str, LiveAgent] | None = None
    extractor: Extractor | None = None
    example_coach: ExampleCoach | None = None
    illustrator: Illustrator | None = None
    phrasing: PhrasingMarker | None = None
    assessor: AzureAssessor | None = None
    voice_key_name: str = "OPENAI_API_KEY"

    def __post_init__(self) -> None:
        self.agents = self.agents or {}


def build_services(settings: Settings, agent_dirs: dict[str, Path], image_dir: Path | None = None) -> Services:
    """`agent_dirs` maps read-aloud / phrase / example to their folders; `image_dir` is
    where the vocabulary pictures land (none: no pictures)."""
    openai_key = settings.get("OPENAI_API_KEY")
    return Services(
        generator=ClaudeCliGenerator(
            model=settings.get("CLAUDE_MODEL"),
            effort=settings.get("CLAUDE_EFFORT"),
            skills=settings.claude_skills,
        ),
        topic_source=ClaudeTopicSource(model=settings.get("TOPICS_MODEL"), effort=settings.get("TOPICS_EFFORT")),
        agents=_live_agents(settings, agent_dirs),
        extractor=_extractor(openai_key, agent_dirs["phrase"], "cards.schema.json", settings, PhraseCardExtractor),
        example_coach=_example_coach(settings, agent_dirs["example"]),
        illustrator=_illustrator(settings, image_dir),
        phrasing=_phrasing(settings, agent_dirs["read-aloud"]),
        assessor=_assessor(settings),
        voice_key_name=settings.voice_api_key_name,
    )


def _assessor(settings: Settings) -> AzureAssessor | None:
    """Azure pronunciation assessment, once its key is set."""
    key = settings.azure_speech_key
    if not key:
        return None
    return AzureAssessor(
        key,
        settings.azure_speech_region,
        settings.assess_word_score,
        settings.assess_break_confidence,
    )


def voice_provider(settings: Settings) -> VoiceProvider | None:
    """The configured provider, or None while its key is missing."""
    key = settings.voice_api_key
    if not key:
        return None
    if settings.voice_provider == "gemini":
        return GeminiVoice(key, settings.voice_model, settings.voice_name, settings.voice_thinking)
    return OpenAIVoice(key, settings.voice_model)


def _live_agents(settings: Settings, agent_dirs: dict[str, Path]) -> dict[str, LiveAgent]:
    provider = voice_provider(settings)
    if provider is None:
        return {}
    agents = {}
    for name in AGENT_NAMES:
        agent_dir = agent_dirs[name]
        if (agent_dir / "session.json").is_file():
            agents[name] = LiveAgent(name, AgentDefinition(agent_dir), provider)
        else:
            log.warning("%s agent folder not found: %s", name, agent_dir)
    return agents


def _extractor(api_key: str, agent_dir: Path, schema: str, settings: Settings, build) -> Extractor | None:
    """An extractor per agent folder, once an OpenAI key and that folder's schema exist."""
    if not api_key or not (agent_dir / schema).is_file():
        return None
    return build(api_key, agent_dir, settings.get("SUMMARY_MODEL"))


def _phrasing(settings: Settings, agent_dir: Path) -> PhrasingMarker | None:
    """Thought-group marking, once the read-aloud folder carries the phrasing prompt."""
    if not (agent_dir / "prompts" / "phrasing.md").is_file():
        log.warning("read-aloud phrasing prompt not found: %s", agent_dir)
        return None
    return PhrasingMarker.with_cli(agent_dir, settings.get("EXAMPLE_MODEL"), settings.get("EXAMPLE_EFFORT"))


def _example_coach(settings: Settings, agent_dir: Path) -> ExampleCoach | None:
    """The text half of the example coach, once its folder carries the feedback prompt."""
    if not all((agent_dir / "prompts" / name).is_file() for name in TEMPLATES.values()):
        log.warning("example-coach feedback prompts not found: %s", agent_dir)
        return None
    return ExampleCoach.with_cli(agent_dir, settings.get("EXAMPLE_MODEL"), settings.get("EXAMPLE_EFFORT"))


def _illustrator(settings: Settings, image_dir: Path | None) -> Illustrator | None:
    """Pictures for the words, once a provider is chosen, the host is logged in to it, and there is a folder."""
    if image_dir is None:
        return None
    painter = painter_for(settings.get("IMAGE_PROVIDER"), settings.get("IMAGE_MODEL"))
    return Illustrator(painter, image_dir) if painter else None
