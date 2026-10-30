"""The event streams: one while a session is open, one while an account's list of sessions is. Each says what to read
again over REST, and never carries data."""

from collections.abc import AsyncIterator, Awaitable, Callable

from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse

from app.api.deps import LOGIN_COOKIE, Db, Me, require_access
from app.live.changes import Changes, SessionChange, Subscription

router = APIRouter(prefix="/api")

HEARTBEAT_S = 25.0  # well inside what proxies allow an idle connection, and often enough for a browser to notice silence
RETRY_MS = 5000


def _event(name: str) -> str:
    return f"event: {name}\ndata: {{}}\n\n"


async def events_of(
    subscription: Subscription, still_allowed: Callable[[], Awaitable[bool]], heartbeat_s: float = HEARTBEAT_S
) -> AsyncIterator[str]:
    """Each wake-up checks the login and the session again, so who has lost access is decided in one place."""
    yield f"retry: {RETRY_MS}\n\n"
    while True:
        changed = await subscription.next(heartbeat_s)
        if not await still_allowed():
            yield _event("gone")
            return
        if not changed:
            yield _event("alive")  # an event, not a comment: a browser's EventSource never shows it a comment
        for change in sorted(changed - {SessionChange.ACCESS}):
            yield _event(change)


def _streaming(changes: Changes, key: int, allowed: Callable[[], bool]) -> StreamingResponse:
    async def still_allowed() -> bool:
        return await run_in_threadpool(allowed)

    async def stream() -> AsyncIterator[str]:
        subscription = changes.subscribe(key)
        try:
            async for chunk in events_of(subscription, still_allowed):
                yield chunk
        finally:
            subscription.close()

    return StreamingResponse(
        stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )


@router.get("/sessions/{session_id}/events")
async def session_events(session_id: int, request: Request, db: Db, me: Me) -> StreamingResponse:
    await run_in_threadpool(require_access, db, me, session_id)
    token = request.cookies.get(LOGIN_COOKIE, "")

    def allowed() -> bool:
        user = db.accounts.user_of_login(token)
        return user is not None and db.shares.can_access(user, session_id)

    return _streaming(db.changes, session_id, allowed)


@router.get("/me/events")
async def account_events(request: Request, db: Db, me: Me) -> StreamingResponse:
    """Open to any login, and only ever about that account: it goes when the login does."""
    token = request.cookies.get(LOGIN_COOKIE, "")

    def allowed() -> bool:
        return db.accounts.user_of_login(token) is not None

    return _streaming(db.account_changes, me.id, allowed)
