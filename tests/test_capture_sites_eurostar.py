"""The capture script runs on eurostar.com (#954): each Eurostar search is a full page load, and the page gets its
results after the load with POST site-api.eurostar.com/gateway, so only the hook at document start records them."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import capture  # noqa: E402


def test_the_capture_script_runs_on_eurostar():
    assert "https://www.eurostar.com/*" in capture.capture_sites()
    assert "// @match        https://www.eurostar.com/*\n" in capture.USERSCRIPT_FILE.read_text("utf-8")


def test_the_version_is_higher_than_the_last_one_without_eurostar():
    assert capture.USERSCRIPT_VERSION >= 4
