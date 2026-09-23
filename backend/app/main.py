import logging
import os
from collections.abc import Mapping
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api import ROUTERS
from app.api.deps import Rebuild
from app.config.catalog import Catalog
from app.config.settings import Settings
from app.db import Database
from app.generation.jobs import Executor, JobRunner
from app.topics.daily import DailyTopics
from app.wiring import Services, agent_dirs, build_services

ROOT = Path(__file__).resolve().parent.parent


def create_app(
    db: Database,
    services: Services,
    executor: Executor | None = None,
    rebuild: Rebuild | None = None,
    env: Mapping[str, str] | None = None,
    image_dir: Path | None = None,
    catalog: Catalog | None = None,
) -> FastAPI:
    """`rebuild` turns saved settings into fresh services; without it a settings
    change is stored but the running services stay as they are (tests). Without a
    `catalog` the model lists are whatever the database holds, never fetched."""
    app = FastAPI(title="english-speaking-claude")
    app.state.db = db
    app.state.services = services
    app.state.env = os.environ if env is None else env
    app.state.rebuild = rebuild
    app.state.catalog = catalog or Catalog(db.caches, fetchers={})
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
    dirs = agent_dirs(os.environ, ROOT.parent.parent)
    image_dir = db.path.parent / "images"
    catalog = Catalog(db.caches)

    def rebuild(settings: Settings) -> Services:
        return build_services(settings, dirs, image_dir, catalog.efforts_of)

    return create_app(
        db,
        rebuild(Settings(os.environ, db.settings.load())),
        rebuild=rebuild,
        image_dir=image_dir,
        catalog=catalog,
    )


app = default_app()
