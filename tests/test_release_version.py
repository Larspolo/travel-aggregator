import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))

from release_version import next_version  # noqa: E402


def test_no_tag_gives_first_version():
    assert next_version([]) == "v0.1.0"


def test_one_minor_step_after_newest():
    assert next_version(["v0.3.0"]) == "v0.4.0"


def test_numeric_order_and_other_tags_ignored():
    assert next_version(["v0.9.0", "v0.10.0", "v1.0.0-rc", "preview", "v0.2.1"]) == "v0.11.0"
