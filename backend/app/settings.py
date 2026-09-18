"""Runtime settings. Every value has an environment default; the settings
modal writes overrides into a SQLite table, and the app rebuilds its services
from the merged result without a restart. Infra values that need a restart
(DB path, agent folders, ports, the Claude OAuth token) stay out of here."""

import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

Group = Literal["voice", "claude", "text"]
Source = Literal["env", "db", "default"]

EFFORTS = ("low", "medium", "high", "xhigh", "max")
CLAUDE_MODELS = ("opus", "sonnet")
OPENAI_VOICE_MODEL = "gpt-live-1"
GEMINI_VOICE_MODEL = "gemini-3.8-live-extended-thinking"
GEMINI_VOICE_MODELS = ("gemini-3.8-live", GEMINI_VOICE_MODEL)
THINKING_LEVELS = ("low", "medium", "high")


@dataclass(frozen=True)
class Spec:
    key: str
    group: Group
    default: str = ""
    secret: bool = False
    choices: tuple[str, ...] | None = None  # strict: a value outside is rejected
    suggestions: tuple[str, ...] = ()  # free text with a menu of common values


SPECS: tuple[Spec, ...] = (
    Spec("VOICE_PROVIDER", "voice", "openai", choices=("openai", "gemini")),
    Spec("VOICE_MODEL", "voice", suggestions=(OPENAI_VOICE_MODEL, *GEMINI_VOICE_MODELS)),
    Spec("VOICE_THINKING", "voice", "low", choices=THINKING_LEVELS),
    Spec("VOICE_NAME", "voice", "Kore"),
    Spec("OPENAI_API_KEY", "voice", secret=True),
    Spec("GEMINI_API_KEY", "voice", secret=True),
    Spec("CLAUDE_MODEL", "claude", "opus", suggestions=CLAUDE_MODELS),
    Spec("CLAUDE_EFFORT", "claude", "xhigh", choices=EFFORTS),
    Spec("CLAUDE_SKILLS", "claude"),
    Spec("TOPICS_MODEL", "claude", "sonnet", suggestions=CLAUDE_MODELS),
    Spec("TOPICS_EFFORT", "claude", "medium", choices=EFFORTS),
    Spec("EXAMPLE_MODEL", "claude", "opus", suggestions=CLAUDE_MODELS),
    Spec("EXAMPLE_EFFORT", "claude", "low", choices=EFFORTS),
    Spec("SUMMARY_MODEL", "text", "gpt-5.6-luna"),
)
SPEC_BY_KEY = {spec.key: spec for spec in SPECS}


class InvalidSetting(ValueError):
    pass


def validate(values: Mapping[str, str | None]) -> None:
    """Rejects unknown keys and values outside a strict choice list. None clears an override."""
    for key, value in values.items():
        spec = SPEC_BY_KEY.get(key)
        if spec is None:
            raise InvalidSetting(f"unknown setting {key}")
        if value is not None and spec.choices and value not in spec.choices:
            raise InvalidSetting(f"{key} must be one of {', '.join(spec.choices)}")


class SettingsStore:
    """The overrides table. Same file as the sessions, its own table."""

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

    def save(self, values: Mapping[str, str | None]) -> None:
        """Writes each value; None removes the override so the env default shows through."""
        validate(values)
        with self._connect() as conn:
            for key, value in values.items():
                if value is None:
                    conn.execute("DELETE FROM settings WHERE key = ?", (key,))
                else:
                    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))


@dataclass(frozen=True)
class Field:
    """One setting as the modal sees it: the effective value (secrets masked) and where it came from."""

    key: str
    group: Group
    value: str
    source: Source
    secret: bool
    default: str
    choices: tuple[str, ...] | None
    suggestions: tuple[str, ...]


class Settings:
    """Env defaults under DB overrides. Blank env values count as unset."""

    def __init__(self, env: Mapping[str, str], overrides: Mapping[str, str]) -> None:
        self._env = {k: v.strip() for k, v in env.items() if k in SPEC_BY_KEY}
        self._overrides = dict(overrides)

    @classmethod
    def resolve(cls, env: Mapping[str, str], store: SettingsStore) -> "Settings":
        return cls(env, store.load())

    def source(self, key: str) -> Source:
        if key in self._overrides:
            return "db"
        if self._env.get(key):
            return "env"
        return "default"

    def get(self, key: str) -> str:
        spec = SPEC_BY_KEY[key]
        if key in self._overrides:
            return self._overrides[key]
        return self._env.get(key) or spec.default

    def fields(self) -> list[Field]:
        return [
            Field(
                key=spec.key,
                group=spec.group,
                value=mask(self.get(spec.key)) if spec.secret else self.get(spec.key),
                source=self.source(spec.key),
                secret=spec.secret,
                default=spec.default,
                choices=spec.choices,
                suggestions=spec.suggestions,
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


def mask(secret: str) -> str:
    """Enough to recognise a key, never enough to use it."""
    if not secret:
        return ""
    return f"…{secret[-4:]}" if len(secret) > 8 else "…"
