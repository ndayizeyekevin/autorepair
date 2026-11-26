import secrets

import bcrypt
from fastapi import Depends, HTTPException, Request

from app.db import fetch_one


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def get_user(user_id: int):
    return fetch_one(
        "SELECT UserID, Username, Role FROM APP_USER WHERE UserID = %s",
        (user_id,),
    )


def require_login(request: Request):
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401)
    user = get_user(user_id)
    if not user:
        request.session.clear()
        raise HTTPException(status_code=401)
    return user


def require_admin(request: Request):
    user = require_login(request)
    if user["role"] != "admin":
        raise HTTPException(status_code=403)
    return user


def require_role(role: str):
    def dependency(request: Request):
        user = require_login(request)
        current_role = user["role"] if isinstance(user, dict) else user[2]
        if current_role != role:
            raise HTTPException(status_code=403)
        return user
    return dependency


def ensure_csrf(request: Request):
    token = request.session.get("csrf")
    if not token:
        token = secrets.token_urlsafe(32)
        request.session["csrf"] = token
    return token


def check_csrf(request: Request, submitted_token: str = ""):
    if not submitted_token or not secrets.compare_digest(submitted_token, request.session.get("csrf", "")):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")
