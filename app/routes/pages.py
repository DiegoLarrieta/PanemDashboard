"""HTML page routes — Jinja templates."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from ..auth import current_user_optional
from ..clock import default_bake_date, server_now_iso, today
from ..config import settings
from ..models import User

router = APIRouter()
templates = Jinja2Templates(directory="templates")


def _ctx(request: Request, user: User, **extra) -> dict:
    base = {
        "request": request,
        "user": {"username": user.username, "role": user.role},
        "server_now": server_now_iso(),
        "branches": settings.branches,
        "default_bake_date": default_bake_date().isoformat(),
        "today": today().isoformat(),
        "plan_lock_hour": settings.plan_lock_hour,
        "actuals_open_hour": settings.actuals_open_hour,
    }
    base.update(extra)
    return base


@router.get("/", response_class=HTMLResponse)
def page_plan(request: Request, user: Optional[User] = Depends(current_user_optional)):
    if not user:
        return RedirectResponse("/login", status_code=302)
    return templates.TemplateResponse("plan.html", _ctx(request, user, nav="plan"))


@router.get("/product/{sku}", response_class=HTMLResponse)
def page_product(sku: str, branch: str, request: Request, user: Optional[User] = Depends(current_user_optional)):
    if not user:
        return RedirectResponse("/login", status_code=302)
    return templates.TemplateResponse("product.html", _ctx(
        request, user, nav="product", current_sku=sku, current_branch=branch,
    ))


@router.get("/model", response_class=HTMLResponse)
def page_model(request: Request, user: Optional[User] = Depends(current_user_optional)):
    if not user:
        return RedirectResponse("/login", status_code=302)
    if user.role != "analyst":
        raise HTTPException(403, "Analyst role required")
    return templates.TemplateResponse("model.html", _ctx(request, user, nav="model"))


@router.get("/feedback", response_class=HTMLResponse)
def page_feedback(request: Request, user: Optional[User] = Depends(current_user_optional)):
    if not user:
        return RedirectResponse("/login", status_code=302)
    if user.role != "analyst":
        raise HTTPException(403, "Analyst role required")
    return templates.TemplateResponse("feedback_log.html", _ctx(request, user, nav="feedback"))


@router.get("/analytics", response_class=HTMLResponse)
def page_analytics(request: Request, user: Optional[User] = Depends(current_user_optional)):
    if not user:
        return RedirectResponse("/login", status_code=302)
    return templates.TemplateResponse("analytics.html", _ctx(request, user, nav="analytics"))
