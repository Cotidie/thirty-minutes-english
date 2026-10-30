import logging
import os
from collections.abc import Mapping
from pathlib import Path

from fastapi import Depends, FastAPI

from app.accounts.admin import ensure_admin_from
from app.accounts.limits import FailedLogins, SignupLimit
from app.api import ROUTERS
from app.api.auth import public_router
from app.api.presence import router as presence_router
from app.api.deps import Rebuild, signed_in
from app.config.catalog import Catalog
from app.config.settings import Settings
from app.db import Database
from app.generation.jobs import Executor, JobRunner
from app.live.presence import Rooms
from app.pictures.figures import SourceImages
from app.pictures.files import PictureFiles
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
    app.state.files = PictureFiles(image_dir or db.images_dir)
    app.state.services = services
    app.state.env = os.environ if env is None else env
    app.state.rebuild = rebuild
    app.state.catalog = catalog or Catalog(db.caches, fetchers={})
    app.state.jobs = JobRunner(db.sessions, db.expressions, db.stages, executor, SourceImages(db.pictures, app.state.files))
    app.state.topics = DailyTopics(db.topics, app.state.jobs.executor)
    app.state.failed_logins = FailedLogins()
    app.state.signups = SignupLimit()
    app.state.presence = Rooms()
    app.include_router(public_router)
    app.include_router(presence_router)
    for router in ROUTERS:
        app.include_router(router, dependencies=[Depends(signed_in)])
    return app


def default_app() -> FastAPI:
    """The app over the real data folder; uvicorn calls it (--factory), so importing this module opens nothing."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    db = Database(os.environ.get("DB_PATH", ROOT / "data" / "sessions.db"))
    ensure_admin_from(db, os.environ)
    dirs = agent_dirs(os.environ, ROOT.parent / "agents")
    image_dir = db.images_dir
    catalog = Catalog(db.caches)

    def rebuild(settings: Settings) -> Services:
        return build_services(settings, dirs, db.pictures, PictureFiles(image_dir), catalog.efforts_of, db.path.parent / "speech")

    return create_app(
        db,
        rebuild(Settings(os.environ, db.settings.load())),
        rebuild=rebuild,
        image_dir=image_dir,
        catalog=catalog,
    )

