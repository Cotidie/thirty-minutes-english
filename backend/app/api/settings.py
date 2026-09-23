from fastapi import APIRouter, HTTPException, Request

from app.api.deps import CurrentSettings, Db, Rebuild
from app.api.schemas import (
    KeyTestRequest,
    KeyTestResult,
    SettingField,
    SettingsUpdate,
    SettingsView,
)
from app.config.keycheck import check_key
from app.config.settings import InvalidSetting, Settings

router = APIRouter(prefix="/api/settings")


def view(settings: Settings) -> SettingsView:
    return SettingsView(fields=[SettingField(**vars(f)) for f in settings.fields()])


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
    key = body.value.strip() or settings.get(body.key)
    result = check_key(body.key, key, region=settings.get("AZURE_SPEECH_REGION"))
    return KeyTestResult(ok=result.ok, message=result.message)
