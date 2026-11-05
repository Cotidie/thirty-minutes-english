"""What an account has to spend, as the account itself reads it, what its browser reports on a round it opened, and
credits it hands to someone else."""

from fastapi import APIRouter, HTTPException, Response

from app.api.deps import Db, Me, short_of_credits
from app.api.schemas import CreditsView, GiftRequest
from app.credits import PRICES, REPORT_WINDOW
from app.db import Database
from app.db.credits import NotEnoughCredits
from app.models import User

router = APIRouter(prefix="/api/me")


@router.get("/credits", response_model=CreditsView)
def my_credits(db: Db, me: Me) -> CreditsView:
    if me.is_admin:
        return CreditsView(balance=None, prices=PRICES, recent=[])
    return CreditsView(balance=db.credits.balance(me.id), prices=PRICES, recent=db.credits.recent(me.id))


@router.post("/credits/holds/{hold}/confirm", status_code=204)
def confirm_hold(hold: int, db: Db, me: Me) -> Response:
    """The round connected, so its price stays."""
    if not db.credits.confirm(hold, me.id, REPORT_WINDOW):
        raise HTTPException(status_code=404, detail="hold not found")
    return Response(status_code=204)


@router.delete("/credits/holds/{hold}", status_code=204)
def give_back_hold(hold: int, db: Db, me: Me) -> Response:
    """The round did not deliver, so its price comes back."""
    if not db.credits.give_back(hold, me.id):
        raise HTTPException(status_code=404, detail="hold not found")
    return Response(status_code=204)


@router.post("/credits/gifts", status_code=204)
def gift_credits(body: GiftRequest, db: Db, me: Me) -> Response:
    """Hands some of my credits to another account; both see it when their credits are read again."""
    recipient = _recipient_for(db, me, body.to)
    try:
        db.credits.gift(me, recipient, body.amount)
    except NotEnoughCredits as e:
        raise short_of_credits(e) from None
    return Response(status_code=204)


def _recipient_for(db: Database, me: User, to: int) -> User:
    """The account `me` may gift to, or the HTTP error that says why not. Only accounts that pay for things give or take."""
    if me.is_admin:
        raise HTTPException(status_code=400, detail="The admin has no credits to give.")
    recipient = db.accounts.get(to)
    if recipient is None:
        raise HTTPException(status_code=404, detail="account not found")
    if recipient.id == me.id:
        raise HTTPException(status_code=400, detail="You cannot gift credits to yourself.")
    if recipient.is_admin:
        raise HTTPException(status_code=400, detail="The admin is not charged, so there is nothing to add to.")
    return recipient
