from fastapi import APIRouter, HTTPException, Request

from app.api.deps import CurrentSettings, Db, Rebuild
from app.api.schemas import (
    KeyTestRequest,
    KeyTestResult,
    SettingField,
    SettingGroup,
    SettingsUpdate,
    SettingsView,
    Variant,
)
from app.config.keycheck import KEYS, check_key
from app.config.settings import GROUPS, SPECS, InvalidSetting, Settings, Spec, split_list
from app.config.skills import host_skills

router = APIRouter(prefix="/api/settings")


def skill_choices(saved: str) -> dict[str, str]:
    """Host skills with their descriptions, plus any saved one this machine no longer has."""
    skills = host_skills()
    missing = {name: "Not found in ~/.claude/skills; it is skipped." for name in split_list(saved) if name not in skills}
    return {**skills, **missing}


def field_of(spec: Spec, settings: Settings) -> SettingField:
    choices, labels = (spec.choices, spec.labels or {})
    if spec.multi:
        labels = skill_choices(settings.get(spec.key))
        choices = tuple(labels)
    return SettingField(
        key=spec.key,
        group=spec.group,
        value=settings.shown(spec.key),
        secret=spec.secret,
        default=spec.default,
        choices=list(choices) if choices is not None else None,
        suggestions=list(spec.suggestions),
        labels=dict(labels),
        testable=spec.key in KEYS,
        follows=spec.follows,
        variants={value: Variant(default=v.default, suggestions=list(v.suggestions)) for value, v in (spec.variants or {}).items()},
        shown_when=spec.shown_when,
        used_when=spec.used_when,
        help=spec.help,
        multi=spec.multi,
    )


def view(settings: Settings) -> SettingsView:
    fields = [field_of(spec, settings) for spec in SPECS]
    return SettingsView(groups=[SettingGroup(id=g, title=title) for g, title in GROUPS.items()], fields=fields)


def check_multi(values: dict[str, str]) -> None:
    """A ticked skill has to exist on this machine; the SDK refuses unknown names at connect."""
    known = host_skills()
    for spec in SPECS:
        if spec.multi and spec.key in values:
            unknown = [name for name in split_list(values[spec.key]) if name not in known]
            if unknown:
                raise InvalidSetting(f"{spec.key}: no such skill in ~/.claude/skills: {', '.join(unknown)}")


@router.get("", response_model=SettingsView)
def get_settings(settings: CurrentSettings) -> SettingsView:
    return view(settings)


@router.put("", response_model=SettingsView)
def put_settings(body: SettingsUpdate, db: Db, request: Request) -> SettingsView:
    """Saved, then the services are rebuilt so the next round uses them."""
    try:
        check_multi(body.values)
        db.settings.save(body.values)
    except InvalidSetting as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    settings = Settings(request.app.state.env, db.settings.load())
    rebuild: Rebuild | None = request.app.state.rebuild
    if rebuild is not None:
        request.app.state.services = rebuild(settings)
    return view(settings)


@router.post("/test-key", response_model=KeyTestResult)
def test_key(body: KeyTestRequest, settings: CurrentSettings) -> KeyTestResult:
    """`value` is what is typed in the modal; blank tries the saved key."""
    if body.key not in KEYS:
        raise HTTPException(status_code=422, detail=f"{body.key} has no key check")
    key = body.value.strip() or settings.get(body.key)
    result = check_key(body.key, key, region=settings.get("AZURE_SPEECH_REGION"))
    return KeyTestResult(ok=result.ok, message=result.message)
