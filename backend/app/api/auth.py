"""Signing up, logging in and out. `public_router` is the only one open without a login."""

from datetime import timedelta

from fastapi import APIRouter, HTTPException, Request, Response

from app.accounts.passwords import MAX_LENGTH, MIN_LENGTH, burn_time, hash_password, verify_password
from app.api.deps import LOGIN_COOKIE, Db, Me
from app.api.schemas import Credentials
from app.db.accounts import LOGIN_LIFETIME, EmailTaken, is_email, normalize_email
from app.models import User

public_router = APIRouter(prefix="/api/auth")
router = APIRouter(prefix="/api/auth")


def _start_login(request: Request, response: Response, user: User) -> None:
    response.set_cookie(
        LOGIN_COOKIE,
        request.app.state.db.accounts.start_login(user.id),
        max_age=int(LOGIN_LIFETIME / timedelta(seconds=1)),
        path="/",
        httponly=True,
        samesite="lax",
        secure=request.app.state.env.get("COOKIE_SECURE", "true") != "false",
    )


def _check_signup(email: str, password: str) -> None:
    if not is_email(email):
        raise HTTPException(status_code=400, detail="Enter an email address, like you@example.com.")
    if len(password) < MIN_LENGTH:
        raise HTTPException(status_code=400, detail=f"Use at least {MIN_LENGTH} characters.")
    if len(password) > MAX_LENGTH:
        raise HTTPException(status_code=400, detail=f"Use at most {MAX_LENGTH} characters.")


@public_router.post("/signup", response_model=User, status_code=201)
def sign_up(body: Credentials, db: Db, request: Request, response: Response) -> User:
    """An account with no rights, logged in at once. The confirmation of the password is the page's to check."""
    email = normalize_email(body.email)
    _check_signup(email, body.password)
    if not request.app.state.signups.allow():
        raise HTTPException(status_code=429, detail="Too many sign-ups right now. Try again in an hour.")
    try:
        user = db.accounts.create(email, hash_password(body.password))
    except EmailTaken:
        raise HTTPException(status_code=409, detail="An account already uses that email.") from None
    _start_login(request, response, user)
    return user


@public_router.post("/login", response_model=User)
def log_in(body: Credentials, db: Db, request: Request, response: Response) -> User:
    """An unknown email answers as a wrong password does, in about the same time."""
    email = normalize_email(body.email)
    failed = request.app.state.failed_logins
    if failed.blocked(email):
        raise HTTPException(status_code=429, detail="Too many tries. Wait 15 minutes and try again.")
    found = db.accounts.with_hash(email)
    if found is None:
        burn_time()
    if found is None or not verify_password(body.password, found[1]):
        failed.failed(email)
        raise HTTPException(status_code=401, detail="That email and password don't match. Check them and try again.")
    failed.cleared(email)
    _start_login(request, response, found[0])
    return found[0]


@router.post("/logout", status_code=204)
def log_out(db: Db, request: Request, response: Response) -> Response:
    db.accounts.end_login(request.cookies.get(LOGIN_COOKIE, ""))
    response.status_code = 204
    response.delete_cookie(LOGIN_COOKIE, path="/")
    return response


@router.get("/me", response_model=User)
def who_am_i(me: Me) -> User:
    return me
