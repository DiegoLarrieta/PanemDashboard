"""Login + logout routes."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session

from ..auth import COOKIE_NAME, authenticate, current_user_optional, issue_token
from ..clock import server_now_iso
from ..config import settings
from ..db import get_session
from ..models import User

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/login", response_class=HTMLResponse)
def login_page(
    request: Request,
    error: Optional[str] = None,
    user: Optional[User] = Depends(current_user_optional),
):
    if user:
        return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse("login.html", {
        "request": request,
        "error": error,
        "server_now": server_now_iso(),
        "hide_chrome": True,
        "user": {"username": "", "role": ""},
    })


@router.post("/login")
def login_submit(
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_session),
):
    user = authenticate(db, username, password)
    if not user:
        return RedirectResponse("/login?error=Invalid+credentials", status_code=302)
    token = issue_token(user)
    resp = RedirectResponse("/", status_code=302)
    resp.set_cookie(
        COOKIE_NAME,
        token,
        httponly=True,
        samesite="lax",
        max_age=settings.jwt_expire_hours * 3600,
    )
    return resp


@router.get("/logout")
def logout():
    resp = RedirectResponse("/login", status_code=302)
    resp.delete_cookie(COOKIE_NAME)
    return resp
