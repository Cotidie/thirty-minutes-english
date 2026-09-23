"""Runtime settings. The environment seeds each value; what the user saves
in the settings modal lives in a SQLite table and wins from then on, and the
app rebuilds its services from the result without a restart. Infra values
that need a restart (DB path, agent folders, ports, the Claude OAuth token)
stay out of here. The saved values live in app.db.settings."""

from collections.abc import Mapping
from dataclasses import dataclass

from app.pictures.illustrator import STYLE_LABELS, STYLES
from app.pictures.painters import DEFAULT_MODEL as IMAGE_DEFAULT_MODEL

# The modal's sections, in order.
GROUPS: dict[str, str] = {
    "keys": "API keys",
    "voice": "Voice coach",
    "assess": "Read aloud assessor",
    "claude": "Claude generation",
    "text": "Summary text model",
    "images": "Vocabulary pictures",
}

EFFORTS = ("low", "medium", "high", "xhigh", "max")
CLAUDE_MODELS = ("opus", "sonnet")
IMAGE_PROVIDERS = (*IMAGE_DEFAULT_MODEL, "off")
# Image models as each MCP names them. OpenAI ids are spelled OpenRouter's way and translated for comfy.
OPENAI_IMAGE_MODELS = ("openai/gpt-image-2.5-flare", "openai/gpt-image-2.5-sunburst", "openai/gpt-image-2")
IMAGE_MODELS = {
    "openrouter": ("google/gemini-3-pro-image", "google/gemini-3.1-flash-image", "google/gemini-3.1-flash-lite-image", *OPENAI_IMAGE_MODELS),
    "comfy": ("vertexai/nano-banana-pro", "vertexai/nano-banana-2", "vertexai/nano-banana-2-lite", *OPENAI_IMAGE_MODELS),
}
VOICE_MODELS = {"openai": ("gpt-live-1",), "gemini": ("gemini-3.8-live-extended-thinking", "gemini-3.8-live")}
THINKING_LEVELS = ("low", "medium", "high")
# The Gemini API has no voices.list; this is the TTS list the Live native-audio
# models share (ai.google.dev/gemini-api/docs/speech-generation#voices).
GEMINI_VOICES = {
    "Zephyr": "Bright",
    "Puck": "Upbeat",
    "Charon": "Informative",
    "Kore": "Firm",
    "Fenrir": "Excitable",
    "Leda": "Youthful",
    "Orus": "Firm",
    "Aoede": "Breezy",
    "Callirrhoe": "Easy-going",
    "Autonoe": "Bright",
    "Enceladus": "Breathy",
    "Iapetus": "Clear",
    "Umbriel": "Easy-going",
    "Algieba": "Smooth",
    "Despina": "Smooth",
    "Erinome": "Clear",
    "Algenib": "Gravelly",
    "Rasalgethi": "Informative",
    "Laomedeia": "Upbeat",
    "Achernar": "Soft",
    "Alnilam": "Firm",
    "Schedar": "Even",
    "Gacrux": "Mature",
    "Pulcherrima": "Forward",
    "Achird": "Friendly",
    "Zubenelgenubi": "Casual",
    "Vindemiatrix": "Gentle",
    "Sadachbia": "Lively",
    "Sadaltager": "Knowledgeable",
    "Sulafat": "Warm",
}


@dataclass(frozen=True)
class Variant:
    """What a field offers while the setting it follows holds one value."""

    default: str = ""
    suggestions: tuple[str, ...] = ()


def variants(by_value: Mapping[str, tuple[str, ...]]) -> dict[str, Variant]:
    """The first suggestion of each list is that value's default."""
    return {value: Variant(models[0], models) for value, models in by_value.items()}


