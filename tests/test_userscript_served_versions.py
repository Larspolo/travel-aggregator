"""served_versions() maps each site script's SOURCE to its PARSER_VERSION (#1494)."""

import re
from pathlib import Path

from app.web.userscripts import USERSCRIPTS_DIR, served_versions, site_files

GUARDS = ("userscripts/*", "app/web/userscripts.py")   # ship_pr runs this file for these changes

PARSER_LINE = re.compile(r'^\s*const PARSER_VERSION = "([^"]+)";', re.MULTILINE)
SOURCE_LINE = re.compile(r'^\s*const SOURCE = "([^"]+)";', re.MULTILINE)


def _file_source_and_version(path: Path) -> tuple[str, str]:
    text = path.read_text(encoding="utf-8")
    return SOURCE_LINE.search(text).group(1), PARSER_LINE.search(text).group(1)


def test_every_site_file_is_in_the_map():
    versions = served_versions()
    files = site_files()
    assert len(files) == 9  # sbb.user.js (#1787)
    for path in files:
        source, _ = _file_source_and_version(path)
        assert source in versions, path.name


def test_each_value_is_the_parser_version_of_its_file():
    versions = served_versions()
    for path in site_files():
        source, parser_version = _file_source_and_version(path)
        assert versions[source] == parser_version, path.name


def test_bahn_maps_to_its_parser_version():
    text = (USERSCRIPTS_DIR / "bahn.user.js").read_text(encoding="utf-8")
    assert served_versions()["bahn.de"] == PARSER_LINE.search(text).group(1)


def test_flixbus_maps_to_parser_version_not_userscript_version():
    assert served_versions()["flixbus.com"] == "1.0.0"
