"""Runtime settings. The environment seeds each value; what the user saves
in the settings modal lives in a SQLite table and wins from then on, and the
app rebuilds its services from the result without a restart. Infra values
that need a restart (DB path, agent folders, ports, the Claude OAuth token)
stay out of here."""

import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

Group = Literal["keys", "voice", "assess", "claude", "text", "images"]

EFFORTS = ("low", "medium", "high", "xhigh", "max")
CLAUDE_MODELS = ("opus", "sonnet")
# comfy-cloud partner slugs for the vocabulary pictures; blank turns them off.
IMAGE_MODELS = ("vertexai/nano-banana-2-lite", "vertexai/nano-banana-2", "bfl/flux-2-pro", "openai/images-generations")
OPENAI_VOICE_MODEL = "gpt-live-1"
GEMINI_VOICE_MODEL = "gemini-3.8-live-extended-thinking"
GEMINI_VOICE_MODELS = ("gemini-3.8-live", GEMINI_VOICE_MODEL)
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
class Spec:
    key: str
    group: Group
    default: str = ""
    secret: bool = False
    choices: tuple[str, ...] | None = None  # strict: a value outside is rejected
    suggestions: tuple[str, ...] = ()  # free text with a menu of common values
    labels: Mapping[str, str] | None = None  # a short description per choice, for the menu
    number: tuple[float, float] | None = None  # strict: must parse as a number inside [lo, hi]


SPECS: tuple[Spec, ...] = (
    Spec("OPENAI_API_KEY", "keys", secret=True),
    Spec("GEMINI_API_KEY", "keys", secret=True),
    Spec("AZURE_SPEECH_KEY", "keys", secret=True),
    Spec("VOICE_PROVIDER", "voice", "openai", choices=("openai", "gemini")),
    Spec("VOICE_MODEL", "voice", suggestions=(OPENAI_VOICE_MODEL, *GEMINI_VOICE_MODELS)),
    Spec("VOICE_THINKING", "voice", "low", choices=THINKING_LEVELS),
    Spec("VOICE_NAME", "voice", "Kore", choices=tuple(GEMINI_VOICES), labels=GEMINI_VOICES),
    Spec("AZURE_SPEECH_REGION", "assess", "koreacentral"),
    Spec("ASSESS_WORD_SCORE", "assess", "60", number=(0, 100)),
    Spec("ASSESS_BREAK_CONFIDENCE", "assess", "0.75", number=(0, 1)),
    Spec("CLAUDE_MODEL", "claude", "opus", suggestions=CLAUDE_MODELS),
    Spec("CLAUDE_EFFORT", "claude", "xhigh", choices=EFFORTS),
    Spec("CLAUDE_SKILLS", "claude"),
    Spec("TOPICS_MODEL", "claude", "sonnet", suggestions=CLAUDE_MODELS),
    Spec("TOPICS_EFFORT", "claude", "medium", choices=EFFORTS),
    Spec("EXAMPLE_MODEL", "claude", "opus", suggestions=CLAUDE_MODELS),
    Spec("EXAMPLE_EFFORT", "claude", "low", choices=EFFORTS),
    Spec("IMAGES_MODEL", "claude", "sonnet", suggestions=CLAUDE_MODELS),
    Spec("IMAGE_MODEL", "images", "vertexai/nano-banana-2-lite", suggestions=IMAGE_MODELS),
    Spec("SUMMARY_MODEL", "text", "gpt-5.6-luna"),
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


class SettingsStore:
    """What the user saved. Same file as the sessions, its own table."""

    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path)

    def load(self) -> dict[str, str]:
        with self._connect() as conn:
            return dict(conn.execute("SELECT key, value FROM settings").fetchall())

    def save(self, values: Mapping[str, str]) -> None:
        validate(values)
        with self._connect() as conn:
            for key, value in values.items():
                conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))


@dataclass(frozen=True)
class Field:
    """One setting as the modal sees it: the effective value, secrets masked."""

    key: str
    group: Group
    value: str
    secret: bool
    default: str
    choices: tuple[str, ...] | None
    suggestions: tuple[str, ...]
    labels: dict[str, str]


class Settings:
    """Saved values first, then the environment, then the code default. Blank env values count as unset."""

    def __init__(self, env: Mapping[str, str], saved: Mapping[str, str]) -> None:
        self._env = {k: v.strip() for k, v in env.items() if k in SPEC_BY_KEY}
        self._saved = dict(saved)

    @classmethod
    def resolve(cls, env: Mapping[str, str], store: SettingsStore) -> "Settings":
        return cls(env, store.load())

    def get(self, key: str) -> str:
        if key in self._saved:
            return self._saved[key]
        return self._env.get(key) or SPEC_BY_KEY[key].default

    def fields(self) -> list[Field]:
        return [
            Field(
                key=spec.key,
                group=spec.group,
                value=mask(self.get(spec.key)) if spec.secret else self.get(spec.key),
                secret=spec.secret,
                default=spec.default,
                choices=spec.choices,
                suggestions=spec.suggestions,
                labels=dict(spec.labels or {}),
            )
            for spec in SPECS
        ]

    # Typed accessors for the places that build services.

    @property
    def voice_provider(self) -> str:
        return self.get("VOICE_PROVIDER")

    @property
    def voice_model(self) -> str:
        """The chosen model, or the provider's default when the field is blank."""
        chosen = self.get("VOICE_MODEL")
        if chosen:
            return chosen
        return GEMINI_VOICE_MODEL if self.voice_provider == "gemini" else OPENAI_VOICE_MODEL

    @property
    def voice_thinking(self) -> str | None:
        """Only the extended-thinking model accepts a thinking level."""
        return self.get("VOICE_THINKING") if self.voice_model.endswith("-extended-thinking") else None

    @property
    def voice_name(self) -> str:
        return self.get("VOICE_NAME")

    @property
    def voice_api_key(self) -> str:
        return self.get("GEMINI_API_KEY" if self.voice_provider == "gemini" else "OPENAI_API_KEY")

    @property
    def voice_api_key_name(self) -> str:
        return "GEMINI_API_KEY" if self.voice_provider == "gemini" else "OPENAI_API_KEY"

    @property
    def claude_skills(self) -> tuple[str, ...]:
        return tuple(s.strip() for s in self.get("CLAUDE_SKILLS").split(",") if s.strip())

    @property
    def azure_speech_key(self) -> str:
        return self.get("AZURE_SPEECH_KEY")

    @property
    def azure_speech_region(self) -> str:
        return self.get("AZURE_SPEECH_REGION")

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