@dataclass(frozen=True)
class Spec:
    key: str
    group: str
    default: str = ""
    secret: bool = False
    choices: tuple[str, ...] | None = None  # strict: a value outside is rejected
    suggestions: tuple[str, ...] = ()  # free text with a menu of common values
    labels: Mapping[str, str] | None = None  # a short description per choice, for the menu
    number: tuple[float, float] | None = None  # strict: must parse as a number inside [lo, hi]
    follows: str | None = None  # the setting whose value picks a Variant below
    variants: Mapping[str, Variant] | None = None
    shown_when: tuple[str, str] | None = None  # (key, value): the field only matters then
    used_when: tuple[str, str] | None = None  # (key, value): a key the app only calls then; shown, marked idle otherwise
    help: str = ""  # one or two sentences for the modal's info tooltip


SPECS: tuple[Spec, ...] = (
    Spec("OPENAI_API_KEY", "keys", secret=True,
         help="Runs the OpenAI voice coaches and writes the Summary tab."),
    Spec("GEMINI_API_KEY", "keys", secret=True, used_when=("VOICE_PROVIDER", "gemini"),
         help="Runs the voice coaches when the voice provider is Gemini."),
    Spec("AZURE_SPEECH_KEY", "keys", secret=True,
         help="Azure Pronunciation Assessment. Read aloud scores each word with it; without it, Read aloud is off."),
    Spec("OPENROUTER_API_KEY", "keys", secret=True, used_when=("IMAGE_PROVIDER", "openrouter"),
         help="Draws the vocabulary pictures when the picture provider is OpenRouter. Pays per picture."),
    Spec("COMFY_API_KEY", "keys", secret=True, used_when=("IMAGE_PROVIDER", "comfy"),
         help="Draws the vocabulary pictures when the picture provider is Comfy Cloud. Your plan sets how many draw at once."),
    Spec("FIRECRAWL_API_KEY", "keys", secret=True,
         help="Optional. Web search for sessions and daily topics works without a key, at a lower rate limit."),
    Spec("VOICE_PROVIDER", "voice", "openai", choices=("openai", "gemini"),
         help="Which live voice model the three coaches (Read aloud, Phrasing, Your turn) talk through."),
    Spec("VOICE_MODEL", "voice", follows="VOICE_PROVIDER", variants=variants(VOICE_MODELS),
         help="The live model. Blank uses the provider's default."),
    Spec("VOICE_THINKING", "voice", "low", choices=THINKING_LEVELS, shown_when=("VOICE_PROVIDER", "gemini"),
         help="How long Gemini thinks before it answers. Higher is more careful and slower to reply."),
    Spec("VOICE_NAME", "voice", "Kore", choices=tuple(GEMINI_VOICES), labels=GEMINI_VOICES, shown_when=("VOICE_PROVIDER", "gemini"),
         help="The Gemini voice the coaches speak with."),
    Spec("AZURE_SPEECH_REGION", "assess", "koreacentral",
         help="The region of your Azure Speech resource. It must match the key."),
    Spec("ASSESS_WORD_SCORE", "assess", "60", number=(0, 100),
         help="Azure gives every word an accuracy score from 0 to 100. Words below this number get a pronunciation note. Higher is stricter."),
    Spec("ASSESS_BREAK_CONFIDENCE", "assess", "0.75", number=(0, 1),
         help="Azure reports how sure it is (0 to 1) that you paused where the sentence does not. Above this number, the pause gets a phrasing note. Lower flags more pauses."),
    Spec("CLAUDE_MODEL", "claude", "opus", suggestions=CLAUDE_MODELS,
         help="Writes each session: expressions, article, words and picture scenes. Sonnet is faster, Opus writes better."),
    Spec("CLAUDE_EFFORT", "claude", "xhigh", choices=EFFORTS,
         help="How much the session model thinks before it writes. Higher is better and slower."),
    Spec("CLAUDE_SKILLS", "claude",
         help="Claude skills the session model loads first, comma-separated. Example: stop-slop,anti-ai-writing"),
    Spec("TOPICS_MODEL", "claude", "sonnet", suggestions=CLAUDE_MODELS,
         help="Picks the three news topics once a day."),
    Spec("TOPICS_EFFORT", "claude", "medium", choices=EFFORTS,
         help="How much the topics model thinks."),
    Spec("EXAMPLE_MODEL", "claude", "opus", suggestions=CLAUDE_MODELS,
         help="Writes the Your turn and Practice feedback, and new picture scenes on redraw."),
    Spec("EXAMPLE_EFFORT", "claude", "low", choices=EFFORTS,
         help="How much the feedback model thinks. Low keeps feedback quick."),
    Spec("IMAGE_PROVIDER", "images", "openrouter", choices=IMAGE_PROVIDERS,
         help="Who draws the vocabulary pictures. OpenRouter draws them all at once; Comfy draws as many at once as your plan allows; off skips pictures."),
    Spec("IMAGE_MODEL", "images", follows="IMAGE_PROVIDER", variants=variants(IMAGE_MODELS),
         help="The image model. Blank uses the provider's default."),
    Spec("IMAGE_STYLE", "images", "photo", choices=tuple(STYLES), labels=STYLE_LABELS,
         help="The look of new pictures. A photo gives the most to describe."),
    Spec("SUMMARY_MODEL", "text", "gpt-5.6-luna",
         help="The OpenAI text model that turns the session transcript into the Summary tab."),
)
SPEC_BY_KEY = {spec.key: spec for spec in SPECS}


