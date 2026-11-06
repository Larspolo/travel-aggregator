"""The web pages: login, logout and the start page."""

from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.auth import SESSION_KEY, check_password, csrf_token, require_login, verify_csrf
from app.config import get_settings

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")
templates.env.globals["csrf_token"] = csrf_token


@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "login.html", {"error": None})


@router.post("/login", response_class=HTMLResponse, dependencies=[Depends(verify_csrf)])
def login(request: Request, password: str = Form("")) -> HTMLResponse:
    if check_password(password, get_settings().owner_password_hash):
        request.session.clear()
        request.session[SESSION_KEY] = True
        csrf_token(request)  # a new token after the login
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(request, "login.html", {"error": "Wrong password."}, status_code=401)


@router.api_route("/logout", methods=["GET", "POST"])
def logout(request: Request) -> RedirectResponse:
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@router.get("/", response_class=HTMLResponse, dependencies=[Depends(require_login)])
def index() -> HTMLResponse:
    return HTMLResponse(
        "<!doctype html><title>travel-aggregator</title><h1>travel-aggregator</h1>"
        '<p><a href="/logout">Log out</a></p>'
    )
