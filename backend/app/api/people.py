"""Other accounts as anyone logged in may know them: by username, to find someone to share a session with. And one's
own username, which others see."""

from fastapi import APIRouter, HTTPException

from app.accounts.usernames import RULE, is_username, normalize_username
from app.api.deps import Db, Me
from app.api.schemas import PersonMatch, UsernameRequest
from app.db.accounts import UsernameTaken
from app.models import User

router = APIRouter(prefix="/api")

NAME_TAKEN = "Someone already goes by that name."


def chosen_username(typed: str) -> str:
    """The name as it is kept, or a 400 saying the rule it breaks."""
    name = normalize_username(typed)
    if not is_username(name):
        raise HTTPException(status_code=400, detail=RULE)
    return name


@router.get("/users", response_model=list[PersonMatch])
def find_people(q: str, db: Db, me: Me) -> list[PersonMatch]:
    """Whoever's name holds `q`, apart from me."""
    return [PersonMatch(id=user.id, username=user.username) for user in db.accounts.search(q, excluding=me.id)]


@router.put("/me/username", response_model=User)
def rename_me(body: UsernameRequest, db: Db, me: Me) -> User:
    name = chosen_username(body.username)
    try:
        return db.accounts.set_username(me.id, name)
    except UsernameTaken:
        raise HTTPException(status_code=409, detail=NAME_TAKEN) from None
