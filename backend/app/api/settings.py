from dataclasses import asdict

from fastapi import APIRouter, HTTPException, Request

from app.api.deps import CurrentSettings, Db, Models, Rebuild
from app.api.schemas import (
    KeyTestRequest,
    KeyTestResult,
    Option,
    SettingField,
    SettingGroup,
    SettingsUpdate,
    SettingsView,
    Variant,
)
from app.config.catalog import Catalog
from app.config.keycheck import KEYS, check_key
from app.config.settings import GROUPS, SPEC_BY_KEY, SPECS, InvalidSetting, Settings, Spec, split_list
from app.config.skills import host_skills

router = APIRouter(prefix="/api/settings")


def keys_of(settings: Settings) -> dict[str, str]:
    """The API keys the model lists are fetched with."""
    return {spec.key: settings.get(spec.key) for spec in SPECS if spec.secret}


def listed(catalog: Catalog, source: str, settings: Settings, default: str) -> list[Option]:
    """A provider's models; the default first when the list lacks it (or is not fetched yet)."""
    options = [Option(**asdict(o)) for o in catalog.options(source, keys_of(settings))]
    if default and default not in {o.id for o in options}:
        options.insert(0, Option(id=default, description="Default"))
    return options


def skill_options(saved: str) -> list[Option]:
    """Host skills with their descriptions, plus any saved one this machine no longer has."""
    skills = host_skills()
    missing = [Option(id=n, description="Not found in ~/.claude/skills; it is skipped.") for n in split_list(saved) if n not in skills]
    return [Option(id=name, description=text) for name, text in skills.items()] + missing


def options_of(spec: Spec, settings: Settings, catalog: Catalog) -> list[Option]:
    if spec.multi:
        return skill_options(settings.get(spec.key))
    if spec.catalog:
        return listed(catalog, spec.catalog, settings, spec.default)
    labels = spec.labels or {}
    return [Option(id=c, description=labels.get(c, "")) for c in spec.choices or ()]


def field_of(spec: Spec, settings: Settings, catalog: Catalog) -> SettingField:
    return SettingField(
        key=spec.key,
        group=spec.group,
        value=settings.shown(spec.key),
        secret=spec.secret,
        default=spec.default,
        options=options_of(spec, settings, catalog),
        free=bool(spec.catalog or spec.variants),
        testable=spec.key in KEYS,
        follows=spec.follows,
        variants={
            value: Variant(default=v.default, options=listed(catalog, v.catalog, settings, v.default))
            for value, v in (spec.variants or {}).items()
        },
        effort_of=spec.effort_of,
        shown_when=spec.shown_when,
        used_when=spec.used_when,
        help=spec.help,
        multi=spec.multi,
    )


def view(settings: Settings, catalog: Catalog) -> SettingsView:
    return SettingsView(
        groups=[SettingGroup(id=g, title=title) for g, title in GROUPS.items()],
        fields=[field_of(spec, settings, catalog) for spec in SPECS],
    )


def check_multi(values: dict[str, str]) -> None:
    """A ticked skill has to exist on this machine; the SDK refuses unknown names at connect."""
    known = host_skills()
    for spec in SPECS:
        if spec.multi and spec.key in values:
            unknown = [name for name in split_list(values[spec.key]) if name not in known]
            if unknown:
                raise InvalidSetting(f"{spec.key}: no such skill in ~/.claude/skills: {', '.join(unknown)}")


@router.get("", response_model=SettingsView)
def get_settings(settings: CurrentSettings, catalog: Models) -> SettingsView:
    return view(settings, catalog)


@router.post("/models/refresh", response_model=SettingsView)
def refresh_models(settings: CurrentSettings, catalog: Models) -> SettingsView:
    """Fetches every model list now (the ↻ in the modal); a failed one keeps its last copy."""
    catalog.refresh(keys_of(settings))
    return view(settings, catalog)


@router.put("", response_model=SettingsView)
def put_settings(body: SettingsUpdate, db: Db, catalog: Models, request: Request) -> SettingsView:
    """Saved, then the services are rebuilt so the next round uses them."""
    try:
        check_multi(body.values)
        db.settings.save(body.values)
    except InvalidSetting as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    settings = Settings(request.app.state.env, db.settings.load())
    if any(SPEC_BY_KEY[k].secret for k in body.values):
        catalog.refresh_later(keys_of(settings))  # a new key may unlock a provider's list
    rebuild: Rebuild | None = request.app.state.rebuild
    if rebuild is not None:
        request.app.state.services = rebuild(settings)
    return view(settings, catalog)


@router.post("/test-key", response_model=KeyTestResult)
def test_key(body: KeyTestRequest, settings: CurrentSettings) -> KeyTestResult:
    """`value` is what is typed in the modal; blank tries the saved key."""
    if body.key not in KEYS:
        raise HTTPException(status_code=422, detail=f"{body.key} has no key check")
    key = body.value.strip() or settings.get(body.key)
    result = check_key(body.key, key, region=settings.get("AZURE_SPEECH_REGION"))
    return KeyTestResult(ok=result.ok, message=result.message)
