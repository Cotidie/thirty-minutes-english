"""Request and response bodies of the HTTP API; the domain models live in app.models."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

from app.generation.jobs import Status
from app.generation.progress import Stage
from app.models import Correction


class CreateSessionRequest(BaseModel):
    topic: str | None = None


class JobStatus(BaseModel):
    id: str
    topic: str
    status: Status
    stage: Stage
    searches: int
    activity: str
    input_tokens: int
    output_tokens: int
    pictures_done: int
    pictures_total: int
    elapsed_seconds: float
    stage_elapsed_seconds: float
    stage_expected_seconds: float
    expected_seconds: float
    session_id: int | None = None
    error: str | None = None


def _not_blank(value: str) -> str:
    if not value.strip():
        raise ValueError("must not be blank")
    return value


class ReadAloudRequest(BaseModel):
    """`sdp` is the browser's WebRTC offer; only the OpenAI provider needs one."""

    paragraph: str
    sdp: str | None = None

    _check = field_validator("paragraph")(_not_blank)


class PhraseRequest(BaseModel):
    sdp: str | None = None
    topic: str | None = None


class ExampleSessionRequest(BaseModel):
    sdp: str | None = None
    expression: str
    meaning: str
    usage_note: str = ""

    _check = field_validator("expression", "meaning")(_not_blank)


class ExampleFeedbackRequest(BaseModel):
    """One sentence a reader made with a target, for the coach to say back and judge."""

    expression: str
    meaning: str
    usage_note: str = ""
    user_text: str
    """An expression gets the light native fix; a word gets a free rewording that uses it well."""
    kind: Literal["expression", "word"] = "expression"
    """For a word: the picture's scene, so the rewording can describe it."""
    scene: str = ""

    _check = field_validator("expression", "meaning", "user_text")(_not_blank)


class ExampleRequest(BaseModel):
    session_id: int
    expression: str
    user_text: str
    coach_text: str
    seconds: float = 0

    _check = field_validator("expression", "user_text", "coach_text")(_not_blank)


class AskRequest(BaseModel):
    session_id: int | None = None
    user_text: str
    coach_text: str
    seconds: float = 0

    _check = field_validator("user_text", "coach_text")(_not_blank)


class ReadingRequest(BaseModel):
    session_id: int | None = None
    paragraph: str
    user_text: str
    coach_text: str
    seconds: float = 0
    corrections: list[Correction] = []

    _check = field_validator("paragraph")(_not_blank)


class PhrasingRequest(BaseModel):
    paragraph: str

    _check = field_validator("paragraph")(_not_blank)


class RedrawRequest(BaseModel):
    """Which style to draw this one picture in; blank means the configured IMAGE_STYLE."""

    style: str = ""


class Phrasing(BaseModel):
    """Indices of the words a fluent reader starts a new thought group on."""

    breaks: list[int]


class LiveSession(BaseModel):
    """Passthrough of the provider's answer, tagged with `provider`. OpenAI:
    {session: {id}, transport: {type, sdp}}. Gemini: {url, setup}."""

    model_config = ConfigDict(extra="allow")

    provider: Literal["openai", "gemini"]


class AssessorSession(BaseModel):
    """What the browser needs to stream the microphone to Azure and judge the result."""

    token: str
    region: str
    word_score: int
    break_confidence: float


class Variant(BaseModel):
    default: str
    suggestions: list[str]


class SettingField(BaseModel):
    """One setting as the modal draws it. Every rule the modal applies comes from here."""

    key: str
    group: str
    value: str
    secret: bool
    default: str
    choices: list[str] | None
    suggestions: list[str]
    labels: dict[str, str] = {}
    testable: bool = False  # a Test button checks the key
    follows: str | None = None  # the setting whose value picks one of `variants`
    variants: dict[str, Variant] = {}
    shown_when: tuple[str, str] | None = None  # (key, value): hidden otherwise
    used_when: tuple[str, str] | None = None  # (key, value): the key sits idle otherwise
    help: str = ""  # what the setting does, for the info tooltip
    multi: bool = False  # `choices` are ticked, not picked; the value is a comma list


class SettingGroup(BaseModel):
    id: str
    title: str


class SettingsView(BaseModel):
    groups: list[SettingGroup]
    fields: list[SettingField]


class SettingsUpdate(BaseModel):
    values: dict[str, str]


class KeyTestRequest(BaseModel):
    """Which key to try. `value` is what is typed in the modal; blank means the saved key."""

    key: str
    value: str = ""


class KeyTestResult(BaseModel):
    ok: bool
    message: str
