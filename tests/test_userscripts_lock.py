"""A change of core.js or of a userscript needs a higher version (#406). Tampermonkey updates a script only when its
served @version grows, so each file has a lock entry: its sha256 per version. A changed file with the same version
fails this check."""

import hashlib
import json
import shutil
from pathlib import Path

import app.web.userscripts as userscripts

DIR = Path(__file__).resolve().parents[1] / "userscripts"
LOCK = Path(__file__).resolve().parent / "data" / "userscript_versions.json"
HINT = ("raise CORE_VERSION (core.js) or @version (*.user.js), then add the new sha256 to "
        "tests/data/userscript_versions.json")


def parts(version: str) -> list[int]:
    return [int(p) for p in version.split(".")]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def current_version(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    if path.name == userscripts.CORE:
        return str(userscripts.core_version(text))
    m = userscripts.VERSION_LINE.search(text)
    return m.group(1) if m else "0"


def lock_problems(directory: Path, lock: dict) -> list[str]:
    """The problems of each core.js and *.user.js file of the directory against the lock (empty when all is well)."""
    problems = []
    files = [directory / userscripts.CORE, *sorted(directory.glob("*.user.js"))]
    for path in files:
        if not path.is_file():
            continue
        entry = lock.get(path.name)
        version = current_version(path)
        if not entry:
            problems.append(f"{path.name}: no entry in tests/data/userscript_versions.json; {HINT}")
            continue
        if entry.get(version) != sha256(path):
            problems.append(f"{path.name}: the file changed at version {version} (or has no entry for it); {HINT}")
        newest = max(entry, key=parts)
        if newest != version:
            problems.append(f"{path.name}: the current version {version} is not the highest key {newest}; {HINT}")
    return problems


def load_lock() -> dict:
    return json.loads(LOCK.read_text(encoding="utf-8"))


def test_every_userscript_file_matches_its_lock_entry():
    assert lock_problems(DIR, load_lock()) == []


def test_changed_file_with_same_version_fails(tmp_path):
    copy = tmp_path / "userscripts"
    shutil.copytree(DIR, copy)
    lock = load_lock()
    bahn = copy / "bahn.user.js"
    bahn.write_text(bahn.read_text(encoding="utf-8") + "\n// a change without a higher version\n", encoding="utf-8")
    problems = lock_problems(copy, lock)
    assert any(p.startswith("bahn.user.js:") and HINT in p for p in problems)


def test_changed_file_with_higher_version_and_new_entry_passes(tmp_path):
    copy = tmp_path / "userscripts"
    shutil.copytree(DIR, copy)
    lock = load_lock()
    bahn = copy / "bahn.user.js"
    text = bahn.read_text(encoding="utf-8") + "\n// a change with a higher version\n"
    major, minor, patch = parts(current_version(bahn))
    higher = f"{major}.{minor}.{patch + 1}"
    text = userscripts.VERSION_LINE.sub(f"// @version      {higher}", text, count=1)
    bahn.write_text(text, encoding="utf-8")
    lock["bahn.user.js"][higher] = sha256(bahn)
    assert lock_problems(copy, lock) == []
