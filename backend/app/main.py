import logging
import os
from collections.abc import Mapping
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api import ROUTERS
from app.api.deps import Rebuild
from app.config.settings import Settings
from app.db import Database
from app.generation.jobs import Executor, JobRunner
from app.topics.daily import DailyTopics
from app.wiring import Services, build_services

ROOT = Path(__file__).resolve().parent.parent
AGENT_DIRS = {
    "read-aloud": ("READ_ALOUD_AGENT_DIR", ROOT.parent.parent / "read-aloud-coach"),
    "phrase": ("PHRASE_AGENT_DIR", ROOT.parent.parent / "phrase-coach"),
    "example": ("EXAMPLE_AGENT_DIR", ROOT.parent.parent / "example-coach"),
}


def create_app(
    db: Database,
    services: Services,
    executor: Executor | None = None,
    rebuild: Rebuild | None = None,
    env: Mapping[str, str] | None = None,
    image_dir: Path | None = None,
) -> FastAPI:
    """`rebuild` turns saved settings into fresh services; without it a settings
    change is stored but the running services stay as they are (tests)."""
    app = FastAPI(title="english-speaking-claude")
    app.state.db = db
    app.state.services = services
    app.state.env = os.environ if env is None else env
    app.state.rebuild = rebuild
    app.state.jobs = JobRunner(db.sessions, executor)
    app.state.topics = DailyTopics(db.caches, app.state.jobs.executor)
    for router in ROUTERS:
        app.include_router(router)
    if image_dir is not None:
        image_dir.mkdir(parents=True, exist_ok=True)
        app.mount("/api/images", StaticFiles(directory=image_dir), name="images")
    return app


def default_app() -> FastAPI:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    db = Database(os.environ.get("DB_PATH", ROOT / "data" / "sessions.db"))
    dirs = {name: Path(os.environ.get(var, default)) for name, (var, default) in AGENT_DIRS.items()}
    image_dir = db.path.parent / "images"

    def rebuild(settings: Settings) -> Services:
        return build_services(settings, dirs, image_dir)

    return create_app(
        db,
        rebuild(Settings(os.environ, db.settings.load())),
        rebuild=rebuild,
        image_dir=image_dir,
    )


app = default_app()
