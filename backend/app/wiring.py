"""Everything the API needs that depends on settings, built in one place so a
settings change can rebuild it all without a restart."""

import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from app.coaching.example_feedback import TEMPLATES, ExampleCoach
from app.coaching.summary_feedback import SCHEMA as SUMMARY_SCHEMA
from app.coaching.summary_feedback import TEMPLATE as SUMMARY_TEMPLATE
from app.coaching.summary_feedback import SummaryCoach
from app.config.settings import SPEC_BY_KEY, Settings
from app.config.skills import host_skills
from app.generation.generator import ClaudeGenerator, Generator
from app.pictures.files import PictureFiles
from app.pictures.illustrator import Illustrator
from app.pictures.painters import painter_for
from app.pictures.scenes import SceneWriter
from app.topics.daily import ClaudeTopicSource, TopicSource
from app.voice.assessor import AzureAssessor
from app.voice.speech import Speaker, speaker_for
from app.voice.live import (
    AgentDefinition,
    GeminiTranscriber,
    GeminiVoice,
    LiveAgent,
    OpenAIVoice,
    VoiceProvider,
)

if TYPE_CHECKING:
    from app.db.pictures import PictureRepo

log = logging.getLogger(__name__)

# Each coach: the env var that points at its definition folder, and its folder under agents/ by default.
AGENTS: dict[str, tuple[str, str]] = {
    "read-aloud": ("READ_ALOUD_AGENT_DIR", "read-aloud-coach"),
    "example": ("EXAMPLE_AGENT_DIR", "example-coach"),
    "summary": ("SUMMARY_AGENT_DIR", "summary-coach"),
}
# The coaches that talk. Summarize is written down by the transcriber; its folder holds only the text prompt.
LIVE_AGENTS = ("read-aloud", "example")


@dataclass
class Services:
    generator: Generator
    topic_source: TopicSource | None = None
    agents: dict[str, LiveAgent] = field(default_factory=dict)
    example_coach: ExampleCoach | None = None
    summary_coach: SummaryCoach | None = None
    transcriber: GeminiTranscriber | None = None
    illustrator: Illustrator | None = None
    scene_writer: SceneWriter | None = None
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
    pictures: "PictureRepo | None" = None,
    files: PictureFiles | None = None,
    efforts_of: EffortsOf = lambda _: None,
    speech_dir: Path | None = None,
) -> Services:
    """`agent_dirs` maps read-aloud / example / summary to their folders; `pictures` and `files` keep
    each picture drawn, its row and its file (none: no pictures); `efforts_of` gives a Claude model's
    effort levels as Claude Code reported them (None: not known); `speech_dir` keeps sentences read
    aloud (none: no reading aloud)."""
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
        example_coach=_example_coach(settings, agent_dirs["example"], effort(settings, "EXAMPLE_EFFORT", efforts_of)),
        summary_coach=_summary_coach(settings, agent_dirs["summary"], effort(settings, "SUMMARY_EFFORT", efforts_of)),
        transcriber=_transcriber(settings, agent_dirs["summary"]),
        illustrator=_illustrator(settings, pictures, files),
        scene_writer=SceneWriter.with_cli(settings.get("EXAMPLE_MODEL")),
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
    return AzureAssessor(key, settings.get("AZURE_SPEECH_REGION"), settings.assess_word_score)


def _transcriber(settings: Settings, agent_dir: Path) -> GeminiTranscriber | None:
    """Summarize's transcriber, once the Gemini key is set. It does not follow the voice provider."""
    key = settings.get("GEMINI_API_KEY")
    if not key:
        return None
    if not (agent_dir / "transcription.json").is_file():
        log.warning("summary-coach transcription setup not found: %s", agent_dir)
        return None
    return GeminiTranscriber(key, agent_dir)


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
    for name in LIVE_AGENTS:
        agent_dir = agent_dirs[name]
        if (agent_dir / "session.json").is_file():
            agents[name] = LiveAgent(name, AgentDefinition(agent_dir), provider)
        else:
            log.warning("%s agent folder not found: %s", name, agent_dir)
    return agents


def _example_coach(settings: Settings, agent_dir: Path, example_effort: str | None) -> ExampleCoach | None:
    """The text half of the example coach, once its folder carries the feedback prompt."""
    if not all((agent_dir / "prompts" / name).is_file() for name in TEMPLATES.values()):
        log.warning("example-coach feedback prompts not found: %s", agent_dir)
        return None
    return ExampleCoach.with_cli(agent_dir, settings.get("EXAMPLE_MODEL"), example_effort)


def _summary_coach(settings: Settings, agent_dir: Path, summary_effort: str | None) -> SummaryCoach | None:
    """The judge of the summary coach, on its own model: it has to answer fast."""
    if not all((agent_dir / "prompts" / name).is_file() for name in (SUMMARY_TEMPLATE, SUMMARY_SCHEMA)):
        log.warning("summary-coach feedback prompt or schema not found: %s", agent_dir)
        return None
    return SummaryCoach.with_cli(agent_dir, settings.get("SUMMARY_MODEL"), summary_effort)


def _illustrator(settings: Settings, pictures: "PictureRepo | None", files: PictureFiles | None) -> Illustrator | None:
    """Pictures for the words, once a provider is chosen, its key is set, and there is a place to keep them."""
    if pictures is None or files is None:
        return None
    keys = {"openrouter": settings.get("OPENROUTER_API_KEY"), "comfy": settings.get("COMFY_API_KEY")}
    painter = painter_for(settings.get("IMAGE_PROVIDER"), settings.get("IMAGE_MODEL"), keys, pictures)
    if painter is None and settings.get("IMAGE_PROVIDER") != "off":
        log.warning("pictures are off: no key for IMAGE_PROVIDER=%s", settings.get("IMAGE_PROVIDER"))
    return Illustrator(painter, pictures, files, settings.get("IMAGE_STYLE")) if painter else None
