"""README.md names only files, make targets, modules and settings that exist.

A name in the README that does not exist sends the reader to a dead end. This test finds:
- each path that starts with deploy/, userscripts/, scripts/, app/ or docs/;
- each `make X` (the target X must be in Makefile);
- each `python -m app.X` (app/X.py must exist);
- each setting in the Configuration table (it must be in a .env.example file or in app/config.py).

Run: python3 -m pytest -m readme tests/test_readme_names.py"""

import pathlib
import re

import pytest

pytestmark = pytest.mark.readme

ROOT = pathlib.Path(__file__).resolve().parent.parent

# Paths that the README names on purpose, although the repository does not hold them: the reader creates them.
# Each entry needs the reason. Remove an entry when the README stops naming the path.
USER_CREATED_PATHS = {
    "deploy/production/docker-compose.override.yml": "the reader copies it there (README, production step 2)",
}

PATH_RE = re.compile(r"`((?:deploy|userscripts|scripts|app|docs)/[^`\s]*)`")
MAKE_RE = re.compile(r"(?:`make |^\s*make )([a-z][\w-]*)", re.M)
MODULE_RE = re.compile(r"python3? -m app\.(\w+)")
SETTING_ROW_RE = re.compile(r"^\|\s*`([A-Z][A-Z0-9_]*)`", re.M)


def configuration_section(readme: str) -> str:
    """The text from the heading 'Configuration' to the next heading of level 2."""
    match = re.search(r"^## Configuration\n(.*?)(?=^## |\Z)", readme, re.M | re.S)
    return match.group(1) if match else ""


def find_missing(readme: str, root: pathlib.Path) -> list[str]:
    """The names of the README that do not exist under root. An empty list means that all names exist."""
    missing = []
    for path in sorted(set(PATH_RE.findall(readme))):
        if path in USER_CREATED_PATHS:
            continue
        if not (root / path.rstrip("/")).exists():
            missing.append(path)

    makefile = (root / "Makefile").read_text() if (root / "Makefile").exists() else ""
    targets = set(re.findall(r"^([A-Za-z][\w-]*):", makefile, re.M))
    for target in sorted(set(MAKE_RE.findall(readme))):
        if target not in targets:
            missing.append(f"make {target}")

    for module in sorted(set(MODULE_RE.findall(readme))):
        if not (root / "app" / f"{module}.py").exists():
            missing.append(f"python -m app.{module}")

    settings = set(SETTING_ROW_RE.findall(configuration_section(readme)))
    known = set()
    for env_file in root.glob("**/.env.example"):
        if "framework" in env_file.parts:
            continue
        known |= set(re.findall(r"^([A-Z][A-Z0-9_]*)=", env_file.read_text(), re.M))
    config_py = root / "app" / "config.py"
    config_text = config_py.read_text() if config_py.exists() else ""
    for setting in sorted(settings):
        if setting not in known and f'"{setting}"' not in config_text:
            missing.append(f"setting {setting}")
    return missing


@pytest.mark.xfail(
    strict=True,
    reason="README Configuration names GIT_SHA, a Dockerfile build ARG that is in no .env.example nor app/config.py; "
           "the README PR at the end of the epic fixes it, then this marker goes",
)
def test_each_readme_name_exists():
    readme = (ROOT / "README.md").read_text()
    assert find_missing(readme, ROOT) == [], "names of README.md that do not exist (fix the README at the epic's end)"


def test_checker_reports_a_missing_path(tmp_path):
    (tmp_path / "app").mkdir()
    readme = "See `deploy/nope/docker-compose.yml` for the stack.\n"
    assert find_missing(readme, tmp_path) == ["deploy/nope/docker-compose.yml"]


def test_checker_accepts_existing_names(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "backup.py").write_text("")
    (tmp_path / "Makefile").write_text("backup:\n\tdocker compose exec app python -m app.backup --now\n")
    readme = "Run `make backup` or `python -m app.backup --now`.\n"
    assert find_missing(readme, tmp_path) == []


def test_checker_reports_a_missing_make_target_and_module(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "Makefile").write_text("up:\n\ttrue\n")
    readme = "Run `make down` and `python -m app.gone`.\n"
    assert find_missing(readme, tmp_path) == ["make down", "python -m app.gone"]


def test_checker_reports_a_missing_setting(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / ".env.example").write_text("KNOWN_ONE=x\n")
    readme = "## Configuration\n\n| Variable | Use |\n|---|---|\n| `KNOWN_ONE` | ok |\n| `GHOST_SETTING` | no |\n\n## API\n"
    assert find_missing(readme, tmp_path) == ["setting GHOST_SETTING"]
