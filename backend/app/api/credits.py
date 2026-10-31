from fastapi import APIRouter

from app.api.deps import Db, Me
from app.api.schemas import CreditsView
from app.credits import PRICES

router = APIRouter(prefix="/api/me")


@router.get("/credits", response_model=CreditsView)
def my_credits(db: Db, me: Me) -> CreditsView:
    if me.is_admin:
        return CreditsView(balance=None, prices=PRICES, recent=[])
    return CreditsView(balance=db.credits.balance(me.id), prices=PRICES, recent=db.credits.recent(me.id))
