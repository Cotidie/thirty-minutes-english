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
from app.config.settings import GROUPS, SPECS, InvalidSetting, Settings

router = APIRouter(prefix="/api/settings")


def view(settings: Settings) -> SettingsView:
    fields = [
        SettingField(
            key=spec.key,
            group=spec.group,
            value=settings.shown(spec.key),
            secret=spec.secret,
            default=spec.default,
            choices=list(spec.choices) if spec.choices else None,
            suggestions=list(spec.suggestions),
            labels=dict(spec.labels or {}),
            testable=spec.key in KEYS,
            follows=spec.follows,
            variants={value: Variant(default=v.default, suggestions=list(v.suggestions)) for value, v in (spec.variants or {}).items()},
            shown_when=spec.shown_when,
            used_when=spec.used_when,
            help=spec.help,
        )
        for spec in SPECS
    ]
    return SettingsView(groups=[SettingGroup(id=g, title=title) for g, title in GROUPS.items()], fields=fields)


@router.get("", response_model=SettingsView)
def get_settings(settings: CurrentSettings) -> SettingsView:
    return view(settings)


@router.put("", response_model=SettingsView)
def put_settings(body: SettingsUpdate, db: Db, request: Request) -> SettingsView:
    """Saved, then the services are rebuilt so the next round uses them."""
    try:
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
