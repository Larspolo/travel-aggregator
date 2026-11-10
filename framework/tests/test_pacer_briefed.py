"""A run with a brief is no pending run (#1801): the claims of the pacer count it, also after a release."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import pacer  # noqa: E402
import usage  # noqa: E402

NOW = 1_800_000_000          # a Unix time
AT = "%Y-%m-%dT%H:%M:%SZ"


def log(tmp_path, records):
    import datetime
    p = tmp_path / "pacer.jsonl"
    with open(p, "w") as f:
        for minutes, rec in records:
            at = datetime.datetime.fromtimestamp(NOW - minutes * 60, datetime.timezone.utc)
            f.write(json.dumps({"at": at.strftime(AT), **rec}) + "\n")
    return str(p)


def test_brief_start_with_released_claim_is_not_pending(tmp_path):
    path = log(tmp_path, [(10, {"started": {"main": 1}, "briefed": {"main": 1}})])
    started = pacer.recent_starts(path, NOW)
    refs = [f"claim/1665 {NOW - 300} Release #1665 by pacer-r0123abcd"]
    assert usage.pending(started, refs, NOW) == {}


def test_start_with_no_brief_and_no_claim_is_pending(tmp_path):
    path = log(tmp_path, [(11, {"started": {"main": 1}, "briefed": {}})])
    assert usage.pending(pacer.recent_starts(path, NOW), [], NOW) == {"main": 1}
    assert usage.pending(pacer.recent_starts(path, NOW + 120), [], NOW + 120) == {}


def test_pacer_claim_is_not_made_for_a_start_with_no_brief():
    refs = [f"claim/1612 {NOW - 60} Claim #1612 by pacer-r0123abcd"]
    assert usage.pending({"main": 1}, refs, NOW) == {"main": 1}


def test_context_line_keeps_all_starts(tmp_path):
    path = log(tmp_path, [(30, {"started": {"main": 2}, "briefed": {"main": 2}})])
    assert pacer.recent_starts(path, NOW, 60) == {"main": 2}