class InvalidSetting(ValueError):
    pass


def validate(values: Mapping[str, str]) -> None:
    """Rejects unknown keys, values outside a strict choice list, and numbers out of range."""
    for key, value in values.items():
        spec = SPEC_BY_KEY.get(key)
        if spec is None:
            raise InvalidSetting(f"unknown setting {key}")
        if spec.choices and value not in spec.choices:
            raise InvalidSetting(f"{key} must be one of {', '.join(spec.choices)}")
        if spec.number:
            lo, hi = spec.number
            try:
                number = float(value)
            except ValueError:
                raise InvalidSetting(f"{key} must be a number") from None
            if not lo <= number <= hi:
                raise InvalidSetting(f"{key} must be between {lo:g} and {hi:g}")


class Settings:
    """Saved values first, then the environment, then the code default. Blank env values count as unset."""

    def __init__(self, env: Mapping[str, str], saved: Mapping[str, str]) -> None:
        self._env = {k: v.strip() for k, v in env.items() if k in SPEC_BY_KEY}
        self._saved = dict(saved)

    def get(self, key: str) -> str:
        if key in self._saved:
            return self._saved[key]
        return self._env.get(key) or SPEC_BY_KEY[key].default

    def effective(self, key: str) -> str:
        """The value a service uses: a blank field that follows another takes that value's default."""
        spec = SPEC_BY_KEY[key]
        value = self.get(key)
        if not value and spec.variants:
            variant = spec.variants.get(self.get(spec.follows or ""))
            return variant.default if variant else ""
        return value

    def shown(self, key: str) -> str:
        """The value for the modal: secrets masked."""
        value = self.get(key)
        return mask(value) if SPEC_BY_KEY[key].secret else value

    # Typed accessors for the places that build services.

    @property
    def voice_model(self) -> str:
        return self.effective("VOICE_MODEL")

    @property
    def voice_thinking(self) -> str | None:
        """Only the extended-thinking model accepts a thinking level."""
        return self.get("VOICE_THINKING") if self.voice_model.endswith("-extended-thinking") else None

    @property
    def voice_api_key_name(self) -> str:
        return "GEMINI_API_KEY" if self.get("VOICE_PROVIDER") == "gemini" else "OPENAI_API_KEY"

    @property
    def voice_api_key(self) -> str:
        return self.get(self.voice_api_key_name)

    @property
    def claude_skills(self) -> tuple[str, ...]:
        return tuple(s.strip() for s in self.get("CLAUDE_SKILLS").split(",") if s.strip())

    @property
    def assess_word_score(self) -> int:
        return int(float(self.get("ASSESS_WORD_SCORE")))

    @property
    def assess_break_confidence(self) -> float:
        return float(self.get("ASSESS_BREAK_CONFIDENCE"))


def mask(secret: str) -> str:
    """Enough to recognise a key, never enough to use it."""
    if not secret:
        return ""
    return f"…{secret[-4:]}" if len(secret) > 8 else "…"
