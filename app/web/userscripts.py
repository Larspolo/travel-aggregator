"""GET /userscripts/<name> (#389): the app serves its own userscripts and core.js. A `.user.js` file gets the server
address in its `@require`, `@updateURL` and `@downloadURL` lines, so that the install and the updates come from the
owner's server. The files of `userscripts/` do not change: the install from the repository keeps working.

`travel-aggregator.user.js` is one script for all sites: the server makes it from core.js and each *.user.js file, so
the owner installs one script, and a new site file is in it with no new install. Each site part runs only on the
pages of its own @match lines.

The code is public and holds no secret (P5), so there is no login. Only the names of the directory are served."""

import json
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
SOURCE_LINE = re.compile(r'^\s*const SOURCE = "([^"]+)";', re.MULTILINE)
PARSER_VERSION_LINE = re.compile(r'^\s*const PARSER_VERSION = "([^"]+)";', re.MULTILINE)
END_HEADER = "// ==/UserScript=="
BUNDLE = "travel-aggregator.user.js"
BUNDLE_NAME = "travel-aggregator: all sites"
MATCH_LINE = re.compile(r"^// @match[ \t]+(\S+)[ \t]*$", re.MULTILINE)
GRANT_LINE = re.compile(r"^// @grant[ \t]+(\S+)[ \t]*$", re.MULTILINE)


NAME_LINE = re.compile(r"^// @name[ \t]+(.+?)[ \t]*$", re.MULTILINE)


def userscript_list() -> list[dict[str, str]]:
    """Each *.user.js file of the directory (#390): its file name, its @name and its served @version."""
    core_path = USERSCRIPTS_DIR / CORE
    core = core_version(core_path.read_text(encoding="utf-8")) if core_path.is_file() else 0
    result = []
    for path in sorted(USERSCRIPTS_DIR.glob("*.user.js")):
        text = path.read_text(encoding="utf-8")
        name = NAME_LINE.search(text)
        version = VERSION_LINE.search(text)
        result.append({"file": path.name, "name": name.group(1) if name else path.name,
                       "version": f"{version.group(1) if version else '0'}.{core}"})
    return result


def allowed_names() -> set[str]:
    """The allow-list: core.js and each *.user.js file of the directory, read at each request."""
    names = {s["file"] for s in userscript_list()}
    if (USERSCRIPTS_DIR / CORE).is_file():
        names.add(CORE)
        names.add(BUNDLE)
    return names


def site_files() -> list[Path]:
    """The site userscripts of the directory (the bundle name is never a file of it)."""
    return [p for p in sorted(USERSCRIPTS_DIR.glob("*.user.js")) if p.name != BUNDLE]


def served_versions() -> dict[str, str]:
    """The PARSER_VERSION of each site script, by its SOURCE (#1494): "bahn.de" -> "1.2.0".

    Raise PARSER_VERSION of a site script when a change of the script changes what it sends to the server. The
    captures page then warns about the old installed scripts (epic #1493). A file with no SOURCE or no
    PARSER_VERSION line is not in the map.
    """
    result = {}
    for path in site_files():
        text = path.read_text(encoding="utf-8")
        source = SOURCE_LINE.search(text)
        parser_version = PARSER_VERSION_LINE.search(text)
        if source and parser_version:
            result[source.group(1)] = parser_version.group(1)
    return result


def _weight(version: str) -> int:
    """A version as one integer that grows when the version grows (each part below 1000)."""
    nums = [int(x) for x in re.findall(r"\d+", version)[:3]]
    nums += [0] * (3 - len(nums))
    return nums[0] * 1_000_000 + nums[1] * 1_000 + nums[2]


def bundle_version(core: int, versions: list[str]) -> str:
    """The @version of the bundle: CORE_VERSION, then the sum of the site versions. A higher version of a site or a
    new site makes it higher. Raise CORE_VERSION when you remove a site, because the sum then becomes lower."""
    return f"{core}.{sum(_weight(v) for v in versions)}"


def match_regex(pattern: str) -> str:
    """A JavaScript regular expression for a @match pattern (scheme://host/path, with * in the host and the path)."""
    m = re.fullmatch(r"(\*|https?)://([^/]+)(/.*)", pattern)
    if not m:
        return "^$"
    scheme, host, path = m.groups()
    scheme_re = "https?" if scheme == "*" else scheme
    if host == "*":
        host_re = "[^/]+"
    elif host.startswith("*."):
        host_re = r"(?:[^/]+\.)?" + re.escape(host[2:])
    else:
        host_re = re.escape(host)
    path_re = ".*".join(re.escape(part) for part in path.split("*"))
    return f"^{scheme_re}://{host_re}{path_re}$"


def bundle(base: str) -> str:
    """One userscript for all sites: a header with each @match and @grant, core.js, and each site part behind a test
    of its own @match lines (base is the server URL, no trailing slash)."""
    core_text = (USERSCRIPTS_DIR / CORE).read_text(encoding="utf-8")
    matches: list[str] = []
    grants: list[str] = []
    versions: list[str] = []
    parts: list[str] = []
    for path in site_files():
        text = path.read_text(encoding="utf-8")
        head, sep, body = text.partition(END_HEADER)
        if not sep:
            continue
        own = MATCH_LINE.findall(head)
        matches += [m for m in own if m not in matches]
        grants += [g for g in GRANT_LINE.findall(head) if g not in grants]
        version = VERSION_LINE.search(head)
        versions.append(version.group(1) if version else "0")
        tests = ", ".join(f"new RegExp({json.dumps(match_regex(m))})" for m in own)
        parts.append(f"// ---- {path.name} ----\nif ([{tests}].some((r) => r.test(location.href))) {{\n"
                     f"{body.strip()}\n}}\n")
    header = ["// ==UserScript==", f"// @name         {BUNDLE_NAME}",
              "// @namespace    https://github.com/Larspolo/travel-aggregator",
              f"// @version      {bundle_version(core_version(core_text), versions)}",
              "// @description  Send the search results of all supported travel sites to travel-aggregator.",
              *[f"// @match        {m}" for m in matches], "// @run-at       document-start",
              *[f"// @grant        {g}" for g in grants], "// @connect      *",
              f"// @updateURL    {base}/userscripts/{BUNDLE}", f"// @downloadURL  {base}/userscripts/{BUNDLE}",
              END_HEADER]
    return "\n".join(header) + "\n" + core_text.rstrip() + "\n\n" + "\n".join(parts)


def bundle_info() -> dict[str, str]:
    """The file, @name and @version of the bundle for the install list."""
    core = core_version((USERSCRIPTS_DIR / CORE).read_text(encoding="utf-8"))
    versions = []
    for path in site_files():
        m = VERSION_LINE.search(path.read_text(encoding="utf-8"))
        versions.append(m.group(1) if m else "0")
    return {"file": BUNDLE, "name": BUNDLE_NAME, "version": bundle_version(core, versions)}


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
    # url_for gives the address that the proxy reports (X-Forwarded-Proto, see docker-entrypoint.sh).
    base = str(request.url_for("serve_userscript", name=CORE)).removesuffix(f"/userscripts/{CORE}")
    if name == BUNDLE:
        return Response(content=bundle(base), media_type="text/javascript")
    text = (USERSCRIPTS_DIR / name).read_text(encoding="utf-8")
    if name.endswith(".user.js"):
        core_path = USERSCRIPTS_DIR / CORE
        core = core_version(core_path.read_text(encoding="utf-8")) if core_path.is_file() else 0
        text = with_server(text, base, name, core)
    return Response(content=text, media_type="text/javascript")
