"""The admin's view of the accounts: who signed up, and who may create sessions."""

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import Db, admin_only
from app.api.schemas import AccountUpdate
from app.models import User

router = APIRouter(prefix="/api/accounts", dependencies=[Depends(admin_only)])


@router.get("", response_model=list[User])
def list_accounts(db: Db) -> list[User]:
    return db.accounts.list_all()


@router.put("/{user_id}", response_model=User)
def update_account(user_id: int, body: AccountUpdate, db: Db) -> User:
    user = db.accounts.set_can_create(user_id, body.can_create)
    if user is None:
        raise HTTPException(status_code=404, detail="account not found")
    return user
