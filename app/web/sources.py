"""The "Add a website" page (#304): steps to save a HAR file of a travel site and a link that opens a prefilled
GitHub issue, so that the agent can write the userscript and the parser. The app keeps no GitHub token (P5): the
owner attaches the HAR file in GitHub, after the steps remove the private data."""

from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from app.auth import require_login
from app.web.pages import templates

router = APIRouter()

REPO = "Larspolo/travel-aggregator"


def issue_url(site: str) -> str:
    site = site.strip()[:200]
    body = (f"Add the website `{site or '<host>'}` as a source.\n\n"
            "1. The HAR file of a search is attached below (cookies and personal data removed).\n"
            "2. The page of the search: <URL>\n3. Notes: \n")
    query = urlencode({"title": f"Add source {site}".strip(), "body": body})
    return f"https://github.com/{REPO}/issues/new?{query}"


@router.get("/sources/new", response_class=HTMLResponse, dependencies=[Depends(require_login)])
def new_source(request: Request, site: str = "") -> HTMLResponse:
    return templates.TemplateResponse(request, "source_new.html",
                                      {"site": site[:200], "issue_url": issue_url(site)})
