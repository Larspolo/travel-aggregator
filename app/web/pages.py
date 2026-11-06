"""The web pages: login, logout and the trips list."""

from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth import SESSION_KEY, check_password, require_login
from app.config import get_settings
from app.db import get_db
from app.trips import list_trips

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")


@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "login.html", {"error": None})


@router.post("/login", response_class=HTMLResponse)
def login(request: Request, password: str = Form("")) -> HTMLResponse:
    if check_password(password, get_settings().owner_password_hash):
        request.session.clear()
        request.session[SESSION_KEY] = True
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(request, "login.html", {"error": "Wrong password."}, status_code=401)


@router.api_route("/logout", methods=["GET", "POST"])
def logout(request: Request) -> RedirectResponse:
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@router.get("/", response_class=HTMLResponse, dependencies=[Depends(require_login)])
def index(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    return templates.TemplateResponse(request, "trips.html", {"trips": list_trips(db)})
