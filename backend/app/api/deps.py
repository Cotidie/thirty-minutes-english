"""What the routes read off the app: the database, the current services, and the settings."""

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, Request

from app.config.settings import Settings
from app.db import Database
from app.generation.jobs import JobRunner
from app.topics.daily import DailyTopics
from app.wiring import Services

Rebuild = Callable[[Settings], Services]


def _db(request: Request) -> Database:
    return request.app.state.db


def _services(request: Request) -> Services:
    return request.app.state.services


def _jobs(request: Request) -> JobRunner:
    return request.app.state.jobs


def _topics(request: Request) -> DailyTopics:
    return request.app.state.topics


def _settings(request: Request) -> Settings:
    return Settings(request.app.state.env, request.app.state.db.settings.load())


Db = Annotated[Database, Depends(_db)]
Svc = Annotated[Services, Depends(_services)]
Jobs = Annotated[JobRunner, Depends(_jobs)]
Topics = Annotated[DailyTopics, Depends(_topics)]
CurrentSettings = Annotated[Settings, Depends(_settings)]


def require_session(db: Database, session_id: int | None) -> None:
    """404 unless `session_id` is None or names a stored session."""
    if session_id is not None and not db.sessions.exists(session_id):
        raise HTTPException(status_code=404, detail="session not found")


def off(detail: str) -> HTTPException:
    """A feature whose key, provider or agent folder is missing."""
    return HTTPException(status_code=503, detail=detail)


def failed(what: str, error: Exception) -> HTTPException:
    return HTTPException(status_code=502, detail=f"{what} failed: {getattr(error, 'message', error)}")
