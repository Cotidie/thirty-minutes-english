"""What an account has to spend, as the account itself reads it, and what its browser reports on a round it opened."""

from fastapi import APIRouter, HTTPException, Response

from app.api.deps import Db, Me
from app.api.schemas import CreditsView
from app.credits import PRICES, REPORT_WINDOW

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
