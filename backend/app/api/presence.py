"""The presence socket: who is in a session and what is on their screens, for as long as they have it open. It sits
outside the routes that depend on `signed_in`, which takes a Request, and checks the login itself. A browser sends the
login cookie on a socket whatever page opens it, so the Origin is checked first."""

import asyncio
import logging
from urllib.parse import urlsplit

from fastapi import APIRouter, WebSocket
from fastapi.concurrency import run_in_threadpool
from starlette.datastructures import Headers
from starlette.websockets import WebSocketDisconnect

from app.api.deps import LOGIN_COOKIE
from app.api.events import may_open
from app.db import Database
from app.live.changes import Subscription
from app.live.presence import Member, Room, color_order
from app.models import User

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

RECHECK_S = 25.0
CLOSE_NO_LOGIN = 4401
CLOSE_OTHER_ORIGIN = 4403
CLOSE_NO_ACCESS = 4404
CLOSE_START_OVER = 1013  # reading too slowly or writing too fast: the browser reconnects from a fresh welcome


def _same_origin(headers: Headers) -> bool:
    """A page has an Origin; a client without one is no browser, and the login is all that stands in its way."""
    origin = headers.get("origin")
    return origin is None or urlsplit(origin).netloc == headers.get("host")


def _color_of(db: Database, session_id: int, user_id: int) -> int:
    shared_ids = [user.id for user in db.shares.shared_with(session_id)]
    return color_order(db.shares.created_by(session_id), shared_ids, user_id)


async def _send_what_waits(websocket: WebSocket, member: Member) -> None:
    while True:
        await member.outbox.wait()
        if member.outbox.overflowed:
            await websocket.close(code=CLOSE_START_OVER)
            return
        for message in member.outbox.take():
            await websocket.send_json(message)


async def _read_frames(websocket: WebSocket, room: Room, member: Member) -> None:
    while True:
        message = await websocket.receive()
        if message["type"] == "websocket.disconnect":
            return
        if text := message.get("text"):
            room.handle(member, text)


async def _watch_access(websocket: WebSocket, db: Database, token: str, session_id: int, subscription: Subscription) -> None:
    while True:
        await subscription.next(RECHECK_S)
        if not await run_in_threadpool(may_open, db, token, session_id):
            await websocket.close(code=CLOSE_NO_ACCESS)
            return


async def _run_until_one_ends(*jobs) -> None:
    tasks = [asyncio.create_task(job) for job in jobs]
    _, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    for task in pending:
        task.cancel()
    for result in await asyncio.gather(*tasks, return_exceptions=True):
        if isinstance(result, Exception) and not isinstance(result, WebSocketDisconnect):
            log.warning("a presence connection ended on %r", result)


async def _take_part(websocket: WebSocket, db: Database, token: str, session_id: int, user: User) -> None:
    rooms = websocket.app.state.presence
    subscription = db.changes.subscribe(session_id)
    color = await run_in_threadpool(_color_of, db, session_id, user.id)
    room, member = rooms.join(session_id, user.id, color)
    try:
        await websocket.send_json(room.welcome(member))
        await _run_until_one_ends(
            _send_what_waits(websocket, member),
            _read_frames(websocket, room, member),
            _watch_access(websocket, db, token, session_id, subscription),
        )
    finally:
        rooms.leave(session_id, member)
        subscription.close()


@router.websocket("/sessions/{session_id}/presence")
async def presence(websocket: WebSocket, session_id: int) -> None:
    """Accepted before any check, with nothing sent, so a browser can read why it was closed and stop trying: all a refused
    handshake tells it is 1006, which it would retry for as long as the page stays open."""
    await websocket.accept()
    if not _same_origin(websocket.headers):
        await websocket.close(code=CLOSE_OTHER_ORIGIN)
        return
    db = websocket.app.state.db
    token = websocket.cookies.get(LOGIN_COOKIE, "")
    user = await run_in_threadpool(db.accounts.user_of_login, token)
    if user is None:
        await websocket.close(code=CLOSE_NO_LOGIN)
    elif not await run_in_threadpool(db.shares.can_access, user, session_id):
        await websocket.close(code=CLOSE_NO_ACCESS)
    else:
        await _take_part(websocket, db, token, session_id, user)
