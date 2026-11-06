"""GET /userscripts/<name> (#389): the app serves its own userscripts and core.js. A `.user.js` file gets the server
address in its `@require`, `@updateURL` and `@downloadURL` lines, so that the install and the updates come from the
owner's server. The files of `userscripts/` do not change: the install from the repository keeps working.

The code is public and holds no secret (P5), so there is no login. Only the names of the directory are served."""

import re
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import Response

router = APIRouter()

USERSCRIPTS_DIR = Path(__file__).resolve().parents[2] / "userscripts"
CORE = "core.js"
REQUIRE_CORE = re.compile(r"^// @require[ \t]+\S*core\.js[ \t]*$", re.MULTILINE)
UPDATE_LINES = re.compile(r"^// @(?:updateURL|downloadURL)[ \t].*\n?", re.MULTILINE)
VERSION_LINE = re.compile(r"^// @version[ \t]+(\S+)[ \t]*$", re.MULTILINE)
CORE_VERSION_LINE = re.compile(r"^const CORE_VERSION = (\d+);", re.MULTILINE)
END_HEADER = "// ==/UserScript=="


def allowed_names() -> set[str]:
    """The allow-list: core.js and each *.user.js file of the directory, read at each request."""
    names = {p.name for p in USERSCRIPTS_DIR.glob("*.user.js")}
    if (USERSCRIPTS_DIR / CORE).is_file():
        names.add(CORE)
    return names


def core_version(core_text: str) -> int:
    """The CORE_VERSION of core.js (0 when the constant is missing)."""
    m = CORE_VERSION_LINE.search(core_text)
    return int(m.group(1)) if m else 0


def with_server(text: str, base: str, name: str, core: int = 0) -> str:
    """The header of a `.user.js` file with the server address (base is the server URL, no trailing slash).
    The @version gets the CORE_VERSION as a last part, so that Tampermonkey updates the script when core.js changes."""
    text = VERSION_LINE.sub(lambda m: f"// @version      {m.group(1)}.{core}", text)
    text = REQUIRE_CORE.sub(f"// @require      {base}/userscripts/{CORE}", text)
    text = UPDATE_LINES.sub("", text)
    update = f"// @updateURL    {base}/userscripts/{name}\n// @downloadURL  {base}/userscripts/{name}\n"
    return text.replace(END_HEADER, update + END_HEADER, 1)


@router.get("/userscripts/{name}", name="serve_userscript")
def serve_userscript(name: str, request: Request) -> Response:
    if name not in allowed_names():
        return Response(content='{"detail":"Not Found"}', status_code=404, media_type="application/json")
    text = (USERSCRIPTS_DIR / name).read_text(encoding="utf-8")
    if name.endswith(".user.js"):
        # url_for gives the address that the proxy reports (X-Forwarded-Proto, see docker-entrypoint.sh).
        base = str(request.url_for("serve_userscript", name=CORE)).removesuffix(f"/userscripts/{CORE}")
        core_path = USERSCRIPTS_DIR / CORE
        core = core_version(core_path.read_text(encoding="utf-8")) if core_path.is_file() else 0
        text = with_server(text, base, name, core)
    return Response(content=text, media_type="text/javascript")
