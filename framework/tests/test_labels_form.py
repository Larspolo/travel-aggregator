"""The form of `.github/labels.txt` (#5581): the Labels workflow stops at the first label that GitHub refuses, and the
labels after it are not made (the Release run of v0.1.0 stopped at the missing label `rank`)."""
import os
import re

import operator_check as oc

DESC_MAX = 100          # GitHub: "description is too long (maximum is 100 characters)"


def lines():
    text = open(oc.LABELS).read()
    return [line for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")]


def test_each_label_has_a_name_a_hex_colour_and_a_short_description():
    assert os.path.exists(oc.LABELS)
    for line in lines():
        name, colour, desc = line.split("|", 2)
        assert name.strip() and "|" not in desc, line
        assert re.fullmatch(r"[0-9a-f]{6}", colour), f"{name}: colour {colour!r} is not 6 hex digits"
        assert len(desc) <= DESC_MAX, f"{name}: description has {len(desc)} characters, GitHub takes {DESC_MAX}"


def test_label_names_are_unique():
    names = oc.wanted_labels(open(oc.LABELS).read())
    assert len(names) == len(set(names))
