"""framework/tools/claim.py ignores closing keywords in code of a PR body (#536): PR #492 quoted `Closes #428`."""
import claim
from test_claim_active_pr import NOW, pr

QUOTED = "Why: PR #471 (`Closes #428`) was 14 minutes old.\n```\nCloses #428\n```\n"


def test_keyword_in_code_does_not_close():
    now = NOW.timestamp()
    assert claim.other_pr([pr(492, "run-0", QUOTED, 1)], 428, "run-1") is None
    assert claim.active_pr([pr(492, "run-0", QUOTED, 1)], 428, "run-1", now) is None
    assert claim.other_pr([pr(471, "run-0", QUOTED + "Closes #428", 1)], 428, "run-1") == 471
    assert claim.active_pr([pr(471, "run-0", "`x` Closes #428 `y`", 1)], 428, "run-1", now) == 471
