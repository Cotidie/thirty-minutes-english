"""What the routes read off the app: the database, the current services, the settings, and who is asking."""

import logging
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Annotated

from fastapi import Depends, HTTPException, Request

from app.config.catalog import Catalog
from app.config.settings import Settings
from app.credits import CONFIRM_WINDOW
from app.db import Database
from app.db.credits import NotEnoughCredits
from app.generation.jobs import JobRunner
from app.models import User
from app.pictures.files import PictureFiles
from app.topics.daily import DailyTopics
from app.wiring import Services

log = logging.getLogger(__name__)

Rebuild = Callable[[Settings], Services]

LOGIN_COOKIE = "login"


def _db(request: Request) -> Database:
    return request.app.state.db


def _services(request: Request) -> Services:
    return request.app.state.services


def _jobs(request: Request) -> JobRunner:
    return request.app.state.jobs


def _topics(request: Request) -> DailyTopics:
    return request.app.state.topics


def _catalog(request: Request) -> Catalog:
    return request.app.state.catalog


def _files(request: Request) -> PictureFiles:
    return request.app.state.files


def _settings(request: Request) -> Settings:
    return Settings(request.app.state.env, request.app.state.db.settings.load())


Db = Annotated[Database, Depends(_db)]
Svc = Annotated[Services, Depends(_services)]
Jobs = Annotated[JobRunner, Depends(_jobs)]
Topics = Annotated[DailyTopics, Depends(_topics)]
CurrentSettings = Annotated[Settings, Depends(_settings)]
Models = Annotated[Catalog, Depends(_catalog)]
Files = Annotated[PictureFiles, Depends(_files)]


def signed_in(request: Request) -> User:
    """The logged-in account; every route but signing up and logging in depends on this."""
    user = request.app.state.db.accounts.user_of_login(request.cookies.get(LOGIN_COOKIE, ""))
    if user is None:
        raise HTTPException(status_code=401, detail="Log in first.")
    return user


Me = Annotated[User, Depends(signed_in)]


def admin_only(me: Me) -> User:
    if not me.is_admin:
        raise HTTPException(status_code=403, detail="Only the admin can do this.")
    return me


def require_access(db: Database, me: User, session_id: int) -> None:
    """404 unless `me` may open the session, so a session's number says nothing about whether it exists."""
    if not db.shares.can_access(me, session_id):
        raise HTTPException(status_code=404, detail="session not found")


def require_creator(db: Database, me: User, session_id: int) -> None:
    """404 as `require_access`; 403 for someone who can open the session but did not make it."""
    require_access(db, me, session_id)
    if db.shares.created_by(session_id) != me.id:
        raise HTTPException(status_code=403, detail="Only who made this session can do this.")


def require_paragraph(db: Database, me: User, paragraph_id: int) -> None:
    """404 unless `paragraph_id` names a paragraph of a session `me` may open."""
    session_id = db.sessions.session_of_paragraph(paragraph_id)
    if session_id is None or not db.shares.can_access(me, session_id):
        raise HTTPException(status_code=404, detail="paragraph not found")


def held_or_402(db: Database, me: User, kind: str, detail: str | None = None) -> int | None:
    """The last check of a paid route: the price is held, or 402 says what it needs and what there is."""
    try:
        return db.credits.hold(me, kind, detail)
    except NotEnoughCredits as e:
        raise HTTPException(status_code=402, detail=f"Not enough credits: this needs {e.need} and you have {e.have}.") from None


@contextmanager
def paid(db: Database, me: User, kind: str, detail: str | None = None) -> Iterator[None]:
    """The block's work is paid for only if it ends normally; any exception gives the price back.
    A failure of the ledger itself is logged, not raised: the row goes back when the app next starts."""
    hold = held_or_402(db, me, kind, detail)
    try:
        yield
    except BaseException:
        _quietly(db.credits.release, hold)
        raise
    _quietly(db.credits.settle, hold)


def browser_round(db: Database, me: User, kind: str, detail: str | None, start: Callable[[], dict]) -> dict:
    """A round the browser opens by itself: the price stays held until it says the round connected."""
    hold = held_or_402(db, me, kind, detail)
    try:
        session = start()
        db.credits.await_browser(hold, CONFIRM_WINDOW)
    except BaseException:
        _quietly(db.credits.release, hold)
        raise
    return {**session, "hold": hold}


def _quietly(step: Callable[[int | None], None], hold: int | None) -> None:
    try:
        step(hold)
    except sqlite3.Error:
        log.exception("could not finish credit hold %s", hold)


def off(detail: str) -> HTTPException:
    """A feature whose key, provider or agent folder is missing."""
    return HTTPException(status_code=503, detail=detail)


def failed(what: str, error: Exception) -> HTTPException:
    return HTTPException(status_code=502, detail=f"{what} failed: {getattr(error, 'message', error)}")
