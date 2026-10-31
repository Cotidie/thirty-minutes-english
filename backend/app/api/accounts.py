"""The admin's view of the accounts: who signed up, what each has to spend, and topping it up."""

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import Db, Me, admin_only
from app.api.schemas import AccountView, GrantRequest
from app.db import Database
from app.models import CreditEntry, User

router = APIRouter(prefix="/api/accounts", dependencies=[Depends(admin_only)])


@router.get("", response_model=list[AccountView])
def list_accounts(db: Db) -> list[AccountView]:
    return [_view(db, user) for user in db.accounts.list_all()]


@router.get("/{user_id}/credits", response_model=list[CreditEntry])
def account_credits(user_id: int, db: Db) -> list[CreditEntry]:
    return db.credits.recent(_account(db, user_id).id)


@router.post("/{user_id}/credits", response_model=AccountView, status_code=201)
def grant_credits(user_id: int, body: GrantRequest, db: Db, me: Me) -> AccountView:
    user = _account(db, user_id)
    if user.is_admin:
        raise HTTPException(status_code=400, detail="The admin is not charged, so there is nothing to add to.")
    db.credits.grant(user.id, body.amount, by=me.id)
    return _view(db, user)


def _account(db: Database, user_id: int) -> User:
    user = db.accounts.get(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="account not found")
    return user


def _view(db: Database, user: User) -> AccountView:
    return AccountView(**user.model_dump(), credits=None if user.is_admin else db.credits.balance(user.id))
